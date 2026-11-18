"""Production anime image/video pipeline based on the supplied notebook."""

import os
import math
import shutil
import subprocess

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

processor = model = device = upsampler = None

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
VIDEO_DEPTH_RANGE_ALPHA = 0.95
VIDEO_DEPTH_ALPHA = 0.80
VIDEO_STRUCTURE_ALPHA = 0.70
VIDEO_BLUR_ALPHA = 0.80
SCENE_CUT_THRESHOLD = 0.30
USE_OPTICAL_FLOW = True

# The notebook calculation is unchanged; these limits only keep web video
# inference within the T4 worker's practical memory and runtime budget.
VIDEO_MODEL_MAX_WIDTH = 960
VIDEO_MODEL_MAX_HEIGHT = 540
VIDEO_MAX_FPS = 30.0

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


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


def _require_models():
    if processor is None or model is None or device is None or upsampler is None:
        raise RuntimeError("애니 화질 개선 모델이 초기화되지 않았습니다.")


def make_edge_structure_map(image, blur_sigma=1.5):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.sqrt(gx**2 + gy**2)
    magnitude = np.clip(
        magnitude / (np.percentile(magnitude, 99) + 1e-8), 0.0, 1.0
    )
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


def normalize_depth_image(depth):
    low, high = np.percentile(depth, (2, 98))
    return np.clip((depth - low) / (high - low + 1e-8), 0.0, 1.0)


def normalize_depth_video(depth, state):
    current_low, current_high = np.percentile(depth, (2, 98))
    if state.depth_low is None:
        state.depth_low, state.depth_high = current_low, current_high
    else:
        state.depth_low = (
            VIDEO_DEPTH_RANGE_ALPHA * state.depth_low
            + (1.0 - VIDEO_DEPTH_RANGE_ALPHA) * current_low
        )
        state.depth_high = (
            VIDEO_DEPTH_RANGE_ALPHA * state.depth_high
            + (1.0 - VIDEO_DEPTH_RANGE_ALPHA) * current_high
        )
    return np.clip(
        (depth - state.depth_low) / (state.depth_high - state.depth_low + 1e-8),
        0.0,
        1.0,
    )


def detect_scene_cut(previous, current):
    if previous is None:
        return False
    previous = cv2.cvtColor(
        cv2.resize(previous, (64, 64), interpolation=cv2.INTER_AREA),
        cv2.COLOR_BGR2HSV,
    )
    current = cv2.cvtColor(
        cv2.resize(current, (64, 64), interpolation=cv2.INTER_AREA),
        cv2.COLOR_BGR2HSV,
    )
    previous_hist = cv2.calcHist(
        [previous], [0, 1], None, [32, 32], [0, 180, 0, 256]
    )
    current_hist = cv2.calcHist(
        [current], [0, 1], None, [32, 32], [0, 180, 0, 256]
    )
    cv2.normalize(previous_hist, previous_hist)
    cv2.normalize(current_hist, current_hist)
    return (
        cv2.compareHist(previous_hist, current_hist, cv2.HISTCMP_BHATTACHARYYA)
        > SCENE_CUT_THRESHOLD
    )


def calculate_backward_flow(previous, current, output_size):
    output_width, output_height = output_size
    previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(
        current_gray, previous_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
    )
    flow = cv2.resize(flow, output_size, interpolation=cv2.INTER_LINEAR)
    flow[..., 0] *= output_width / previous.shape[1]
    flow[..., 1] *= output_height / previous.shape[0]
    return flow


def warp_previous_map(previous_map, flow):
    height, width = previous_map.shape[:2]
    grid_x, grid_y = np.meshgrid(
        np.arange(width, dtype=np.float32),
        np.arange(height, dtype=np.float32),
    )
    return cv2.remap(
        previous_map.astype(np.float32),
        grid_x + flow[..., 0],
        grid_y + flow[..., 1],
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )


def temporal_blend(current, previous, alpha):
    if previous is None:
        return current.copy()
    return alpha * previous + (1.0 - alpha) * current


