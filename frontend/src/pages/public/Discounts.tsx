import { useInfiniteQuery } from "@tanstack/react-query";
import { BadgePercent, MapPin, Package, Phone, Search, Store as StoreIcon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Card, Empty, Input, Loading, PageHeader, Segmented } from "../../components/ui";
import { api, type Page } from "../../lib/api";
import { num, telLink, toman } from "../../lib/format";
import { useCounty } from "../../lib/prefs";

type Offer = {
  id: number; name: string; description: string; image: string | null; brand: string;
  price: number; old_price: number; discount_percent: number; unit_display: string; is_available: boolean;
  store: { id: number; name: string; address: string; phone: string };
};

/** «تخفیفات فروشگاه‌ها»: محصولاتی که فروشگاه‌ها با تخفیف ویژه عرضه می‌کنند و صمت تایید کرده است. */
export default function Discounts() {
  const [county] = useCounty();
  const [q, setQ] = useState("");
  const [ordering, setOrdering] = useState("");
  const list = useInfiniteQuery({
    queryKey: ["special-offers", county?.id, q, ordering],
    initialPageParam: 1,
    queryFn: ({ pageParam }) => api.get<Page<Offer>>("/public/special-offers/", { county: county?.id, q, ordering, page: pageParam }),
    getNextPageParam: (last, all) => (last.next ? all.length + 1 : undefined),
  });
  const items = list.data?.pages.flatMap((p) => p.results) ?? [];

  return (
    <div className="space-y-4">
      <PageHeader title="تخفیفات فروشگاه‌ها" subtitle="پیشنهادهای ویژه فروشگاه‌های مجاز؛ همه موارد توسط اداره صمت بررسی و تایید شده‌اند." />

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative sm:w-72">
          <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="جستجوی محصول" className="pr-9" />
        </div>
        <Segmented value={ordering} onChange={setOrdering} options={[
          { value: "", label: "بیشترین تخفیف" },
          { value: "price", label: "ارزان‌ترین" },
          { value: "recent", label: "جدیدترین" },
        ]} />
      </div>

      {list.isLoading ? <Loading /> : !items.length ? (
        <Card><Empty title="فعلا تخفیف ویژه‌ای ثبت نشده است" icon={<BadgePercent className="size-7" />} /></Card>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(9.25rem,1fr))] gap-3">
          {items.map((o) => (
            <Card key={o.id} className="flex flex-col overflow-hidden">
              <div className="relative aspect-square bg-surface-2">
                {o.image
                  ? <img src={o.image} alt="" loading="lazy" className="size-full object-contain p-2" />
                  : <span className="grid size-full place-items-center text-muted"><Package className="size-8" /></span>}
                <span className="absolute right-2 top-2 rounded-full bg-danger px-2 py-0.5 text-xs font-bold text-white tabular">
                  {num(o.discount_percent)}٪ تخفیف
                </span>
                {!o.is_available && <Badge tone="warn" className="absolute left-2 top-2">ناموجود</Badge>}
              </div>
              <div className="flex flex-1 flex-col p-3">
                <div className="line-clamp-2 text-sm font-medium leading-6">{o.name}</div>
                <div className="mt-0.5 text-[11px] text-muted">{[o.brand, `هر ${o.unit_display}`].filter(Boolean).join(" · ")}</div>
                <div className="mt-2 text-[11px] text-muted line-through tabular">{toman(o.old_price)}</div>
                <div className="font-bold text-ok tabular">{toman(o.price)}</div>
                <Link to={`/s/${o.store.id}`} className="mt-2 flex items-start gap-1 border-t border-line pt-2 text-xs text-ink">
                  <StoreIcon className="mt-0.5 size-3.5 shrink-0 text-brand" />
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{o.store.name}</span>
                    <span className="flex items-center gap-0.5 truncate text-[11px] text-muted"><MapPin className="size-3 shrink-0" />{o.store.address}</span>
                  </span>
                </Link>
                {o.store.phone && (
                  <a href={telLink(o.store.phone)} className="mt-2 inline-flex h-8 items-center justify-center gap-1 rounded-lg bg-surface-2 text-xs">
                    <Phone className="size-3.5" /> تماس با فروشگاه
                  </a>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
      {list.hasNextPage && (
        <div className="flex justify-center">
          <Button variant="secondary" loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>موارد بیشتر</Button>
        </div>
      )}
    </div>
  );
}
