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

import pipeline as anime_pipeline  # noqa: E402
import photo_pipeline  # noqa: E402
import video_pipeline  # noqa: E402


ROOT = SystemPath(__file__).resolve().parent
WEIGHTS = ROOT / "weights" / "best_proposed_realesrgan_div2k.pth"
BASE_WEIGHTS = ROOT / "weights" / "RealESRGAN_x4plus.pth"
DEPTH_MODEL_ID = "depth-anything/Depth-Anything-V2-Small-hf"


def detect_extension(source: SystemPath) -> str:
    """Detect media type when Replicate downloads a URL without a suffix."""
    suffix = source.suffix.lower()
    if suffix in anime_pipeline.IMAGE_EXTENSIONS | video_pipeline.VIDEO_EXTENSIONS:
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
        """Load shared depth components and defer category models until needed."""
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.depth_processor = AutoImageProcessor.from_pretrained(
            DEPTH_MODEL_ID,
            local_files_only=True,
        )
        self.depth_model = AutoModelForDepthEstimation.from_pretrained(
            DEPTH_MODEL_ID,
            local_files_only=True,
        ).to(self.device).eval()

        # Replicate does not expose prediction inputs while setup() runs. Loading
        # both large upscalers here made every cold start pay for two categories,
        # even though a request uses only one. Load the selected upscaler lazily
        # in predict() and reuse it for later requests on the same worker.
        self.photo_model = None
        self.base_upsampler = None

    def _ensure_photo_model(self) -> None:
        if self.photo_model is not None:
            return

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

    def _ensure_anime_model(self) -> None:
        if self.base_upsampler is not None:
            return

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
            # A 256px tile splits common HD frames into dozens of pieces and
            # makes short videos take tens of minutes on a T4. FP16 inference
            # fits 512px tiles while cutting the number of tile passes by
            # roughly four times.
            tile=512,
            tile_pad=10,
            pre_pad=0,
            half=torch.cuda.is_available(),
        )
        anime_pipeline.configure_models(
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
            self._ensure_anime_model()
            # Use the original, previously verified anime pipeline verbatim.
            # The photo/animal path remains isolated in photo_pipeline.py.
            selected_pipeline = anime_pipeline
            selected_pipeline.configure_models(
                self.depth_processor,
                self.depth_model,
                self.device,
                self.base_upsampler,
            )
        else:
            self._ensure_photo_model()
            selected_pipeline = photo_pipeline
            selected_pipeline.configure_models(
                self.depth_processor,
                self.depth_model,
                self.device,
                self.photo_model,
            )

        effective_scale = scale
        if extension in video_pipeline.VIDEO_EXTENSIONS:
            # OpenCV's mp4v writer commonly fails before inference when a
            # high-resolution input is enlarged to an 8K-class frame. Keep
            # video output within a broadly supported 4K-sized pixel budget;
            # still images continue to use the requested x2/x4 scale.
            capture = cv2.VideoCapture(str(input_path))
            try:
                input_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                input_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            finally:
                capture.release()
            if input_width <= 0 or input_height <= 0:
                raise ValueError("동영상 해상도를 확인하지 못했습니다.")
            while effective_scale > 1 and (
                input_width * effective_scale > 3840
                or input_height * effective_scale > 2160
                or input_width * input_height * effective_scale**2 > 8_294_400
            ):
                effective_scale //= 2

        selected_pipeline.UPSCALE = effective_scale
        selected_pipeline.DOWNSCALE = 8 if category == "anime" else 1
        video_pipeline.image_core = selected_pipeline

        if extension in video_pipeline.VIDEO_EXTENSIONS:
            selected_pipeline.MAKE_LOW_RESOLUTION = False
            result_path = video_pipeline.process_video(str(input_path), str(work_dir))
        else:
            selected_pipeline.MAKE_LOW_RESOLUTION = True
            result_path = selected_pipeline.process_image(str(input_path), str(work_dir))
            # The original anime pipeline returns (result_path, save_dir).
            if isinstance(result_path, tuple):
                result_path = result_path[0]
        return Path(str(result_path))
