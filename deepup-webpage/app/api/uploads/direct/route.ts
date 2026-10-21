import { currentUser, runtimeEnv } from '@/lib/auth';
import { policyFor } from '@/lib/entitlements';
import { cookieValue, guestCookieName } from '@/lib/jobs';

const allowedTypes = new Set(['image/jpeg', 'image/png', 'image/webp', 'video/mp4', 'video/quicktime']);

export async function PUT(request: Request) {
  const user = await currentUser(request);
  const guestToken = cookieValue(request, guestCookieName);
  const key = new URL(request.url).searchParams.get('key') || '';
  const expectedPrefix = user ? `users/${user.id}/original/` : guestToken ? `guests/${guestToken}/original/` : '';
  if (!expectedPrefix || !key.startsWith(expectedPrefix)) {
    return Response.json({ error: '업로드 권한을 확인할 수 없습니다.' }, { status: 403 });
  }

  const type = request.headers.get('content-type') || 'application/octet-stream';
  if (!allowedTypes.has(type)) return Response.json({ error: '지원하지 않는 파일 형식입니다.' }, { status: 400 });
  if (!user && type.startsWith('video/')) return Response.json({ error: '영상 개선은 로그인 후 이용할 수 있습니다.' }, { status: 401 });

  const length = Number(request.headers.get('content-length') || 0);
  const policy = policyFor(user);
  if (length > policy.maxBytes) return Response.json({ error: '파일 용량 제한을 초과했습니다.' }, { status: 413 });

  if (!request.body) return Response.json({ error: '업로드 파일이 없습니다.' }, { status: 400 });
  await runtimeEnv().MEDIA.put(key, request.body, { httpMetadata: { contentType: type } });
  return Response.json({ ok: true });
}
