'use client';
import { FormEvent, useState } from 'react';
import { ArrowLeft, Layers3 } from 'lucide-react';

export default function LoginPage() {
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setLoading(true); setError('');
    try {
      const data = new FormData(e.currentTarget);
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 12000);
      const res = await fetch(`/api/auth/${mode}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: data.get('username'), password: data.get('password') }), signal: controller.signal });
      window.clearTimeout(timeout);
      const body = await res.json() as { error?: string; role?: string };
      if (!res.ok) { setError(body.error || '로그인 처리 중 오류가 발생했습니다.'); return; }
      window.location.href = body.role === 'admin' ? '/admin' : '/';
    } catch { setError('서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.'); }
    finally { setLoading(false); }
  }
  return <main className="grid min-h-screen place-items-center bg-black px-5 text-white"><div className="w-full max-w-md"><a href="/" className="mb-8 inline-flex items-center gap-2 text-sm text-white/50"><ArrowLeft className="size-4" />메인으로</a><div className="rounded-3xl border border-white/12 bg-[#0b0b0c] p-8 shadow-2xl"><div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-[#275cff]"><Layers3 className="size-5" /></span><div><h1 className="text-xl font-black">DeepUp</h1><p className="text-xs text-white/40">사이트 전용 계정</p></div></div><div className="mt-8 grid grid-cols-2 rounded-xl bg-white/5 p-1"><button onClick={() => setMode('login')} className={`rounded-lg py-2.5 text-sm font-bold ${mode === 'login' ? 'bg-[#275cff]' : 'text-white/45'}`}>로그인</button><button onClick={() => setMode('signup')} className={`rounded-lg py-2.5 text-sm font-bold ${mode === 'signup' ? 'bg-[#275cff]' : 'text-white/45'}`}>회원가입</button></div><form onSubmit={submit} className="mt-6 space-y-4"><label className="block"><span className="mb-2 block text-xs font-bold text-white/60">아이디</span><input name="username" required minLength={3} className="h-12 w-full rounded-xl border border-white/12 bg-white/5 px-4 outline-none focus:border-[#5278ff]" /></label><label className="block"><span className="mb-2 block text-xs font-bold text-white/60">비밀번호</span><input name="password" type="password" required minLength={4} className="h-12 w-full rounded-xl border border-white/12 bg-white/5 px-4 outline-none focus:border-[#5278ff]" /></label>{error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>}<button disabled={loading} className="h-12 w-full rounded-xl bg-[#275cff] text-sm font-black disabled:opacity-60">{loading ? '처리 중…' : mode === 'login' ? '로그인' : '계정 만들기'}</button></form><p className="mt-6 text-center text-[11px] text-white/30">관리자 계정은 배포 환경에서 별도로 생성됩니다.</p></div></div></main>;
}
