"""Image-only Depth-aware Real-ESRGAN pipeline.

The image processing parameters and final calculation are preserved from
depth_final_fixed.ipynb. Video, temporal processing, debug images, statistics,
and Colab-only code were removed for the web deployment.
"""

import os
import shutil
import subprocess

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image


processor = None
model = None
device = None
upsampler = None

MAKE_LOW_RESOLUTION = False
DOWNSCALE = 8
UPSCALE = 4

DEPTH_FAR = 0.10
DEPTH_NEAR = 0.30
EDGE_WEIGHT = 0.4
RESIDUAL_WEIGHT = 0.6
RESIDUAL_PERCENTILE = 80
STRUCTURE_START = 0.15
STRUCTURE_PROTECT_POWER = 0.4
MIN_STRUCTURE_BLUR = 0.03
BLUR_SIGMA = 2.5
MASK_SIGMA = 0.5

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

VIDEO_DEPTH_RANGE_ALPHA = 0.95
VIDEO_DEPTH_ALPHA = 0.80
VIDEO_STRUCTURE_ALPHA = 0.70
VIDEO_BLUR_ALPHA = 0.80
SCENE_CUT_THRESHOLD = 0.30
USE_OPTICAL_FLOW = True
VIDEO_MODEL_MAX_WIDTH = 960
VIDEO_MODEL_MAX_HEIGHT = 540


class TemporalState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.prev_frame = None
        self.prev_depth = None
        self.prev_structure = None
        self.prev_blur = None
        self.depth_low = None
        self.depth_high = None


def configure_models(depth_processor, depth_model, torch_device, realesrgan_upsampler):
    global processor, model, device, upsampler
    processor = depth_processor
    model = depth_model
    device = torch_device
    upsampler = realesrgan_upsampler


def make_edge_structure_map(image, blur_sigma=1.5):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.sqrt(gx ** 2 + gy ** 2)
    magnitude = np.clip(magnitude / (np.percentile(magnitude, 99) + 1e-8), 0.0, 1.0)
    if blur_sigma > 0:
        magnitude = cv2.GaussianBlur(magnitude, (0, 0), blur_sigma)
    return np.clip(magnitude, 0.0, 1.0).astype(np.float32)


def make_residual_structure_map(lanczos, sr_image, percentile=80, blur_sigma=2.0):
    difference = np.mean(
        np.abs(sr_image.astype(np.float32) - lanczos.astype(np.float32)), axis=2
    )
    threshold = np.percentile(difference, percentile)
    high = np.percentile(difference, 99)
    residual = np.clip(
        (difference - threshold) / (high - threshold + 1e-8), 0.0, 1.0
    )
    if blur_sigma > 0:
        residual = cv2.GaussianBlur(residual, (0, 0), blur_sigma)
    return np.clip(residual, 0.0, 1.0).astype(np.float32)


@torch.no_grad()
def estimate_raw_depth(image_bgr):
    height, width = image_bgr.shape[:2]
    depth_image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    inputs = processor(images=depth_image, return_tensors="pt")
    inputs = {key: value.to(device) for key, value in inputs.items()}
    predicted_depth = model(**inputs).predicted_depth
    return (
        F.interpolate(
            predicted_depth.unsqueeze(1),
            size=(height, width),
            mode="bicubic",
            align_corners=False,
        )
        .squeeze()
        .detach()
        .cpu()
        .numpy()
        .astype(np.float32)
    )


def normalize_depth(depth):
    low = np.percentile(depth, 2)
    high = np.percentile(depth, 98)
    return np.clip((depth - low) / (high - low + 1e-8), 0.0, 1.0)


def normalize_depth_video(depth, state):
    current_low = np.percentile(depth, 2)
    current_high = np.percentile(depth, 98)
    if state.depth_low is None:
        state.depth_low, state.depth_high = current_low, current_high
    else:
        state.depth_low = VIDEO_DEPTH_RANGE_ALPHA * state.depth_low + (1.0 - VIDEO_DEPTH_RANGE_ALPHA) * current_low
        state.depth_high = VIDEO_DEPTH_RANGE_ALPHA * state.depth_high + (1.0 - VIDEO_DEPTH_RANGE_ALPHA) * current_high
    return np.clip((depth - state.depth_low) / (state.depth_high - state.depth_low + 1e-8), 0.0, 1.0)


