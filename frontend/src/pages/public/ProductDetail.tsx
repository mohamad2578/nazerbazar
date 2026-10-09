import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BadgeCheck, ChevronLeft, Clock, Info, List, LocateFixed, Map as MapIcon, Phone, ShieldAlert, ShoppingBag, Star } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Directions from "../../components/Directions";
import { ProductThumb } from "../../components/ProductCard";
import Sparkline from "../../components/Sparkline";
import { Badge, Card, cx, Empty, ErrorBox, Loading, Segmented } from "../../components/ui";
import { api } from "../../lib/api";
import { ago, km, num, telLink, toman } from "../../lib/format";
import { useGeo } from "../../lib/prefs";

const MapView = lazy(() => import("../../components/MapView"));

export type Offer = {
  id: number;
  price: number;
  discount_percent: number;
  confirmed_at: string;
  pending_update: boolean;
  distance_km: number | null;
  shop_products: number;
  store: {
    id: number; name: string; address: string; phone: string; lat: string | null; lng: string | null;
    working_hours: string; is_verified: boolean; rating_avg: string; rating_count: number; photo: string | null;
  };
};

type Detail = {
  id: number; name: string; unit_display: string; image: string | null; union_name: string; union_phone: string;
  county_name: string; description: string; official_price: number; min_allowed_price: number; max_discount_percent: number;
  price_changed_at: string | null; offers: Offer[]; offers_count: number; min_price: number | null; avg_price: number | null;
  history: { price: number; created_at: string }[];
};