def process_core(image_bgr, state=None):
    """Run the notebook's shared image/video enhancement calculation."""
    _require_models()
    height, width = image_bgr.shape[:2]
    output_size = (width * UPSCALE, height * UPSCALE)
    if state is not None and detect_scene_cut(state.prev_frame, image_bgr):
        state.reset()

    lanczos = cv2.resize(image_bgr, output_size, interpolation=cv2.INTER_LANCZOS4)
    with torch.no_grad():
        sr_image, _ = upsampler.enhance(image_bgr, outscale=UPSCALE)
    if sr_image.shape[:2] != (output_size[1], output_size[0]):
        sr_image = cv2.resize(sr_image, output_size, interpolation=cv2.INTER_CUBIC)

    raw_depth = estimate_raw_depth(image_bgr)
    normalized_depth = (
        normalize_depth_image(raw_depth)
        if state is None
        else normalize_depth_video(raw_depth, state)
    )
    depth = cv2.resize(normalized_depth, output_size, interpolation=cv2.INTER_CUBIC)
    depth = np.clip(cv2.GaussianBlur(depth, (0, 0), 2.0), 0.0, 1.0).astype(
        np.float32
    )
    edge = make_edge_structure_map(lanczos)
    residual = make_residual_structure_map(
        lanczos, sr_image, percentile=RESIDUAL_PERCENTILE
    )
    structure = np.clip(
        EDGE_WEIGHT * edge + RESIDUAL_WEIGHT * residual, 0.0, 1.0
    ).astype(np.float32)

    warped_blur = None
    if state is not None:
        warped_depth = state.prev_depth
        warped_structure = state.prev_structure
        warped_blur = state.prev_blur
        if state.prev_frame is not None and USE_OPTICAL_FLOW:
            flow = calculate_backward_flow(state.prev_frame, image_bgr, output_size)
            if state.prev_depth is not None:
                warped_depth = warp_previous_map(state.prev_depth, flow)
            if state.prev_structure is not None:
                warped_structure = warp_previous_map(state.prev_structure, flow)
            if state.prev_blur is not None:
                warped_blur = warp_previous_map(state.prev_blur, flow)
        depth = np.clip(
            temporal_blend(depth, warped_depth, VIDEO_DEPTH_ALPHA), 0.0, 1.0
        )
        structure = np.clip(
            temporal_blend(structure, warped_structure, VIDEO_STRUCTURE_ALPHA),
            0.0,
            1.0,
        )

    far_strength = 1.0 - np.clip(
        (depth - DEPTH_FAR) / (DEPTH_NEAR - DEPTH_FAR + 1e-8), 0.0, 1.0
    )
    far_strength = far_strength**2 * (3.0 - 2.0 * far_strength)
    structure_protection = np.clip(
        (structure - STRUCTURE_START) / (1.0 - STRUCTURE_START + 1e-8),
        0.0,
        1.0,
    ) ** STRUCTURE_PROTECT_POWER
    blur = far_strength * (
        1.0 - (1.0 - MIN_STRUCTURE_BLUR) * structure_protection
    )
    if MASK_SIGMA > 0:
        blur = cv2.GaussianBlur(blur, (0, 0), MASK_SIGMA)
    blur = np.clip(blur, 0.0, 1.0)
    if state is not None:
        blur = np.clip(
            temporal_blend(blur, warped_blur, VIDEO_BLUR_ALPHA), 0.0, 1.0
        )

    sr_float = sr_image.astype(np.float32)
    blurred_sr = cv2.GaussianBlur(
        sr_float, (0, 0), sigmaX=BLUR_SIGMA, sigmaY=BLUR_SIGMA
    )
    final = np.clip(
        (1.0 - blur[..., None]) * sr_float + blur[..., None] * blurred_sr,
        0,
        255,
    ).astype(np.uint8)

    if state is not None:
        state.prev_frame = image_bgr.copy()
        state.prev_depth = depth.copy()
        state.prev_structure = structure.copy()
        state.prev_blur = blur.copy()

    return {
        "input": image_bgr,
        "lanczos": lanczos,
        "esrgan": sr_image,
        "depth": depth,
        "edge": edge,
        "residual": residual,
        "structure": structure,
        "far": far_strength,
        "structure_protect": structure_protection,
        "blur": blur,
        "esrgan_blurred": np.clip(blurred_sr, 0, 255).astype(np.uint8),
        "final": final,
        "difference": np.mean(
            np.abs(sr_image.astype(np.float32) - final.astype(np.float32)), axis=2
        ),
    }


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
    result = process_core(image, state=None)
    os.makedirs(save_path, exist_ok=True)
    result_path = os.path.join(save_path, "deepup_result.png")
    if not cv2.imwrite(result_path, result["final"]):
        raise RuntimeError("결과 이미지를 저장하지 못했습니다.")
    return result_path, save_path


