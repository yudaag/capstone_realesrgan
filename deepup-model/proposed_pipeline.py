"""Training-time Proposed pipeline copied from the Colab notebook.

The fine-tuned RRDBNet is executed directly.  Depth, edge, residual, structure,
and blur fusion stay in PyTorch/FP32 in the same order as training.
"""

import cv2
import numpy as np
import torch
import torch.nn.functional as F
import torchvision.transforms.functional as TVF
from PIL import Image


SCALE = 4
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

# Still images are fed as uploaded.  The x4 output of a 1000px-side input
# (4000x4000 = 16M px) stays below torch.quantile's 2^24-element limit, so
# only larger uploads are reduced.  On CUDA OOM the side is lowered step by
# step down to MIN_IMAGE_INPUT_SIDE.
MAX_IMAGE_INPUT_SIDE = 1000
MIN_IMAGE_INPUT_SIDE = 512

_processor = None
_depth_model = None
_sr_model = None
_device = None


def configure_models(processor, depth_model, sr_model, device):
    global _processor, _depth_model, _sr_model, _device
    _processor = processor
    _depth_model = depth_model
    _sr_model = sr_model
    _device = device


def _odd_kernel_from_sigma(sigma, minimum=3):
    kernel = max(minimum, int(2 * round(3 * sigma) + 1))
    return kernel if kernel % 2 else kernel + 1


def gaussian_blur_tensor(value, sigma):
    if sigma <= 0:
        return value
    kernel = _odd_kernel_from_sigma(sigma)
    return TVF.gaussian_blur(value, [kernel, kernel], [sigma, sigma])


def _check_finite(name, value):
    if not torch.isfinite(value).all():
        raise RuntimeError(f"{name} 맵 계산 중 NaN/Inf가 발생했습니다.")


