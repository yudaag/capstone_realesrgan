# DeepUp Replicate 모델

`depth_final.ipynb`의 Depth Anything V2 + Real-ESRGAN 이미지·영상 처리 코드를 Replicate용 Cog 모델로 변환한 폴더입니다.

## 사용자가 할 일

### 1. Docker 실행

Mac에서 Docker Desktop을 실행합니다.

### 2. 이 폴더에서 터미널 열기

Finder에서 이 폴더를 연 뒤 폴더를 우클릭하고 `폴더에서 새로운 터미널 열기`를 선택합니다.

### 3. Replicate 로그인

```bash
cog login
```

브라우저가 열리면 Replicate 로그인을 승인합니다.

### 4. 모델 올리기

```bash
cog push r8.im/yudaag/realesrgan_upscailing
```

처음 올릴 때는 PyTorch, 두 AI 모델과 실행 환경을 만들기 때문에 시간이 오래 걸릴 수 있습니다.

### 5. 테스트

업로드가 끝나면 아래 페이지를 새로고침합니다.

```text
https://replicate.com/yudaag/realesrgan_upscailing
```

`놀이터`에서 먼저 작은 JPG 이미지로 시험하고, 성공한 뒤 짧은 MP4를 사용합니다.

## 입력과 출력

- 입력: JPG, JPEG, PNG, WEBP, BMP, TIFF, MP4, MOV, AVI, MKV, WEBM, M4V
- 배율: 2배 또는 4배
- 이미지 출력: PNG
- 영상 출력: 브라우저에서 재생 가능한 H.264 MP4

## 원본 노트북에서 바뀐 점

- Colab 파일 업로드와 Google Drive 코드를 제거했습니다.
- 사용자가 올린 실제 파일은 일부러 저해상도로 만들지 않습니다.
- Depth 모델과 Real-ESRGAN 모델은 서버가 시작될 때 한 번만 로드합니다.
- 이미지와 영상은 확장자로 자동 구분합니다.
- 중간 실험 결과 대신 최종 결과 파일만 반환합니다.
- 영상 결과를 웹 호환 H.264 MP4로 변환합니다.

## 주의사항

- Replicate에서 실제 예측을 실행하면 선택한 GPU의 사용 시간만큼 비용이 발생할 수 있습니다.
- 영상은 프레임마다 두 모델을 실행하므로 이미지보다 오래 걸리고 비용도 커질 수 있습니다.
- 처음에는 작은 이미지와 3초 이내의 짧은 영상으로 확인하세요.
- 문제가 발생하면 Replicate의 실패 화면에 나온 로그를 복사해서 전달해 주세요.
