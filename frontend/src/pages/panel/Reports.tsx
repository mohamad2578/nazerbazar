import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { BarsChart, TrendChart } from "../../components/charts";
import { Badge, Button, Card, DataTable, Loading, PageHeader, Segmented, Select } from "../../components/ui";
import { api, download, type Page } from "../../lib/api";
import { num, pct, toman } from "../../lib/format";

type Tab = "prices" | "complaints" | "unions" | "counties" | "basket" | "distribution";

export default function Reports() {
  const [tab, setTab] = useState<Tab>("prices");
  const [days, setDays] = useState("30");
  return (
    <div className="space-y-4">
      <PageHeader title="گزارش‌های تحلیلی" actions={
        <Select value={days} onChange={(e) => setDays(e.target.value)} className="h-9 w-32 text-sm" aria-label="بازه">
          <option value="7">۷ روز</option><option value="30">۳۰ روز</option><option value="90">۹۰ روز</option><option value="365">یک سال</option>
        </Select>
      } />
      <Segmented value={tab} onChange={setTab} options={[
        { value: "prices", label: "روند قیمت" }, { value: "complaints", label: "شکایات" }, { value: "unions", label: "عملکرد اتحادیه‌ها" },
        { value: "counties", label: "شهرستان‌ها" }, { value: "basket", label: "سبد خانوار" }, { value: "distribution", label: "توزیع" },
      ]} />
      {tab === "prices" && <PricesTab days={days} />}
      {tab === "complaints" && <ComplaintsTab days={days} />}
      {tab === "unions" && <TableTab url="/analytics/unions/" exportName="unions" columns={[
        { key: "name", label: "اتحادیه" }, { key: "county", label: "شهرستان" }, { key: "products", label: "کالا", render: (r: any) => num(r.products) },
        { key: "stores_active", label: "فروشگاه فعال", render: (r: any) => num(r.stores_active) },
        { key: "stores_pending", label: "در انتظار", render: (r: any) => (r.stores_pending ? <Badge tone="warn">{num(r.stores_pending)}</Badge> : "—") },
        { key: "compliance_percent", label: "انطباق قیمت", render: (r: any) => pct(r.compliance_percent) },
        { key: "price_changes_30d", label: "تغییر نرخ ۳۰ روز", render: (r: any) => num(r.price_changes_30d) },
        { key: "complaints", label: "شکایات (باز)", render: (r: any) => `${num(r.complaints)} (${num(r.complaints_open)})` },
        { key: "avg_resolution_hours", label: "میانگین رسیدگی", render: (r: any) => (r.avg_resolution_hours != null ? `${num(r.avg_resolution_hours, 1)} ساعت` : "—") },
      ]} />}
      {tab === "counties" && <TableTab url="/analytics/counties/" exportName="counties" columns={[
        { key: "name", label: "شهرستان" }, { key: "stores_active", label: "فروشگاه فعال", render: (r: any) => num(r.stores_active) },
        { key: "stores_per_10k", label: "به ازای ۱۰ هزار نفر", render: (r: any) => num(r.stores_per_10k, 2) },
        { key: "offers", label: "قیمت ثبت‌شده", render: (r: any) => num(r.offers) },
        { key: "avg_discount_percent", label: "میانگین تخفیف", render: (r: any) => pct(r.avg_discount_percent) },
        { key: "complaints", label: "شکایات", render: (r: any) => num(r.complaints) },
        { key: "basket_total", label: "سبد خانوار", render: (r: any) => (r.basket_total ? toman(r.basket_total) : "—") },
        { key: "basket_coverage", label: "پوشش سبد" },
      ]} />}
      {tab === "basket" && <BasketTab days={days} />}
      {tab === "distribution" && <TableTab url="/analytics/distribution/" columns={[
        { key: "title", label: "تخصیص" }, { key: "commodity", label: "کالا" }, { key: "status", label: "وضعیت" },
        { key: "total", label: "کل", render: (r: any) => num(r.total) }, { key: "assigned", label: "سهمیه فروشگاه‌ها", render: (r: any) => num(r.assigned) },
        { key: "received", label: "تحویل", render: (r: any) => num(r.received) }, { key: "sold", label: "فروش", render: (r: any) => num(r.sold) },
        { key: "delivery_gap", label: "کسری تحویل", render: (r: any) => (r.delivery_gap > 0 ? <span className="text-danger">{num(r.delivery_gap)} ({pct(r.delivery_gap_percent)})</span> : "—") },
        { key: "stores", label: "فروشگاه", render: (r: any) => num(r.stores) },
      ]} />}
    </div>
  );
}

