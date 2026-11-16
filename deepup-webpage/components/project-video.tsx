'use client';

import { useEffect, useRef, useState } from 'react';

export function ProjectVideo() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = true;
    void video.play().catch(() => undefined);
  }, []);

  return <div className="relative h-full w-full">
    <video
      ref={videoRef}
      aria-label="알고리즘 적용 과정 영상"
      className="h-full w-full object-contain"
      autoPlay
      muted
      loop
      playsInline
      controls
      preload="auto"
      onCanPlay={() => { setError(false); void videoRef.current?.play().catch(() => undefined); }}
      onError={() => setError(true)}
    >
      <source src="/capstone-presentation.mp4" type="video/mp4" />
      이 브라우저에서는 영상을 재생할 수 없습니다.
    </video>
    {error && <div className="absolute inset-0 grid place-items-center bg-[#080b12] px-8 text-center text-sm font-bold text-white/60">발표 영상을 불러오지 못했습니다.<br />잠시 후 새로고침해 주세요.</div>}
  </div>;
}
