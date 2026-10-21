import { currentUser, db } from '@/lib/auth';
import { cookieValue, guestCookieName, startPrediction } from '@/lib/jobs';

export async function GET(request: Request) {
  const user = await currentUser(request);
  if (!user) return Response.json({ error: '로그인이 필요합니다.' }, { status: 401 });
  const url = new URL(request.url);
  const media = url.searchParams.get('media');
  const q = url.searchParams.get('q')?.trim();
  let sql = 'SELECT * FROM processing_jobs WHERE user_id = ?';
  const values: unknown[] = [user.id];
  if (media === 'image' || media === 'video') { sql += ' AND media_type = ?'; values.push(media); }
  if (q) { sql += ' AND original_name LIKE ?'; values.push(`%${q}%`); }
  sql += ' ORDER BY created_at DESC LIMIT 50';
  const result = await db().prepare(sql).bind(...values).all();
  return Response.json({ jobs: result.results });
}

export async function POST(request: Request) {
  const user = await currentUser(request);
  const guestToken = cookieValue(request, guestCookieName);
  if (!user && !guestToken) return Response.json({ error: '업로드 세션이 만료되었습니다.' }, { status: 401 });
  const body = await request.json() as { objectKey?: string; mediaType?: 'image' | 'video'; name?: string; size?: number; contentType?: string };
  if (!body.objectKey || !body.name || !body.mediaType) return Response.json({ error: '업로드 정보가 올바르지 않습니다.' }, { status: 400 });
  const expectedPrefix = user ? `users/${user.id}/original/` : `guests/${guestToken}/original/`;
  if (!body.objectKey.startsWith(expectedPrefix)) return Response.json({ error: '허용되지 않은 파일 경로입니다.' }, { status: 403 });
  if (!user && body.mediaType === 'video') return Response.json({ error: '영상 개선은 로그인 후 이용할 수 있습니다.' }, { status: 401 });
  const id = crypto.randomUUID();
  try {
    const prediction = await startPrediction(body.objectKey, user ? 4 : 2, new URL(request.url).origin);
    await db().prepare(`INSERT INTO processing_jobs
      (id, user_id, guest_token, media_type, original_name, original_r2_key, replicate_prediction_id, status, progress, file_size, expires_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, 'processing', 5, ?, ?)`)
      .bind(id, user?.id || null, user ? null : guestToken, body.mediaType, body.name, body.objectKey, prediction.id, Number(body.size || 0), user ? null : new Date(Date.now() + 86400000).toISOString()).run();
    return Response.json({ id, status: 'processing' });
  } catch (error) {
    await db().prepare(`INSERT INTO processing_jobs
      (id, user_id, guest_token, media_type, original_name, original_r2_key, status, progress, file_size, error_message, expires_at)
      VALUES (?, ?, ?, ?, ?, ?, 'failed', 0, ?, ?, ?)`)
      .bind(id, user?.id || null, user ? null : guestToken, body.mediaType, body.name, body.objectKey, Number(body.size || 0), error instanceof Error ? error.message : '처리 요청 실패', user ? null : new Date(Date.now() + 86400000).toISOString()).run();
    return Response.json({ id, error: error instanceof Error ? error.message : '처리 요청 실패' }, { status: 502 });
  }
}
