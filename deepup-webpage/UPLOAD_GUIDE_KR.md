# GitHub 및 Cloudflare 배포 순서

## 1. GitHub 파일 교체

GitHub 저장소 `yudaag/capstone_realesrgan` 안의 기존 `deepup-webpage` 폴더를 이 폴더의 내용으로 교체합니다.

이 폴더 자체를 중첩해서 올리지 말고 다음 구조가 되게 합니다.

```text
capstone_realesrgan/
  deepup-webpage/
    app/
    components/
    lib/
    package.json
    wrangler.jsonc
```

## 2. Git으로 올리기

```bash
cd /Users/han-yujeong/Desktop/capstone_realesrgan
git add deepup-webpage
git commit -m "Fix image upload content type"
git push origin main
```

## 3. Cloudflare 설정 확인

- 프로젝트: `capstone-realesrgan`
- Production branch: `main`
- Root directory: `deepup-webpage`
- Build command: `npm run build`
- Deploy command: `npx wrangler deploy --config dist/server/wrangler.json`

## 4. Cloudflare 배포

GitHub push 후 Cloudflare의 **Workers & Pages → capstone-realesrgan → Deployments**로 이동합니다.
최신 커밋의 빌드가 `Success`인지 확인합니다. 실패하면 실패한 빌드 로그를 확인하고 `Retry deployment`를 누릅니다.

## 5. 적용 확인

아래 주소가 JSON을 반환해야 합니다.

```text
https://capstone-realesrgan.yjhan1409.workers.dev/api/health
```

그 다음 브라우저에서 `Cmd + Shift + R`을 눌러 캐시를 지우고 JPG 또는 PNG 파일을 다시 선택합니다.

이번 버전은 브라우저가 파일 형식을 빈 값이나 `image/x-png`로 보내도 `.jpg`, `.jpeg`, `.png`, `.webp` 확장자를 우선 사용합니다.
