"""Temporal Depth-aware Real-ESRGAN pipeline for videos."""

import os
import shutil
import subprocess

import cv2
import numpy as np
import torch

import image_pipeline as image_core


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

VIDEO_DEPTH_RANGE_ALPHA = 0.95
VIDEO_DEPTH_ALPHA = 0.80
VIDEO_STRUCTURE_ALPHA = 0.70
VIDEO_BLUR_ALPHA = 0.80
SCENE_CUT_THRESHOLD = 0.30
USE_OPTICAL_FLOW = True


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
    return cv2.compareHist(previous, current, cv2.HISTCMP_BHATTACHARYYA) > SCENE_CUT_THRESHOLD


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
    structure_protection = np.clip(
        (structure - image_core.STRUCTURE_START)
        / (1.0 - image_core.STRUCTURE_START + 1e-8),
        0.0,
        1.0,
    ) ** image_core.STRUCTURE_PROTECT_POWER
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


def _mux_original_audio(original_path, silent_path, output_path):
    if shutil.which("ffmpeg") is None:
        shutil.move(silent_path, output_path)
        return
    command = [
        "ffmpeg", "-y", "-i", silent_path, "-i", original_path,
        "-map", "0:v:0", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac",
        "-shortest", output_path,
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
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
    output_size = (
        input_width * image_core.UPSCALE,
        input_height * image_core.UPSCALE,
    )
    os.makedirs(save_path, exist_ok=True)
    silent_path = os.path.join(save_path, "deepup_video_silent.mp4")
    output_path = os.path.join(save_path, "deepup_result.mp4")
    writer = cv2.VideoWriter(
        silent_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, output_size
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("결과 동영상 파일을 만들지 못했습니다.")

    state = TemporalState()
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            writer.write(process_frame(frame, state))
    finally:
        capture.release()
        writer.release()

    _mux_original_audio(video_path, silent_path, output_path)
    return output_path
