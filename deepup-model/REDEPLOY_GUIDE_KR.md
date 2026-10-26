# Replicate 모델 재배포

## 원인

Replicate가 웹 URL의 파일을 임시 파일로 내려받을 때 확장자가 없는 이름으로 저장할 수 있습니다. 기존 `predict.py`는 임시 파일 이름의 확장자만 확인하여 정상 PNG/JPG도 거부했습니다.

수정 버전은 파일 이름에 확장자가 없어도 이미지 내용을 Pillow로 확인하고, 동영상은 `ffprobe`로 확인합니다.

## GitHub에 반영

이 폴더의 `predict.py`를 저장소의 `deepup-model/predict.py`로 교체합니다. 안전하게 전체 `deepup-model` 폴더를 이 폴더 내용으로 교체해도 됩니다.

```bash
cd /Users/han-yujeong/Desktop/capstone_realesrgan
git add deepup-model
git commit -m "Detect extensionless Replicate input files"
git push origin main
```

## Replicate 새 버전 만들기

GitHub Actions의 **Push model to Replicate**를 다시 실행하거나, 로컬에서 다음을 실행합니다.

```bash
cd /Users/han-yujeong/Desktop/capstone_realesrgan/deepup-model
cog push r8.im/yudaag/realesrgan_upscaling
```

완료되면 Replicate 모델 페이지에 새로운 Version ID가 생성됩니다.

## Cloudflare Version ID 교체

새로운 Replicate Version ID를 복사한 뒤 실행합니다.

```bash
cd /Users/han-yujeong/Desktop/capstone_realesrgan/deepup-webpage
npx wrangler secret put REPLICATE_VERSION --name capstone-realesrgan
```

프롬프트에 새 Version ID만 붙여넣습니다. URL이나 `owner/model` 이름을 넣지 않습니다.

이후 웹페이지를 새로고침하고 다시 테스트합니다.
