"""Replicate/Cog entry point for the DeepUp capstone model."""

import os
import shutil
import sys
import tempfile
import types
from pathlib import Path as SystemPath

import cv2
import torch
import torchvision.transforms.functional as TF
from cog import BasePredictor, Input, Path
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation

# BasicSR still imports a torchvision module removed in newer torchvision.
# This compatibility shim is the same one used in the original notebook.
functional_tensor = types.ModuleType("torchvision.transforms.functional_tensor")
functional_tensor.rgb_to_grayscale = TF.rgb_to_grayscale
sys.modules["torchvision.transforms.functional_tensor"] = functional_tensor

from basicsr.archs.rrdbnet_arch import RRDBNet  # noqa: E402
from realesrgan import RealESRGANer  # noqa: E402

import image_pipeline  # noqa: E402
import photo_pipeline  # noqa: E402
import video_pipeline  # noqa: E402


ROOT = SystemPath(__file__).resolve().parent
WEIGHTS = ROOT / "weights" / "best_proposed_realesrgan_div2k.pth"
BASE_WEIGHTS = ROOT / "weights" / "RealESRGAN_x4plus.pth"
DEPTH_MODEL_ID = "depth-anything/Depth-Anything-V2-Small-hf"


def detect_extension(source: SystemPath) -> str:
    """Detect media type when Replicate downloads a URL without a suffix."""
    suffix = source.suffix.lower()
    if suffix in image_pipeline.IMAGE_EXTENSIONS | video_pipeline.VIDEO_EXTENSIONS:
        return suffix
    try:
        with Image.open(source) as image:
            image_format = (image.format or "").upper()
        mapped = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "BMP": ".bmp", "TIFF": ".tiff"}
        if image_format in mapped:
            return mapped[image_format]
    except Exception:
        pass
    capture = cv2.VideoCapture(str(source))
    try:
        if capture.isOpened():
            return ".mp4"
    finally:
        capture.release()
    raise ValueError("지원하지 않는 파일 형식입니다. 이미지 또는 동영상 파일을 선택해 주세요.")


class Predictor(BasePredictor):
    def setup(self) -> None:
        """Load both models once when the Replicate worker starts."""
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.depth_processor = AutoImageProcessor.from_pretrained(
            DEPTH_MODEL_ID,
            local_files_only=True,
        )
        self.depth_model = AutoModelForDepthEstimation.from_pretrained(
            DEPTH_MODEL_ID,
            local_files_only=True,
        ).to(self.device).eval()

        # Match the Colab landscape/animal notebook exactly: load params_ema
        # into RRDBNet and call the network directly in proposed_forward().
        checkpoint = torch.load(str(WEIGHTS), map_location="cpu", weights_only=True)
        if not isinstance(checkpoint, dict) or "params_ema" not in checkpoint:
            raise KeyError("Fine-tuned checkpoint must contain params_ema.")

        self.photo_model = RRDBNet(
            num_in_ch=3,
            num_out_ch=3,
            num_feat=64,
            num_block=23,
            num_grow_ch=32,
            scale=4,
        )
        self.photo_model.load_state_dict(checkpoint["params_ema"], strict=True)
        self.photo_model = self.photo_model.to(self.device).eval()
        for parameter in self.photo_model.parameters():
            parameter.requires_grad_(False)

        photo_pipeline.configure_models(
            self.depth_processor,
            self.depth_model,
            self.device,
            self.photo_model,
        )

        base_model = RRDBNet(
            num_in_ch=3,
            num_out_ch=3,
            num_feat=64,
            num_block=23,
            num_grow_ch=32,
            scale=4,
        )
        self.base_upsampler = RealESRGANer(
            scale=4,
            model_path=str(BASE_WEIGHTS),
            model=base_model,
            # Video frames and large anime images can exceed a T4 GPU's memory
            # when processed in one pass. Tiling preserves the same model and
            # parameters while limiting peak VRAM usage.
            tile=256,
            tile_pad=10,
            pre_pad=0,
            half=torch.cuda.is_available(),
        )
        image_pipeline.configure_models(
            self.depth_processor,
            self.depth_model,
            self.device,
            self.base_upsampler,
        )

    def predict(
        self,
        media: Path = Input(description="개선할 이미지 또는 동영상 파일"),
        category: str = Input(description="이미지 카테고리", default="photo", choices=["photo", "anime"]),
        scale: int = Input(
            description="출력 확대 배율",
            default=4,
            choices=[2, 4],
        ),
    ) -> Path:
        """Enhance one image or video and return the final media file."""
        source = SystemPath(str(media))
        extension = detect_extension(source)

        work_dir = SystemPath(tempfile.mkdtemp(prefix="deepup-"))
        input_path = work_dir / f"input{extension}"
        shutil.copyfile(source, input_path)

        # Keep anime unchanged. Photo uses the notebook's direct fine-tuned
        # RRDBNet Proposed forward for both images and video frames.
        if category == "anime":
            selected_pipeline = image_pipeline
            selected_pipeline.configure_models(
                self.depth_processor,
                self.depth_model,
                self.device,
                self.base_upsampler,
            )
        else:
            selected_pipeline = photo_pipeline
            selected_pipeline.configure_models(
                self.depth_processor,
                self.depth_model,
                self.device,
                self.photo_model,
            )

        selected_pipeline.UPSCALE = scale
        selected_pipeline.DOWNSCALE = 8 if category == "anime" else 1
        video_pipeline.image_core = selected_pipeline

        if extension in video_pipeline.VIDEO_EXTENSIONS:
            selected_pipeline.MAKE_LOW_RESOLUTION = False
            result_path = video_pipeline.process_video(str(input_path), str(work_dir))
        else:
            selected_pipeline.MAKE_LOW_RESOLUTION = True
            result_path = selected_pipeline.process_image(str(input_path), str(work_dir))
        return Path(str(result_path))
