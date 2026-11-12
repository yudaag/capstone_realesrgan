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

import photo_video_pipeline  # noqa: E402
import pipeline  # noqa: E402
import proposed_pipeline  # noqa: E402


ROOT = SystemPath(__file__).resolve().parent
WEIGHTS = ROOT / "weights" / "best_proposed_realesrgan_div2k.pth"
BASE_WEIGHTS = ROOT / "weights" / "RealESRGAN_x4plus.pth"
DEPTH_MODEL_ID = "depth-anything/Depth-Anything-V2-Small-hf"


def detect_extension(source: SystemPath) -> str:
    """Detect media type when Replicate downloads a URL without a suffix."""
    suffix = source.suffix.lower()
    if suffix in pipeline.IMAGE_EXTENSIONS | photo_video_pipeline.VIDEO_EXTENSIONS:
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
        if capture.isOpened() and capture.read()[0]:
            return ".mp4"
    finally:
        capture.release()
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

        # photo (landscape/animal): fine-tuned RRDBNet run directly with the
        # training-time Proposed forward (depth_풍경_동물_파이프라인.ipynb).
        checkpoint = torch.load(str(WEIGHTS), map_location="cpu", weights_only=True)
        if not isinstance(checkpoint, dict) or "params_ema" not in checkpoint:
            raise KeyError("Best Proposed checkpoint must contain 'params_ema'.")
        self.proposed_model = RRDBNet(
            num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4,
        )
        self.proposed_model.load_state_dict(checkpoint["params_ema"], strict=True)
        self.proposed_model = self.proposed_model.to(self.device).eval()
        for parameter in self.proposed_model.parameters():
            parameter.requires_grad_(False)
        proposed_pipeline.configure_models(
            self.depth_processor, self.depth_model, self.proposed_model, self.device,
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
        media: Path = Input(description="개선할 이미지 또는 동영상 파일"),
        category: str = Input(description="이미지 카테고리", default="photo", choices=["photo", "anime"]),
        scale: int = Input(
            description="출력 확대 배율",
            default=4,
            choices=[2, 4],
        ),
    ) -> Path:
        """Enhance one image (or a photo-category video) and return the result."""
        source = SystemPath(str(media))
        extension = detect_extension(source)

        work_dir = SystemPath(tempfile.mkdtemp(prefix="deepup-"))
        input_path = work_dir / f"input{extension}"
        shutil.copyfile(source, input_path)

        if category == "photo":
            # Uploads are used as-is (no synthetic 1/4 bicubic degradation)
            # and restored x4 by the fine-tuned Proposed forward.
            if extension in photo_video_pipeline.VIDEO_EXTENSIONS:
                return Path(photo_video_pipeline.process_video(str(input_path), str(work_dir)))
            frame = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError("이미지 파일을 읽을 수 없습니다.")
            output, lr = proposed_pipeline.enhance_image(frame)
            if scale != proposed_pipeline.SCALE:
                output = cv2.resize(
                    output, (lr.shape[1] * scale, lr.shape[0] * scale), interpolation=cv2.INTER_AREA,
                )
            result_path = work_dir / "deepup_result.png"
            if not cv2.imwrite(str(result_path), output):
                raise RuntimeError("결과 이미지를 저장하지 못했습니다.")
            return Path(str(result_path))

        if extension in photo_video_pipeline.VIDEO_EXTENSIONS:
            raise ValueError("애니 카테고리는 현재 이미지만 지원합니다.")

        # anime: unchanged (bb04ec76) — RealESRGAN_x4plus + depth/structure pipeline
        selected_upsampler = self.base_upsampler if category == "anime" else self.upsampler
        pipeline.configure_models(
            self.depth_processor,
            self.depth_model,
            self.device,
            selected_upsampler,
        )

        pipeline.UPSCALE = scale
        pipeline.MAKE_LOW_RESOLUTION = category == "anime"
        pipeline.DOWNSCALE = 8

        result_path, _ = pipeline.process_media(str(input_path), str(work_dir))
        return Path(str(result_path))
