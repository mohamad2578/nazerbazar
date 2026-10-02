import { createContext, useCallback, useContext, useEffect, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Inbox, Loader2, X } from "lucide-react";
import { groupDigits } from "../lib/format";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "soft";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
};

export function Button({ variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest }: BtnProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition active:scale-[.98] disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap",
        size === "sm" && "h-9 px-3 text-sm",
        size === "md" && "h-11 px-4 text-[15px]",
        size === "lg" && "h-12 px-5 text-base",
        variant === "primary" && "bg-brand text-brand-ink hover:bg-brand-strong",
        variant === "secondary" && "bg-surface text-ink border border-line hover:bg-surface-2",
        variant === "soft" && "bg-brand-soft text-brand hover:brightness-95",
        variant === "ghost" && "text-ink hover:bg-surface-2",
        variant === "danger" && "bg-danger text-white hover:brightness-110",
        className,
      )}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function Card({ className, children, ...rest }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div {...rest} className={cx("rounded-2xl bg-surface border border-line shadow-card", className)}>
      {children}
    </div>
  );
}

export function Field({ label, error, hint, children, className }: { label?: string; error?: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cx("block", className)}>
      {label && <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>}
      {children}
      {error ? <span className="mt-1 block text-xs text-danger">{error}</span> : hint ? <span className="mt-1 block text-xs text-muted">{hint}</span> : null}
    </label>
  );
}

const inputCls =
  "w-full rounded-xl border border-line bg-surface px-3.5 text-[15px] text-ink placeholder:text-muted/70 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 disabled:bg-surface-2";

export const Input = ({ className, ...p }: React.ComponentProps<"input">) => <input {...p} className={cx(inputCls, "h-11", className)} />;
export const Textarea = ({ className, ...p }: React.ComponentProps<"textarea">) => (
  <textarea {...p} className={cx(inputCls, "min-h-24 py-2.5", className)} />
);
export const Select = ({ className, children, ...p }: React.ComponentProps<"select">) => (
  <select {...p} className={cx(inputCls, "h-11 appearance-none bg-[length:1rem] pl-8", className)}>
    {children}
  </select>
);

/** ورودی قیمت به تومان با جداکننده هزارگان؛ مقدار خروجی رشته ارقام انگلیسی است */
export function PriceInput({ value, onChange, className, ...p }: { value: string; onChange: (v: string) => void } & Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  return (
    <div className="relative">
      <input
        {...p}
        inputMode="numeric"
        dir="ltr"
        value={groupDigits(value)}
        onChange={(e) => onChange(groupDigits(e.target.value).replace(/[^\d۰-۹]/g, "").replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))))}
        className={cx(inputCls, "h-11 pl-14 text-left tabular", className)}
      />
      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-xs text-muted">تومان</span>
    </div>
  );
}

type Tone = "neutral" | "brand" | "ok" | "warn" | "danger";
export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        tone === "neutral" && "bg-surface-2 text-muted",
        tone === "brand" && "bg-brand-soft text-brand",
        tone === "ok" && "bg-ok-soft text-ok",
        tone === "warn" && "bg-warn-soft text-warn",
        tone === "danger" && "bg-danger-soft text-danger",
        className,
      )}
    >
      {children}
    </span>
  );
}

export const STATUS_TONE: Record<string, Tone> = {
  active: "ok", pending: "warn", rejected: "danger", suspended: "danger",
  new: "warn", reviewing: "brand", inspection: "brand", resolved: "ok",
  assigned: "neutral", dispatched: "brand", received: "ok", sold_out: "neutral", canceled: "danger",
  draft: "neutral", closed: "neutral", critical: "danger", warning: "warn", info: "brand",
};

export const Spinner = ({ className }: { className?: string }) => <Loader2 className={cx("size-5 animate-spin text-brand", className)} />;

export function Loading({ label = "در حال بارگذاری…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted">
      <Spinner /> {label}
    </div>
  );
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <div className="mb-1 grid size-14 place-items-center rounded-2xl bg-surface-2 text-muted">{icon ?? <Inbox className="size-7" />}</div>
      <p className="font-medium">{title}</p>
      {children && <div className="max-w-sm text-sm text-muted">{children}</div>}
    </div>
  );
}

