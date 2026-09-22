import { db, hashPassword, initDb, sessionCookie } from '@/lib/auth';

export async function POST(request: Request) {
  await initDb();
  const { username, password } = await request.json() as { username?: string; password?: string };
  if (!username || username.length < 3 || !password || password.length < 4) return Response.json({ error: '아이디는 3자, 비밀번호는 4자 이상 입력하세요.' }, { status: 400 });
  if (username === '1234') return Response.json({ error: '사용할 수 없는 아이디입니다.' }, { status: 400 });
  const salt = crypto.randomUUID();
  const hash = await hashPassword(password, salt);
  const userId = crypto.randomUUID();
  try { await db().prepare('INSERT INTO users (id, username, password_hash, salt, role) VALUES (?, ?, ?, ?, ?)').bind(userId, username, hash, salt, 'user').run(); }
  catch { return Response.json({ error: '이미 사용 중인 아이디입니다.' }, { status: 409 }); }
  const sid = crypto.randomUUID();
  const expires = new Date(Date.now() + 7 * 86400000).toISOString();
  await db().prepare('INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)').bind(sid, userId, expires).run();
  return Response.json({ ok: true, role: 'user' }, { headers: { 'Set-Cookie': sessionCookie(sid) } });
}