def bgr_to_tensor(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return (
        torch.from_numpy(rgb.copy())
        .permute(2, 0, 1)
        .unsqueeze(0)
        .to(device=_device, dtype=torch.float32)
        / 255.0
    )


def tensor_to_bgr(value):
    rgb = (
        value.detach().float().clamp(0, 1)[0]
        .permute(1, 2, 0).cpu().numpy() * 255.0
    ).round().astype(np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def fit_input_side(frame, max_side):
    """Reduce only when the longer side exceeds max_side (aspect preserved)."""
    height, width = frame.shape[:2]
    if max(height, width) <= max_side:
        return frame
    ratio = max_side / max(height, width)
    size = (max(1, int(round(width * ratio))), max(1, int(round(height * ratio))))
    return cv2.resize(frame, size, interpolation=cv2.INTER_AREA)


def enhance_image(frame, max_side=None, min_side=None):
    """Run the training-time Proposed forward on a still image.

    Returns (output_bgr, input_bgr_actually_used).
    """
    side = MAX_IMAGE_INPUT_SIDE if max_side is None else max_side
    floor = MIN_IMAGE_INPUT_SIDE if min_side is None else min_side
    while True:
        lr = fit_input_side(frame, side)
        try:
            return tensor_to_bgr(proposed_forward(bgr_to_tensor(lr))), lr
        except torch.cuda.OutOfMemoryError:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            if side <= floor or max(lr.shape[:2]) <= floor:
                raise
            side = max(floor, int(side * 0.75))


def depth_map_from_lr(lr, out_size):
    images = []
    for item in lr.detach().float().cpu().clamp(0, 1):
        array = (item.permute(1, 2, 0).numpy() * 255).round().astype(np.uint8)
        images.append(Image.fromarray(array))
    inputs = _processor(images=images, return_tensors="pt")
    inputs = {
        key: (value.to(_device, dtype=torch.float32)
              if torch.is_floating_point(value) else value.to(_device))
        for key, value in inputs.items()
    }
    with torch.no_grad(), torch.amp.autocast(device_type="cuda", enabled=False):
        prediction = _depth_model(**inputs).predicted_depth.unsqueeze(1).float()
        prediction = F.interpolate(
            prediction, size=out_size, mode="bicubic", align_corners=False
        )
        flat = prediction.flatten(1)
        low = torch.quantile(flat, 0.02, dim=1).view(-1, 1, 1, 1)
        high = torch.quantile(flat, 0.98, dim=1).view(-1, 1, 1, 1)
        depth = ((prediction - low) / (high - low).clamp_min(1e-6)).clamp(0, 1)
    _check_finite("depth", depth)
    return depth


def make_edge_structure_map(img_rgb, blur_sigma=1.5):
    gray = 0.2989 * img_rgb[:, 0:1] + 0.5870 * img_rgb[:, 1:2] + 0.1140 * img_rgb[:, 2:3]
    kx = torch.tensor(
        [[-1., 0., 1.], [-2., 0., 2.], [-1., 0., 1.]],
        device=img_rgb.device, dtype=torch.float32,
    ).view(1, 1, 3, 3)
    gx = F.conv2d(gray, kx, padding=1)
    gy = F.conv2d(gray, kx.transpose(2, 3), padding=1)
    magnitude = torch.sqrt(gx.square() + gy.square() + 1e-12)
    norm = torch.quantile(magnitude.detach().flatten(1), 0.99, dim=1).view(-1, 1, 1, 1)
    return gaussian_blur_tensor((magnitude / norm.clamp_min(1e-6)).clamp(0, 1), blur_sigma).clamp(0, 1)


def make_residual_structure_map(upscaled, restored, percentile=80, blur_sigma=2.0):
    difference = torch.abs(restored - upscaled).mean(dim=1, keepdim=True)
    flat = difference.detach().flatten(1)
    threshold = torch.quantile(flat, percentile / 100.0, dim=1).view(-1, 1, 1, 1)
    high = torch.quantile(flat, 0.99, dim=1).view(-1, 1, 1, 1)
    residual = ((difference - threshold) / (high - threshold).clamp_min(1e-6)).clamp(0, 1)
    return gaussian_blur_tensor(residual, blur_sigma).clamp(0, 1)


@torch.no_grad()
def proposed_forward(lr, return_maps=False):
    if any(value is None for value in (_processor, _depth_model, _sr_model, _device)):
        raise RuntimeError("Proposed 모델이 설정되지 않았습니다.")
    with torch.amp.autocast(device_type="cuda", enabled=_device.type == "cuda"):
        restored = _sr_model(lr)
    restored = restored.float()
    upscaled = F.interpolate(lr.float(), scale_factor=SCALE, mode="bicubic", align_corners=False)
    depth = depth_map_from_lr(lr, restored.shape[-2:])
    edge = make_edge_structure_map(upscaled)
    residual = make_residual_structure_map(upscaled, restored, RESIDUAL_PERCENTILE)
    structure = (EDGE_WEIGHT * edge + RESIDUAL_WEIGHT * residual).clamp(0, 1)
    far = 1.0 - ((depth - DEPTH_FAR) / max(DEPTH_NEAR - DEPTH_FAR, 1e-6)).clamp(0, 1)
    far = far * far * (3.0 - 2.0 * far)
    structure_raw = ((structure - STRUCTURE_START) / max(1.0 - STRUCTURE_START, 1e-6)).clamp(0, 1)
    epsilon = 1e-4
    epsilon_power = epsilon ** STRUCTURE_PROTECT_POWER
    protection = ((structure_raw + epsilon).pow(STRUCTURE_PROTECT_POWER) - epsilon_power)
    protection /= (1.0 + epsilon) ** STRUCTURE_PROTECT_POWER - epsilon_power
    protection = protection.clamp(0, 1)
    blur = far * (1.0 - (1.0 - MIN_STRUCTURE_BLUR) * protection)
    blur = gaussian_blur_tensor(blur, MASK_SIGMA).clamp(0, 1)
    blurred = gaussian_blur_tensor(restored, BLUR_SIGMA)
    final = (1.0 - blur) * restored + blur * blurred
    if return_maps:
        return final, {
            "I_sr": restored, "I_up": upscaled, "depth": depth,
            "edge": edge, "residual": residual, "structure": structure,
            "far_strength": far, "structure_protect": protection,
            "blur_strength": blur,
        }
    return final
