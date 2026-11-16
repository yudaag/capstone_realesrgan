"""Image-only Depth-aware Real-ESRGAN pipeline.

The image processing parameters and final calculation are preserved from
depth_final_fixed.ipynb. Video, temporal processing, debug images, statistics,
and Colab-only code were removed for the web deployment.
"""

import os

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


def process_media(input_path, save_path):
    extension = os.path.splitext(input_path)[1].lower()
    if extension not in IMAGE_EXTENSIONS:
        raise ValueError("지원하지 않는 파일 형식입니다. 이미지 파일을 선택해 주세요.")
    return process_image(input_path, save_path)
