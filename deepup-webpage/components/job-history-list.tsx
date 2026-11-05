'use client';

import { Check, Pencil, Trash2, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { JobActions } from '@/components/job-actions';

type Job = {
  id: string;
  media_type: 'image' | 'video';
  category: string;
  original_name: string;
  status: 'pending' | 'processing' | 'succeeded' | 'failed' | 'canceled';
  progress: number;
  source_width: number | null;
  source_height: number | null;
  result_width: number | null;
  result_height: number | null;
  duration_seconds: number | null;
  created_at: string;
};

const statusLabel: Record<Job['status'], string> = {
  pending: '대기 중', processing: '처리 중', succeeded: '완료', failed: '실패', canceled: '취소됨',
};

function resolution(job: Job) {
  if (!job.source_width || !job.source_height) return '해상도 확인 중';
  const source = `${job.source_width}×${job.source_height}`;
  return job.result_width && job.result_height ? `${source} → ${job.result_width}×${job.result_height}` : source;
}

function dateText(value: string) {
  return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Seoul' }).format(new Date(value));
}

export function JobHistoryList({ jobs }: { jobs: Job[] }) {
  const [items, setItems] = useState(jobs);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState('');
  const [savingName, setSavingName] = useState(false);
  const allSelected = items.length > 0 && selected.size === items.length;
  const selectedCount = selected.size;
  const selectedIds = useMemo(() => Array.from(selected), [selected]);
  const activeKey = items.filter((job) => job.status === 'pending' || job.status === 'processing').map((job) => job.id).join(',');

  useEffect(() => {
    const activeIds = activeKey ? activeKey.split(',') : [];
    if (!activeIds.length) return;
    let alive = true;
    const refresh = async () => {
      const refreshed = await Promise.all(activeIds.map(async (id) => {
        const response = await fetch(`/api/jobs/${id}`, { cache: 'no-store' });
        if (!response.ok) return null;
        const data = await response.json() as { job?: Job };
        return data.job || null;
      }));
      if (!alive) return;
      const updates = new Map(refreshed.filter((job): job is Job => Boolean(job)).map((job) => [job.id, job]));
      if (updates.size) setItems((current) => current.map((job) => updates.get(job.id) || job));
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3500);
    return () => { alive = false; window.clearInterval(timer); };
  }, [activeKey]);

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(items.map((job) => job.id)));
  }

  function startRename(job: Job) {
    setEditingId(job.id);
    setDraftName(job.original_name);
  }

  async function saveName(id: string) {
    const name = draftName.trim();
    if (!name || savingName) return;
    setSavingName(true);
    try {
      const response = await fetch(`/api/jobs/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '파일 이름을 변경하지 못했습니다.');
      setItems((current) => current.map((job) => job.id === id ? { ...job, original_name: result.name } : job));
      setEditingId(null);
    } catch (error) {
      alert(error instanceof Error ? error.message : '파일 이름을 변경하지 못했습니다.');
    } finally {
      setSavingName(false);
    }
  }

  async function deleteSelected() {
    if (!selectedCount || !confirm(`선택한 ${selectedCount}건의 작업과 저장된 파일을 모두 삭제할까요?`)) return;
    setDeleting(true);
    const results = await Promise.all(selectedIds.map(async (id) => {
      try {
        const response = await fetch(`/api/jobs/${id}`, { method: 'DELETE' });
        return response.ok;
      } catch {
        return false;
      }
    }));
    const failed = results.filter((ok) => !ok).length;
    if (failed) {
      alert(`${failed}건을 삭제하지 못했습니다. 잠시 후 다시 시도해 주세요.`);
      setDeleting(false);
      return;
    }
    window.location.reload();
  }

  if (items.length === 0) return <div className="rounded-2xl border border-dashed border-white/15 px-6 py-20 text-center"><p className="font-bold">아직 처리 이력이 없습니다.</p><a href="/#service" className="mt-5 inline-block rounded-full bg-[#3867ff] px-6 py-3 text-sm font-bold">첫 화질 개선 시작하기</a></div>;

  return <>
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-[#0b0b0d] px-5 py-3.5">
      <label className="flex cursor-pointer items-center gap-3 text-xs font-bold text-white/70">
        <input type="checkbox" checked={allSelected} onChange={toggleAll} className="size-4 accent-[#3867ff]" />
        전체 선택
      </label>
      <div className="flex items-center gap-3">
        <span className="text-xs text-white/40">{selectedCount}건 선택</span>
        <button type="button" disabled={!selectedCount || deleting} onClick={() => void deleteSelected()} className="flex items-center gap-2 rounded-full border border-red-400/35 px-4 py-2 text-xs font-bold text-red-300 transition hover:bg-red-400/10 disabled:cursor-not-allowed disabled:opacity-35">
          <Trash2 className="size-3.5" />{deleting ? '삭제 중' : '선택 삭제'}
        </button>
      </div>
    </div>

    {items.map((job) => <article key={job.id} className={`grid gap-5 rounded-2xl border bg-[#0b0b0d] p-5 transition md:grid-cols-[36px_minmax(0,1fr)_170px_170px] md:items-center ${selected.has(job.id) ? 'border-[#5278ff] bg-[#0d1222]' : 'border-white/10'}`}>
      <label className="flex cursor-pointer items-center md:justify-center" aria-label={`${job.original_name} 선택`}>
        <input type="checkbox" checked={selected.has(job.id)} onChange={() => toggle(job.id)} className="size-4 accent-[#3867ff]" />
      </label>
      <div className="min-w-0"><div className="flex items-center gap-2"><span className="rounded-full border border-[#4565c5] bg-[#111c3e] px-2.5 py-1 text-[10px] font-bold text-[#8fa8ff]">{job.category === 'anime' ? '애니 · 일러스트' : '풍경 · 실사'}</span><span className="text-[10px] text-white/40">{job.media_type === 'image' ? '이미지' : '영상'}</span></div>{editingId === job.id ? <div className="mt-3 flex items-center gap-2"><input autoFocus value={draftName} maxLength={200} onChange={(event) => setDraftName(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void saveName(job.id); if (event.key === 'Escape') setEditingId(null); }} className="min-w-0 flex-1 rounded-lg border border-[#5278ff] bg-black/40 px-3 py-2 text-sm font-bold outline-none" aria-label="새 파일 이름" /><button type="button" disabled={savingName || !draftName.trim()} onClick={() => void saveName(job.id)} aria-label="파일 이름 저장" className="rounded-lg p-2 text-emerald-300 hover:bg-white/10 disabled:opacity-30"><Check className="size-4" /></button><button type="button" disabled={savingName} onClick={() => setEditingId(null)} aria-label="파일 이름 변경 취소" className="rounded-lg p-2 text-white/50 hover:bg-white/10"><X className="size-4" /></button></div> : <div className="mt-3 flex min-w-0 items-center gap-2"><h3 className="truncate font-extrabold">{job.original_name}</h3><button type="button" onClick={() => startRename(job)} aria-label={`${job.original_name} 이름 변경`} className="shrink-0 rounded-lg p-1.5 text-white/35 transition hover:bg-white/10 hover:text-white"><Pencil className="size-3.5" /></button></div>}<p className="mt-2 text-xs text-white/38">{resolution(job)}{job.duration_seconds ? ` · ${job.duration_seconds}초` : ''}</p></div>
      <div><p className="text-[10px] text-white/35">처리 일시</p><p className="mt-2 text-xs font-bold">{dateText(job.created_at)}</p><p className={`mt-3 text-xs font-black ${job.status === 'succeeded' ? 'text-emerald-400' : job.status === 'failed' ? 'text-red-400' : 'text-[#6f91ff]'}`}>{statusLabel[job.status]}{job.status === 'processing' ? ` ${job.progress}%` : ''}</p>{job.status === 'processing' && <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/10"><div className="h-full bg-[#3867ff]" style={{ width: `${job.progress}%` }} /></div>}</div>
      <JobActions id={job.id} status={job.status} />
    </article>)}
  </>;
}
