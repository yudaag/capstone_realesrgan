import { db } from '@/lib/auth';
import { findOwnedJob, startPrediction } from '@/lib/jobs';

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const job = await findOwnedJob(request, id);
  if (!job || !job.user_id || job.status !== 'failed') return Response.json({ error: '로그인 회원의 실패한 작업만 다시 시도할 수 있습니다.' }, { status: 409 });
  const category = job.category === 'anime' ? 'anime' : 'photo';
  const prediction = await startPrediction(String(job.original_r2_key), job.user_id ? 4 : 2, new URL(request.url).origin, category);
  await db().prepare("UPDATE processing_jobs SET status = 'processing', progress = 5, error_message = NULL, replicate_prediction_id = ? WHERE id = ?").bind(prediction.id, id).run();
  return Response.json({ ok: true });
}