function PricesTab({ days }: { days: string }) {
  const [product, setProduct] = useState("");
  const products = useQuery({ queryKey: ["products-all"], queryFn: () => api.get<Page<any>>("/products/", { page_size: 200, is_active: true }) });
  const trend = useQuery({ queryKey: ["trend", days, product], queryFn: () => api.get("/analytics/trends/", { days, product }) });
  const movers = useQuery({ queryKey: ["movers", days], queryFn: () => api.get<any[]>("/analytics/price-changes/", { days }) });
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="font-semibold">{product ? "روند قیمت کالا" : "شاخص قیمت (پایه = ۱۰۰)"}</h2>
            <p className="text-xs text-muted">{product ? "نرخ مصوب در برابر میانگین و کمینه قیمت فروشگاه‌ها (تومان)" : "میانگین نسبت قیمت هر کالا به روز اول بازه"}</p>
          </div>
          <Select value={product} onChange={(e) => setProduct(e.target.value)} className="h-9 w-56 text-sm" aria-label="کالا">
            <option value="">شاخص کل</option>
            {products.data?.results.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
        </div>
        {trend.isLoading ? <Loading /> : !trend.data?.series?.length ? <p className="py-10 text-center text-sm text-muted">داده‌ای در این بازه نیست.</p> : product ? (
          <TrendChart data={trend.data.series.map((r: any) => ({ ...r, official: r.official / 10, avg: r.avg && r.avg / 10, min: r.min && r.min / 10 }))}
            series={[{ key: "official", label: "نرخ مصوب" }, { key: "avg", label: "میانگین فروشگاه‌ها" }, { key: "min", label: "کمترین قیمت" }]} />
        ) : (
          <TrendChart data={trend.data.series} series={[{ key: "official_index", label: "نرخ مصوب" }, { key: "market_index", label: "قیمت فروشگاه‌ها" }]} format={(v) => num(v, 1)} />
        )}
      </Card>
      <Card>
        <h2 className="px-4 pt-4 font-semibold">بیشترین تغییرات نرخ مصوب</h2>
        <DataTable<any> rows={(movers.data ?? []).map((r, i) => ({ ...r, id: i }))} columns={[
          { key: "product_name", label: "کالا" }, { key: "union_name", label: "اتحادیه" },
          { key: "previous_price", label: "نرخ قبلی", render: (r) => toman(r.previous_price) }, { key: "price", label: "نرخ جدید", render: (r) => toman(r.price) },
          { key: "change_percent", label: "تغییر", render: (r) => <span className={r.change_percent > 0 ? "text-danger" : "text-ok"}>{r.change_percent > 0 ? "+" : ""}{num(r.change_percent, 1)}٪</span> },
        ]} />
        {!movers.data?.length && <p className="p-6 text-center text-sm text-muted">تغییری ثبت نشده</p>}
      </Card>
    </div>
  );
}

