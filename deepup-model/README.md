# DeepUp 빠른·안정화 모델 코드

파인튜닝된 `best_proposed_realesrgan_div2k.pth`를 사용하되, 웹 추론에서는
Real-ESRGAN 결과를 바로 반환합니다.

## 변경 사항

- Depth Anything 모델 제거
- 깊이 기반 Gaussian Blur 및 구조 합성 제거
- 파인튜닝된 RRDBNet 가중치는 그대로 사용
- 확장자 없는 Replicate 입력 파일도 내용으로 판별
- 이미지와 동영상 입력 지원
- 동영상은 H.264 MP4로 반환

이 버전은 기존 버전보다 GPU 시작 시간이 짧고, 잘못된 깊이 추정 때문에
이미지가 다시 흐려지는 문제를 피합니다.

## GitHub 반영

저장소의 기존 `deepup-model` 폴더를 백업한 뒤 이 폴더의 내용으로
교체합니다. 그다음 커밋하고 GitHub Actions의 `Push model to Replicate`를
실행합니다.

새 Replicate 버전 생성 후 Cloudflare의 `REPLICATE_VERSION`을 새 Version
ID로 교체하고 Worker를 다시 배포해야 합니다.

## 참고

포함된 노트북은 학습 재현용이며 Replicate 실행에는 사용되지 않습니다.
실제 실행 파일은 `predict.py`, `cog.yaml`, `requirements.txt`입니다.
