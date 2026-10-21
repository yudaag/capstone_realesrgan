'use client';

import { useEffect, useRef, useState } from 'react';
import { Download, ImageUp, LoaderCircle, Sparkles } from 'lucide-react';

type Job = { id: string; status: string; progress: number; media_type: 'image' | 'video'; error_message?: string };
type User = { username: string } | null;

export function EnhancementWorkspace() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [user, setUser] = useState<User>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [stage, setStage] = useState('파일을 선택해 주세요.');
  const [busy, setBusy] = useState(false);

  useEffect(() => { fetch('/api/auth/me').then((r) => r.json()).then((d) => setUser(d.user || null)); }, []);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  async function choose(selected?: File) {
    if (!selected) return;
    if (!user && selected.type.startsWith('video/')) { setStage('영상 개선은 로그인 후 이용할 수 있습니다.'); return; }
    setFile(selected); setJob(null); setStage('업로드 준비 완료');
    if (preview) URL.revokeObjectURL(preview);
    setPreview(URL.createObjectURL(selected));
  }

  async function poll(id: string) {
    for (let count = 0; count < 180; count++) {
      const response = await fetch(`/api/jobs/${id}`, { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '상태 확인 실패');
      setJob(data.job); setStage(data.job.status === 'processing' ? `AI 처리 중 · ${data.job.progress || 0}%` : data.job.status);
      if (data.job.status === 'succeeded') { setStage('화질 개선이 완료되었습니다.'); return; }
      if (data.job.status === 'failed' || data.job.status === 'canceled') throw new Error(data.job.error_message || '처리에 실패했습니다.');
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    throw new Error('처리 시간이 길어지고 있습니다. 마이페이지에서 상태를 확인해 주세요.');
  }

  async function run() {
    if (!file || busy) return;
    setBusy(true);
    try {
      setStage('R2 업로드 주소 생성 중');
      const presign = await fetch('/api/uploads/presign', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: file.name, type: file.type, size: file.size }) });
      const upload = await presign.json();
      if (!presign.ok) throw new Error(upload.error || '업로드 준비 실패');
      setStage('파일 업로드 중');
      const put = await fetch(upload.uploadUrl, { method: 'PUT', headers: { 'Content-Type': file.type }, body: file });
      if (!put.ok) throw new Error('R2 업로드에 실패했습니다. 버킷 CORS 설정을 확인해 주세요.');
      setStage('AI 작업 생성 중');
      const create = await fetch('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ objectKey: upload.objectKey, mediaType: upload.mediaType, name: file.name, size: file.size, contentType: file.type }) });
      const created = await create.json();
      if (!create.ok) throw new Error(created.error || 'AI 작업 생성 실패');
      setJob({ id: created.id, status: created.status, progress: 5, media_type: upload.mediaType });
      await poll(created.id);
    } catch (error) { setStage(error instanceof Error ? error.message : '처리에 실패했습니다.'); }
    finally { setBusy(false); }
  }

  const finished = job?.status === 'succeeded';
  return <div className="max-w-[620px]">
    <div onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void choose(event.dataTransfer.files[0]); }} onClick={() => inputRef.current?.click()} className="cursor-pointer rounded-2xl border-2 border-[#5477ff] bg-[#14255d]/75 p-7 shadow-[0_0_55px_rgba(39,92,255,.18)] transition hover:bg-[#192d70] lg:p-9">
      <input ref={inputRef} type="file" accept={user ? 'image/jpeg,image/png,image/webp,video/mp4,video/quicktime' : 'image/jpeg,image/png,image/webp'} className="hidden" onChange={(event) => void choose(event.target.files?.[0])} />
      <div className="flex flex-col items-center text-center"><ImageUp className="size-10 text-white/90" strokeWidth={1.6} /><div className="mt-5 rounded-full bg-[#3867ff] px-7 py-3.5 text-sm font-extrabold shadow-[0_10px_30px_rgba(39,92,255,.35)]">이미지 또는 영상 업로드</div><p className="mt-5 text-lg font-bold">또는 여기에 끌어다 놓으세요</p><p className="mt-3 text-xs leading-5 text-white/45">{user ? 'JPG, PNG, WEBP, MP4, MOV · 최대 500MB' : '비로그인 체험 · JPG, PNG, WEBP · 최대 10MB'}</p></div>
    </div>
    {file && <div className="mt-5 rounded-2xl border border-white/10 bg-white/[.04] p-5"><div className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="truncate text-sm font-bold">{file.name}</p><p className="mt-1 text-xs text-white/40">{(file.size / 1024 / 1024).toFixed(2)}MB · {stage}</p></div><button onClick={run} disabled={busy} className="flex shrink-0 items-center gap-2 rounded-full bg-[#3867ff] px-5 py-3 text-xs font-black disabled:opacity-50">{busy ? <LoaderCircle className="size-4 animate-spin" /> : <Sparkles className="size-4" />}화질 개선</button></div></div>}
    {finished && job && <div className="mt-5 overflow-hidden rounded-2xl border border-[#5278ff] bg-[#090d1b] p-5"><div className="grid gap-3 sm:grid-cols-2">{job.media_type === 'image' ? <><img src={`/api/jobs/${job.id}/file?kind=original`} alt="원본" className="aspect-video w-full rounded-xl object-contain bg-black" /><img src={`/api/jobs/${job.id}/file?kind=result`} alt="개선 결과" className="aspect-video w-full rounded-xl object-contain bg-black" /></> : <><video src={`/api/jobs/${job.id}/file?kind=original`} controls className="aspect-video w-full rounded-xl bg-black" /><video src={`/api/jobs/${job.id}/file?kind=result`} controls className="aspect-video w-full rounded-xl bg-black" /></>}</div><div className="mt-4 flex gap-2"><a href={`/compare/${job.id}`} className="rounded-full bg-[#3867ff] px-5 py-3 text-xs font-black">결과 비교</a><a href={`/api/jobs/${job.id}/download`} className="flex items-center gap-2 rounded-full border border-white/15 px-5 py-3 text-xs font-black"><Download className="size-4" />다운로드</a></div></div>}
  </div>;
}
