import { db, ensureAdmin, hashPassword, sessionCookie } from '@/lib/auth';

export async function POST(request: Request) {
  await ensureAdmin();
  const { username, password } = await request.json() as { username?: string; password?: string };
  const user = await db().prepare('SELECT id, username, password_hash, salt, role FROM users WHERE username = ?').bind(username || '').first<{ id: string; username: string; password_hash: string; salt: string; role: string }>();
  if (!user || await hashPassword(password || '', user.salt) !== user.password_hash) return Response.json({ error: '아이디 또는 비밀번호가 올바르지 않습니다.' }, { status: 401 });
  const sid = crypto.randomUUID();
  const expires = new Date(Date.now() + 7 * 86400000).toISOString();
  await db().prepare('INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)').bind(sid, user.id, expires).run();
  return Response.json({ ok: true, role: user.role }, { headers: { 'Set-Cookie': sessionCookie(sid) } });
}
