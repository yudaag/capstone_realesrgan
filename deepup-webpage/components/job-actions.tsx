'use client';

import { Download, RefreshCw, Trash2 } from 'lucide-react';
import { useState } from 'react';

export function JobActions({ id, status }: { id: string; status: string }) {
  const [busy, setBusy] = useState(false);
  async function act(path: string, method: string) {
    setBusy(true);
    const response = await fetch(path, { method });
    if (response.ok) window.location.reload();
    else { const data = await response.json().catch(() => ({})); alert(data.error || '요청 처리에 실패했습니다.'); setBusy(false); }
  }
  return <div className="flex flex-wrap justify-start gap-2 md:justify-end">
    {status === 'succeeded' && <><a href={`/compare/${id}`} className="rounded-full bg-[#3867ff] px-4 py-2.5 text-xs font-bold">결과 비교</a><a href={`/api/jobs/${id}/download`} className="rounded-full border border-white/15 p-2.5" aria-label="다운로드"><Download className="size-4" /></a></>}
    {status === 'failed' && <button disabled={busy} onClick={() => void act(`/api/jobs/${id}/retry`, 'POST')} className="rounded-full border border-white/15 p-2.5" aria-label="다시 시도"><RefreshCw className="size-4" /></button>}
    <button disabled={busy} onClick={() => { if (confirm('이 작업과 저장된 파일을 삭제할까요?')) void act(`/api/jobs/${id}`, 'DELETE'); }} className="rounded-full border border-white/15 p-2.5 text-white/45" aria-label="삭제"><Trash2 className="size-4" /></button>
  </div>;
}
