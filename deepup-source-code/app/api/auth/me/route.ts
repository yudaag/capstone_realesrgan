import { db, initDb } from '@/lib/auth';

export async function GET(request: Request) {
  await initDb();
  const cookie = request.headers.get('cookie') || '';
  const sid = cookie.match(/(?:^|;\s*)deepup_session=([^;]+)/)?.[1];
  if (!sid) return Response.json({ user: null });
  const user = await db().prepare('SELECT users.username, users.role FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.id = ? AND sessions.expires_at > ?').bind(sid, new Date().toISOString()).first<{ username: string; role: string }>();
  return Response.json({ user: user || null });
}
