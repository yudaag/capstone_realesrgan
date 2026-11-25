"""Fine-tuned landscape/animal pipeline matching the Colab Proposed forward."""

import os
import shutil
import subprocess

import cv2
import numpy as np
import torch
import torch.nn.functional as F
import torchvision.transforms.functional as TVF
from PIL import Image


processor = None
depth_model = None
device = None
sr_model = None

MAKE_LOW_RESOLUTION = True
DOWNSCALE = 1
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
MASK_SIGMA = 1.0
POWER_EPS = 1e-4
MODEL_SCALE = 4
VIDEO_MODEL_MAX_WIDTH = 960
VIDEO_MODEL_MAX_HEIGHT = 540

# Video-only parameters from the landscape/animal Colab pipeline.
VIDEO_DEPTH_RANGE_ALPHA = 0.95
VIDEO_DEPTH_ALPHA = 0.80
VIDEO_STRUCTURE_ALPHA = 0.70
VIDEO_BLUR_ALPHA = 0.80
SCENE_CUT_THRESHOLD = 0.30
USE_OPTICAL_FLOW = True

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


class TemporalState:
    def __init__(self):
        self.prev_frame = None
        self.prev_depth = None
        self.prev_structure = None
        self.prev_blur = None
        self.depth_low = None
        self.depth_high = None

    def reset(self):
        self.prev_frame = None
        self.prev_depth = None
        self.prev_structure = None
        self.prev_blur = None
        self.depth_low = None
        self.depth_high = None


def configure_models(depth_processor, loaded_depth_model, torch_device, proposed_model):
    global processor, depth_model, device, sr_model
    processor = depth_processor
    depth_model = loaded_depth_model
    device = torch_device
    sr_model = proposed_model


def _odd_kernel_from_sigma(sigma, minimum=3):
    kernel = max(minimum, int(2 * round(3 * sigma) + 1))
    return kernel if kernel % 2 == 1 else kernel + 1


def gaussian_blur_tensor(tensor, sigma):
    if sigma <= 0:
        return tensor
    kernel = _odd_kernel_from_sigma(sigma)
    return TVF.gaussian_blur(tensor, [kernel, kernel], [sigma, sigma])


def _check_finite(name, tensor):
    if not torch.isfinite(tensor).all():
        raise RuntimeError(f"[{name}] NaN/Inf detected")


def depth_map_from_lr(lr, out_size, state=None):
    pil_images = []
    lr_cpu = lr.detach().float().cpu().clamp(0.0, 1.0)
    for image in lr_cpu:
        array = (
            image.permute(1, 2, 0).numpy() * 255.0
        ).round().astype(np.uint8)
        pil_images.append(Image.fromarray(array))

    inputs = processor(images=pil_images, return_tensors="pt")
    inputs = {
        key: (
            value.to(device=device, dtype=torch.float32)
            if torch.is_floating_point(value)
            else value.to(device)
        )
        for key, value in inputs.items()
    }

    with torch.no_grad():
        with torch.amp.autocast(device_type="cuda", enabled=False):
            predicted = depth_model(**inputs).predicted_depth
            predicted = predicted.unsqueeze(1).float()
            predicted = F.interpolate(
                predicted,
                size=out_size,
                mode="bicubic",
                align_corners=False,
            )
            _check_finite("depth_raw", predicted)

            flat = predicted.flatten(1)
            current_low = torch.quantile(flat, 0.02, dim=1).view(-1, 1, 1, 1)
            current_high = torch.quantile(flat, 0.98, dim=1).view(-1, 1, 1, 1)
            if state is None:
                low = current_low
                high = current_high
            else:
                current_low_value = float(current_low.item())
                current_high_value = float(current_high.item())
                if state.depth_low is None:
                    state.depth_low = current_low_value
                    state.depth_high = current_high_value
                else:
                    state.depth_low = (
                        VIDEO_DEPTH_RANGE_ALPHA * state.depth_low
                        + (1.0 - VIDEO_DEPTH_RANGE_ALPHA) * current_low_value
                    )
                    state.depth_high = (
                        VIDEO_DEPTH_RANGE_ALPHA * state.depth_high
                        + (1.0 - VIDEO_DEPTH_RANGE_ALPHA) * current_high_value
                    )
                low = torch.full_like(current_low, state.depth_low)
                high = torch.full_like(current_high, state.depth_high)
            depth = ((predicted - low) / (high - low).clamp_min(1e-6)).clamp(0.0, 1.0)
            _check_finite("depth_norm", depth)
    return depth


