import { findOwnedJob } from '@/lib/jobs';
import { mediaBucket } from '@/lib/storage';

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const job = await findOwnedJob(request, id);
  if (!job) return new Response('Not found', { status: 404 });
  const kind = new URL(request.url).searchParams.get('kind');
  const key = kind === 'original' ? job.original_r2_key : job.result_r2_key;
  if (!key) return new Response('File not ready', { status: 404 });
  const object = await mediaBucket().get(String(key));
  if (!object) return new Response('Not found', { status: 404 });
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('ETag', object.httpEtag);
  headers.set('Cache-Control', 'private, max-age=300');
  return new Response(object.body, { headers });
}
