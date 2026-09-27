import { env } from 'cloudflare:workers';

type DB = D1Database;
type RuntimeEnv = {
  DB: DB;
  ADMIN_USERNAME?: string;
  ADMIN_PASSWORD?: string;
  ADMIN_SETUP_TOKEN?: string;
};

export const runtimeEnv = () => env as unknown as RuntimeEnv;
export const db = () => runtimeEnv().DB;

const enc = new TextEncoder();
const hex = (bytes: Uint8Array) => Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');

export async function hashPassword(password: string, salt: string) {
  const key = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', salt: enc.encode(salt), iterations: 100000, hash: 'SHA-256' }, key, 256);
  return hex(new Uint8Array(bits));
}

export async function initDb() {
  const d = db();
  await d.batch([
    d.prepare('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, salt TEXT NOT NULL, role TEXT NOT NULL DEFAULT \'user\', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)'),
    d.prepare('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)'),
    d.prepare('CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)'),
  ]);
}

export async function bootstrapAdmin() {
  await initDb();
  const { ADMIN_USERNAME, ADMIN_PASSWORD } = runtimeEnv();
  if (!ADMIN_USERNAME || !ADMIN_PASSWORD) throw new Error('관리자 환경변수가 설정되지 않았습니다.');
  if (ADMIN_USERNAME.length < 3 || ADMIN_PASSWORD.length < 12) throw new Error('관리자 아이디는 3자 이상, 비밀번호는 12자 이상이어야 합니다.');

  const existingAdmin = await db().prepare("SELECT id FROM users WHERE role = 'admin' LIMIT 1").first();
  if (existingAdmin) return { created: false };

  const existingUser = await db().prepare('SELECT id FROM users WHERE username = ?').bind(ADMIN_USERNAME).first();
  if (existingUser) throw new Error('같은 아이디의 일반 회원이 이미 존재합니다.');

  const salt = crypto.randomUUID();
  const hash = await hashPassword(ADMIN_PASSWORD, salt);
  await db().prepare('INSERT INTO users (id, username, password_hash, salt, role) VALUES (?, ?, ?, ?, ?)').bind(crypto.randomUUID(), ADMIN_USERNAME, hash, salt, 'admin').run();
  return { created: true };
}

export const sessionCookie = (id: string) => `deepup_session=${id}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=604800`;
