"""Fast Replicate inference for the fine-tuned DeepUp Real-ESRGAN model.

This intentionally returns the RRDBNet result directly.  The previous runtime
also ran Depth Anything and blurred parts of the enhanced image, which made
predictions slower and could distort subjects when the depth estimate was
wrong.
"""

import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path as SystemPath

import cv2
import torch
import torchvision.transforms.functional as TF
from cog import BasePredictor, Input, Path
from PIL import Image


# BasicSR imports this module, which was removed from recent torchvision.
functional_tensor = types.ModuleType("torchvision.transforms.functional_tensor")
functional_tensor.rgb_to_grayscale = TF.rgb_to_grayscale
sys.modules["torchvision.transforms.functional_tensor"] = functional_tensor

from basicsr.archs.rrdbnet_arch import RRDBNet  # noqa: E402
from realesrgan import RealESRGANer  # noqa: E402


ROOT = SystemPath(__file__).resolve().parent
WEIGHTS = ROOT / "weights" / "best_proposed_realesrgan_div2k.pth"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def detect_extension(source: SystemPath) -> str:
    """Detect content even when Replicate gives the downloaded file no suffix."""
    suffix = source.suffix.lower()
    if suffix in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
        return suffix

    try:
        with Image.open(source) as image:
            image_format = (image.format or "").upper()
        image_extensions = {
            "JPEG": ".jpg",
            "PNG": ".png",
            "WEBP": ".webp",
            "BMP": ".bmp",
            "TIFF": ".tiff",
        }
        if image_format in image_extensions:
            return image_extensions[image_format]
    except Exception:
        pass

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=format_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    formats = {item.strip().lower() for item in probe.stdout.split(",") if item.strip()}
    if formats & {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}:
        return ".mp4"
    if "webm" in formats:
        return ".webm"
    if "matroska" in formats:
        return ".mkv"
    if "avi" in formats:
        return ".avi"
    raise ValueError("지원하지 않는 파일 형식입니다. 이미지 또는 동영상 내용을 확인할 수 없습니다.")


class Predictor(BasePredictor):
    def setup(self) -> None:
        """Load only the fine-tuned Real-ESRGAN model once per GPU worker."""
        if not WEIGHTS.is_file():
            raise FileNotFoundError(f"가중치 파일이 없습니다: {WEIGHTS}")

        model = RRDBNet(
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
            model=model,
            tile=256,
            tile_pad=10,
            pre_pad=0,
            half=torch.cuda.is_available(),
        )

    def enhance_frame(self, frame, scale: int):
        enhanced, _ = self.upsampler.enhance(frame, outscale=scale)
        return enhanced

    def enhance_image(self, source: SystemPath, work_dir: SystemPath, scale: int) -> Path:
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("이미지를 읽을 수 없습니다.")
        result = self.enhance_frame(image, scale)
        output = work_dir / "deepup_result.png"
        if not cv2.imwrite(str(output), result):
            raise RuntimeError("결과 이미지를 저장하지 못했습니다.")
        return Path(str(output))

    def enhance_video(self, source: SystemPath, work_dir: SystemPath, scale: int) -> Path:
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise ValueError("동영상을 읽을 수 없습니다.")

        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) * scale
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) * scale
        frame_output = work_dir / "frames.mp4"
        writer = cv2.VideoWriter(
            str(frame_output),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            capture.release()
            raise RuntimeError("동영상 결과 파일을 만들 수 없습니다.")

        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                writer.write(self.enhance_frame(frame, scale))
        finally:
            capture.release()
            writer.release()

        output = work_dir / "deepup_result.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(frame_output),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(output),
            ],
            check=True,
        )
        return Path(str(output))

    def predict(
        self,
        media: Path = Input(description="개선할 이미지 또는 동영상 파일"),
        scale: int = Input(description="출력 확대 배율", default=4, choices=[2, 4]),
    ) -> Path:
        source = SystemPath(str(media))
        extension = detect_extension(source)
        work_dir = SystemPath(tempfile.mkdtemp(prefix="deepup-"))
        local_input = work_dir / f"input{extension}"
        shutil.copyfile(source, local_input)

        if extension in IMAGE_EXTENSIONS:
            return self.enhance_image(local_input, work_dir, scale)
        return self.enhance_video(local_input, work_dir, scale)