export function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-danger/30 bg-danger-soft p-4 text-sm text-danger">
      <AlertTriangle className="mt-0.5 size-5 shrink-0" />
      <div className="flex-1">
        <p>{(error as Error)?.message || "خطایی رخ داد."}</p>
        {retry && (
          <button onClick={retry} className="mt-2 font-medium underline">
            تلاش دوباره
          </button>
        )}
      </div>
    </div>
  );
}

export function Sheet({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[1000] flex items-end justify-center sm:items-center" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={onClose} />
      <div className={cx("relative flex max-h-[92dvh] w-full flex-col rounded-t-3xl bg-surface shadow-xl sm:rounded-3xl", wide ? "sm:max-w-3xl" : "sm:max-w-lg")}>
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-base font-semibold">{title}</h2>
          <button onClick={onClose} className="grid size-9 place-items-center rounded-full hover:bg-surface-2" aria-label="بستن">
            <X className="size-5" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="safe-bottom flex gap-2 border-t border-line px-5 pt-3">{footer}</div>}
      </div>
    </div>
  );
}

export function Stat({ label, value, sub, tone, icon }: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone; icon?: ReactNode }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted">{label}</span>
        {icon && (
          <span className={cx("grid size-8 place-items-center rounded-lg", tone === "danger" ? "bg-danger-soft text-danger" : tone === "warn" ? "bg-warn-soft text-warn" : tone === "ok" ? "bg-ok-soft text-ok" : "bg-brand-soft text-brand")}>
            {icon}
          </span>
        )}
      </div>
      <div className="mt-2 text-2xl font-bold tabular">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </Card>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Segmented<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[] }) {
  return (
    <div className="flex gap-1 overflow-x-auto rounded-xl bg-surface-2 p-1">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={cx("h-9 shrink-0 rounded-lg px-3 text-sm font-medium transition", value === o.value ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ─── Toast ───
type ToastT = { id: number; text: string; tone: "ok" | "danger" };
const ToastCtx = createContext<(text: string, tone?: "ok" | "danger") => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastT[]>([]);
  const push = useCallback((text: string, tone: "ok" | "danger" = "ok") => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, text, tone }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 3800);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-20 z-[1100] flex flex-col items-center gap-2 px-4 lg:bottom-6" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={cx("pointer-events-auto flex max-w-md items-center gap-2 rounded-2xl px-4 py-3 text-sm text-white shadow-lg", t.tone === "ok" ? "bg-[#12332e]" : "bg-danger")}>
            {t.tone === "ok" ? <CheckCircle2 className="size-5 shrink-0 text-[#5fd0c2]" /> : <AlertTriangle className="size-5 shrink-0" />}
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/** جدول واکنش‌گرا: در موبایل به کارت تبدیل می‌شود */
export type Column<T> = { key: string; label: string; render?: (row: T) => ReactNode; className?: string; hideOnMobile?: boolean };

export function DataTable<T extends { id?: number | string }>({ rows, columns, onRowClick, rowKey }: { rows: T[]; columns: Column<T>[]; onRowClick?: (r: T) => void; rowKey?: (r: T) => string | number }) {
  const val = (r: T, c: Column<T>) => (c.render ? c.render(r) : ((r as any)[c.key] ?? "—"));
  const keyOf = (r: T, i: number) => (rowKey ? rowKey(r) : (r.id ?? i));
  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-right text-xs text-muted">
              {columns.map((c) => (
                <th key={c.key} className={cx("px-4 py-3 font-medium", c.className)}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={keyOf(r, i)} onClick={() => onRowClick?.(r)} className={cx("border-b border-line/70 last:border-0", onRowClick && "cursor-pointer hover:bg-surface-2")}>
                {columns.map((c) => (
                  <td key={c.key} className={cx("px-4 py-3 align-middle", c.className)}>
                    {val(r, c)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="divide-y divide-line md:hidden">
        {rows.map((r, i) => (
          <div key={keyOf(r, i)} onClick={() => onRowClick?.(r)} className={cx("px-4 py-3", onRowClick && "active:bg-surface-2")}>
            <div className="mb-1.5 font-medium">{val(r, columns[0])}</div>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              {columns.slice(1).filter((c) => !c.hideOnMobile).map((c) => (
                <div key={c.key} className="flex min-w-0 items-center gap-1">
                  <dt className="shrink-0 text-muted">{c.label}:</dt>
                  <dd className="min-w-0 truncate">{val(r, c)}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
    </>
  );
}
