import { bootstrapAdmin, runtimeEnv } from '@/lib/auth';

export async function POST(request: Request) {
  const expectedToken = runtimeEnv().ADMIN_SETUP_TOKEN;
  const suppliedToken = request.headers.get('x-admin-setup-token');

  if (!expectedToken || !suppliedToken || suppliedToken !== expectedToken) {
    return Response.json({ error: '관리자 초기화 권한이 없습니다.' }, { status: 401 });
  }

  try {
    const result = await bootstrapAdmin();
    return Response.json({
      ok: true,
      created: result.created,
      message: result.created ? '관리자 계정을 생성했습니다.' : '관리자 계정이 이미 존재합니다.',
    });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : '관리자 계정을 생성하지 못했습니다.' },
      { status: 400 },
    );
  }
}
