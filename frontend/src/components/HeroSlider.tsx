import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { cx } from "./ui";

type Slide = {
  id: number;
  title: string;
  subtitle: string;
  image: string;
  link_url: string;
  link_label: string;
  order: number;
  is_active: boolean;
};

/** اسلایدشوی تبلیغاتی/اطلاع‌رسانی صفحه اصلی؛ داده از /api/public/slides/ (مدیریت از پنل مدیر کل). */
export default function HeroSlider() {
  const q = useQuery({ queryKey: ["slides"], queryFn: () => api.get<Slide[]>("/public/slides/"), staleTime: 300_000 });
  const slides = q.data ?? [];
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const touchStart = useRef<number | null>(null);
  const total = slides.length;

  const next = () => setIndex((i) => (i + 1) % total);
  const prev = () => setIndex((i) => (i - 1 + total) % total);

  useEffect(() => {
    if (total <= 1 || paused) return;
    const t = setInterval(next, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [total, paused, index]);

  useEffect(() => {
    if (index >= total) setIndex(0);
  }, [total, index]);

  // کالای تبلیغاتی اختیاری است: در نبود اسلاید یا خطا، چیزی نمایش داده نمی‌شود تا صفحه اصلی شلوغ نشود
  if (q.isLoading) return <div className="h-48 animate-pulse rounded-3xl bg-surface-2 sm:h-64" />;
  if (!total) return null;

  const s = slides[index];
  const isExternal = /^https?:\/\//.test(s.link_url);

  return (
    <div
      className="group relative select-none overflow-hidden rounded-3xl border border-line bg-ink shadow-card"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onTouchStart={(e) => {
        setPaused(true);
        touchStart.current = e.targetTouches[0].clientX;
      }}
      onTouchEnd={(e) => {
        setPaused(false);
        if (touchStart.current == null) return;
        const dx = touchStart.current - e.changedTouches[0].clientX;
        if (dx > 45) next();
        else if (dx < -45) prev();
        touchStart.current = null;
      }}
      role="region"
      aria-roledescription="carousel"
      aria-label="اطلاعیه‌ها و بنرهای صفحه اصلی"
    >
      <div className="relative aspect-[16/10] max-h-[22rem] min-h-[13rem] w-full sm:aspect-[21/9]">
        {slides.map((slide, i) => (
          <div key={slide.id} className={cx("absolute inset-0 transition-opacity duration-700", i === index ? "z-10 opacity-100" : "pointer-events-none z-0 opacity-0")} aria-hidden={i !== index}>
            <img src={slide.image} alt="" loading={i === 0 ? "eager" : "lazy"} className="size-full object-cover" onError={(e) => (e.currentTarget.style.display = "none")} />
            <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent sm:bg-gradient-to-l sm:from-black/85 sm:via-black/40 sm:to-transparent" />
            <div className="absolute inset-0 z-20 flex max-w-xl flex-col justify-end p-5 text-white sm:justify-center sm:p-10">
              <h2 className="text-balance text-lg font-bold leading-snug drop-shadow sm:text-2xl">{slide.title}</h2>
              {slide.subtitle && <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-white/85 sm:text-sm">{slide.subtitle}</p>}
              {slide.link_url && (
                <div className="mt-4">
                  {isExternal ? (
                    <a href={slide.link_url} target="_blank" rel="noreferrer" className="inline-flex h-11 items-center gap-2 rounded-xl bg-brand px-4 text-sm font-medium text-brand-ink">
                      {slide.link_label || "مشاهده"} <ArrowLeft className="size-4" />
                    </a>
                  ) : (
                    <Link to={slide.link_url} className="inline-flex h-11 items-center gap-2 rounded-xl bg-brand px-4 text-sm font-medium text-brand-ink">
                      {slide.link_label || "مشاهده"} <ArrowLeft className="size-4" />
                    </Link>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {total > 1 && (
        <>
          <div className="pointer-events-none absolute inset-x-3 top-1/2 z-30 hidden -translate-y-1/2 justify-between opacity-0 transition-opacity group-hover:opacity-100 sm:flex">
            <button onClick={prev} aria-label="اسلاید قبلی" className="pointer-events-auto grid size-10 place-items-center rounded-full border border-white/20 bg-black/40 text-white backdrop-blur">
              <ChevronRight className="size-5" />
            </button>
            <button onClick={next} aria-label="اسلاید بعدی" className="pointer-events-auto grid size-10 place-items-center rounded-full border border-white/20 bg-black/40 text-white backdrop-blur">
              <ChevronLeft className="size-5" />
            </button>
          </div>
          <div className="absolute inset-x-0 bottom-3 z-30 flex justify-center gap-1.5">
            {slides.map((_, i) => (
              <button key={i} onClick={() => setIndex(i)} aria-label={`اسلاید ${i + 1}`} className="grid h-6 w-6 place-items-center">
                <span className={cx("block h-1.5 rounded-full transition-all", i === index ? "w-5 bg-brand" : "w-1.5 bg-white/50")} />
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
