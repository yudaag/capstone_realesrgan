'use client';

import { useEffect, useRef, useState } from 'react';
import { Download, Layers3 } from 'lucide-react';

export function CompareViewer({ id }: { id: string }) {
  const [job, setJob] = useState<{ media_type: 'image' | 'video'; original_name: string } | null>(null);
  const [position, setPosition] = useState(50);
  const [originalSize, setOriginalSize] = useState('확인 중');
  const [resultSize, setResultSize] = useState('확인 중');
  const [resultDimensions, setResultDimensions] = useState<{ width: number; height: number } | null>(null);
  const originalVideoRef = useRef<HTMLVideoElement>(null);
  const resultVideoRef = useRef<HTMLVideoElement>(null);
  const [originalVideoSize, setOriginalVideoSize] = useState('확인 중');
  const [resultVideoSize, setResultVideoSize] = useState('확인 중');

  function syncTime() {
    const original = originalVideoRef.current;
    const result = resultVideoRef.current;
    if (!original || !result || !Number.isFinite(original.currentTime)) return;
    if (Math.abs(result.currentTime - original.currentTime) > 0.05) result.currentTime = original.currentTime;
  }

  function syncPlay() {
    syncTime();
    void resultVideoRef.current?.play().catch(() => undefined);
  }

  function syncPause() {
    resultVideoRef.current?.pause();
    syncTime();
  }
  useEffect(() => { fetch(`/api/jobs/${id}`).then((r) => r.json()).then((data) => setJob(data.job || null)); }, [id]);
  if (!job) return <main className="grid min-h-screen place-items-center bg-black text-white">결과를 불러오는 중...</main>;
  return <main className="min-h-screen bg-black px-6 py-10 text-white">
    <div className="mx-auto max-w-6xl"><a href="/mypage" className="flex items-center gap-2 font-black"><span className="grid size-9 place-items-center rounded-lg bg-[#275cff]"><Layers3 className="size-5" /></span>DeepUp</a><p className="mt-14 text-xs font-black tracking-[.2em] text-[#6f91ff]">BEFORE &amp; AFTER</p><div className="mt-3 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><h1 className="text-4xl font-black">결과 비교</h1><p className="mt-3 text-sm text-white/45">{job.original_name}</p></div><a href={`/api/jobs/${id}/download`} className="flex items-center gap-2 rounded-full bg-[#3867ff] px-5 py-3 text-xs font-black"><Download className="size-4" />결과 다운로드</a></div>
      {job.media_type === 'image' ? <><div className="relative mx-auto mt-10 overflow-hidden rounded-3xl border border-white/15 bg-[#080808]" style={{ width: resultDimensions ? `${resultDimensions.width}px` : '100%', maxWidth: '100%', aspectRatio: resultDimensions ? `${resultDimensions.width} / ${resultDimensions.height}` : '16 / 9' }}><img src={`/api/jobs/${id}/file?kind=result`} alt="개선 결과" onLoad={(event) => { const { naturalWidth, naturalHeight } = event.currentTarget; setResultSize(`${naturalWidth}×${naturalHeight}`); setResultDimensions({ width: naturalWidth, height: naturalHeight }); }} className="absolute inset-0 size-full" /><img src={`/api/jobs/${id}/file?kind=original`} alt="원본" onLoad={(event) => setOriginalSize(`${event.currentTarget.naturalWidth}×${event.currentTarget.naturalHeight}`)} className="absolute inset-0 size-full" style={{ clipPath: `inset(0 ${100 - position}% 0 0)`, imageRendering: 'pixelated' }} /><div className="absolute inset-y-0 w-0.5 bg-white" style={{ left: `${position}%` }} /><input aria-label="원본과 결과 비교 위치" type="range" min="0" max="100" value={position} onChange={(event) => setPosition(Number(event.target.value))} className="absolute inset-0 size-full cursor-ew-resize opacity-0" /><span className="absolute left-4 top-4 rounded-full bg-black/65 px-3 py-1.5 text-xs font-bold">원본 · {originalSize}</span><span className="absolute right-4 top-4 rounded-full bg-[#275cff]/90 px-3 py-1.5 text-xs font-bold">개선 결과 · {resultSize}</span></div><p className="mt-3 text-center text-xs text-white/35">결과 파일의 실제 픽셀 크기로 표시됩니다.</p><div className="mt-4 flex flex-wrap justify-center gap-2 text-xs font-bold"><a href={`/api/jobs/${id}/file?kind=original`} target="_blank" rel="noreferrer" className="rounded-full border border-white/15 px-4 py-2.5">원본 파일 열기</a><a href={`/api/jobs/${id}/file?kind=result`} target="_blank" rel="noreferrer" className="rounded-full border border-[#5278ff] bg-[#12204b] px-4 py-2.5 text-[#a9baff]">결과 파일 열기</a></div></> : <><p className="mt-10 text-center text-xs text-white/40">왼쪽 원본 영상을 조작하면 오른쪽 결과 영상도 같은 시점으로 재생됩니다.</p><div className="mt-4 grid gap-4 md:grid-cols-2"><div><p className="mb-3 flex items-center justify-between text-sm font-bold"><span>원본</span><span className="text-xs font-medium text-white/40">{originalVideoSize}</span></p><video ref={originalVideoRef} src={`/api/jobs/${id}/file?kind=original`} controls playsInline onPlay={syncPlay} onPause={syncPause} onSeeking={syncTime} onTimeUpdate={syncTime} onRateChange={() => { if (resultVideoRef.current && originalVideoRef.current) resultVideoRef.current.playbackRate = originalVideoRef.current.playbackRate; }} onLoadedMetadata={(event) => setOriginalVideoSize(`${event.currentTarget.videoWidth}×${event.currentTarget.videoHeight}`)} className="aspect-video w-full bg-[#080808] object-contain" /></div><div><p className="mb-3 flex items-center justify-between text-sm font-bold text-[#8da6ff]"><span>개선 결과</span><span className="text-xs font-medium text-[#8da6ff]/60">{resultVideoSize}</span></p><video ref={resultVideoRef} src={`/api/jobs/${id}/file?kind=result`} playsInline muted onLoadedMetadata={(event) => setResultVideoSize(`${event.currentTarget.videoWidth}×${event.currentTarget.videoHeight}`)} className="aspect-video w-full bg-[#080808] object-contain" /></div></div><div className="mt-4 flex flex-wrap justify-center gap-2 text-xs font-bold"><a href={`/api/jobs/${id}/file?kind=original`} target="_blank" rel="noreferrer" className="rounded-full border border-white/15 px-4 py-2.5">원본 실제 크기로 열기</a><a href={`/api/jobs/${id}/file?kind=result`} target="_blank" rel="noreferrer" className="rounded-full border border-[#5278ff] bg-[#12204b] px-4 py-2.5 text-[#a9baff]">결과 실제 크기로 열기</a></div></>}
    </div>
  </main>;
}
