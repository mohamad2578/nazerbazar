import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { cx } from "./ui";

/** نوار افقی استاندارد: لغزش با snap و دکمه‌های پیمایش کنار عنوان بخش.
 *  دکمه‌ها عمدا روی کارت‌ها نمی‌افتند تا متن را نپوشانند. با چیدمان راست‌به‌چپ سازگار است. */
export default function Carousel({ title, children, className, itemClass }: {
  /** عنوان بخش؛ دکمه‌های پیمایش کنار همین عنوان می‌نشینند */
  title?: ReactNode;
  children: ReactNode;
  className?: string;
  /** کلاس عرض هر آیتم؛ پیش‌فرض برای کارت‌های باریک تنظیم شده است */
  itemClass?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [edge, setEdge] = useState({ start: true, end: true });

  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    const x = Math.abs(el.scrollLeft);
    setEdge({ start: x <= 2, end: max <= 2 || x >= max - 2 });
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    update();
    el.addEventListener("scroll", update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      ro.disconnect();
    };
  }, [update]);

  const page = (forward: boolean) => {
    const el = ref.current;
    if (!el) return;
    // در راست‌به‌چپ، حرکت رو به جلو یعنی کاهش scrollLeft
    const rtl = getComputedStyle(el).direction === "rtl";
    const step = el.clientWidth * 0.85 * (forward ? 1 : -1) * (rtl ? -1 : 1);
    el.scrollBy({ left: step, behavior: "smooth" });
  };

  const hasOverflow = !(edge.start && edge.end);

  return (
    <div className={className}>
      {(title || hasOverflow) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title ? <h2 className="font-semibold">{title}</h2> : <span />}
          {hasOverflow && (
            <div className="flex shrink-0 gap-1.5">
              <NavButton dir="prev" disabled={edge.start} onClick={() => page(false)} />
              <NavButton dir="next" disabled={edge.end} onClick={() => page(true)} />
            </div>
          )}
        </div>
      )}

      <div>
        <div
          ref={ref}
          className={cx(
            "-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-smooth px-4 pb-1",
            "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
            itemClass ?? "[&>*]:w-44 [&>*]:shrink-0 [&>*]:snap-start",
          )}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

function NavButton({ dir, disabled, onClick }: { dir: "prev" | "next"; disabled: boolean; onClick: () => void }) {
  const Icon = dir === "next" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={dir === "next" ? "موارد بعدی" : "موارد قبلی"}
      className={cx(
        "grid size-8 place-items-center rounded-full border border-line bg-surface text-ink",
        "transition hover:bg-surface-2 disabled:opacity-35",
      )}
    >
      <Icon className="size-4" />
    </button>
  );
}
