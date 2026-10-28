

"""Replicate/Cog entry point for the DeepUp capstone model."""

import os
import shutil
import sys
import tempfile
import types
from pathlib import Path as SystemPath

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

import pipeline  # noqa: E402


ROOT = SystemPath(__file__).resolve().parent
WEIGHTS = ROOT / "weights" / "best_proposed_realesrgan_div2k.pth"
BASE_WEIGHTS = ROOT / "weights" / "RealESRGAN_x4plus.pth"
DEPTH_MODEL_ID = "depth-anything/Depth-Anything-V2-Small-hf"


def detect_extension(source: SystemPath) -> str:
    """Detect image content when Replicate downloads a URL without a suffix."""
    suffix = source.suffix.lower()
    if suffix in pipeline.IMAGE_EXTENSIONS:
        return suffix
    try:
        with Image.open(source) as image:
            image_format = (image.format or "").upper()
        mapped = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "BMP": ".bmp", "TIFF": ".tiff"}
        if image_format in mapped:
            return mapped[image_format]
    except Exception:
        pass
    raise ValueError("지원하지 않는 파일 형식입니다. 이미지 파일을 선택해 주세요.")


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

        rrdbnet = RRDBNet(
            num_in_ch=3,
            num_out_ch=3,
            num_feat=64,
            num_block=23,
            num_grow_ch=32,
            scale=4,
        )
        self.upsampler = RealESRGANer(
            scale=4,
            model_path=str(WEIGHTS),
            model=rrdbnet,
            tile=0,
            tile_pad=10,
            pre_pad=0,
            half=torch.cuda.is_available(),
        )

        pipeline.configure_models(
            self.depth_processor,
            self.depth_model,
            self.device,
            self.upsampler,
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
            tile=0,
            tile_pad=10,
            pre_pad=0,
            half=torch.cuda.is_available(),
        )

    def predict(
        self,
        media: Path = Input(description="개선할 이미지 파일"),
        category: str = Input(description="이미지 카테고리", default="photo", choices=["photo", "anime"]),
        scale: int = Input(
            description="출력 확대 배율",
            default=4,
            choices=[2, 4],
        ),
        downscale: int = Input(
            description="Real-ESRGAN 전에 입력을 먼저 줄이는 배율 (코랩 노트북과 동일하게 8). 1이면 줄이지 않음",
            default=8,
            choices=[1, 2, 4, 8],
        ),
    ) -> Path:
        """Enhance one image and return the final PNG file."""
        source = SystemPath(str(media))
        extension = detect_extension(source)

        work_dir = SystemPath(tempfile.mkdtemp(prefix="deepup-"))
        input_path = work_dir / f"input{extension}"
        shutil.copyfile(source, input_path)

        # photo: fine-tuned RRDBNet + notebook's Depth/Structure pipeline
        # anime: depth_final.ipynb's original RealESRGAN_x4plus + same pipeline
        selected_upsampler = self.base_upsampler if category == "anime" else self.upsampler
        pipeline.configure_models(
            self.depth_processor,
            self.depth_model,
            self.device,
            selected_upsampler,
        )

        pipeline.UPSCALE = scale
        pipeline.MAKE_LOW_RESOLUTION = downscale > 1
        pipeline.DOWNSCALE = downscale

        result_path, _ = pipeline.process_media(str(input_path), str(work_dir))
        return Path(str(result_path))
