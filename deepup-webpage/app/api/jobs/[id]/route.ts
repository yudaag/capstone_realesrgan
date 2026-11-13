import { db, runtimeEnv } from '@/lib/auth';
import { findOwnedJob } from '@/lib/jobs';
import { mediaBucket } from '@/lib/storage';

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  let job = await findOwnedJob(request, id);
  if (!job) return Response.json({ error: '작업을 찾을 수 없습니다.' }, { status: 404 });
  if ((job.status === 'pending' || job.status === 'processing') && job.replicate_prediction_id) {
    const token = runtimeEnv().REPLICATE_API_TOKEN;
    const response = await fetch(`https://api.replicate.com/v1/predictions/${job.replicate_prediction_id}`, { headers: { Authorization: `Bearer ${token}` } });
    const prediction = await response.json() as { status?: string; output?: string | string[]; error?: string };
    const mapped = prediction.status === 'succeeded' ? 'succeeded' : prediction.status === 'failed' || prediction.status === 'canceled' ? prediction.status : 'processing';
    let resultKey = job.result_r2_key as string | null;
    if (mapped === 'succeeded' && !resultKey) {
      const outputUrl = Array.isArray(prediction.output) ? prediction.output[0] : prediction.output;
      if (outputUrl) {
        const output = await fetch(outputUrl);
        if (output.ok && output.body) {
          const extension = job.media_type === 'video' ? 'mp4' : 'png';
          resultKey = `${job.user_id ? `users/${job.user_id}` : `guests/${job.guest_token}`}/result/${id}.${extension}`;
          await mediaBucket().put(resultKey, output.body, { httpMetadata: { contentType: output.headers.get('content-type') || (job.media_type === 'video' ? 'video/mp4' : 'image/png') } });
        }
      }
    }
    const currentProgress = Number(job.progress || 5);
    const progress = mapped === 'succeeded'
      ? 100
      : mapped === 'processing'
        ? prediction.status === 'starting'
          ? Math.min(30, Math.max(12, currentProgress + 3))
          : Math.min(92, Math.max(35, currentProgress + 4))
        : 0;
    await db().prepare('UPDATE processing_jobs SET status = ?, progress = ?, result_r2_key = COALESCE(?, result_r2_key), error_message = ?, completed_at = CASE WHEN ? IN (\'succeeded\', \'failed\', \'canceled\') THEN CURRENT_TIMESTAMP ELSE completed_at END WHERE id = ?')
      .bind(mapped, progress, resultKey, prediction.error || null, mapped, id).run();
    job = await findOwnedJob(request, id) || job;
  }
  return Response.json({ job });
}

export async function DELETE(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const job = await findOwnedJob(request, id);
  if (!job) return Response.json({ error: '작업을 찾을 수 없습니다.' }, { status: 404 });
  const keys = [job.original_r2_key, job.result_r2_key, job.preview_r2_key].filter(Boolean) as string[];
  if (keys.length) await mediaBucket().delete(keys);
  await db().prepare('DELETE FROM processing_jobs WHERE id = ?').bind(id).run();
  return Response.json({ ok: true });
}