function ComplaintsTab({ days }: { days: string }) {
  const q = useQuery({ queryKey: ["c-report", days], queryFn: () => api.get("/analytics/complaints/", { days }) });
  if (q.isLoading) return <Loading />;
  const d = q.data;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-4 lg:col-span-2">
        <h2 className="mb-2 font-semibold">تعداد شکایات روزانه</h2>
        {d.by_day.length ? <TrendChart data={d.by_day} series={[{ key: "count", label: "شکایات" }]} height={220} /> : <p className="py-8 text-center text-sm text-muted">شکایتی ثبت نشده</p>}
      </Card>
      <Card className="p-4">
        <h2 className="mb-2 font-semibold">بر اساس نوع تخلف</h2>
        <BarsChart data={d.by_kind} x="label" series={[{ key: "count", label: "تعداد" }]} horizontal height={Math.max(160, d.by_kind.length * 40)} />
      </Card>
      <Card className="p-4">
        <h2 className="mb-2 font-semibold">بر اساس وضعیت</h2>
        <BarsChart data={d.by_status} x="label" series={[{ key: "count", label: "تعداد" }]} horizontal height={Math.max(160, d.by_status.length * 40)} />
      </Card>
      <Card className="lg:col-span-2">
        <h2 className="px-4 pt-4 font-semibold">عملکرد رسیدگی اتحادیه‌ها</h2>
        <DataTable<any> rows={d.by_union.map((r: any, i: number) => ({ ...r, id: i }))} columns={[
          { key: "union__name", label: "اتحادیه" }, { key: "total", label: "کل", render: (r) => num(r.total) }, { key: "open", label: "باز", render: (r) => num(r.open) },
          { key: "resolved", label: "رسیدگی‌شده", render: (r) => num(r.resolved) }, { key: "violations", label: "تخلف محرز", render: (r) => num(r.violations) },
          { key: "avg_res", label: "میانگین رسیدگی", render: (r) => (r.avg_res != null ? `${num(r.avg_res, 1)} ساعت` : "—") },
        ]} />
      </Card>
      <Card>
        <h2 className="px-4 pt-4 font-semibold">فروشگاه‌های پرشکایت</h2>
        <DataTable<any> rows={d.top_stores.map((r: any) => ({ ...r, id: r.store }))} columns={[
          { key: "store__name", label: "فروشگاه" }, { key: "store__union__name", label: "اتحادیه" }, { key: "c", label: "شکایت", render: (r) => num(r.c) }, { key: "v", label: "تخلف محرز", render: (r) => num(r.v) },
        ]} />
      </Card>
      <Card>
        <h2 className="px-4 pt-4 font-semibold">کالاهای پرشکایت</h2>
        <DataTable<any> rows={d.top_products.map((r: any, i: number) => ({ ...r, id: i }))} columns={[{ key: "product__name", label: "کالا" }, { key: "c", label: "شکایت", render: (r) => num(r.c) }]} />
      </Card>
    </div>
  );
}

function BasketTab({ days }: { days: string }) {
  const q = useQuery({ queryKey: ["basket", days], queryFn: () => api.get("/analytics/basket/", { days }) });
  if (q.isLoading) return <Loading />;
  const { current, series } = q.data;
  return (
    <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
      <Card className="p-4">
        <h2 className="font-semibold">روند هزینه ماهانه سبد خانوار (تومان)</h2>
        <p className="mb-2 text-xs text-muted">محاسبه از قیمت واقعی فروشگاه‌ها؛ در نبود قیمت فروشگاهی، نرخ مصوب</p>
        {series.length ? <TrendChart data={series.map((s: any) => ({ ...s, total: s.total / 10 }))} series={[{ key: "total", label: "سبد خانوار" }]} /> : <p className="py-10 text-center text-sm text-muted">داده‌ای نیست</p>}
      </Card>
      <Card className="p-4">
        <div className="text-sm text-muted">هزینه فعلی سبد</div>
        <div className="text-2xl font-bold tabular">{toman(current.total)}</div>
        <div className="text-xs text-muted">{num(current.covered)} از {num(current.items_count)} قلم دارای قیمت</div>
        <div className="mt-3 max-h-80 divide-y divide-line overflow-y-auto text-sm">
          {current.items.map((i: any) => (
            <div key={i.commodity} className="flex justify-between py-2">
              <span>{i.commodity} <span className="text-xs text-muted">×{num(i.qty, 1)}</span></span>
              <span className="tabular">{i.cost ? toman(i.cost, false) : "—"}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function TableTab({ url, columns, exportName }: { url: string; columns: any[]; exportName?: string }) {
  const q = useQuery({ queryKey: [url], queryFn: () => api.get<any[]>(url) });
  if (q.isLoading) return <Loading />;
  return (
    <Card>
      {exportName && (
        <div className="flex justify-end p-3">
          <Button size="sm" variant="secondary" icon={<Download className="size-4" />} onClick={() => download(`/analytics/export/${exportName}/`, `${exportName}.xlsx`)}>اکسل</Button>
        </div>
      )}
      <DataTable<any> rows={q.data ?? []} columns={columns} />
      {!q.data?.length && <p className="p-6 text-center text-sm text-muted">داده‌ای نیست</p>}
    </Card>
  );
}
