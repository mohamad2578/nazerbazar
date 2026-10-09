import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ClipboardList, PackageCheck, Search, Store as StoreIcon, Truck, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Carousel from "../../components/Carousel";
import HeroSlider from "../../components/HeroSlider";
import ProductCard, { type PublicProduct } from "../../components/ProductCard";
import { Button, cx, Empty, ErrorBox, Loading } from "../../components/ui";
import { ReportFab } from "../../layouts/PublicLayout";
import { api, type Page } from "../../lib/api";
import { num, toman } from "../../lib/format";
import { useCounty } from "../../lib/prefs";

type Stats = { stores: number; products: number; unions: number; resolved_complaints: number; latest_changes: PublicProduct[] };

export default function Home() {
  const [county] = useCounty();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const category = params.get("category") ?? "";
  const ordering = params.get("ordering") ?? "";

  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams(params);
      if (q) p.set("q", q);
      else p.delete("q");
      if (p.toString() !== params.toString()) setParams(p, { replace: true });
    }, 350);
    return () => clearTimeout(t);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const setParam = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
  };

  const stats = useQuery({ queryKey: ["stats", county?.id], queryFn: () => api.get<Stats>("/public/stats/", { county: county?.id }) });
  const cats = useQuery({ queryKey: ["categories"], queryFn: () => api.get<{ id: number; name: string }[]>("/categories/"), staleTime: 3600_000 });
  const list = useInfiniteQuery({
    queryKey: ["products", county?.id, params.get("q"), category, ordering],
    queryFn: ({ pageParam }) =>
      api.get<Page<PublicProduct>>("/public/products/", { county: county?.id, q: params.get("q"), category, ordering, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last, all) => (last.next ? all.length + 1 : undefined),
  });
  const items = list.data?.pages.flatMap((p) => p.results) ?? [];
  const searching = !!params.get("q") || !!category;

  return (
    <div className="space-y-6">
      {!searching && <HeroSlider />}

      <section className="rounded-3xl bg-brand px-4 py-4 text-brand-ink sm:px-6 sm:py-5">
        <h1 className="sr-only">بررسی و جستجوی قیمت کالاها</h1>
        <div className="relative">
          <Search className="pointer-events-none absolute right-4 top-1/2 size-5 -translate-y-1/2 text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="جستجوی کالا: برنج، مرغ، روغن…"
            className="h-13 w-full rounded-2xl bg-surface pr-12 pl-10 text-[15px] text-ink shadow-lg placeholder:text-muted focus:outline-none"
            type="search"
            enterKeyHint="search"
          />
          {q && (
            <button onClick={() => setQ("")} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-label="پاک کردن">
              <X className="size-5" />
            </button>
          )}
        </div>
      </section>

      {!searching && (
        <section className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
          <QuickLink to="/subsidized" icon={<PackageCheck className="size-5" />} title="کالای تنظیم بازار" sub="سهمیه‌ای و یارانه‌ای" />
          <QuickLink to="/register-store" icon={<StoreIcon className="size-5" />} title="ثبت‌نام فروشگاه" sub="ویژه صاحبان صنف" />
          <QuickLink to="/rates" icon={<ClipboardList className="size-5" />} title="نرخ‌نامه اتحادیه‌ها" sub="نرخ مصوب هر کالا" />
          <QuickLink to="/suppliers" icon={<Truck className="size-5" />} title="ثبت‌نام تامین‌کنندگان" sub="فرم تامین کالا" />
        </section>
      )}

      {!searching && !!stats.data?.latest_changes.length && (
        <section>
          <Carousel title="آخرین تغییرات نرخ مصوب">
            {stats.data.latest_changes.map((p) => {
              const up = p.previous_price ? p.official_price > p.previous_price : null;
              const change = p.previous_price ? ((p.official_price - p.previous_price) / p.previous_price) * 100 : null;
              return (
                <Link key={p.id} to={`/p/${p.id}`} className="rounded-2xl border border-line bg-surface p-3 shadow-card">
                  <div className="truncate text-sm font-medium">{p.name}</div>
                  <div className="mt-0.5 truncate text-[11px] text-muted">{p.union_name}</div>
                  <div className="mt-2 tabular font-semibold">{toman(p.official_price)}</div>
                  {change != null && change !== 0 && (
                    <div className={cx("mt-1 inline-flex items-center gap-0.5 text-xs", up ? "text-danger" : "text-ok")}>
                      {up ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />}
                      {num(Math.abs(change), 1)}٪
                    </div>
                  )}
                </Link>
              );
            })}
          </Carousel>
        </section>
      )}

      <section>
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="font-semibold">{searching ? "نتایج" : "نرخ کالاها"}</h2>
          <select
            value={ordering}
            onChange={(e) => setParam("ordering", e.target.value)}
            className="h-9 rounded-lg border border-line bg-surface px-2 text-sm"
            aria-label="مرتب‌سازی"
          >
            <option value="">الفبایی</option>
            <option value="price">ارزان‌ترین</option>
            <option value="-price">گران‌ترین</option>
            <option value="recent">آخرین تغییر نرخ</option>
          </select>
        </div>
        <div className="-mx-4 mb-4 flex gap-2 overflow-x-auto px-4">
          <Chip active={!category} onClick={() => setParam("category", "")}>همه</Chip>
          {cats.data?.map((c) => (
            <Chip key={c.id} active={category === String(c.id)} onClick={() => setParam("category", String(c.id))}>
              {c.name}
            </Chip>
          ))}
        </div>
        {list.isLoading ? (
          <Loading />
        ) : list.error ? (
          <ErrorBox error={list.error} retry={() => list.refetch()} />
        ) : !items.length ? (
          <Empty title="کالایی پیدا نشد" icon={<StoreIcon className="size-7" />}>
            {county ? `در شهرستان ${county.name} برای این جستجو نتیجه‌ای نیست. شهرستان را تغییر دهید.` : "عبارت دیگری را جستجو کنید."}
          </Empty>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {items.map((p) => (
              <ProductCard key={p.id} p={p} />
            ))}
          </div>
        )}
        {list.hasNextPage && (
          <div className="mt-4 text-center">
            <Button variant="secondary" loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>
              نمایش بیشتر
            </Button>
          </div>
        )}
      </section>
      <ReportFab />
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cx("h-9 shrink-0 rounded-full border px-4 text-sm transition", active ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface text-ink hover:border-brand/50")}
    >
      {children}
    </button>
  );
}

function QuickLink({ to, icon, title, sub, danger }: { to: string; icon: React.ReactNode; title: string; sub: string; danger?: boolean }) {
  return (
    <Link to={to} className="rounded-2xl border border-line bg-surface p-3 shadow-card sm:p-4">
      <span className={cx("grid size-9 place-items-center rounded-xl", danger ? "bg-danger-soft text-danger" : "bg-brand-soft text-brand")}>{icon}</span>
      <div className="mt-2 text-sm font-medium leading-5">{title}</div>
      <div className="mt-0.5 hidden text-xs text-muted sm:block">{sub}</div>
    </Link>
  );
}
