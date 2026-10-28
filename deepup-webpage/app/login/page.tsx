'use client';

import { FormEvent, useState } from 'react';
import { ArrowLeft, ArrowRight, Eye, EyeOff, Layers3, ShieldCheck, Sparkles } from 'lucide-react';

type AuthMode = 'login' | 'signup';

export default function LoginPage() {
  const [mode, setMode] = useState<AuthMode>('login');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  function changeMode(nextMode: AuthMode) {
    setMode(nextMode);
    setError('');
    setShowPassword(false);
    setShowConfirm(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError('');
    const data = new FormData(event.currentTarget);
    const password = String(data.get('password') || '');

    if (mode === 'signup' && password !== String(data.get('passwordConfirm') || '')) {
      setError('비밀번호와 비밀번호 확인이 일치하지 않습니다.');
      setLoading(false);
      return;
    }

    try {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 12000);
      const response = await fetch(`/api/auth/${mode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: data.get('username'), password }),
        signal: controller.signal,
      });
      window.clearTimeout(timeout);
      const body = (await response.json()) as { error?: string; role?: string };
      if (!response.ok) {
        setError(body.error || '계정 처리 중 오류가 발생했습니다.');
        return;
      }
      window.location.href = body.role === 'admin' ? '/admin' : '/';
    } catch {
      setError('서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.');
    } finally {
      setLoading(false);
    }
  }

  const fieldClass = 'h-[58px] w-full rounded-2xl border border-white/15 bg-white/[.045] px-5 text-[15px] font-semibold text-white outline-none transition placeholder:text-white/28 hover:border-white/25 focus:border-[#5d82ff] focus:bg-white/[.065] focus:shadow-[0_0_0_4px_rgba(55,101,255,.13)]';

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#050506] px-5 py-8 text-white sm:px-8 sm:py-12">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_10%,rgba(42,89,255,.16),transparent_30%),radial-gradient(circle_at_90%_85%,rgba(92,45,210,.13),transparent_32%)]" />
      <a href="/" className="relative mx-auto mb-7 flex w-full max-w-[1120px] items-center gap-3 text-sm font-bold text-white/55 transition hover:text-white">
        <ArrowLeft className="size-4" /> 메인으로 돌아가기
      </a>

      <section className="relative mx-auto grid min-h-[720px] w-full max-w-[1120px] overflow-hidden rounded-[34px] border border-white/10 bg-[#0b0b0d] shadow-[0_35px_100px_rgba(0,0,0,.55)] lg:grid-cols-[.82fr_1.18fr]">
        <aside className="relative hidden overflow-hidden border-r border-white/10 bg-[#0c1229] p-12 lg:flex lg:flex-col lg:justify-between">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(66,112,255,.35),transparent_36%),radial-gradient(circle_at_75%_80%,rgba(114,56,224,.28),transparent_42%)]" />
          <div className="relative">
            <a href="/" className="inline-flex items-center gap-3 text-xl font-black">
              <span className="grid size-11 place-items-center rounded-2xl bg-[#3867ff] shadow-[0_10px_30px_rgba(56,103,255,.35)]"><Layers3 className="size-6" /></span>
              DeepUp
            </a>
            <p className="mt-16 text-xs font-black tracking-[.22em] text-[#7897ff]">AI UPSCALING SERVICE</p>
            <h1 className="mt-5 text-[42px] font-black leading-[1.15] tracking-[-.045em]">더 선명한 결과를<br />계정에 안전하게.</h1>
            <p className="mt-6 max-w-sm text-sm leading-7 text-white/52">이미지와 영상을 개선하고, 처리 이력과 결과 파일을 언제든 다시 확인하세요.</p>
          </div>
          <div className="relative space-y-4 text-sm font-bold text-white/62">
            <p className="flex items-center gap-3"><Sparkles className="size-4 text-[#7897ff]" /> 최대 500MB 이미지·영상 처리</p>
            <p className="flex items-center gap-3"><ShieldCheck className="size-4 text-[#7897ff]" /> 결과 저장 및 작업 이력 관리</p>
          </div>
        </aside>

        <div className="flex items-center justify-center px-6 py-12 sm:px-12 lg:px-16">
          <div className="w-full max-w-[520px]">
            <div className="flex items-center gap-3 lg:hidden">
              <span className="grid size-10 place-items-center rounded-xl bg-[#3867ff]"><Layers3 className="size-5" /></span>
              <span className="text-xl font-black">DeepUp</span>
            </div>
            <p className="mt-10 text-xs font-black tracking-[.2em] text-[#7897ff] lg:mt-0">{mode === 'login' ? 'WELCOME BACK' : 'CREATE ACCOUNT'}</p>
            <h2 className="mt-4 text-3xl font-black tracking-[-.035em] sm:text-[40px]">{mode === 'login' ? 'DeepUp에 로그인' : '새 계정 만들기'}</h2>
            <p className="mt-3 text-sm leading-6 text-white/42">{mode === 'login' ? '저장된 작업과 화질 개선 결과를 계속 관리하세요.' : '무료 계정을 만들고 모든 화질 개선 기능을 이용하세요.'}</p>

            <div className="mt-8 grid grid-cols-2 rounded-2xl border border-white/10 bg-black/25 p-1.5">
              <button type="button" onClick={() => changeMode('login')} className={`rounded-xl py-3 text-sm font-black transition ${mode === 'login' ? 'bg-[#3867ff] text-white shadow-[0_8px_24px_rgba(56,103,255,.28)]' : 'text-white/40 hover:text-white/70'}`}>로그인</button>
              <button type="button" onClick={() => changeMode('signup')} className={`rounded-xl py-3 text-sm font-black transition ${mode === 'signup' ? 'bg-[#3867ff] text-white shadow-[0_8px_24px_rgba(56,103,255,.28)]' : 'text-white/40 hover:text-white/70'}`}>회원가입</button>
            </div>

            <form onSubmit={submit} className="mt-7 space-y-4">
              <label className="block">
                <span className="mb-2.5 block text-xs font-black text-white/60">아이디</span>
                <input name="username" required minLength={3} autoComplete="username" placeholder="3자 이상 입력하세요" className={fieldClass} />
              </label>
              <label className="block">
                <span className="mb-2.5 block text-xs font-black text-white/60">비밀번호</span>
                <span className="relative block">
                  <input name="password" type={showPassword ? 'text' : 'password'} required minLength={4} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder="4자 이상 입력하세요" className={`${fieldClass} pr-14`} />
                  <button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'} className="absolute right-3 top-1/2 grid size-10 -translate-y-1/2 place-items-center rounded-xl text-white/40 transition hover:bg-white/5 hover:text-white">{showPassword ? <EyeOff className="size-5" /> : <Eye className="size-5" />}</button>
                </span>
              </label>

              {mode === 'signup' && (
                <label className="block">
                  <span className="mb-2.5 block text-xs font-black text-white/60">비밀번호 확인</span>
                  <span className="relative block">
                    <input name="passwordConfirm" type={showConfirm ? 'text' : 'password'} required minLength={4} autoComplete="new-password" placeholder="비밀번호를 다시 입력하세요" className={`${fieldClass} pr-14`} />
                    <button type="button" onClick={() => setShowConfirm((value) => !value)} aria-label={showConfirm ? '비밀번호 확인 숨기기' : '비밀번호 확인 보기'} className="absolute right-3 top-1/2 grid size-10 -translate-y-1/2 place-items-center rounded-xl text-white/40 transition hover:bg-white/5 hover:text-white">{showConfirm ? <EyeOff className="size-5" /> : <Eye className="size-5" />}</button>
                  </span>
                </label>
              )}

              {mode === 'signup' && (
                <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-white/8 bg-white/[.025] px-4 py-3.5 text-xs leading-5 text-white/45">
                  <input type="checkbox" required className="mt-0.5 size-4 accent-[#3867ff]" />
                  <span>개인정보 처리방침과 서비스 이용약관에 동의합니다.</span>
                </label>
              )}

              {error && <p role="alert" className="rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm font-semibold text-red-200">{error}</p>}
              <button disabled={loading} className="group flex h-[58px] w-full items-center justify-center gap-2 rounded-2xl bg-[#3867ff] text-sm font-black shadow-[0_12px_34px_rgba(56,103,255,.28)] transition hover:bg-[#4b76ff] disabled:cursor-wait disabled:opacity-55">
                {loading ? '처리 중…' : mode === 'login' ? '로그인' : '계정 만들기'}
                {!loading && <ArrowRight className="size-4 transition group-hover:translate-x-1" />}
              </button>
            </form>

            <p className="mt-7 text-center text-sm text-white/40">
              {mode === 'login' ? '아직 계정이 없으신가요?' : '이미 계정이 있으신가요?'}{' '}
              <button type="button" onClick={() => changeMode(mode === 'login' ? 'signup' : 'login')} className="font-black text-[#7897ff] hover:text-[#9bb0ff]">{mode === 'login' ? '무료로 가입하기' : '로그인하기'}</button>
            </p>
            <p className="mt-8 text-center text-[11px] leading-5 text-white/24">관리자 계정은 배포 환경에서 별도로 생성됩니다.</p>
          </div>
        </div>
      </section>
    </main>
  );
}
