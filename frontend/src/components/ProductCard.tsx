import { ChevronLeft, Store } from "lucide-react";
import { Link } from "react-router-dom";
import { num, toman } from "../lib/format";

export type PublicProduct = {
  id: number;
  name: string;
  unit_display: string;
  image: string | null;
  union_name: string;
  county_name: string;
  category_name: string;
  official_price: number;
  min_allowed_price: number;
  price_changed_at: string | null;
  offers_count: number;
  min_price: number | null;
  previous_price?: number | null;
};

export function ProductThumb({ src, name, size = "size-14" }: { src?: string | null; name: string; size?: string }) {
  return src ? (
    <img src={src} alt="" loading="lazy" className={`${size} shrink-0 rounded-xl object-cover`} />
  ) : (
    <div className={`${size} grid shrink-0 place-items-center rounded-xl bg-brand-soft text-lg font-bold text-brand`}>{name.slice(0, 1)}</div>
  );
}

export default function ProductCard({ p }: { p: PublicProduct }) {
  return (
    <Link to={`/p/${p.id}`} className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-3 shadow-card transition hover:border-brand/40">
      <ProductThumb src={p.image} name={p.name} />
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{p.name}</div>
        <div className="mt-0.5 truncate text-xs text-muted">
          {p.union_name} · هر {p.unit_display}
        </div>
        <div className="mt-2 space-y-1">
          {p.min_price ? (
            <div className="inline-flex items-center gap-1 text-xs text-ok">
              <Store className="size-3.5 shrink-0" />
              <span>از <b className="tabular">{toman(p.min_price)}</b> در {num(p.offers_count)} فروشگاه</span>
            </div>
          ) : (
            <div className="text-xs text-muted">هنوز فروشگاهی قیمت نداده</div>
          )}
          <div className="flex items-baseline justify-between gap-2 border-t border-line pt-1 text-xs text-muted">
            <span>نرخ مصوب</span>
            <b className="tabular text-sm font-medium text-muted">{toman(p.official_price)}</b>
          </div>
        </div>
      </div>
      <ChevronLeft className="size-5 shrink-0 text-muted" />
    </Link>
  );
}
