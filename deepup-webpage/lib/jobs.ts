import { currentUser, db, runtimeEnv } from '@/lib/auth';

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

const encoder = new TextEncoder();
const toHex = (buffer: ArrayBuffer) => Array.from(new Uint8Array(buffer)).map((byte) => byte.toString(16).padStart(2, '0')).join('');

export async function sourceSignature(key: string, expires: string) {
  const secret = runtimeEnv().REPLICATE_API_TOKEN;
  if (!secret) throw new Error('REPLICATE_API_TOKEN이 설정되지 않았습니다.');
  const cryptoKey = await crypto.subtle.importKey('raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return toHex(await crypto.subtle.sign('HMAC', cryptoKey, encoder.encode(`${key}\n${expires}`)));
}

export async function startPrediction(originalKey: string, scale: number, origin: string, category: 'photo' | 'anime' = 'photo') {
  const env = runtimeEnv();
  if (!env.REPLICATE_API_TOKEN || !env.REPLICATE_VERSION) throw new Error('Replicate 환경변수가 설정되지 않았습니다.');
  const expires = String(Math.floor(Date.now() / 1000) + 3600);
  const signature = await sourceSignature(originalKey, expires);
  const mediaUrl = new URL('/api/media/source', origin);
  mediaUrl.searchParams.set('key', originalKey);
  mediaUrl.searchParams.set('expires', expires);
  mediaUrl.searchParams.set('sig', signature);
  const media = mediaUrl.toString();
  const response = await fetch('https://api.replicate.com/v1/predictions', {
    method: 'POST', headers: { Authorization: `Bearer ${env.REPLICATE_API_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ version: env.REPLICATE_VERSION, input: { media, scale, category } }),
  });
  const prediction = await response.json() as { id?: string; error?: string; detail?: string };
  if (!response.ok || !prediction.id) throw new Error(prediction.detail || prediction.error || 'Replicate 작업 생성에 실패했습니다.');
  return prediction;
}
