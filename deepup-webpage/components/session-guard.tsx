'use client';

import { useEffect } from 'react';

const BROWSER_SESSION_KEY = 'deepup_browser_session';
const BROWSER_EXIT_KEY = 'deepup_browser_exit';
const ALLOW_NAVIGATION_KEY = 'deepup_allow_navigation_once';

export function SessionGuard() {
  useEffect(() => {
    // 로그인 페이지에서는 세션 종료 감지를 실행하지 않는다. 로그인 요청과
    // 페이지 이동 사이에 기존 인증 확인이 뒤늦게 끝나면 새 세션을 지우는
    // 경쟁 상태가 생길 수 있기 때문이다.
    if (window.location.pathname === '/login') return;

    let active = true;

    const markBrowserExit = () => {
      if (sessionStorage.getItem(ALLOW_NAVIGATION_KEY) === 'true') {
        sessionStorage.removeItem(ALLOW_NAVIGATION_KEY);
        return;
      }
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
        // 종료된 브라우저 세션의 서버 쿠키만 정리한다. 공개 홈 화면에서
        // 로그인 페이지를 잠깐 보여 주지 않고, 사용자가 원할 때 로그인한다.
        if (active && window.location.pathname !== '/') window.location.replace('/');
      })
      .catch(() => undefined);
    return () => {
      active = false;
      window.removeEventListener('beforeunload', markBrowserExit);
    };
  }, []);

  return null;
}