def make_edge_structure_map_torch(image_rgb, blur_sigma=1.5):
    image_rgb = image_rgb.float()
    gray = (
        0.2989 * image_rgb[:, 0:1]
        + 0.5870 * image_rgb[:, 1:2]
        + 0.1140 * image_rgb[:, 2:3]
    )
    kernel_x = torch.tensor(
        [[-1.0, 0.0, 1.0], [-2.0, 0.0, 2.0], [-1.0, 0.0, 1.0]],
        device=image_rgb.device,
        dtype=torch.float32,
    ).view(1, 1, 3, 3)
    kernel_y = kernel_x.transpose(2, 3)
    grad_x = F.conv2d(gray, kernel_x, padding=1)
    grad_y = F.conv2d(gray, kernel_y, padding=1)
    magnitude = torch.sqrt(grad_x.square() + grad_y.square() + 1e-12)
    norm = torch.quantile(
        magnitude.detach().flatten(1), 0.99, dim=1
    ).view(-1, 1, 1, 1).clamp_min(1e-6)
    result = gaussian_blur_tensor(
        (magnitude / norm).clamp(0.0, 1.0), blur_sigma
    ).clamp(0.0, 1.0)
    _check_finite("edge_map", result)
    return result


def make_residual_structure_map_torch(
    lanczos, sr_image, percentile=80, blur_sigma=2.0
):
    difference = torch.abs(sr_image.float() - lanczos.float()).mean(
        dim=1, keepdim=True
    )
    _check_finite("residual_diff", difference)
    flat = difference.detach().flatten(1)
    threshold = torch.quantile(
        flat, percentile / 100.0, dim=1
    ).view(-1, 1, 1, 1)
    high = torch.quantile(flat, 0.99, dim=1).view(-1, 1, 1, 1)
    residual = (
        (difference - threshold) / (high - threshold).clamp_min(1e-6)
    ).clamp(0.0, 1.0)
    residual = gaussian_blur_tensor(residual, blur_sigma).clamp(0.0, 1.0)
    _check_finite("residual_map", residual)
    return residual


def proposed_forward(model, lr, return_maps=False, temporal_state=None):
    amp_enabled = device.type == "cuda"
    with torch.amp.autocast(device_type="cuda", enabled=amp_enabled):
        image_sr = model(lr)
    _check_finite("rrdbnet_output", image_sr)

    image_sr = image_sr.float()
    lanczos = F.interpolate(
        lr.float(), scale_factor=MODEL_SCALE, mode="bicubic", align_corners=False
    )
    depth = depth_map_from_lr(lr, image_sr.shape[-2:], state=temporal_state).to(
        device=image_sr.device, dtype=torch.float32
    )
    edge = make_edge_structure_map_torch(lanczos, blur_sigma=1.5)
    residual = make_residual_structure_map_torch(
        lanczos,
        image_sr,
        percentile=RESIDUAL_PERCENTILE,
        blur_sigma=2.0,
    )
    structure = (EDGE_WEIGHT * edge + RESIDUAL_WEIGHT * residual).clamp(0.0, 1.0)

    far_strength = 1.0 - (
        (depth - DEPTH_FAR) / max(DEPTH_NEAR - DEPTH_FAR, 1e-6)
    ).clamp(0.0, 1.0)
    far_strength = far_strength * far_strength * (3.0 - 2.0 * far_strength)

    structure_raw = (
        (structure - STRUCTURE_START) / max(1.0 - STRUCTURE_START, 1e-6)
    ).clamp(0.0, 1.0)
    eps_power = POWER_EPS ** STRUCTURE_PROTECT_POWER
    structure_protect = (
        (structure_raw + POWER_EPS).pow(STRUCTURE_PROTECT_POWER) - eps_power
    ) / (
        (1.0 + POWER_EPS) ** STRUCTURE_PROTECT_POWER - eps_power
    )
    structure_protect = structure_protect.clamp(0.0, 1.0)

    blur_strength = far_strength * (
        1.0 - (1.0 - MIN_STRUCTURE_BLUR) * structure_protect
    )
    blur_strength = gaussian_blur_tensor(
        blur_strength, MASK_SIGMA
    ).clamp(0.0, 1.0)

    blurred_sr = gaussian_blur_tensor(image_sr, BLUR_SIGMA)
    final = (1.0 - blur_strength) * image_sr + blur_strength * blurred_sr
    _check_finite("I_final", final)

    if return_maps:
        return final, {
            "I_sr": image_sr,
            "I_up": lanczos,
            "depth": depth,
            "edge": edge,
            "residual": residual,
            "structure": structure,
            "far_strength": far_strength,
            "structure_protect": structure_protect,
            "blur_strength": blur_strength,
        }
    return final


