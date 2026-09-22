import { db, initDb } from '@/lib/auth';

export async function POST(request: Request) {
  await initDb();
  const cookie = request.headers.get('cookie') || '';
  const sid = cookie.match(/(?:^|;\s*)deepup_session=([^;]+)/)?.[1];
  if (sid) await db().prepare('DELETE FROM sessions WHERE id = ?').bind(sid).run();
  return Response.json({ ok: true }, { headers: { 'Set-Cookie': 'deepup_session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0' } });
}
