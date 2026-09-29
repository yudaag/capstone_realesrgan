'use client';

import { useEffect, useState } from 'react';
import { LogOut, Menu, ShieldCheck, UserRound } from 'lucide-react';

type User = { username: string; role: string };

export function AccountMenu() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then((res) => res.json())
      .then((data: { user: User | null }) => setUser(data.user))
      .catch(() => setUser(null));
  }, []);

  if (user === undefined) return <span className="h-9 w-24 animate-pulse rounded-full bg-white/10" />;
  if (!user) return <a href="/login" className="flex items-center gap-2 rounded-full border border-white/20 px-4 py-2 text-xs font-bold"><Menu className="size-4" /> 로그인</a>;

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
    window.location.href = '/';
  }

  return <div className="relative">
    <button onClick={() => setOpen(!open)} className="flex items-center gap-2 rounded-full border border-white/20 bg-white/[.06] py-1.5 pl-1.5 pr-3 text-xs font-bold">
      <span className="grid size-7 place-items-center rounded-full bg-[#275cff]"><UserRound className="size-3.5" /></span>
      <span>{user.username}</span>
      <span className="text-[9px] text-white/40">{user.role === 'admin' ? '관리자' : '회원'}</span>
    </button>
    {open && <div className="absolute right-0 top-12 z-50 w-48 overflow-hidden rounded-xl border border-white/12 bg-[#111114] p-1.5 shadow-2xl">
      <div className="border-b border-white/8 px-3 py-2.5"><p className="text-xs font-bold">{user.username}</p><p className="mt-1 text-[10px] text-white/40">{user.role === 'admin' ? '관리자 계정' : 'DeepUp 회원'}</p></div>
      {user.role === 'admin' && <a href="/admin" className="mt-1 flex items-center gap-2 rounded-lg px-3 py-2.5 text-xs font-bold hover:bg-white/8"><ShieldCheck className="size-4 text-[#7895ff]" />관리자 페이지</a>}
      <button onClick={logout} className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-xs font-bold text-red-300 hover:bg-white/8"><LogOut className="size-4" />로그아웃</button>
    </div>}
  </div>;
}