def _create_writer(path, fps, size):
    writer = cv2.VideoWriter(
        path, cv2.VideoWriter_fourcc(*"mp4v"), fps, size
    )
    if not writer.isOpened():
        raise RuntimeError("결과 동영상 파일을 만들지 못했습니다.")
    return writer


def _mux_original_audio(original_path, silent_path, output_path):
    if shutil.which("ffmpeg") is None:
        shutil.move(silent_path, output_path)
        return
    completed = subprocess.run(
        [
            "ffmpeg", "-y", "-i", silent_path, "-i", original_path,
            "-map", "0:v:0", "-map", "1:a?",
            # OpenCV writes an MPEG-4 Part 2 intermediate (mp4v), which many
            # browsers cannot play. Convert the final result to browser-safe
            # H.264 and put MP4 metadata first for immediate web playback.
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "192k", "-shortest", output_path,
        ],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        shutil.move(silent_path, output_path)


def process_video(video_path, save_path):
    """Apply the notebook core to video frames with temporal stabilization."""
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError("지원하지 않거나 손상된 동영상 파일입니다.")
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(source_fps) or source_fps <= 0:
        source_fps = VIDEO_MAX_FPS
    output_fps = min(source_fps, VIDEO_MAX_FPS)
    source_frame_count = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    total_output_frames = (
        max(1, min(source_frame_count, math.ceil(source_frame_count * output_fps / source_fps)))
        if source_frame_count > 0
        else 0
    )
    input_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    input_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if input_width <= 0 or input_height <= 0:
        capture.release()
        raise ValueError("동영상 해상도를 확인하지 못했습니다.")

    ratio = min(
        1.0,
        VIDEO_MODEL_MAX_WIDTH / input_width,
        VIDEO_MODEL_MAX_HEIGHT / input_height,
    )
    model_width = max(2, int(input_width * ratio) // 2 * 2)
    model_height = max(2, int(input_height * ratio) // 2 * 2)
    if MAKE_LOW_RESOLUTION:
        model_width = max(2, model_width // DOWNSCALE // 2 * 2)
        model_height = max(2, model_height // DOWNSCALE // 2 * 2)
    output_size = (model_width * UPSCALE, model_height * UPSCALE)

    os.makedirs(save_path, exist_ok=True)
    silent_path = os.path.join(save_path, "deepup_video_silent.mp4")
    output_path = os.path.join(save_path, "deepup_result.mp4")
    try:
        writer = _create_writer(silent_path, output_fps, output_size)
    except Exception:
        capture.release()
        raise

    state = TemporalState()
    frame_index = written_frames = 0
    next_output_time = 0.0
    last_reported_percent = -1
    print(f"DEEPUP_STAGE frames total={total_output_frames}", flush=True)
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_time = frame_index / source_fps
            frame_index += 1
            if frame_time + 1e-9 < next_output_time:
                continue
            next_output_time += 1.0 / output_fps
            if frame.shape[:2] != (model_height, model_width):
                frame = cv2.resize(
                    frame,
                    (model_width, model_height),
                    interpolation=cv2.INTER_AREA,
                )
            writer.write(process_core(frame, state=state)["final"])
            written_frames += 1
            if total_output_frames > 0:
                percent = min(100, int(written_frames * 100 / total_output_frames))
                if percent != last_reported_percent:
                    print(f"DEEPUP_PROGRESS {written_frames}/{total_output_frames}", flush=True)
                    last_reported_percent = percent
    finally:
        capture.release()
        writer.release()

    if written_frames == 0 or not os.path.isfile(silent_path):
        raise RuntimeError("처리할 수 있는 동영상 프레임이 없습니다.")
    print("DEEPUP_STAGE encoding", flush=True)
    _mux_original_audio(video_path, silent_path, output_path)
    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError("결과 동영상 파일을 만들지 못했습니다.")
    return output_path


def process_media(input_path, save_path):
    extension = os.path.splitext(input_path)[1].lower()
    if extension in IMAGE_EXTENSIONS:
        return process_image(input_path, save_path)
    if extension in VIDEO_EXTENSIONS:
        return process_video(input_path, save_path)
    raise ValueError(f"지원하지 않는 파일 형식입니다: {extension}")
