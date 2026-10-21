import { currentUser, db } from '@/lib/auth';

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const user = await currentUser(request);
  if (!user) return Response.json({ error: '로그인이 필요합니다.' }, { status: 401 });
  const { id } = await context.params;
  const result = await db().prepare("UPDATE processing_jobs SET status = 'pending', progress = 0, error_message = NULL WHERE id = ? AND user_id = ? AND status = 'failed'").bind(id, user.id).run();
  return result.meta.changes ? Response.json({ ok: true }) : Response.json({ error: '다시 시도할 수 없는 작업입니다.' }, { status: 409 });
}
