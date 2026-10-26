# DeepUp 카테고리 선택 모델 코드

노트북에서 보았던 `OURS` 결과와 같은 Depth + Structure 후처리를 웹 추론에도 적용합니다.

`category=photo`는 파인튜닝 모델 + Depth/Structure 파이프라인을 사용합니다.
`category=anime`는 `depth_final.ipynb`처럼 원본 `RealESRGAN_x4plus` +
Depth/Structure 파이프라인을 사용합니다.

## 변경 사항

- Depth Anything V2 적용
- 깊이 기반 블러와 구조 보호 합성 적용
- 파인튜닝된 RRDBNet 가중치는 그대로 사용
- 확장자 없는 Replicate 입력 파일도 내용으로 판별
- 이미지와 동영상 입력 지원
- 동영상은 H.264 MP4로 반환

노트북의 `OURS` 처리 경로를 그대로 사용하기 때문에 단순 Real-ESRGAN보다
실행 시간이 더 필요합니다.

## GitHub 반영

저장소의 기존 `deepup-model` 폴더를 백업한 뒤 이 폴더의 내용으로
교체합니다. 그다음 커밋하고 GitHub Actions의 `Push model to Replicate`를
실행합니다.

새 Replicate 버전 생성 후 Cloudflare의 `REPLICATE_VERSION`을 새 Version
ID로 교체하고 Worker를 다시 배포해야 합니다.

## 참고

포함된 노트북은 학습 재현용이며 Replicate 실행에는 사용되지 않습니다.
실제 실행 파일은 `predict.py`, `cog.yaml`, `requirements.txt`입니다.
