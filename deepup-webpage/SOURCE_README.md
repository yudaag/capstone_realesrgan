# DeepUp — Cloudflare 독립 배포판

ChatGPT Sites와 분리해 GitHub + Cloudflare Workers + Cloudflare D1로 배포할 수 있도록 변환한 소스입니다.

## 이 배포판에서 변경된 점

- `@openai/sites-vite-plugin` 제거
- `.openai/hosting.json` 및 ChatGPT Sites 프로젝트 ID 제거
- 일반 Cloudflare Workers용 `wrangler.jsonc` 추가
- 별도 D1 데이터베이스 `deepup-db` 사용
- `1234 / 1234` 관리자 자동 생성 코드 제거
- Cloudflare 비밀 환경변수로 관리자를 한 번만 생성하는 초기화 API 추가

기존 ChatGPT Sites의 회원 데이터는 이 프로젝트로 자동 복사되지 않습니다. 새 D1 데이터베이스에서 회원가입을 다시 받는 독립 환경입니다.

## 필요한 환경

- Node.js 22.13 이상
- npm
- GitHub 계정
- Cloudflare 계정

## 1. 설치 및 Cloudflare 로그인

```bash
npm install
npx wrangler login
```

## 2. 새로운 D1 데이터베이스 생성

```bash
npx wrangler d1 create deepup-db
```

출력 결과에 표시되는 `database_id`를 복사한 뒤 `wrangler.jsonc`의 아래 값을 교체합니다.

```json
"database_id": "00000000-0000-4000-8000-000000000000"
```

이 ID는 새 Cloudflare 계정에서 직접 발급받아야 하므로 배포 전 사용자가 한 번 입력해야 합니다.

## 3. 회원 데이터베이스 테이블 생성

```bash
npm run db:migrate:remote
```

로컬 개발용 테이블은 다음 명령으로 생성합니다.

```bash
npm run db:migrate:local
```

## 4. 로컬 실행

`.dev.vars.example`을 복사해 `.dev.vars`를 만들고 세 값을 본인 값으로 바꿉니다.

```env
ADMIN_USERNAME=본인만_아는_관리자_아이디
ADMIN_PASSWORD=12자_이상의_강한_비밀번호
ADMIN_SETUP_TOKEN=길고_무작위인_초기화_토큰
```

`.dev.vars`는 `.gitignore`에 포함되어 있으므로 GitHub에 올라가지 않습니다.

```bash
npm run dev
```

브라우저에서 `http://localhost:3000`을 엽니다.

## 5. Cloudflare 비밀값 등록

관리자 아이디, 비밀번호 및 초기화 토큰을 코드나 GitHub에 저장하지 말고 다음 명령으로 Cloudflare에 등록합니다.

```bash
npx wrangler secret put ADMIN_USERNAME
npx wrangler secret put ADMIN_PASSWORD
npx wrangler secret put ADMIN_SETUP_TOKEN
```

각 명령을 실행하면 값을 입력하라는 안내가 표시됩니다. 관리자 비밀번호는 최소 12자로 설정합니다.

## 6. 배포

```bash
npm run deploy
```

배포 완료 후 표시되는 `https://deepup-web.<계정>.workers.dev` 주소를 확인합니다.

## 7. 관리자 계정 최초 1회 생성

아래 명령의 사이트 주소와 토큰을 본인의 값으로 교체해 한 번만 실행합니다.

```bash
curl -X POST "https://deepup-web.<계정>.workers.dev/api/admin/bootstrap" \
  -H "x-admin-setup-token: 본인의_ADMIN_SETUP_TOKEN"
```

`관리자 계정을 생성했습니다.`가 표시되면 성공입니다. 이후 보안을 위해 초기화 토큰을 삭제합니다.

```bash
npx wrangler secret delete ADMIN_SETUP_TOKEN
```

관리자 계정은 이미 D1에 안전한 해시로 저장되므로 초기화가 끝난 뒤 세 비밀값을 모두 삭제해도 로그인할 수 있습니다. 일반 회원가입으로는 관리자 권한을 획득할 수 없습니다.

```bash
npx wrangler secret delete ADMIN_USERNAME
npx wrangler secret delete ADMIN_PASSWORD
```

## 8. GitHub 자동 배포

1. 이 폴더를 GitHub 비공개 저장소에 올립니다.
2. Cloudflare 대시보드에서 `Workers & Pages → Create → Import a repository`를 선택합니다.
3. GitHub의 저장소를 선택합니다.
4. 빌드 명령은 `npm run build`로 설정합니다.
5. 배포 명령은 `npx wrangler deploy --config dist/server/wrangler.json`으로 설정합니다.
6. 최초 관리자 생성이 필요한 경우에만 세 관리자 비밀값을 잠시 등록합니다.

세 관리자 비밀값은 새 관리자를 처음 만들 때만 잠시 등록하고, 생성 후 삭제합니다.

## 주요 파일

- `wrangler.jsonc`: Cloudflare Worker와 새 D1 연결 설정
- `migrations/0001_auth.sql`: 회원 및 로그인 세션 테이블
- `lib/auth.ts`: 비밀번호 해시, 세션, 관리자 초기화
- `app/api/admin/bootstrap/route.ts`: 보호된 최초 관리자 생성 API
- `app/api/auth/*`: 회원가입, 로그인, 로그아웃, 프로필 API
- `public/`: 사이트 이미지와 발표 영상

## 보안 메모

- `.dev.vars`, API 키, 관리자 비밀번호를 GitHub에 올리지 마세요.
- 기존 `1234 / 1234` 계정은 완전히 제거되었습니다.
- 관리자 생성 API는 유효한 초기화 토큰이 없으면 실행되지 않습니다.
- 관리자 생성 후 `ADMIN_SETUP_TOKEN`을 Cloudflare에서 삭제하세요.
- 실제 공개 운영 전에는 로그인 요청 제한, 비밀번호 재설정, 이메일 인증을 추가하는 것이 좋습니다.
