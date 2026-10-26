'use client';

import { useEffect, useState } from 'react';
import { Download, Layers3 } from 'lucide-react';

export function CompareViewer({ id }: { id: string }) {
  const [job, setJob] = useState<{ media_type: 'image' | 'video'; original_name: string } | null>(null);
  const [position, setPosition] = useState(50);
  const [originalSize, setOriginalSize] = useState('확인 중');
  const [resultSize, setResultSize] = useState('확인 중');
  useEffect(() => { fetch(`/api/jobs/${id}`).then((r) => r.json()).then((data) => setJob(data.job || null)); }, [id]);
  if (!job) return <main className="grid min-h-screen place-items-center bg-black text-white">결과를 불러오는 중...</main>;
  return <main className="min-h-screen bg-black px-6 py-10 text-white">
    <div className="mx-auto max-w-6xl"><a href="/mypage" className="flex items-center gap-2 font-black"><span className="grid size-9 place-items-center rounded-lg bg-[#275cff]"><Layers3 className="size-5" /></span>DeepUp</a><p className="mt-14 text-xs font-black tracking-[.2em] text-[#6f91ff]">BEFORE &amp; AFTER</p><div className="mt-3 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><h1 className="text-4xl font-black">결과 비교</h1><p className="mt-3 text-sm text-white/45">{job.original_name}</p></div><a href={`/api/jobs/${id}/download`} className="flex items-center gap-2 rounded-full bg-[#3867ff] px-5 py-3 text-xs font-black"><Download className="size-4" />결과 다운로드</a></div>
      {job.media_type === 'image' ? <><div className="relative mt-10 aspect-video overflow-hidden rounded-3xl border border-white/15 bg-[#080808]"><img src={`/api/jobs/${id}/file?kind=result`} alt="개선 결과" onLoad={(event) => setResultSize(`${event.currentTarget.naturalWidth}×${event.currentTarget.naturalHeight}`)} className="absolute inset-0 size-full object-contain" /><div className="absolute inset-y-0 left-0 overflow-hidden" style={{ width: `${position}%` }}><img src={`/api/jobs/${id}/file?kind=original`} alt="원본" onLoad={(event) => setOriginalSize(`${event.currentTarget.naturalWidth}×${event.currentTarget.naturalHeight}`)} className="h-full max-w-none object-contain" style={{ width: 'calc(100vw - 3rem)', maxWidth: '72rem' }} /></div><div className="absolute inset-y-0 w-0.5 bg-white" style={{ left: `${position}%` }} /><input aria-label="원본과 결과 비교 위치" type="range" min="0" max="100" value={position} onChange={(event) => setPosition(Number(event.target.value))} className="absolute inset-0 size-full cursor-ew-resize opacity-0" /><span className="absolute left-4 top-4 rounded-full bg-black/65 px-3 py-1.5 text-xs font-bold">원본 · {originalSize}</span><span className="absolute right-4 top-4 rounded-full bg-[#275cff]/90 px-3 py-1.5 text-xs font-bold">개선 결과 · {resultSize}</span></div><div className="mt-4 flex flex-wrap gap-2 text-xs font-bold"><a href={`/api/jobs/${id}/file?kind=original`} target="_blank" rel="noreferrer" className="rounded-full border border-white/15 px-4 py-2.5">원본 실제 크기로 보기</a><a href={`/api/jobs/${id}/file?kind=result`} target="_blank" rel="noreferrer" className="rounded-full border border-[#5278ff] bg-[#12204b] px-4 py-2.5 text-[#a9baff]">결과 실제 크기로 보기</a></div></> : <div className="mt-10 grid gap-4 md:grid-cols-2"><div><p className="mb-3 text-sm font-bold">원본</p><video src={`/api/jobs/${id}/file?kind=original`} controls className="aspect-video w-full rounded-2xl bg-[#080808]" /></div><div><p className="mb-3 text-sm font-bold text-[#8da6ff]">개선 결과</p><video src={`/api/jobs/${id}/file?kind=result`} controls className="aspect-video w-full rounded-2xl bg-[#080808]" /></div></div>}
    </div>
  </main>;
}
