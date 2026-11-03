'use client';

import { useEffect } from 'react';

const BROWSER_SESSION_KEY = 'deepup_browser_session';
const BROWSER_EXIT_KEY = 'deepup_browser_exit';

export function SessionGuard() {
  useEffect(() => {
    let active = true;

    const markBrowserExit = () => {
      sessionStorage.removeItem(BROWSER_SESSION_KEY);
      localStorage.setItem(BROWSER_EXIT_KEY, String(Date.now()));
    };

    window.addEventListener('beforeunload', markBrowserExit);

    void fetch('/api/auth/me', { cache: 'no-store' })
      .then((response) => response.json())
      .then(async (data: { user?: unknown }) => {
        if (!active || !data.user) return;
        if (sessionStorage.getItem(BROWSER_SESSION_KEY) === 'active') return;

        // beforeunload는 창 종료뿐 아니라 새로고침에도 발생한다. 새로고침은
        // 같은 브라우저 세션으로 인정하고, 새 창/복원 진입만 로그아웃한다.
        const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
        const exitedAt = Number(localStorage.getItem(BROWSER_EXIT_KEY) || 0);
        const isImmediateReload = navigation?.type === 'reload' && Date.now() - exitedAt < 15_000;
        if (isImmediateReload) {
          sessionStorage.setItem(BROWSER_SESSION_KEY, 'active');
          localStorage.removeItem(BROWSER_EXIT_KEY);
          return;
        }

        await fetch('/api/auth/logout', { method: 'POST' });
        localStorage.removeItem(BROWSER_EXIT_KEY);
        if (active && window.location.pathname !== '/login') window.location.replace('/login');
      })
      .catch(() => undefined);
    return () => {
      active = false;
      window.removeEventListener('beforeunload', markBrowserExit);
    };
  }, []);

  return null;
}
