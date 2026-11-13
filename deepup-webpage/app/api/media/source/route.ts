import { runtimeEnv } from '@/lib/auth';
import { sourceSignature } from '@/lib/jobs';

function constantTimeEqual(left: string, right: string) {
  if (left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index++) difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  return difference === 0;
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const key = url.searchParams.get('key') || '';
  const expires = url.searchParams.get('expires') || '';
  const signature = url.searchParams.get('sig') || '';
  if (!key || !expires || !signature || Number(expires) < Math.floor(Date.now() / 1000)) {
    return Response.json({ error: '파일 접근 주소가 만료되었거나 올바르지 않습니다.' }, { status: 403 });
  }
  const expected = await sourceSignature(key, expires);
  if (!constantTimeEqual(signature, expected)) return Response.json({ error: '파일 접근 권한이 없습니다.' }, { status: 403 });
  const object = await runtimeEnv().MEDIA.get(key);
  if (!object) return Response.json({ error: '원본 파일을 찾을 수 없습니다.' }, { status: 404 });
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('etag', object.httpEtag);
  // Replicate downloads large inputs with a streaming HTTP client. Without an
  // explicit length the Worker response is chunked, and large MOV files can be
  // interpreted as a broken/incomplete read after the first 16 KiB chunk.
  headers.set('content-length', String(object.size));
  headers.set('accept-ranges', 'bytes');
  headers.set('cache-control', 'private, max-age=300');
  return new Response(object.body, { headers });
}