export default function ProductDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const geo = useGeo();
  const [view, setView] = useState<"list" | "map">("list");
  const [sort, setSort] = useState<"price" | "distance">("price");
  const q = useQuery({
    queryKey: ["product", id, geo.pos?.lat, geo.pos?.lng, sort],
    queryFn: () => api.get<Detail>(`/public/products/${id}/`, { lat: geo.pos?.lat, lng: geo.pos?.lng, sort }),
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;
  const p = q.data!;
  const history = p.history.map((h) => h.price);

  return (
    <div className="space-y-4">
      <button onClick={() => (window.history.length > 1 ? nav(-1) : nav("/"))} className="inline-flex items-center gap-1 text-sm text-muted">
        <ArrowRight className="size-4" /> بازگشت
      </button>

      <Card className="p-4 sm:p-6">
        <div className="flex gap-4">
          <ProductThumb src={p.image} name={p.name} size="size-16 sm:size-20" />
          <div className="min-w-0 flex-1">
            <h1 className="text-lg font-bold sm:text-xl">{p.name}</h1>
            <p className="mt-0.5 text-sm text-muted">
              {p.union_name} · {p.county_name} · هر {p.unit_display}
            </p>
          </div>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-[1fr_1.2fr]">
          <div>
            <div className="text-xs text-muted">نرخ مصوب اتحادیه</div>
            <div className="mt-1 text-3xl font-bold tabular">{toman(p.official_price)}</div>
            <div className="mt-2 text-xs text-muted">
              فروش مجاز: از <b className="tabular text-ink">{toman(p.min_allowed_price)}</b> تا <b className="tabular text-ink">{toman(p.official_price)}</b>
              {p.price_changed_at && <> · به‌روزرسانی {ago(p.price_changed_at)}</>}
            </div>
          </div>
          {history.length > 1 && (
            <div>
              <div className="mb-1 text-xs text-muted">روند نرخ مصوب</div>
              <Sparkline values={history} />
            </div>
          )}
        </div>
        <div className="mt-5 grid grid-cols-3 gap-2 text-center">
          <Mini label="فروشگاه" value={num(p.offers_count)} />
          <Mini label="کمترین قیمت" value={p.min_price ? toman(p.min_price, false) : "—"} />
          <Mini label="میانگین" value={p.avg_price ? toman(p.avg_price, false) : "—"} />
        </div>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">فروشگاه‌های عرضه‌کننده</h2>
        <div className="flex items-center gap-2">
          <Segmented
            value={sort}
            onChange={(v) => {
              if (v === "distance" && !geo.pos) geo.ask();
              setSort(v);
            }}
            options={[{ value: "price", label: "ارزان‌ترین" }, { value: "distance", label: "نزدیک‌ترین" }]}
          />
          <Segmented value={view} onChange={setView} options={[{ value: "list", label: <List className="size-4" /> }, { value: "map", label: <MapIcon className="size-4" /> }]} />
        </div>
      </div>
      {!geo.pos && (
        <button onClick={geo.ask} className="flex w-full items-center gap-2 rounded-xl bg-brand-soft px-3 py-2.5 text-sm text-brand">
          <LocateFixed className="size-4" /> {geo.asking ? "در حال یافتن موقعیت…" : "برای نمایش فاصله فروشگاه‌ها، موقعیت خود را فعال کنید"}
        </button>
      )}

      {!p.offers.length ? (
        <Card>
          <Empty title="هنوز فروشگاهی برای این کالا قیمت ثبت نکرده است">
            اگر این کالا را بالاتر از نرخ مصوب خریده‌اید، <Link to={`/report?product=${p.id}`} className="text-brand underline">گزارش دهید</Link>.
          </Empty>
        </Card>
      ) : view === "map" ? (
        <Suspense fallback={<Loading />}>
          <MapView
            height="60vh"
            me={geo.pos}
            points={p.offers.map((o, i) => ({
              id: o.id, lat: o.store.lat ?? 0, lng: o.store.lng ?? 0, title: o.store.name, sub: toman(o.price),
              label: String(i + 1), highlight: i === 0, href: `/s/${o.store.id}`,
            }))}
          />
        </Suspense>
      ) : (
        <ol className="space-y-3">
          {p.offers.map((o, i) => (
            <OfferRow key={o.id} o={o} rank={i + 1} best={i === 0 && sort === "price"} productId={p.id} />
          ))}
        </ol>
      )}

      <p className="flex items-start gap-2 rounded-xl bg-surface-2 p-3 text-xs leading-6 text-muted">
        <Info className="mt-1 size-4 shrink-0" />
        قیمت‌ها از کمترین به بیشترین مرتب شده‌اند. فروشگاه‌ها مجازند حداکثر {num(p.max_discount_percent)}٪ کمتر از نرخ مصوب بفروشند.
        اگر نرخ مصوب تغییر کند و فروشگاهی ظرف ۲۴ ساعت قیمت خود را به‌روز نکند، تا زمان به‌روزرسانی در این فهرست نمایش داده نمی‌شود.
      </p>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-surface-2 px-2 py-2.5">
      <div className="text-[11px] text-muted">{label}</div>
      <div className="mt-0.5 text-sm font-semibold tabular">{value}</div>
    </div>
  );
}

export function OfferRow({ o, rank, best, productId }: { o: Offer; rank: number; best?: boolean; productId: number }) {
  const s = o.store;
  return (
    <li className={cx("rounded-2xl border bg-surface p-4 shadow-card", best ? "border-brand/50" : "border-line")}>
      <div className="flex items-start gap-3">
        <span className={cx("grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold tabular", best ? "bg-brand text-brand-ink" : "bg-surface-2 text-muted")}>
          {num(rank)}
        </span>
        <div className="min-w-0 flex-1">
          <Link to={`/s/${s.id}`} className="flex flex-wrap items-center gap-1.5 font-medium">
            <span className="truncate">{s.name}</span>
            {s.is_verified && <BadgeCheck className="size-4 shrink-0 text-brand" aria-label="احراز شده" />}
            {o.shop_products > 0 && <Badge tone="brand">سایر محصولات</Badge>}
          </Link>
          <div className="mt-0.5 line-clamp-1 text-xs text-muted">{s.address}</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted">
            {s.rating_count > 0 && (
              <span className="inline-flex items-center gap-0.5">
                <Star className="size-3.5 fill-accent text-accent" /> {num(s.rating_avg, 1)} ({num(s.rating_count)})
              </span>
            )}
            {o.distance_km != null && <span>{km(o.distance_km)}</span>}
            {s.working_hours && (
              <span className="inline-flex items-center gap-0.5">
                <Clock className="size-3.5" /> {s.working_hours}
              </span>
            )}
            {o.pending_update && <Badge tone="warn">در انتظار به‌روزرسانی نرخ</Badge>}
          </div>
        </div>
        <div className="text-left">
          <div className="text-lg font-bold tabular">{toman(o.price, false)}</div>
          <div className="text-[11px] text-muted">تومان</div>
          {o.discount_percent > 0 && <Badge tone="ok" className="mt-1">{num(o.discount_percent, 1)}٪ زیر نرخ</Badge>}
        </div>
      </div>
      <Link
        to={`/s/${s.id}`}
        className="mt-3 flex items-center justify-between gap-2 rounded-xl bg-brand px-4 py-3 text-brand-ink transition hover:bg-brand-strong"
      >
        <span className="flex items-center gap-2 text-sm font-semibold">
          <ShoppingBag className="size-5" />
          برای مشاهده سایر محصولات این فروشگاه کلیک کنید
        </span>
        <span className="flex items-center gap-1 text-xs opacity-90">
          {o.shop_products > 0 ? `${num(o.shop_products)} محصول` : ""}
          <ChevronLeft className="size-4" />
        </span>
      </Link>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <a href={telLink(s.phone)} className={cx("inline-flex h-10 items-center justify-center gap-1.5 rounded-xl bg-surface-2 text-sm", !s.phone && "pointer-events-none opacity-40")}>
          <Phone className="size-4" /> تماس
        </a>
        <Directions
          lat={s.lat}
          lng={s.lng}
          name={s.name}
          className="inline-flex h-10 items-center justify-center gap-1.5 rounded-xl bg-surface-2 text-sm"
        />
        <Link to={`/report?store=${s.id}&product=${productId}`} className="inline-flex h-10 items-center justify-center gap-1.5 rounded-xl bg-danger-soft text-sm text-danger">
          <ShieldAlert className="size-4" /> تخلف
        </Link>
      </div>
    </li>
  );
}

