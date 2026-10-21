import { currentUser, db, runtimeEnv } from '@/lib/auth';
import { signedObjectUrl } from '@/lib/storage';

export const guestCookieName = 'deepup_guest';
export const cookieValue = (request: Request, name: string) => (request.headers.get('cookie') || '').match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`))?.[1] || null;
export async function requester(request: Request) { return { user: await currentUser(request), guestToken: cookieValue(request, guestCookieName) }; }
export const guestCookie = (token: string) => `${guestCookieName}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=86400`;

export async function findOwnedJob(request: Request, id: string) {
  const { user, guestToken } = await requester(request);
  if (user) return db().prepare('SELECT * FROM processing_jobs WHERE id = ? AND user_id = ?').bind(id, user.id).first<Record<string, unknown>>();
  if (guestToken) return db().prepare('SELECT * FROM processing_jobs WHERE id = ? AND guest_token = ?').bind(id, guestToken).first<Record<string, unknown>>();
  return null;
}

export async function startPrediction(originalKey: string, scale: number) {
  const env = runtimeEnv();
  if (!env.REPLICATE_API_TOKEN || !env.REPLICATE_VERSION) throw new Error('Replicate 환경변수가 설정되지 않았습니다.');
  const media = await signedObjectUrl(originalKey, 'GET');
  const response = await fetch('https://api.replicate.com/v1/predictions', {
    method: 'POST', headers: { Authorization: `Bearer ${env.REPLICATE_API_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ version: env.REPLICATE_VERSION, input: { media, scale } }),
  });
  const prediction = await response.json() as { id?: string; error?: string; detail?: string };
  if (!response.ok || !prediction.id) throw new Error(prediction.detail || prediction.error || 'Replicate 작업 생성에 실패했습니다.');
  return prediction;
}
