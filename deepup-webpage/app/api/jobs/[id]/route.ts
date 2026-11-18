import { db, runtimeEnv } from '@/lib/auth';
import { findOwnedJob } from '@/lib/jobs';
import { mediaBucket } from '@/lib/storage';

function predictionProgress(logs: string | undefined, mediaType: string, status: string) {
  if (status === 'succeeded') return { progress: 100, exact: true, stage: '화질 개선이 완료되었습니다.' };
  if (status === 'starting') return { progress: 0, exact: false, stage: 'GPU 할당 및 모델 준비 중' };

  if (mediaType === 'video' && logs) {
    const matches = [...logs.matchAll(/DEEPUP_PROGRESS\s+(\d+)\/(\d+)/g)];
    const last = matches.at(-1);
    if (/DEEPUP_STAGE encoding/.test(logs)) {
      return { progress: 0, exact: false, stage: '처리된 프레임으로 결과 영상 생성 중' };
    }
    if (last) {
      const processed = Number(last[1]);
      const total = Number(last[2]);
      if (total > 0) {
        return {
          progress: Math.min(100, Math.round(processed * 100 / total)),
          exact: true,
          stage: `영상 프레임 처리 중 (${processed}/${total})`,
        };
      }
    }
  }

  return {
    progress: 0,
    exact: false,
    stage: mediaType === 'video' ? '영상 분석 및 모델 초기화 중' : '이미지 분석 및 화질 개선 중',
  };
}

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  let job = await findOwnedJob(request, id);
  if (!job) return Response.json({ error: '작업을 찾을 수 없습니다.' }, { status: 404 });
  if ((job.status === 'pending' || job.status === 'processing') && job.replicate_prediction_id) {
    const token = runtimeEnv().REPLICATE_API_TOKEN;
    const response = await fetch(`https://api.replicate.com/v1/predictions/${job.replicate_prediction_id}`, { headers: { Authorization: `Bearer ${token}` } });
    const prediction = await response.json() as { status?: string; output?: string | string[]; error?: string; logs?: string };
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
    const progressInfo = predictionProgress(prediction.logs, String(job.media_type), String(prediction.status || ''));
    const progress = mapped === 'failed' || mapped === 'canceled' ? 0 : progressInfo.progress;
    await db().prepare('UPDATE processing_jobs SET status = ?, progress = ?, result_r2_key = COALESCE(?, result_r2_key), error_message = ?, completed_at = CASE WHEN ? IN (\'succeeded\', \'failed\', \'canceled\') THEN CURRENT_TIMESTAMP ELSE completed_at END WHERE id = ?')
      .bind(mapped, progress, resultKey, prediction.error || null, mapped, id).run();
    job = await findOwnedJob(request, id) || job;
    return Response.json({
      job: {
        ...job,
        progress_exact: mapped !== 'failed' && mapped !== 'canceled' && progressInfo.exact,
        progress_stage: mapped === 'failed' || mapped === 'canceled'
          ? prediction.error || '처리에 실패했습니다.'
          : progressInfo.stage,
      },
    });
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