def detect_scene_cut(previous, current):
    if previous is None:
        return False
    previous = cv2.cvtColor(cv2.resize(previous, (64, 64), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)
    current = cv2.cvtColor(cv2.resize(current, (64, 64), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)
    hist_previous = cv2.calcHist([previous], [0, 1], None, [32, 32], [0, 180, 0, 256])
    hist_current = cv2.calcHist([current], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(hist_previous, hist_previous)
    cv2.normalize(hist_current, hist_current)
    return cv2.compareHist(hist_previous, hist_current, cv2.HISTCMP_BHATTACHARYYA) > SCENE_CUT_THRESHOLD


def calculate_backward_flow(previous, current, output_size):
    out_width, out_height = output_size
    previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(current_gray, previous_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    flow = cv2.resize(flow, output_size, interpolation=cv2.INTER_LINEAR)
    flow[..., 0] *= out_width / previous.shape[1]
    flow[..., 1] *= out_height / previous.shape[0]
    return flow


def warp_previous_map(previous_map, flow):
    height, width = previous_map.shape[:2]
    grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    return cv2.remap(previous_map.astype(np.float32), grid_x + flow[..., 0], grid_y + flow[..., 1], interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def temporal_blend(current, previous, alpha):
    if previous is None:
        return current.copy()
    return alpha * previous + (1.0 - alpha) * current


def process_core(image_bgr):
    height, width = image_bgr.shape[:2]
    out_width = width * UPSCALE
    out_height = height * UPSCALE

    lanczos = cv2.resize(
        image_bgr, (out_width, out_height), interpolation=cv2.INTER_LANCZOS4
    )

    with torch.no_grad():
        sr_image, _ = upsampler.enhance(image_bgr, outscale=UPSCALE)
    if sr_image.shape[:2] != (out_height, out_width):
        sr_image = cv2.resize(
            sr_image, (out_width, out_height), interpolation=cv2.INTER_CUBIC
        )

    depth = cv2.resize(
        normalize_depth(estimate_raw_depth(image_bgr)),
        (out_width, out_height),
        interpolation=cv2.INTER_CUBIC,
    )
    depth = np.clip(
        cv2.GaussianBlur(depth, (0, 0), sigmaX=2.0), 0.0, 1.0
    ).astype(np.float32)

    edge = make_edge_structure_map(lanczos)
    residual = make_residual_structure_map(
        lanczos, sr_image, percentile=RESIDUAL_PERCENTILE
    )
    structure = np.clip(
        EDGE_WEIGHT * edge + RESIDUAL_WEIGHT * residual, 0.0, 1.0
    ).astype(np.float32)

    far_strength = 1.0 - np.clip(
        (depth - DEPTH_FAR) / (DEPTH_NEAR - DEPTH_FAR + 1e-8), 0.0, 1.0
    )
    far_strength = far_strength ** 2 * (3.0 - 2.0 * far_strength)

    structure_protection = np.clip(
        (structure - STRUCTURE_START) / (1.0 - STRUCTURE_START + 1e-8),
        0.0,
        1.0,
    ) ** STRUCTURE_PROTECT_POWER

    blur_weight = far_strength * (
        1.0 - (1.0 - MIN_STRUCTURE_BLUR) * structure_protection
    )
    if MASK_SIGMA > 0:
        blur_weight = cv2.GaussianBlur(blur_weight, (0, 0), sigmaX=MASK_SIGMA)
    blur_weight = np.clip(blur_weight, 0.0, 1.0)[..., None]

    sr_float = sr_image.astype(np.float32)
    blurred = cv2.GaussianBlur(
        sr_float, (0, 0), sigmaX=BLUR_SIGMA, sigmaY=BLUR_SIGMA
    )
    final = (1.0 - blur_weight) * sr_float + blur_weight * blurred
    return np.clip(final, 0, 255).astype(np.uint8)


def process_image(image_path, save_path):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("지원하지 않거나 손상된 이미지 파일입니다.")

    if MAKE_LOW_RESOLUTION:
        height, width = image.shape[:2]
        image = cv2.resize(
            image,
            (max(1, width // DOWNSCALE), max(1, height // DOWNSCALE)),
            interpolation=cv2.INTER_AREA,
        )

    result = process_core(image)
    os.makedirs(save_path, exist_ok=True)
    result_path = os.path.join(save_path, "deepup_result.png")
    if not cv2.imwrite(result_path, result):
        raise RuntimeError("결과 이미지를 저장하지 못했습니다.")
    return result_path, save_path


def process_video_frame(frame, state):
    height, width = frame.shape[:2]
    out_width, out_height = width * UPSCALE, height * UPSCALE
    if detect_scene_cut(state.prev_frame, frame):
        state.reset()
    lanczos = cv2.resize(frame, (out_width, out_height), interpolation=cv2.INTER_LANCZOS4)
    with torch.no_grad():
        sr_image, _ = upsampler.enhance(frame, outscale=UPSCALE)
    if sr_image.shape[:2] != (out_height, out_width):
        sr_image = cv2.resize(sr_image, (out_width, out_height), interpolation=cv2.INTER_CUBIC)

    depth = normalize_depth_video(estimate_raw_depth(frame), state)
    depth = cv2.resize(depth, (out_width, out_height), interpolation=cv2.INTER_CUBIC)
    depth = np.clip(cv2.GaussianBlur(depth, (0, 0), 2.0), 0.0, 1.0)
    edge = make_edge_structure_map(lanczos)
    residual = make_residual_structure_map(lanczos, sr_image, percentile=RESIDUAL_PERCENTILE)
    structure = np.clip(EDGE_WEIGHT * edge + RESIDUAL_WEIGHT * residual, 0.0, 1.0)

    warped_depth = warped_structure = warped_blur = None
    if state.prev_frame is not None and USE_OPTICAL_FLOW:
        flow = calculate_backward_flow(state.prev_frame, frame, (out_width, out_height))
        if state.prev_depth is not None:
            warped_depth = warp_previous_map(state.prev_depth, flow)
        if state.prev_structure is not None:
            warped_structure = warp_previous_map(state.prev_structure, flow)
        if state.prev_blur is not None:
            warped_blur = warp_previous_map(state.prev_blur, flow)
    depth = np.clip(temporal_blend(depth, warped_depth, VIDEO_DEPTH_ALPHA), 0.0, 1.0)
    structure = np.clip(temporal_blend(structure, warped_structure, VIDEO_STRUCTURE_ALPHA), 0.0, 1.0)
    far_strength = 1.0 - np.clip((depth - DEPTH_FAR) / (DEPTH_NEAR - DEPTH_FAR + 1e-8), 0.0, 1.0)
    far_strength = far_strength**2 * (3.0 - 2.0 * far_strength)
    structure_protection = np.clip((structure - STRUCTURE_START) / (1.0 - STRUCTURE_START + 1e-8), 0.0, 1.0) ** STRUCTURE_PROTECT_POWER
    blur = far_strength * (1.0 - (1.0 - MIN_STRUCTURE_BLUR) * structure_protection)
    if MASK_SIGMA > 0:
        blur = cv2.GaussianBlur(blur, (0, 0), MASK_SIGMA)
    blur = np.clip(temporal_blend(blur, warped_blur, VIDEO_BLUR_ALPHA), 0.0, 1.0)
    sr_float = sr_image.astype(np.float32)
    blurred = cv2.GaussianBlur(sr_float, (0, 0), BLUR_SIGMA, BLUR_SIGMA)
    final = np.clip((1.0 - blur[..., None]) * sr_float + blur[..., None] * blurred, 0, 255).astype(np.uint8)
    state.prev_frame = frame.copy()
    state.prev_depth = depth.copy()
    state.prev_structure = structure.copy()
    state.prev_blur = blur.copy()
    return final


def _mux_original_audio(original_path, silent_path, output_path):
    if shutil.which("ffmpeg") is None:
        shutil.move(silent_path, output_path)
        return
    completed = subprocess.run([
        "ffmpeg", "-y", "-i", silent_path, "-i", original_path,
        "-map", "0:v:0", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac",
        "-shortest", output_path,
    ], capture_output=True, text=True)
    if completed.returncode != 0:
        shutil.move(silent_path, output_path)


def process_video(video_path, save_path):
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError("지원하지 않거나 손상된 동영상 파일입니다.")
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(fps) or fps <= 0:
        fps = 30.0
    input_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    input_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    resize_ratio = min(
        1.0,
        VIDEO_MODEL_MAX_WIDTH / max(input_width, 1),
        VIDEO_MODEL_MAX_HEIGHT / max(input_height, 1),
    )
    model_width = max(2, int(input_width * resize_ratio) // 2 * 2)
    model_height = max(2, int(input_height * resize_ratio) // 2 * 2)
    output_size = (model_width * UPSCALE, model_height * UPSCALE)
    os.makedirs(save_path, exist_ok=True)
    silent_path = os.path.join(save_path, "deepup_video_silent.mp4")
    output_path = os.path.join(save_path, "deepup_result.mp4")
    writer = cv2.VideoWriter(silent_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, output_size)
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("결과 동영상 파일을 만들지 못했습니다.")
    state = TemporalState()
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame.shape[1] != model_width or frame.shape[0] != model_height:
                frame = cv2.resize(
                    frame,
                    (model_width, model_height),
                    interpolation=cv2.INTER_AREA,
                )
            writer.write(process_video_frame(frame, state))
    finally:
        capture.release()
        writer.release()
    _mux_original_audio(video_path, silent_path, output_path)
    return output_path


def process_media(input_path, save_path):
    extension = os.path.splitext(input_path)[1].lower()
    if extension in IMAGE_EXTENSIONS:
        return process_image(input_path, save_path)
    if extension in VIDEO_EXTENSIONS:
        return process_video(input_path, save_path)
    raise ValueError("지원하지 않는 파일 형식입니다.")
