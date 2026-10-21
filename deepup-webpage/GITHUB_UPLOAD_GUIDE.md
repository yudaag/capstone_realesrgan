# GitHub 업로드 안내

이 폴더의 내용 전체를 저장소의 `deepup-webpage/` 폴더에 올립니다.

## 포함된 변경 사항

- 비로그인/회원 이용권한 정책 (`lib/entitlements.ts`)
- 프로필 메뉴의 마이페이지 링크
- 첨부 시안을 반영한 `/mypage` 화면
- 회원별 작업 목록 조회 API
- 실패 작업 재시도 API
- 작업 삭제 API
- 처리 이력용 D1 마이그레이션

## GitHub에 올리지 않는 파일

- `node_modules/`
- `dist/`
- `.vinext/`
- `.dev.vars`
- `.env*`
- Replicate 및 Cloudflare 비밀키

위 파일들은 `.gitignore`에 의해 제외됩니다.

## GitHub에 올린 후 필수 작업

Cloudflare 빌드의 Root directory가 `deepup-webpage`인지 확인합니다.

새 작업 이력 테이블을 운영 D1에 적용합니다.

```bash
cd deepup-webpage
npm install
npm run db:migrate:remote
```

그다음 GitHub의 `main` 브랜치에 푸시하면 Cloudflare 자동 배포가 실행됩니다.

## 아직 연결이 필요한 부분

현재 추가된 코드는 마이페이지 UI, 권한 정책, 작업 이력 조회·삭제·재시도 기반입니다. 다음 기능은 Replicate 모델 버전과 사용자 업로드용 R2 버킷 정보가 확정된 후 연결해야 합니다.

- 이미지·영상 실제 업로드
- Replicate prediction 생성 및 상태 동기화
- 처리 결과를 사용자 R2 버킷에 저장
- 결과 비교 화면
- 실제 다운로드 및 워터마크 생성
- 500MB 파일용 R2 직접 업로드 URL

비밀키는 코드에 적지 말고 Cloudflare의 Variables and Secrets에 등록합니다.
