'use client';

import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';

export function ThemeToggle() {
  const [light, setLight] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem('deepup-theme');
    const next = saved === 'light';
    setLight(next);
    document.documentElement.dataset.theme = next ? 'light' : 'dark';
  }, []);

  function toggle() {
    const next = !light;
    setLight(next);
    document.documentElement.dataset.theme = next ? 'light' : 'dark';
    window.localStorage.setItem('deepup-theme', next ? 'light' : 'dark');
  }

  return (
    <button onClick={toggle} className="theme-toggle" aria-label={light ? '다크 모드 켜기' : '라이트 모드 켜기'} title={light ? '다크 모드' : '라이트 모드'}>
      {light ? <Moon /> : <Sun />}
      <span>{light ? '다크' : '라이트'}</span>
    </button>
  );
}
