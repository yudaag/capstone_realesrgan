"""Temporal Depth-aware Real-ESRGAN pipeline for videos."""

import os
import shutil
import subprocess

import cv2
import numpy as np
import torch

import image_pipeline as image_core
import proposed_pipeline


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

VIDEO_DEPTH_RANGE_ALPHA = 0.95
VIDEO_DEPTH_ALPHA = 0.80
VIDEO_STRUCTURE_ALPHA = 0.70
VIDEO_BLUR_ALPHA = 0.80
# Real uploads already contain compression blur. Keep the notebook's
# depth-aware fusion, but prevent it from erasing restored subject detail.
VIDEO_BLUR_SCALE = 0.25
VIDEO_BLUR_MAX = 0.18
SCENE_CUT_THRESHOLD = 0.30
# Web inference prioritizes turnaround time.  The depth/structure maps are
# already temporally blended, so disabling dense optical flow removes a large
# per-frame CPU cost without changing the restoration model itself.
USE_OPTICAL_FLOW = False
# Only retained for the non-Proposed/anime compatibility path. The notebook
# Proposed path processes every source frame at the original FPS.
VIDEO_MAX_FPS = 5.0
# The original Colab pipeline downsamples video frames before x4 restoration.
# MAX_OUTPUT_SIDE remains as a safety limit when low-resolution mode is off.
# Direct RRDBNet forward keeps the notebook math exact but cannot use
# RealESRGANer's tile helper.  A 480px input side produces a 1920px x4 result
# and stays within the Replicate T4 memory budget.
MAX_OUTPUT_SIDE = 1920
# Preserve genuinely low-resolution uploads. Only oversized inputs are reduced
# as an OOM safety fallback because direct RRDBNet forward cannot be tiled.
MAX_PROPOSED_INPUT_SIDE = 640
USE_TRAINING_PROPOSED = False


def use_training_proposed(enabled):
    """Select the notebook's trained Proposed forward for photo/video."""
    global USE_TRAINING_PROPOSED
    USE_TRAINING_PROPOSED = bool(enabled)


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


