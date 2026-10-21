import { policyFor } from '@/lib/entitlements';
import { currentUser, db } from '@/lib/auth';
import { guestCookie, guestCookieName, cookieValue } from '@/lib/jobs';
import { safeFileName } from '@/lib/storage';

const imageTypes = new Set(['image/jpeg', 'image/png', 'image/webp']);
const videoTypes = new Set(['video/mp4', 'video/quicktime']);

export async function POST(request: Request) {
  const user = await currentUser(request);
  const policy = policyFor(user);
  const body = await request.json() as { name?: string; type?: string; size?: number };
  const name = safeFileName(body.name || 'upload.bin');
  const type = body.type || 'application/octet-stream';
  const size = Number(body.size || 0);
  const isImage = imageTypes.has(type), isVideo = videoTypes.has(type);
  if (!isImage && !isVideo) return Response.json({ error: '지원하지 않는 파일 형식입니다.' }, { status: 400 });
  if (isVideo && !policy.allowVideo) return Response.json({ error: '영상 개선은 로그인 후 이용할 수 있습니다.' }, { status: 401 });
  if (size <= 0 || size > policy.maxBytes) return Response.json({ error: `파일은 최대 ${Math.floor(policy.maxBytes / 1024 / 1024)}MB까지 업로드할 수 있습니다.` }, { status: 413 });
  const existingGuest = cookieValue(request, guestCookieName);
  if (!user && existingGuest) {
    const previous = await db().prepare('SELECT id FROM processing_jobs WHERE guest_token = ? LIMIT 1').bind(existingGuest).first();
    if (previous) return Response.json({ error: '비로그인 체험은 이미지 1장만 가능합니다. 로그인하면 계속 이용할 수 있습니다.' }, { status: 403 });
  }
  const guestToken = user ? null : existingGuest || crypto.randomUUID();
  const owner = user ? `users/${user.id}` : `guests/${guestToken}`;
  const objectKey = `${owner}/original/${crypto.randomUUID()}-${name}`;
  const directUrl = `/api/uploads/direct?key=${encodeURIComponent(objectKey)}`;
  return Response.json(
    { uploadUrl: directUrl, objectKey, mediaType: isImage ? 'image' : 'video', uploadMode: 'worker' },
    { headers: guestToken && !existingGuest ? { 'Set-Cookie': guestCookie(guestToken) } : undefined },
  );
}
