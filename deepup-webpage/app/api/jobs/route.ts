import { currentUser, db } from '@/lib/auth';

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
