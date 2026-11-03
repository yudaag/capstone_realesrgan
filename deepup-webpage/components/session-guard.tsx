'use client';

import { useEffect } from 'react';

const BROWSER_SESSION_KEY = 'deepup_browser_session';

export function SessionGuard() {
  useEffect(() => {
    let active = true;
    void fetch('/api/auth/me', { cache: 'no-store' })
      .then((response) => response.json())
      .then(async (data: { user?: unknown }) => {
        if (!active || !data.user) return;
        if (sessionStorage.getItem(BROWSER_SESSION_KEY) === 'active') return;
        await fetch('/api/auth/logout', { method: 'POST' });
        if (active && window.location.pathname !== '/login') window.location.replace('/login');
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  return null;
}
