"""Landscape/animal (photo) video: fine-tuned Proposed forward per frame.

Frames are fed as uploaded (no synthetic 1/4 bicubic degradation) and
restored x4. Temporal smoothing of the depth/structure/blur maps follows
depth_풍경_동물_파이프라인.ipynb. Anime is not handled here.
"""

import os
import shutil
import subprocess

import cv2
import numpy as np

import proposed_pipeline


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

VIDEO_DEPTH_ALPHA = 0.80
VIDEO_STRUCTURE_ALPHA = 0.70
VIDEO_BLUR_ALPHA = 0.80
SCENE_CUT_THRESHOLD = 0.30
# Sampled fps for web turnaround. None = every source frame (like the notebook).
MAX_FPS = 5.0
# Speed/OOM safety: frames whose longer side exceeds this are reduced
# (x4 output up to 2560px). Smaller uploads are used as-is.
MAX_INPUT_SIDE = 640


class TemporalState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.prev_frame = None
        self.prev_depth = None
        self.prev_structure = None
        self.prev_blur = None


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


def process_frame(frame, state):
    if detect_scene_cut(state.prev_frame, frame):
        state.reset()

    lr = proposed_pipeline.bgr_to_tensor(frame)
    _, maps = proposed_pipeline.proposed_forward(lr, return_maps=True)

    depth = maps["depth"][0, 0].detach().float().cpu().numpy().astype(np.float32)
    structure = maps["structure"][0, 0].detach().float().cpu().numpy().astype(np.float32)
    blur = maps["blur_strength"][0, 0].detach().float().cpu().numpy().astype(np.float32)

    if state.prev_depth is not None and state.prev_depth.shape == depth.shape:
        depth = VIDEO_DEPTH_ALPHA * depth + (1.0 - VIDEO_DEPTH_ALPHA) * state.prev_depth
    if state.prev_structure is not None and state.prev_structure.shape == structure.shape:
        structure = VIDEO_STRUCTURE_ALPHA * structure + (1.0 - VIDEO_STRUCTURE_ALPHA) * state.prev_structure
    if state.prev_blur is not None and state.prev_blur.shape == blur.shape:
        blur = VIDEO_BLUR_ALPHA * blur + (1.0 - VIDEO_BLUR_ALPHA) * state.prev_blur

    blurred = proposed_pipeline.gaussian_blur_tensor(maps["I_sr"], proposed_pipeline.BLUR_SIGMA)
    restored_rgb = maps["I_sr"][0].detach().float().permute(1, 2, 0).cpu().numpy()
    blurred_rgb = blurred[0].detach().float().permute(1, 2, 0).cpu().numpy()
    merged_rgb = np.clip((1.0 - blur[..., None]) * restored_rgb + blur[..., None] * blurred_rgb, 0.0, 1.0)
    final = cv2.cvtColor((merged_rgb * 255.0).round().astype(np.uint8), cv2.COLOR_RGB2BGR)

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
        "-map", "0:v:0", "-map", "1:a?",
        # Browser-compatible H.264 with the index at the start.
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "192k", "-shortest", output_path,
    ]
    if subprocess.run(command, capture_output=True, text=True).returncode != 0:
        shutil.move(silent_path, output_path)


def _processing_size(width, height):
    if width <= 0 or height <= 0:
        raise ValueError("동영상 해상도를 확인할 수 없습니다.")
    if max(width, height) <= MAX_INPUT_SIDE:
        return width, height
    ratio = MAX_INPUT_SIDE / max(width, height)
    return max(1, int(round(width * ratio))), max(1, int(round(height * ratio)))


def process_video(video_path, save_path):
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError("지원하지 않거나 손상된 동영상 파일입니다.")

    source_fps = capture.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(source_fps) or source_fps <= 0:
        source_fps = 30.0
    output_fps = float(source_fps) if MAX_FPS is None else min(float(source_fps), MAX_FPS)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    process_width, process_height = _processing_size(width, height)
    output_size = (process_width * proposed_pipeline.SCALE, process_height * proposed_pipeline.SCALE)

    os.makedirs(save_path, exist_ok=True)
    silent_path = os.path.join(save_path, "deepup_video_silent.mp4")
    output_path = os.path.join(save_path, "deepup_result.mp4")
    writer = cv2.VideoWriter(silent_path, cv2.VideoWriter_fourcc(*"mp4v"), output_fps, output_size)
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("결과 동영상 파일을 만들지 못했습니다.")

    state = TemporalState()
    index = 0
    next_output_time = 0.0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_time = index / source_fps
            index += 1
            if frame_time + (0.5 / source_fps) < next_output_time:
                continue
            next_output_time += 1.0 / output_fps
            if frame.shape[1] != process_width or frame.shape[0] != process_height:
                frame = cv2.resize(frame, (process_width, process_height), interpolation=cv2.INTER_AREA)
            writer.write(process_frame(frame, state))
    finally:
        capture.release()
        writer.release()

    if not os.path.exists(silent_path) or os.path.getsize(silent_path) == 0:
        raise RuntimeError("동영상 인코딩 결과가 비어 있습니다.")
    _mux_original_audio(video_path, silent_path, output_path)
    return output_path
