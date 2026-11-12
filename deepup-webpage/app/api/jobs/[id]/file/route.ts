import { findOwnedJob } from '@/lib/jobs';
import { mediaBucket } from '@/lib/storage';

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const job = await findOwnedJob(request, id);
  if (!job) return new Response('Not found', { status: 404 });
  const kind = new URL(request.url).searchParams.get('kind');
  const key = kind === 'original' ? job.original_r2_key : job.result_r2_key;
  if (!key) return new Response('File not ready', { status: 404 });
  const rangeHeader = request.headers.get('range');
  const object = await mediaBucket().get(
    String(key),
    rangeHeader ? { range: request.headers } : undefined,
  );
  if (!object) return new Response('Not found', { status: 404 });
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('ETag', object.httpEtag);
  headers.set('Cache-Control', 'private, max-age=300');
  headers.set('Accept-Ranges', 'bytes');

  let status = 200;
  if (rangeHeader && object.range && 'offset' in object.range) {
    const start = object.range.offset;
    const length = object.range.length;
    headers.set('Content-Range', `bytes ${start}-${start + length - 1}/${object.size}`);
    headers.set('Content-Length', String(length));
    status = 206;
  } else {
    headers.set('Content-Length', String(object.size));
  }

  return new Response(object.body, { status, headers });
}
