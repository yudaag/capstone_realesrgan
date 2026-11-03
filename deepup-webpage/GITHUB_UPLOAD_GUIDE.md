# DeepUp GitHub·Cloudflare 배포 안내

## 구현된 기능

- 클릭 및 드래그 앤 드롭 파일 선택
- 비로그인: 이미지 1장, 10MB, 2배 개선, 영상 차단
- 로그인: 이미지·영상, 최대 500MB, 4배 개선
- 브라우저에서 R2로 직접 업로드
- Replicate prediction 생성 및 상태 조회
- 완료 결과를 Replicate 임시 URL에서 R2로 복사
- 원본·결과 비교, 결과 다운로드
- 회원 마이페이지 통계·검색·필터·정렬
- 작업 삭제 시 D1 기록과 R2 파일 동시 삭제
- 로그인 회원의 실패 작업 재시도

## GitHub 업로드

이 폴더의 내용 전체를 저장소의 `deepup-webpage/` 폴더에 덮어씁니다. `node_modules`, `dist`, `.vinext`, `.dev.vars`, `.env`는 올리지 않습니다.

## 1. Cloudflare 리소스

기존 D1 `deepup-db`를 사용합니다. `wrangler.jsonc`의 `database_id`를 실제 값으로 바꿉니다.

R2에서 비공개 버킷 `deepup-media`를 생성합니다. `wrangler.jsonc`에는 `MEDIA`라는 이름으로 연결되어 있습니다. R2 API Tokens에서 해당 버킷에 대한 Object Read & Write 토큰을 만들고 Access Key ID, Secret Access Key, Account ID를 보관합니다.

R2 버킷 Settings → CORS Policy에 아래 내용을 넣습니다. 주소는 실제 Workers 주소로 교체합니다.

```json
[
  {
    "AllowedOrigins": ["https://본인-사이트.workers.dev"],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["Content-Type"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

비로그인 파일 자동 정리를 위해 R2 Object lifecycle rule에서 `guests/` prefix를 1일 후 삭제하도록 설정하는 것을 권장합니다.

## 2. DB 마이그레이션

```bash
cd deepup-webpage
npm install
npm run db:migrate:remote
```

`0001_auth.sql`과 `0002_processing_jobs.sql`이 적용됩니다.

## 3. Cloudflare 비밀변수

Cloudflare Worker → Settings → Variables and Secrets에서 아래 값을 Secret으로 추가합니다.

```text
REPLICATE_API_TOKEN     Replicate의 r8_ 토큰
REPLICATE_VERSION       Replicate 모델 Versions의 버전 ID
R2_ACCOUNT_ID           Cloudflare Account ID
R2_BUCKET_NAME          deepup-media
R2_ACCESS_KEY_ID        R2 API Access Key ID
R2_SECRET_ACCESS_KEY    R2 API Secret Access Key
```

실제 키를 GitHub 코드나 `.dev.vars.example`에 적지 마세요.

## 4. Cloudflare Git 빌드 설정

```text
Root directory: deepup-webpage
Build command: npm run build
Deploy command: npx wrangler deploy --config dist/server/wrangler.json
```

## 5. Replicate 입력 규격

웹은 Replicate 모델에 `media`와 `scale`을 보냅니다. 제공된 Cog `predict.py` 입력과 일치합니다. 비로그인 체험은 `scale: 2`, 회원은 `scale: 4`입니다.

## 6. 배포 후 확인 순서

1. 비로그인 JPG 한 장 업로드
2. 두 번째 비로그인 업로드 차단 확인
3. 회원가입·로그인
4. 이미지 업로드 및 결과 비교·다운로드
5. 마이페이지 이력 확인
6. 삭제 후 목록과 R2 파일 제거 확인
7. 짧은 MP4 처리 확인

500MB 영상은 업로드할 수 있지만 GPU 처리 시간과 Replicate 비용이 매우 커질 수 있으므로 처음에는 10초 이내의 작은 MP4로 시험하세요.
