import { env } from 'cloudflare:workers';

type DB = D1Database;
export const db = () => (env as unknown as { DB: DB }).DB;

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

export async function ensureAdmin() {
  await initDb();
  const found = await db().prepare('SELECT id FROM users WHERE username = ?').bind('1234').first();
  if (!found) {
    const salt = crypto.randomUUID();
    const hash = await hashPassword('1234', salt);
    await db().prepare('INSERT INTO users (id, username, password_hash, salt, role) VALUES (?, ?, ?, ?, ?)').bind(crypto.randomUUID(), '1234', hash, salt, 'admin').run();
  }
}

export const sessionCookie = (id: string) => `deepup_session=${id}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=604800`;
