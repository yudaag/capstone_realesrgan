import { findOwnedJob } from '@/lib/jobs';
import { mediaBucket, safeFileName } from '@/lib/storage';

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const job = await findOwnedJob(request, id);
  if (!job || !job.result_r2_key) return new Response('Result not found', { status: 404 });
  const object = await mediaBucket().get(String(job.result_r2_key));
  if (!object) return new Response('Result not found', { status: 404 });
  const original = safeFileName(String(job.original_name || 'result'));
  const base = original.replace(/\.[^.]+$/, '');
  const extension = job.media_type === 'video' ? 'mp4' : 'png';
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('Content-Disposition', `attachment; filename="${base}-deepup.${extension}"`);
  return new Response(object.body, { headers });
}
