'use client';

import { useEffect, useRef, useState } from 'react';
import { Download, ImageUp, LoaderCircle, Sparkles } from 'lucide-react';
import { mediaContentType } from '@/lib/media-type';

type Job = { id: string; status: string; progress: number; media_type: 'image' | 'video'; error_message?: string };
type User = { username: string } | null;
type Category = 'photo' | 'anime';
type ActiveJob = { id: string; mediaType: 'image' | 'video'; name: string; category: Category };

const ACTIVE_JOB_KEY = 'deepup_active_job';
const PROCESSING_LOCK_KEY = 'deepup_processing_lock';

export function EnhancementWorkspace() {
  const inputRef = useRef<HTMLInputElement>(null);
  const aliveRef = useRef(true);
  const [user, setUser] = useState<User>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [stage, setStage] = useState('파일을 선택해 주세요.');
  const [stageProgress, setStageProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const [category, setCategory] = useState<Category>('photo');
  const [activeName, setActiveName] = useState('');

  useEffect(() => { fetch('/api/auth/me').then((r) => r.json()).then((d) => setUser(d.user || null)); }, []);
  useEffect(() => {
    aliveRef.current = true;
    const saved = localStorage.getItem(ACTIVE_JOB_KEY);
    if (saved) {
      try {
        const active = JSON.parse(saved) as ActiveJob;
        if (active.id && (active.mediaType === 'image' || active.mediaType === 'video')) {
          setActiveName(active.name || '진행 중인 작업');
          setCategory(active.category === 'anime' ? 'anime' : 'photo');
          setJob({ id: active.id, status: 'processing', progress: 5, media_type: active.mediaType });
          setStage('진행 중인 작업을 다시 불러오는 중');
          setStageProgress(5);
          setBusy(true);
          localStorage.setItem(PROCESSING_LOCK_KEY, String(Date.now()));
          void poll(active.id, active.mediaType).catch((error) => {
            if (!aliveRef.current) return;
            setStage(error instanceof Error ? error.message : '작업 상태를 확인하지 못했습니다.');
          }).finally(() => {
            localStorage.removeItem(PROCESSING_LOCK_KEY);
            if (aliveRef.current) setBusy(false);
          });
        }
      } catch {
        localStorage.removeItem(ACTIVE_JOB_KEY);
      }
    }
    return () => { aliveRef.current = false; };
  }, []);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  async function choose(selected?: File) {
    if (!selected) return;
    if (busy) { setStage('현재 화질 개선 작업이 처리 중입니다.'); return; }
    const detectedType = mediaContentType(selected.name, selected.type);
    const isImage = detectedType.startsWith('image/');
    const isVideo = detectedType.startsWith('video/');
    if (!isImage && !isVideo) { setStage('이미지 또는 동영상 파일만 선택할 수 있습니다.'); return; }
    if (isVideo && !user) { setStage('동영상 개선은 로그인 후 이용할 수 있습니다.'); return; }
    setFile(selected); setActiveName(selected.name); setJob(null); setStage('업로드 준비 완료'); setStageProgress(0);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(URL.createObjectURL(selected));
  }

  function resetForNewFile() {
    if (busy) return;
    setFile(null); setJob(null); setActiveName(''); setStage('파일을 선택해 주세요.'); setStageProgress(0);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(null);
    if (inputRef.current) { inputRef.current.value = ''; inputRef.current.click(); }
  }

  function selectCategory(next: Category) {
    setCategory(next);
    // Allow re-running the same file with the other category after a finished job.
    if (!busy && job?.status === 'succeeded' && file) { setJob(null); setStage('업로드 준비 완료'); setStageProgress(0); }
  }

  async function poll(id: string, mediaType: 'image' | 'video') {
    const maxPolls = mediaType === 'video' ? 900 : 180;
    for (let count = 0; count < maxPolls; count++) {
      if (!aliveRef.current) return;
      const response = await fetch(`/api/jobs/${id}`, { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '상태 확인 실패');
      if (!aliveRef.current) return;
      setJob(data.job); setStageProgress(Number(data.job.progress || 0)); setStage(data.job.status === 'processing' ? 'AI 화질 개선 처리 중' : data.job.status);
      if (data.job.status === 'succeeded') { localStorage.removeItem(ACTIVE_JOB_KEY); setStageProgress(100); setStage('화질 개선이 완료되었습니다.'); return; }
      if (data.job.status === 'failed' || data.job.status === 'canceled') { localStorage.removeItem(ACTIVE_JOB_KEY); throw new Error(data.job.error_message || '처리에 실패했습니다.'); }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    throw new Error('처리 시간이 길어지고 있습니다. 마이페이지에서 상태를 확인해 주세요.');
  }

  async function run() {
    if (!file || busy) return;
    setBusy(true);
    localStorage.setItem(PROCESSING_LOCK_KEY, String(Date.now()));
    try {
      const contentType = mediaContentType(file.name, file.type);
      setStageProgress(8); setStage('R2 업로드 주소 생성 중');
      const presign = await fetch('/api/uploads/presign', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: file.name, type: contentType, size: file.size }) });
      const upload = await presign.json();
      if (!presign.ok) throw new Error(upload.error || '업로드 준비 실패');
      const uploadContentType = upload.contentType || contentType;
      setStageProgress(16); setStage('파일 업로드 중');
      const put = await fetch(upload.uploadUrl, { method: 'PUT', headers: { 'Content-Type': uploadContentType }, body: file });
      if (!put.ok) {
        const failure = await put.json().catch(() => null) as { error?: string } | null;
        throw new Error(failure?.error || `R2 업로드에 실패했습니다. (${put.status})`);
      }
      setStageProgress(27); setStage('AI 작업 생성 중');
      const create = await fetch('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ objectKey: upload.objectKey, mediaType: upload.mediaType, name: file.name, size: file.size, contentType: uploadContentType, category }) });
      const created = await create.json();
      if (!create.ok) throw new Error(created.error || 'AI 작업 생성 실패');
      const active: ActiveJob = { id: created.id, mediaType: upload.mediaType, name: file.name, category };
      localStorage.setItem(ACTIVE_JOB_KEY, JSON.stringify(active));
      setActiveName(file.name);
      setStageProgress(32); setJob({ id: created.id, status: created.status, progress: 5, media_type: upload.mediaType });
      await poll(created.id, upload.mediaType);
    } catch (error) { setStageProgress(0); setStage(error instanceof Error ? error.message : '처리에 실패했습니다.'); }
    finally { localStorage.removeItem(PROCESSING_LOCK_KEY); setBusy(false); }
  }

  const finished = job?.status === 'succeeded';
  const displayedName = file?.name || activeName;
  const displayedSize = file ? `${(file.size / 1024 / 1024).toFixed(2)}MB · ` : '';
  return <div className="mx-auto w-full max-w-[920px] rounded-[30px] border border-white/10 bg-gradient-to-b from-white/[.065] to-white/[.025] p-3 shadow-[0_30px_100px_rgba(0,0,0,.36),0_0_80px_rgba(39,92,255,.08)] lg:p-4">
    <div className="mb-3 rounded-[22px] border border-white/[.08] bg-black/25 p-5">
      <p className="mb-3 text-xs font-bold text-white/55">이미지 카테고리를 선택하세요</p>
      <div className="grid grid-cols-2 gap-2">
        <button type="button" disabled={busy} onClick={() => selectCategory('photo')} className={`rounded-xl border px-4 py-3.5 text-sm font-black transition ${category === 'photo' ? 'border-[#6f8fff] bg-gradient-to-r from-[#20377d] to-[#182b67] text-white shadow-[0_8px_26px_rgba(39,92,255,.18)]' : 'border-white/10 bg-black/20 text-white/45 hover:border-white/20 hover:text-white'}`}>풍경 · 동물</button>
        <button type="button" disabled={busy} onClick={() => selectCategory('anime')} className={`rounded-xl border px-4 py-3.5 text-sm font-black transition ${category === 'anime' ? 'border-[#6f8fff] bg-gradient-to-r from-[#20377d] to-[#182b67] text-white shadow-[0_8px_26px_rgba(39,92,255,.18)]' : 'border-white/10 bg-black/20 text-white/45 hover:border-white/20 hover:text-white'}`}>애니 · 일러스트</button>
      </div>
    </div>
    <div onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void choose(event.dataTransfer.files[0]); }} onClick={() => inputRef.current?.click()} className="group cursor-pointer rounded-[24px] border border-[#5477ff]/80 bg-[radial-gradient(circle_at_50%_15%,rgba(73,112,255,.22),transparent_42%),linear-gradient(135deg,rgba(20,37,93,.94),rgba(11,20,50,.94))] p-8 shadow-[inset_0_1px_0_rgba(255,255,255,.08),0_18px_55px_rgba(20,45,120,.2)] transition hover:border-[#7997ff] hover:shadow-[inset_0_1px_0_rgba(255,255,255,.1),0_24px_70px_rgba(39,92,255,.25)] lg:min-h-[290px] lg:p-10">
      <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime" className="hidden" onChange={(event) => { const picked = event.target.files?.[0]; event.target.value = ''; void choose(picked); }} />
      <div className="flex h-full flex-col items-center justify-center text-center"><span className="grid size-16 place-items-center rounded-2xl border border-white/10 bg-white/[.07] shadow-[0_12px_36px_rgba(0,0,0,.18)] transition group-hover:-translate-y-1 group-hover:bg-white/[.1]"><ImageUp className="size-8 text-white/90" strokeWidth={1.6} /></span><div className="mt-6 rounded-full bg-gradient-to-r from-[#3867ff] to-[#587fff] px-8 py-3.5 text-sm font-extrabold shadow-[0_12px_34px_rgba(39,92,255,.35)]">이미지·동영상 업로드</div><p className="mt-5 text-base font-bold text-white/85">또는 파일을 이곳에 끌어다 놓으세요</p><p className="mt-2 text-xs leading-5 text-white/38">{user ? 'JPG, PNG, WEBP, MP4, MOV · 최대 90MB' : '비로그인 체험 · 이미지 전용 · 최대 10MB'}</p></div>
    </div>
    {displayedName && <div className="deepup-reveal mt-5 rounded-2xl border border-white/10 bg-white/[.04] p-5"><div className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="truncate text-sm font-bold">{displayedName}</p><p className="mt-1 text-xs text-white/40">{displayedSize}{stage}</p></div>{file && !finished && <button onClick={run} disabled={busy} className="flex shrink-0 items-center gap-2 rounded-full bg-[#3867ff] px-5 py-3 text-xs font-black disabled:opacity-50">{busy ? <LoaderCircle className="size-4 animate-spin" /> : <Sparkles className="size-4" />}화질 개선</button>}</div>{(busy || stageProgress > 0) && <div className="mt-5"><div className="mb-2 flex items-center justify-between text-[11px] font-bold"><span className="text-white/45">{stage}</span><span className="text-[#8fa8ff]">{Math.round(stageProgress)}%</span></div><div className="h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-gradient-to-r from-[#315fff] to-[#7997ff] shadow-[0_0_16px_rgba(82,120,255,.65)] transition-[width] duration-700 ease-out" style={{ width: `${Math.min(100, Math.max(0, stageProgress))}%` }} /></div></div>}</div>}
    {finished && job && <div className="deepup-reveal mt-5 overflow-hidden rounded-2xl border border-[#5278ff] bg-[#090d1b] p-5"><div className="grid gap-3 sm:grid-cols-2">{job.media_type === 'image' ? <><img src={`/api/jobs/${job.id}/file?kind=original`} alt="원본" className="aspect-video w-full rounded-xl object-contain bg-black" /><img src={`/api/jobs/${job.id}/file?kind=result`} alt="개선 결과" className="aspect-video w-full rounded-xl object-contain bg-black" /></> : <><video src={`/api/jobs/${job.id}/file?kind=original`} controls className="aspect-video w-full rounded-xl bg-black" /><video src={`/api/jobs/${job.id}/file?kind=result`} controls className="aspect-video w-full rounded-xl bg-black" /></>}</div><div className="mt-4 flex gap-2"><a href={`/compare/${job.id}`} className="rounded-full bg-[#3867ff] px-5 py-3 text-xs font-black">결과 비교</a><a href={`/api/jobs/${job.id}/download`} className="flex items-center gap-2 rounded-full border border-white/15 px-5 py-3 text-xs font-black"><Download className="size-4" />다운로드</a><button type="button" onClick={resetForNewFile} className="rounded-full border border-white/15 px-5 py-3 text-xs font-black">새 파일로 다시 하기</button></div></div>}
  </div>;
}
