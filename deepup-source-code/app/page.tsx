import { ArrowRight, BarChart3, ImageUp, Layers3, ScanSearch, Sparkles } from 'lucide-react';
import { AccountMenu } from '@/components/account-menu';

export default function Home() {
  return (
    <main className="min-h-screen bg-black text-white">
      <header className="border-b border-white/10 bg-[#080808]">
        <div className="mx-auto flex h-[72px] max-w-[1600px] items-center justify-between px-6 lg:px-12">
          <a href="#" className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-lg bg-[#275cff]"><Layers3 className="size-5" /></span>
            <span className="text-lg font-black tracking-[-.04em]">DeepUp</span>
          </a>
          <nav className="hidden items-center gap-9 text-[13px] font-semibold text-white/65 md:flex">
            <a className="text-white" href="#service">서비스</a>
            <a href="#technology">기술 소개</a>
            <a href="#process">프로젝트 과정</a>
            <a href="#team">팀 소개</a>
          </nav>
          <AccountMenu />
        </div>
      </header>

      <section id="service" className="relative overflow-hidden border-b border-white/10">
        <div className="hero-glow absolute inset-0 opacity-80" />
        <div className="relative mx-auto grid min-h-[calc(100vh-72px)] max-w-[1600px] gap-14 px-6 py-16 lg:grid-cols-[.8fr_1.2fr] lg:items-center lg:px-12 xl:gap-24">
          <div>
            <div className="mb-8 flex items-center gap-3 text-sm font-bold text-white/80"><span className="grid size-8 place-items-center rounded-md bg-[#275cff]"><Sparkles className="size-4" /></span>AI IMAGE &amp; VIDEO ENHANCEMENT</div>
            <h1 className="max-w-[650px] text-[clamp(48px,6vw,92px)] font-black leading-[1.02] tracking-[-.065em]">
              깊이를 이해하는<br />
              <span className="text-[#6f91ff]">AI 화질 개선</span>
            </h1>
            <p className="mt-7 max-w-xl text-base leading-7 text-white/58 lg:text-lg">이미지와 영상의 깊이 정보를 분석해 중요한 영역은 더 선명하게, 배경은 더 자연스럽게 개선합니다.</p>

            <div className="mt-10 max-w-[620px] rounded-2xl border-2 border-[#5477ff] bg-[#14255d]/75 p-7 shadow-[0_0_55px_rgba(39,92,255,.18)] lg:p-9">
              <div className="flex flex-col items-center text-center">
                <ImageUp className="size-10 text-white/90" strokeWidth={1.6} />
                <div className="mt-5 rounded-full bg-[#3867ff] px-7 py-3.5 text-sm font-extrabold shadow-[0_10px_30px_rgba(39,92,255,.35)]">이미지 또는 영상 업로드</div>
                <p className="mt-5 text-lg font-bold">또는 여기에 끌어다 놓으세요</p>
                <p className="mt-3 text-xs leading-5 text-white/45">JPG, PNG, WEBP, MP4, MOV · 최대 500MB</p>
              </div>
            </div>
          </div>

          <div className="lg:pt-16">
            <div className="mb-5 flex items-end justify-between">
              <div><p className="text-xs font-bold tracking-[.18em] text-[#6f91ff]">PROJECT VIDEO</p><h2 className="mt-2 text-2xl font-extrabold tracking-[-.03em]">캡스톤 프로젝트 발표 영상</h2></div>
              <span className="hidden rounded-full border border-white/15 px-3 py-1.5 text-[10px] font-bold text-white/55 sm:block">CAPSTONE</span>
            </div>
            <div className="relative aspect-video overflow-hidden rounded-[26px] border border-white/15 bg-[#101828] shadow-[0_30px_90px_rgba(0,0,0,.5)]">
              <video src="/capstone-presentation.mp4" aria-label="캡스톤 프로젝트 발표 영상" className="h-full w-full object-contain" autoPlay muted loop playsInline controls />
            </div>
            <p className="mt-4 text-xs leading-5 text-white/40">깊이 정보를 활용한 선택적 화질 개선 프로젝트의 기획 배경과 구현 방향을 소개합니다.</p>
          </div>
        </div>
      </section>

      <section id="technology" className="mx-auto max-w-[1600px] px-6 py-24 lg:px-12 lg:py-32">
        <div className="grid gap-12 lg:grid-cols-[.72fr_1.28fr]">
          <div><p className="text-xs font-black tracking-[.2em] text-[#6f91ff]">WHY WE STARTED</p><h2 className="mt-5 text-4xl font-black leading-tight tracking-[-.05em] lg:text-5xl">선명함만으로는<br />충분하지 않았습니다.</h2><p className="mt-6 max-w-md text-sm leading-7 text-white/48">기존 AI 업스케일링은 저해상도 이미지의 질감과 윤곽을 복원하는 데 뛰어나지만, 장면의 깊이와 3D 구조, 원근감을 직접 이해하지는 못합니다.</p></div>
          <div className="rounded-[28px] border border-white/10 bg-[#0b0b0c] p-7 lg:p-10">
            <div className="grid gap-7 sm:grid-cols-2"><div><span className="text-[10px] font-black tracking-[.16em] text-red-300">PROBLEM 01</span><h3 className="mt-3 text-xl font-extrabold">모든 영역을 동일하게 복원</h3><p className="mt-3 text-sm leading-6 text-white/45">가까운 핵심 피사체와 멀리 있는 배경에 같은 수준의 선명화를 적용하면, 배경의 나무나 건물까지 불필요하게 또렷해져 화면의 깊이감이 약해질 수 있습니다.</p></div><div><span className="text-[10px] font-black tracking-[.16em] text-red-300">PROBLEM 02</span><h3 className="mt-3 text-xl font-extrabold">공간 구조와 원근감 미반영</h3><p className="mt-3 text-sm leading-6 text-white/45">픽셀의 디테일 복원에 집중하기 때문에 객체 사이의 거리와 장면의 3차원 관계를 고려하지 못하고, 결과가 평면적이거나 부자연스럽게 보일 수 있습니다.</p></div></div>
            <div className="my-8 h-px bg-white/10" /><div className="flex flex-col gap-4 sm:flex-row sm:items-center"><span className="grid size-11 shrink-0 place-items-center rounded-xl bg-[#275cff]"><Layers3 className="size-5" /></span><div><p className="text-xs font-black text-[#8da6ff]">OUR APPROACH</p><p className="mt-1 text-sm font-bold leading-6">장면의 Depth map을 먼저 계산하고, 거리에 따라 개선 강도를 다르게 적용해 원근감은 유지하면서 필요한 영역만 선택적으로 복원합니다.</p></div></div>
          </div>
        </div>

        <div className="mt-20"><p className="text-xs font-black tracking-[.2em] text-[#6f91ff]">DEPTH-AWARE PROCESSING</p><h2 className="mt-4 text-3xl font-black tracking-[-.04em]">화면 속 거리를 읽고, 영역마다 다르게.</h2><div className="mt-8 grid gap-4 sm:grid-cols-3">{[['01', '전경', '인물·제품 등 핵심 피사체의 윤곽과 질감을 집중적으로 복원합니다.'], ['02', '중경', '장면의 구조와 자연스러운 디테일이 유지되도록 균형 있게 개선합니다.'], ['03', '배경', '과도한 선명화를 줄이고 노이즈를 억제해 깊이감과 원근감을 보존합니다.']].map(([num, title, desc]) => <article key={num} className="group rounded-2xl border border-white/10 bg-[#0b0b0c] p-7"><span className="text-xs font-black text-[#6f91ff]">{num}</span><h3 className="mt-10 text-xl font-extrabold">{title}</h3><p className="mt-3 text-xs leading-6 text-white/45">{desc}</p><ArrowRight className="mt-7 size-4 text-white/30" /></article>)}</div></div>
      </section>

      <section id="process" className="border-y border-white/10 bg-[#080808]">
        <div className="mx-auto max-w-[1600px] px-6 py-24 lg:px-12 lg:py-28"><p className="text-xs font-black tracking-[.2em] text-[#6f91ff]">PROJECT PIPELINE</p><div className="mt-4 flex flex-col justify-between gap-4 md:flex-row md:items-end"><h2 className="text-3xl font-black tracking-[-.04em] lg:text-4xl">입력부터 결과 평가까지,<br />프로젝트의 전체 과정</h2><p className="max-w-md text-sm leading-6 text-white/40">이미지는 한 장의 Depth를 계산하고, 영상은 프레임 단위로 깊이를 분석한 뒤 다시 하나의 결과 영상으로 결합합니다.</p></div>
          <div className="mt-12 grid gap-4 lg:grid-cols-5">
            {[
              ['01', '입력 및 전처리', '사용자가 이미지 또는 영상을 선택합니다. 영상은 프레임 단위로 분리하고, 크기와 색상 형식을 처리 모델에 맞게 정규화합니다.'],
              ['02', 'Depth 추정', '각 이미지 또는 프레임에서 상대적인 거리 정보를 계산해 가까운 영역과 먼 영역을 표현하는 Depth map을 생성합니다.'],
              ['03', '영역 분리·가중치', 'Depth 값을 기준으로 전경·중경·배경을 구분하고, 핵심 피사체에는 높은 개선 강도, 배경에는 낮은 강도를 배정합니다.'],
              ['04', '선택적 화질 복원', '영역별 가중치를 반영해 디테일을 복원합니다. 피사체는 또렷하게, 먼 배경은 노이즈와 과도한 선명화를 억제합니다.'],
              ['05', '재결합 및 평가', '처리된 프레임을 순서대로 결합해 영상을 생성하고, 원본과 비교해 선명도·자연스러움·깊이감과 처리 속도를 평가합니다.'],
            ].map(([num, title, desc]) => <article key={num} className="relative rounded-2xl border border-white/10 bg-[#0b0b0c] p-6"><div className="flex items-center justify-between"><span className="text-[10px] font-black text-[#6f91ff]">STEP {num}</span><Layers3 className="size-4 text-white/25" /></div><h3 className="mt-8 text-base font-extrabold">{title}</h3><p className="mt-3 text-xs leading-6 text-white/42">{desc}</p></article>)}
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-3"><div className="rounded-2xl border border-white/10 p-6"><BarChart3 className="size-5 text-[#6f91ff]" /><h3 className="mt-4 text-sm font-extrabold">정량 평가</h3><p className="mt-2 text-xs leading-5 text-white/40">해상도, 처리 시간, PSNR·SSIM 등 객관적 지표를 비교합니다.</p></div><div className="rounded-2xl border border-white/10 p-6"><ScanSearch className="size-5 text-[#6f91ff]" /><h3 className="mt-4 text-sm font-extrabold">시각 평가</h3><p className="mt-2 text-xs leading-5 text-white/40">피사체 디테일, 배경 자연스러움, 경계 왜곡과 원근감 유지 여부를 확인합니다.</p></div><div className="rounded-2xl border border-[#3159d9] bg-[#13204a] p-6"><Sparkles className="size-5 text-[#8da6ff]" /><h3 className="mt-4 text-sm font-extrabold">최종 목표</h3><p className="mt-2 text-xs leading-5 text-white/55">깊이 정보를 활용해 필요한 영역만 선택적으로 개선하는 웹 서비스를 완성합니다.</p></div></div>
        </div>
      </section>

      <footer id="team" className="mx-auto flex max-w-[1600px] flex-col justify-between gap-4 px-6 py-10 text-xs text-white/35 sm:flex-row lg:px-12"><span>© 2026 DeepUp Capstone Project</span><span>RealESRGAN × Monocular Depth Estimation</span></footer>
    </main>
  );
}