def detect_scene_cut(previous, current):
    if previous is None:
        return False
    previous = cv2.resize(previous, (64, 64), interpolation=cv2.INTER_AREA)
    current = cv2.resize(current, (64, 64), interpolation=cv2.INTER_AREA)
    previous = cv2.cvtColor(previous, cv2.COLOR_BGR2HSV)
    current = cv2.cvtColor(current, cv2.COLOR_BGR2HSV)
    hist_previous = cv2.calcHist([previous], [0, 1], None, [32, 32], [0, 180, 0, 256])
    hist_current = cv2.calcHist([current], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(hist_previous, hist_previous)
    cv2.normalize(hist_current, hist_current)
    return cv2.compareHist(hist_previous, hist_current, cv2.HISTCMP_BHATTACHARYYA) > SCENE_CUT_THRESHOLD


def calculate_backward_flow(previous, current, output_size):
    out_width, out_height = output_size
    previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(
        current_gray, previous_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
    )
    flow = cv2.resize(flow, output_size, interpolation=cv2.INTER_LINEAR)
    flow[..., 0] *= out_width / previous.shape[1]
    flow[..., 1] *= out_height / previous.shape[0]
    return flow


def warp_previous_map(previous_map, flow):
    height, width = previous_map.shape[:2]
    grid_x, grid_y = np.meshgrid(
        np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32)
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


def normalize_depth_video(depth, state):
    current_low = np.percentile(depth, 2)
    current_high = np.percentile(depth, 98)
    if state.depth_low is None:
        state.depth_low, state.depth_high = current_low, current_high
    else:
        state.depth_low = VIDEO_DEPTH_RANGE_ALPHA * state.depth_low + (1.0 - VIDEO_DEPTH_RANGE_ALPHA) * current_low
        state.depth_high = VIDEO_DEPTH_RANGE_ALPHA * state.depth_high + (1.0 - VIDEO_DEPTH_RANGE_ALPHA) * current_high
    return np.clip(
        (depth - state.depth_low) / (state.depth_high - state.depth_low + 1e-8),
        0.0,
        1.0,
    )


def process_frame(frame, state):
    if USE_TRAINING_PROPOSED:
        return process_proposed_frame(frame, state)

    height, width = frame.shape[:2]
    out_width, out_height = width * image_core.UPSCALE, height * image_core.UPSCALE
    if detect_scene_cut(state.prev_frame, frame):
        state.reset()

    lanczos = cv2.resize(frame, (out_width, out_height), interpolation=cv2.INTER_LANCZOS4)
    with torch.no_grad():
        sr_image, _ = image_core.upsampler.enhance(frame, outscale=image_core.UPSCALE)
    if sr_image.shape[:2] != (out_height, out_width):
        sr_image = cv2.resize(sr_image, (out_width, out_height), interpolation=cv2.INTER_CUBIC)

    depth = normalize_depth_video(image_core.estimate_raw_depth(frame), state)
    depth = cv2.resize(depth, (out_width, out_height), interpolation=cv2.INTER_CUBIC)
    depth = np.clip(cv2.GaussianBlur(depth, (0, 0), 2.0), 0.0, 1.0)
    edge = image_core.make_edge_structure_map(lanczos)
    residual = image_core.make_residual_structure_map(
        lanczos, sr_image, percentile=image_core.RESIDUAL_PERCENTILE
    )
    structure = np.clip(
        image_core.EDGE_WEIGHT * edge + image_core.RESIDUAL_WEIGHT * residual,
        0.0,
        1.0,
    )

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
    structure = np.clip(
        temporal_blend(structure, warped_structure, VIDEO_STRUCTURE_ALPHA), 0.0, 1.0
    )
    far_strength = 1.0 - np.clip(
        (depth - image_core.DEPTH_FAR)
        / (image_core.DEPTH_NEAR - image_core.DEPTH_FAR + 1e-8),
        0.0,
        1.0,
    )
    far_strength = far_strength**2 * (3.0 - 2.0 * far_strength)
    structure_raw = np.clip(
        (structure - image_core.STRUCTURE_START)
        / (1.0 - image_core.STRUCTURE_START + 1e-8),
        0.0,
        1.0,
    )
    power_eps = 1e-4
    eps_power = power_eps ** image_core.STRUCTURE_PROTECT_POWER
    structure_protection = (
        (structure_raw + power_eps) ** image_core.STRUCTURE_PROTECT_POWER
        - eps_power
    ) / (
        (1.0 + power_eps) ** image_core.STRUCTURE_PROTECT_POWER
        - eps_power
    )
    structure_protection = np.clip(structure_protection, 0.0, 1.0)
    blur = far_strength * (
        1.0 - (1.0 - image_core.MIN_STRUCTURE_BLUR) * structure_protection
    )
    if image_core.MASK_SIGMA > 0:
        blur = cv2.GaussianBlur(blur, (0, 0), image_core.MASK_SIGMA)
    blur = np.clip(temporal_blend(blur, warped_blur, VIDEO_BLUR_ALPHA), 0.0, 1.0)

    sr_float = sr_image.astype(np.float32)
    blurred = cv2.GaussianBlur(
        sr_float, (0, 0), image_core.BLUR_SIGMA, image_core.BLUR_SIGMA
    )
    final = np.clip(
        (1.0 - blur[..., None]) * sr_float + blur[..., None] * blurred, 0, 255
    ).astype(np.uint8)

    state.prev_frame = frame.copy()
    state.prev_depth = depth.copy()
    state.prev_structure = structure.copy()
    state.prev_blur = blur.copy()
    return final


def process_proposed_frame(frame, state):
    """Cell 14 process_core(), using maps returned by proposed_forward()."""
    if detect_scene_cut(state.prev_frame, frame):
        state.reset()

    lr = proposed_pipeline.bgr_to_tensor(frame)
    final_tensor, maps = proposed_pipeline.proposed_forward(lr, return_maps=True)

    depth = maps["depth"][0, 0].detach().float().cpu().numpy().astype(np.float32)
    structure = maps["structure"][0, 0].detach().float().cpu().numpy().astype(np.float32)
    blur = maps["blur_strength"][0, 0].detach().float().cpu().numpy().astype(np.float32)

    # The notebook smooths the learned Proposed maps for video.  Still-image
    # inference returns final_tensor directly without this temporal branch.
    if state.prev_depth is not None and state.prev_depth.shape == depth.shape:
        depth = VIDEO_DEPTH_ALPHA * depth + (1.0 - VIDEO_DEPTH_ALPHA) * state.prev_depth
    if state.prev_structure is not None and state.prev_structure.shape == structure.shape:
        structure = VIDEO_STRUCTURE_ALPHA * structure + (1.0 - VIDEO_STRUCTURE_ALPHA) * state.prev_structure
    if state.prev_blur is not None and state.prev_blur.shape == blur.shape:
        blur = VIDEO_BLUR_ALPHA * blur + (1.0 - VIDEO_BLUR_ALPHA) * state.prev_blur

    temporal_blur = blur.copy()
    blur = np.minimum(blur * VIDEO_BLUR_SCALE, VIDEO_BLUR_MAX)

    blurred = proposed_pipeline.gaussian_blur_tensor(
        maps["I_sr"], proposed_pipeline.BLUR_SIGMA
    )
    restored_rgb = maps["I_sr"][0].detach().float().permute(1, 2, 0).cpu().numpy()
    blurred_rgb = blurred[0].detach().float().permute(1, 2, 0).cpu().numpy()
    merged_rgb = np.clip(
        (1.0 - blur[..., None]) * restored_rgb + blur[..., None] * blurred_rgb,
        0.0,
        1.0,
    )
    final = cv2.cvtColor(
        (merged_rgb * 255.0).round().astype(np.uint8), cv2.COLOR_RGB2BGR
    )

    state.prev_frame = frame.copy()
    state.prev_depth = depth.copy()
    state.prev_structure = structure.copy()
    state.prev_blur = temporal_blur
    return final


def _mux_original_audio(original_path, silent_path, output_path):
    if shutil.which("ffmpeg") is None:
        shutil.move(silent_path, output_path)
        return
    command = [
        "ffmpeg", "-y", "-i", silent_path, "-i", original_path,
        "-map", "0:v:0", "-map", "1:a?",
        # OpenCV's mp4v output is not reliably playable in Chrome/Safari.
        # Re-encode to browser-compatible H.264 and move the MP4 index to the
        # beginning so playback can start while the file is streaming.
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "192k", "-shortest", output_path,
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        shutil.move(silent_path, output_path)


def _processing_size(width, height):
    if width <= 0 or height <= 0:
        raise ValueError("동영상 해상도를 확인할 수 없습니다.")
    if USE_TRAINING_PROPOSED:
        # Service inference receives a real LR frame, not an HR benchmark
        # target. Do not apply the notebook's synthetic x4 degradation again.
        ratio = min(1.0, MAX_PROPOSED_INPUT_SIDE / max(width, height))
        process_width = max(1, int(round(width * ratio)))
        process_height = max(1, int(round(height * ratio)))
    elif image_core.MAKE_LOW_RESOLUTION:
        process_width = max(2, width // image_core.DOWNSCALE)
        process_height = max(2, height // image_core.DOWNSCALE)
    elif image_core.UPSCALE > 1:
        max_input_side = max(2, MAX_OUTPUT_SIDE // image_core.UPSCALE)
        ratio = min(1.0, max_input_side / max(width, height))
        process_width = max(2, int(round(width * ratio)))
        process_height = max(2, int(round(height * ratio)))
    else:
        # Video restoration uses outscale=1: do not downsample the source
        # before the proposed model sees it.
        process_width = width
        process_height = height
    # The x4 Proposed output is always even. The compatibility path still
    # needs an even input for its direct writer size.
    if not USE_TRAINING_PROPOSED:
        process_width -= process_width % 2
        process_height -= process_height % 2
    return process_width, process_height


def process_video(video_path, save_path):
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError("지원하지 않거나 손상된 동영상 파일입니다.")

    source_fps = capture.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(source_fps) or source_fps <= 0:
        source_fps = 30.0
    # Processing every source frame is prohibitively expensive because each
    # frame runs both Real-ESRGAN and the depth model.  The temporary 5 fps
    # verification preset preserves the duration while making it quick to
    # confirm that the complete enhancement pipeline works end-to-end.
    output_fps = (
        float(source_fps)
        if USE_TRAINING_PROPOSED
        else min(float(source_fps), VIDEO_MAX_FPS)
    )
    input_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    input_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    process_width, process_height = _processing_size(input_width, input_height)
    output_scale = proposed_pipeline.SCALE if USE_TRAINING_PROPOSED else image_core.UPSCALE
    output_size = (process_width * output_scale, process_height * output_scale)
    os.makedirs(save_path, exist_ok=True)
    silent_path = os.path.join(save_path, "deepup_video_silent.mp4")
    output_path = os.path.join(save_path, "deepup_result.mp4")
    writer = cv2.VideoWriter(
        silent_path, cv2.VideoWriter_fourcc(*"mp4v"), output_fps, output_size
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("결과 동영상 파일을 만들지 못했습니다.")

    state = TemporalState()
    source_frame_index = 0
    next_output_time = 0.0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_time = source_frame_index / source_fps
            source_frame_index += 1
            if not USE_TRAINING_PROPOSED:
                # Compatibility path keeps representative frames on a time
                # grid. Proposed follows the notebook and processes all frames.
                if frame_time + (0.5 / source_fps) < next_output_time:
                    continue
                next_output_time += 1.0 / output_fps
            if frame.shape[1] != process_width or frame.shape[0] != process_height:
                frame = cv2.resize(
                    frame,
                    (process_width, process_height),
                    interpolation=cv2.INTER_AREA,
                )
            writer.write(process_frame(frame, state))
    finally:
        capture.release()
        writer.release()

    if not os.path.exists(silent_path) or os.path.getsize(silent_path) == 0:
        raise RuntimeError("동영상 인코딩 결과가 비어 있습니다.")

    _mux_original_audio(video_path, silent_path, output_path)
    return output_path