def _as_bgr(tensor):
    rgb = (
        tensor[0].detach().float().clamp(0.0, 1.0)
        .permute(1, 2, 0).cpu().numpy() * 255.0
    ).round().astype(np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _as_map(tensor):
    return tensor[0, 0].detach().float().cpu().numpy().astype(np.float32)


def detect_scene_cut(previous_frame, current_frame):
    if previous_frame is None:
        return False
    previous_small = cv2.resize(previous_frame, (64, 64), interpolation=cv2.INTER_AREA)
    current_small = cv2.resize(current_frame, (64, 64), interpolation=cv2.INTER_AREA)
    previous_hsv = cv2.cvtColor(previous_small, cv2.COLOR_BGR2HSV)
    current_hsv = cv2.cvtColor(current_small, cv2.COLOR_BGR2HSV)
    previous_hist = cv2.calcHist([previous_hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    current_hist = cv2.calcHist([current_hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(previous_hist, previous_hist)
    cv2.normalize(current_hist, current_hist)
    distance = cv2.compareHist(previous_hist, current_hist, cv2.HISTCMP_BHATTACHARYYA)
    return distance > SCENE_CUT_THRESHOLD


def calculate_backward_flow(previous_frame, current_frame, output_size):
    output_width, output_height = output_size
    previous_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(
        current_gray, previous_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
    )
    flow = cv2.resize(flow, (output_width, output_height), interpolation=cv2.INTER_LINEAR)
    flow[..., 0] *= output_width / previous_frame.shape[1]
    flow[..., 1] *= output_height / previous_frame.shape[0]
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
    if state is not None and detect_scene_cut(state.prev_frame, image_bgr):
        state.reset()

    previous_frame = state.prev_frame if state is not None else None
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    lr = torch.from_numpy(
        np.ascontiguousarray(rgb.transpose(2, 0, 1))
    ).unsqueeze(0).to(device=device, dtype=torch.float32) / 255.0

    with torch.inference_mode():
        proposed, maps = proposed_forward(
            sr_model, lr, return_maps=True, temporal_state=state
        )

        # The trained network is native x4. Keep the notebook path untouched
        # for x4, and only resize its completed tensors when the API requests x2.
        target_size = (
            image_bgr.shape[0] * UPSCALE,
            image_bgr.shape[1] * UPSCALE,
        )
        if proposed.shape[-2:] != target_size:
            proposed = F.interpolate(
                proposed, size=target_size, mode="bicubic", align_corners=False
            )
            maps = {
                key: F.interpolate(
                    value, size=target_size, mode="bilinear", align_corners=False
                )
                for key, value in maps.items()
            }

        blurred_tensor = gaussian_blur_tensor(maps["I_sr"], BLUR_SIGMA)

    image_sr = _as_bgr(maps["I_sr"])
    image_up = cv2.resize(
        image_bgr,
        (image_sr.shape[1], image_sr.shape[0]),
        interpolation=cv2.INTER_LANCZOS4,
    )
    depth = _as_map(maps["depth"])
    edge = _as_map(maps["edge"])
    residual = _as_map(maps["residual"])
    structure = _as_map(maps["structure"])
    far = _as_map(maps["far_strength"])
    protect = _as_map(maps["structure_protect"])
    blur = _as_map(maps["blur_strength"])

    if state is None:
        final = _as_bgr(proposed)
    else:
        previous_depth = state.prev_depth
        previous_structure = state.prev_structure
        previous_blur = state.prev_blur
        if USE_OPTICAL_FLOW and previous_frame is not None:
            flow = calculate_backward_flow(
                previous_frame,
                image_bgr,
                (depth.shape[1], depth.shape[0]),
            )
            if previous_depth is not None and previous_depth.shape == depth.shape:
                previous_depth = warp_previous_map(previous_depth, flow)
            if previous_structure is not None and previous_structure.shape == structure.shape:
                previous_structure = warp_previous_map(previous_structure, flow)
            if previous_blur is not None and previous_blur.shape == blur.shape:
                previous_blur = warp_previous_map(previous_blur, flow)

        if previous_depth is not None and previous_depth.shape == depth.shape:
            depth = temporal_blend(depth, previous_depth, VIDEO_DEPTH_ALPHA)
        if previous_structure is not None and previous_structure.shape == structure.shape:
            structure = temporal_blend(
                structure, previous_structure, VIDEO_STRUCTURE_ALPHA
            )
        if previous_blur is not None and previous_blur.shape == blur.shape:
            blur = temporal_blend(blur, previous_blur, VIDEO_BLUR_ALPHA)
        state.prev_frame = image_bgr.copy()
        state.prev_depth = depth.copy()
        state.prev_structure = structure.copy()
        state.prev_blur = blur.copy()

        sr_float = (
            maps["I_sr"][0].detach().float().permute(1, 2, 0).cpu().numpy()
        )
        blur_float = (
            blurred_tensor[0].detach().float().permute(1, 2, 0).cpu().numpy()
        )
        merged = np.clip(
            (1.0 - blur[..., None]) * sr_float
            + blur[..., None] * blur_float,
            0.0,
            1.0,
        )
        final = cv2.cvtColor(
            (merged * 255.0).round().astype(np.uint8),
            cv2.COLOR_RGB2BGR,
        )

    return {
        "input": image_bgr,
        "lanczos": image_up,
        "esrgan": image_sr,
        "depth": depth,
        "edge": edge,
        "residual": residual,
        "structure": structure,
        "far": far,
        "structure_protect": protect,
        "blur": blur,
        "esrgan_blurred": _as_bgr(blurred_tensor),
        "final": final,
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

    result = process_core(image, state=None)["final"]
    os.makedirs(save_path, exist_ok=True)
    result_path = os.path.join(save_path, "deepup_result.png")
    if not cv2.imwrite(result_path, result):
        raise RuntimeError("결과 이미지를 저장하지 못했습니다.")
    return result_path


def _mux_original_audio(original_path, silent_path, output_path):
    if shutil.which("ffmpeg") is None:
        shutil.move(silent_path, output_path)
        return
    completed = subprocess.run([
        "ffmpeg", "-y", "-i", silent_path, "-i", original_path,
        "-map", "0:v:0", "-map", "1:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k",
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
    total_frames = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
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
    output_size = (model_width * UPSCALE, model_height * UPSCALE)
    os.makedirs(save_path, exist_ok=True)
    silent_path = os.path.join(save_path, "deepup_video_silent.mp4")
    output_path = os.path.join(save_path, "deepup_result.mp4")
    writer = cv2.VideoWriter(silent_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, output_size)
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("결과 동영상 파일을 만들지 못했습니다.")
    state = TemporalState()
    written_frames = 0
    last_reported_percent = -1
    print(f"DEEPUP_STAGE frames total={total_frames}", flush=True)
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame.shape[:2] != (model_height, model_width):
                frame = cv2.resize(
                    frame,
                    (model_width, model_height),
                    interpolation=cv2.INTER_AREA,
                )
            writer.write(process_core(frame, state=state)["final"])
            written_frames += 1
            if total_frames > 0:
                percent = min(100, int(written_frames * 100 / total_frames))
                if percent != last_reported_percent:
                    print(f"DEEPUP_PROGRESS {written_frames}/{total_frames}", flush=True)
                    last_reported_percent = percent
    finally:
        capture.release()
        writer.release()
    print("DEEPUP_STAGE encoding", flush=True)
    _mux_original_audio(video_path, silent_path, output_path)
    return output_path


def process_media(input_path, save_path):
    extension = os.path.splitext(input_path)[1].lower()
    if extension in IMAGE_EXTENSIONS:
        return process_image(input_path, save_path)
    if extension in VIDEO_EXTENSIONS:
        return process_video(input_path, save_path)
    raise ValueError("지원하지 않는 파일 형식입니다.")
