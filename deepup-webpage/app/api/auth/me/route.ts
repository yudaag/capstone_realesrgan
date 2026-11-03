import { currentUser, sessionCookie } from '@/lib/auth';

export async function GET(request: Request) {
  const user = await currentUser(request);
  const sid = request.headers.get('cookie')?.match(/(?:^|;\s*)deepup_session=([^;]+)/)?.[1];
  return Response.json(
    { user },
    { headers: user && sid ? { 'Set-Cookie': sessionCookie(sid) } : undefined },
  );
}
