import { currentUser, db } from '@/lib/auth';

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const user = await currentUser(request);
  if (!user) return Response.json({ error: '로그인이 필요합니다.' }, { status: 401 });
  const { id } = await context.params;
  const job = await db().prepare('SELECT * FROM processing_jobs WHERE id = ? AND user_id = ?').bind(id, user.id).first();
  return job ? Response.json({ job }) : Response.json({ error: '작업을 찾을 수 없습니다.' }, { status: 404 });
}

export async function DELETE(request: Request, context: { params: Promise<{ id: string }> }) {
  const user = await currentUser(request);
  if (!user) return Response.json({ error: '로그인이 필요합니다.' }, { status: 401 });
  const { id } = await context.params;
  const result = await db().prepare('DELETE FROM processing_jobs WHERE id = ? AND user_id = ?').bind(id, user.id).run();
  return result.meta.changes ? Response.json({ ok: true }) : Response.json({ error: '작업을 찾을 수 없습니다.' }, { status: 404 });
}
