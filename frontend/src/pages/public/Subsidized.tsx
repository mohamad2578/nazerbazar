import { useQuery } from "@tanstack/react-query";
import { Navigation, PackageCheck, Phone } from "lucide-react";
import { Card, Empty, ErrorBox, Loading } from "../../components/ui";
import { api } from "../../lib/api";
import { directionsLink, num, telLink, toman } from "../../lib/format";
import { useCounty } from "../../lib/prefs";

type Row = {
  tracking_code: string; commodity: string; allocation: string; consumer_price: number; unit: string; remaining: number;
  store: { id: number; name: string; address: string; phone: string; lat: string; lng: string };
};

export default function Subsidized() {
  const [county] = useCounty();
  const q = useQuery({ queryKey: ["subsidized", county?.id], queryFn: () => api.get<Row[]>("/public/subsidized/", { county: county?.id }) });
  const groups = new Map<string, Row[]>();
  q.data?.forEach((r) => groups.set(r.commodity, [...(groups.get(r.commodity) ?? []), r]));
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold">کالای تنظیم بازار</h1>
        <p className="mt-1 text-sm text-muted">
          فروشگاه‌هایی که کالای تخصیصی (سهمیه‌ای/یارانه‌ای) را تحویل گرفته‌اند و موجودی دارند. خرید بالاتر از سقف قیمت اعلامی تخلف است.
        </p>
      </div>
      {q.isLoading ? <Loading /> : q.error ? <ErrorBox error={q.error} /> : !q.data?.length ? (
        <Card><Empty title="در حال حاضر کالای تنظیم بازار در شهرستان انتخابی موجود نیست" icon={<PackageCheck className="size-7" />} /></Card>
      ) : (
        [...groups.entries()].map(([commodity, rows]) => (
          <section key={commodity}>
            <h2 className="mb-2 font-semibold">{commodity}</h2>
            <div className="grid gap-3 md:grid-cols-2">
              {rows.map((r) => (
                <Card key={r.tracking_code} className="p-4">
                  <div className="flex justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-medium">{r.store.name}</div>
                      <div className="truncate text-xs text-muted">{r.store.address}</div>
                      <div className="mt-1 text-xs text-muted">{r.allocation}</div>
                    </div>
                    <div className="shrink-0 text-left">
                      <div className="text-xs text-muted">سقف قیمت</div>
                      <div className="font-bold tabular">{toman(r.consumer_price)}</div>
                      <div className="text-[11px] text-muted">هر {r.unit}</div>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center justify-between gap-2">
                    <span className="text-xs text-ok">موجودی حدود {num(r.remaining)} {r.unit}</span>
                    <div className="flex gap-2">
                      <a href={telLink(r.store.phone)} className="grid size-9 place-items-center rounded-xl bg-surface-2" aria-label="تماس"><Phone className="size-4" /></a>
                      <a href={directionsLink(r.store.lat, r.store.lng)} className="grid size-9 place-items-center rounded-xl bg-surface-2" aria-label="مسیریابی"><Navigation className="size-4" /></a>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
