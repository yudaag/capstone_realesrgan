import { Download, Layers3, RefreshCw, Trash2 } from 'lucide-react';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { currentUserFromCookie, db } from '@/lib/auth';

export const dynamic = 'force-dynamic';

type Job = {
  id: string;
  media_type: 'image' | 'video';
  category: string;
  original_name: string;
  status: 'pending' | 'processing' | 'succeeded' | 'failed' | 'canceled';
  progress: number;
  file_size: number;
  source_width: number | null;
  source_height: number | null;
  result_width: number | null;
  result_height: number | null;
  duration_seconds: number | null;
  created_at: string;
  error_message: string | null;
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

export default async function MyPage() {
  const cookieStore = await cookies();
  const cookie = cookieStore.getAll().map(({ name, value }) => `${name}=${value}`).join('; ');
  const user = await currentUserFromCookie(cookie);
  if (!user) redirect('/login');

  let jobs: Job[] = [];
  try {
    const result = await db().prepare('SELECT * FROM processing_jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT 50').bind(user.id).all<Job>();
    jobs = result.results;
  } catch {
    // 첫 배포에서 0002 마이그레이션을 적용하기 전에도 빈 화면을 안전하게 표시한다.
  }

  const completed = jobs.filter((job) => job.status === 'succeeded').length;
  const active = jobs.filter((job) => job.status === 'pending' || job.status === 'processing').length;
  const storedBytes = jobs.reduce((sum, job) => sum + (job.file_size || 0), 0);
  const storedGb = storedBytes / 1024 / 1024 / 1024;

  return <main className="min-h-screen bg-black text-white">
    <header className="border-b border-white/10 bg-[#080808]">
      <div className="mx-auto flex h-[72px] max-w-[1600px] items-center justify-between px-6 lg:px-12">
        <a href="/" className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-lg bg-[#275cff]"><Layers3 className="size-5" /></span><span className="text-lg font-black">DeepUp</span></a>
        <nav className="flex items-center gap-2 text-xs font-bold"><a href="/#service" className="rounded-full border border-white/15 px-5 py-2.5">화질 개선</a><span className="rounded-full border border-[#5278ff] bg-[#12204b] px-5 py-2.5 text-[#9bb0ff]">마이페이지</span><span className="hidden rounded-full border border-white/15 px-5 py-2.5 sm:block">{user.username}</span></nav>
      </div>
    </header>

    <div className="mx-auto max-w-[1600px] px-6 py-16 lg:px-12 lg:py-20">
      <p className="text-xs font-black tracking-[.22em] text-[#6f91ff]">MY PAGE</p>
      <h1 className="mt-5 text-4xl font-black tracking-[-.05em] lg:text-5xl">내 <span className="text-[#5f83ff]">화질 개선</span> 작업 내역</h1>
      <p className="mt-5 text-sm text-white/45">업로드한 이미지·영상의 처리 상태와 결과를 확인하고 다시 내려받을 수 있습니다.</p>

      <section className="mt-12 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[['전체 작업', jobs.length, '건'], ['완료', completed, '건'], ['처리 중 / 대기', active, '건']].map(([label, value, unit]) => <article key={String(label)} className="rounded-2xl border border-white/10 bg-[#0b0b0d] p-7"><p className="text-xs font-bold text-white/45">{label}</p><p className="mt-6 text-3xl font-black">{value}<span className="ml-1 text-sm text-white/40">{unit}</span></p></article>)}
        <article className="rounded-2xl border border-white/10 bg-[#0b0b0d] p-7"><p className="text-xs font-bold text-white/45">저장 공간</p><p className="mt-6 text-3xl font-black">{storedGb.toFixed(2)}<span className="ml-1 text-sm text-white/40">/ 5GB</span></p><div className="mt-5 h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-[#3867ff]" style={{ width: `${Math.min(100, storedGb / 5 * 100)}%` }} /></div></article>
      </section>

      <section className="mt-16">
        <div className="flex flex-col justify-between gap-5 md:flex-row md:items-center"><h2 className="text-2xl font-black">처리 이력</h2><div className="flex flex-wrap gap-2 text-xs font-bold"><span className="rounded-full border border-[#5278ff] bg-[#12204b] px-5 py-2.5 text-[#9bb0ff]">전체</span><span className="rounded-full border border-white/15 px-5 py-2.5">이미지</span><span className="rounded-full border border-white/15 px-5 py-2.5">영상</span><span className="rounded-full border border-white/15 px-5 py-2.5">최신순</span></div></div>

        <div className="mt-6 space-y-3">
          {jobs.length === 0 && <div className="rounded-2xl border border-dashed border-white/15 px-6 py-20 text-center"><p className="font-bold">아직 처리 이력이 없습니다.</p><a href="/#service" className="mt-5 inline-block rounded-full bg-[#3867ff] px-6 py-3 text-sm font-bold">첫 화질 개선 시작하기</a></div>}
          {jobs.map((job) => <article key={job.id} className="grid gap-5 rounded-2xl border border-white/10 bg-[#0b0b0d] p-5 md:grid-cols-[minmax(0,1fr)_170px_170px] md:items-center">
            <div className="min-w-0"><div className="flex items-center gap-2"><span className="rounded-full border border-[#4565c5] bg-[#111c3e] px-2.5 py-1 text-[10px] font-bold text-[#8fa8ff]">{job.category}</span><span className="text-[10px] text-white/40">{job.media_type === 'image' ? '이미지' : '영상'}</span></div><h3 className="mt-3 truncate font-extrabold">{job.original_name}</h3><p className="mt-2 text-xs text-white/38">{resolution(job)}{job.duration_seconds ? ` · ${job.duration_seconds}초` : ''}</p></div>
            <div><p className="text-[10px] text-white/35">처리 일시</p><p className="mt-2 text-xs font-bold">{dateText(job.created_at)}</p><p className={`mt-3 text-xs font-black ${job.status === 'succeeded' ? 'text-emerald-400' : job.status === 'failed' ? 'text-red-400' : 'text-[#6f91ff]'}`}>{statusLabel[job.status]}{job.status === 'processing' ? ` ${job.progress}%` : ''}</p>{job.status === 'processing' && <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/10"><div className="h-full bg-[#3867ff]" style={{ width: `${job.progress}%` }} /></div>}</div>
            <div className="flex flex-wrap justify-start gap-2 md:justify-end">{job.status === 'succeeded' && <><a href={`/compare/${job.id}`} className="rounded-full bg-[#3867ff] px-4 py-2.5 text-xs font-bold">결과 비교</a><a href={`/api/jobs/${job.id}/download`} className="rounded-full border border-white/15 p-2.5" aria-label="다운로드"><Download className="size-4" /></a></>}{job.status === 'failed' && <form action={`/api/jobs/${job.id}/retry`} method="post"><button className="rounded-full border border-white/15 p-2.5" aria-label="다시 시도"><RefreshCw className="size-4" /></button></form>}<button className="rounded-full border border-white/15 p-2.5 text-white/45" aria-label="삭제"><Trash2 className="size-4" /></button></div>
          </article>)}
        </div>
      </section>
    </div>
  </main>;
}
