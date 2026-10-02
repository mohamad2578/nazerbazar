import { useQuery } from "@tanstack/react-query";
import { ShoppingBasket } from "lucide-react";
import { Badge, Card, ErrorBox, Loading } from "../../components/ui";
import { api } from "../../lib/api";
import { num, pct, toman } from "../../lib/format";
import { useCounty } from "../../lib/prefs";

type Report = {
  consumer_price_county: number | null; consumer_price_center: number | null; consumer_price_tehran: number | null;
  producer_price: number | null; wholesale_price: number | null; national_avg: number | null; national_min: number | null;
  national_max: number | null; chain_markup_percent: number | null; period: string; source: string;
};
type Item = { id: number; name: string; group: string; unit: string; subsidized: boolean; live_min: number | null; live_avg: number | null; live_max: number | null; report: Report | null };
type Basket = { total: number; covered: number; items_count: number; items: { commodity: string; qty: number; unit: string; unit_price: number | null; cost: number | null }[] };

export default function Observatory() {
  const [county] = useCounty();
  const q = useQuery({ queryKey: ["observatory", county?.id], queryFn: () => api.get<{ items: Item[]; basket: Basket }>("/public/observatory/", { county: county?.id }) });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const { items, basket } = q.data!;
  const groups = new Map<string, Item[]>();
  items.forEach((i) => groups.set(i.group, [...(groups.get(i.group) ?? []), i]));
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-bold">رصد بازار کالاهای اساسی</h1>
        <p className="mt-1 text-sm text-muted">قیمت واقعی عرضه در فروشگاه‌های {county ? county.name : "سامانه"} و فاصله قیمت از تولید تا مصرف</p>
      </div>

      <Card className="p-5">
        <div className="flex items-center gap-3">
          <span className="grid size-11 place-items-center rounded-2xl bg-brand-soft text-brand"><ShoppingBasket className="size-6" /></span>
          <div>
            <div className="text-sm text-muted">هزینه ماهانه سبد کالاهای اساسی خانوار</div>
            <div className="text-2xl font-bold tabular">{basket.total ? toman(basket.total) : "—"}</div>
          </div>
        </div>
        <p className="mt-2 text-xs text-muted">
          بر اساس قیمت روز {num(basket.covered)} قلم از {num(basket.items_count)} قلم سبد (اقلام بدون قیمت در سامانه محاسبه نشده‌اند).
        </p>
        <details className="mt-3">
          <summary className="cursor-pointer text-sm text-brand">جزئیات سبد</summary>
          <div className="mt-2 divide-y divide-line text-sm">
            {basket.items.map((b) => (
              <div key={b.commodity} className="flex justify-between py-2">
                <span>{b.commodity} <span className="text-xs text-muted">({num(b.qty, 1)} {b.unit})</span></span>
                <span className="tabular">{b.cost ? toman(b.cost) : <span className="text-muted">بدون قیمت</span>}</span>
              </div>
            ))}
          </div>
        </details>
      </Card>

      {[...groups.entries()].map(([g, rows]) => (
        <section key={g}>
          <h2 className="mb-2 font-semibold">{g}</h2>
          <Card className="divide-y divide-line">
            {rows.map((i) => (
              <div key={i.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 text-sm font-medium">
                      {i.name} {i.subsidized && <Badge tone="brand">تنظیم بازار</Badge>}
                    </div>
                    <div className="text-xs text-muted">هر {i.unit}</div>
                  </div>
                  <div className="text-left">
                    {i.live_avg ? (
                      <>
                        <div className="font-semibold tabular">{toman(i.live_avg)}</div>
                        <div className="text-[11px] text-muted tabular">{toman(i.live_min, false)} تا {toman(i.live_max, false)}</div>
                      </>
                    ) : (
                      <span className="text-xs text-muted">بدون قیمت فروشگاهی</span>
                    )}
                  </div>
                </div>
                {i.report && (
                  <div className="mt-2 grid grid-cols-2 gap-2 rounded-xl bg-surface-2 p-2.5 text-[11px] sm:grid-cols-4">
                    <Cell label="تولید/عمده" value={toman(i.report.wholesale_price ?? i.report.producer_price)} />
                    <Cell label="متوسط کشور" value={toman(i.report.national_avg)} />
                    <Cell label="ارزان‌ترین/گران‌ترین استان" value={`${toman(i.report.national_min, false)} / ${toman(i.report.national_max, false)}`} />
                    <Cell label="فاصله تولید تا مصرف" value={pct(i.report.chain_markup_percent)} warn />
                  </div>
                )}
              </div>
            ))}
          </Card>
        </section>
      ))}
    </div>
  );
}

function Cell({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div>
      <div className="text-muted">{label}</div>
      <div className={`mt-0.5 font-medium tabular ${warn ? "text-warn" : ""}`}>{value}</div>
    </div>
  );
}
