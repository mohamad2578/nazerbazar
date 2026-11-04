import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { BarsChart } from "../../../components/charts";
import { Button, Card, ErrorBox, Field, Input, Loading, PageHeader, Segmented } from "../../../components/ui";
import { api, download } from "../../../lib/api";
import { isoDaysAgo, todayIso } from "../../../lib/erp";
import { num, toman } from "../../../lib/format";

type Rep = {
  from: string; to: string;
  totals: { orders: number; gross: number; discount: number; revenue: number; cogs: number; gross_profit: number; margin: number; delivery_income: number; courier_cost: number; expenses: number; net_profit: number; tax: number; purchases: number; avg_order: number };
  series: { date: string; orders: number; revenue: number; cogs: number; profit: number }[];
  by_product: { name: string; qty: number; revenue: number; cost: number; profit: number; margin: number }[];
  by_method: { payment_method: string; count: number; total: number }[];
  expenses_by_category: { category: string; total: number }[];
};
const METHOD: Record<string, string> = { online: "پرداخت اینترنتی", cash: "نقدی", wallet: "کیف پول" };
const CAT: Record<string, string> = { rent: "اجاره", salary: "حقوق و دستمزد", packaging: "بسته‌بندی", transport: "حمل و نقل", marketing: "تبلیغات", utility: "قبوض و انرژی", other: "سایر" };

/** گزارش سود و زیان و فروش بر اساس بازه زمانی. */
export default function Reports() {
  const [preset, setPreset] = useState("30");
  const [from, setFrom] = useState(isoDaysAgo(29));
  const [to, setTo] = useState(todayIso());
  const pick = (v: string) => {
    setPreset(v);
    if (v !== "custom") { setFrom(isoDaysAgo(Number(v) - 1)); setTo(todayIso()); }
  };
  const q = useQuery({ queryKey: ["erp-sales", from, to], queryFn: () => api.get<Rep>("/erp/reports/sales/", { from, to }) });
  const t = q.data?.totals;
  const chart = (q.data?.series ?? []).map((s) => ({ ...s, label: s.date.slice(5), revenue: Math.round(s.revenue / 10), profit: Math.round(s.profit / 10) }));
  return (
    <div className="space-y-4">
      <PageHeader title="گزارش سود و فروش" subtitle="فقط سفارش‌های تحویل‌شده در بازه حساب می‌شود." actions={
        <Button size="sm" variant="secondary" icon={<Download className="size-4" />} onClick={() => download(`/erp/export/sales/?from=${from}&to=${to}`, "sales.csv")}>خروجی اکسل</Button>} />
      <Segmented value={preset} onChange={pick} options={[{ value: "7", label: "۷ روز" }, { value: "30", label: "۳۰ روز" }, { value: "90", label: "۹۰ روز" }, { value: "custom", label: "بازه دلخواه" }]} />
      {preset === "custom" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="از"><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} dir="ltr" /></Field>
          <Field label="تا"><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} dir="ltr" /></Field>
        </div>
      )}
      {q.isLoading ? <Loading /> : q.error ? <ErrorBox error={q.error} /> : t && (<>
        <Card className="overflow-hidden">
          <div className="border-b border-line bg-surface-2 px-4 py-2.5 font-semibold">صورت سود و زیان ({num(t.orders)} سفارش)</div>
          <div className="divide-y divide-line text-sm">
            <Line label="جمع فروش کالاها (پیش از تخفیف)" v={t.gross} />
            <Line label="تخفیف بسته‌ها" v={-t.discount} />
            <Line label="درآمد کالا" v={t.revenue} bold />
            <Line label="بهای تمام‌شده کالای فروخته‌شده" v={-t.cogs} />
            <Line label={`سود ناخالص (${num(t.margin, 1)}٪)`} v={t.gross_profit} bold tone />
            <Line label="درآمد هزینه ارسال" v={t.delivery_income} />
            <Line label="کارمزد پیک‌ها" v={-t.courier_cost} />
            <Line label="هزینه‌های جاری" v={-t.expenses} />
            <Line label="سود خالص" v={t.net_profit} bold tone big />
            <Line label="مالیات ارزش افزوده دریافتی (بدهی مالیاتی)" v={t.tax} muted />
            <Line label="خرید از تامین‌کنندگان در بازه" v={t.purchases} muted />
            <Line label="میانگین ارزش هر سفارش" v={t.avg_order} muted />
          </div>
        </Card>
        <Card className="p-4">
          <h2 className="mb-2 font-semibold">درآمد و سود روزانه (تومان)</h2>
          <BarsChart data={chart} x="label" series={[{ key: "revenue", label: "درآمد" }, { key: "profit", label: "سود ناخالص" }]} height={240} />
        </Card>
        <Card className="overflow-hidden">
          <div className="border-b border-line bg-surface-2 px-4 py-2.5 font-semibold">فروش به تفکیک کالا</div>
          {!q.data!.by_product.length ? <p className="p-5 text-center text-sm text-muted">فروشی در این بازه نیست.</p> : (
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead className="text-xs text-muted"><tr><th className="px-3 py-2 text-right">کالا</th><th className="px-3 py-2">تعداد</th><th className="px-3 py-2">درآمد</th><th className="px-3 py-2">سود</th><th className="px-3 py-2">حاشیه</th></tr></thead>
              <tbody className="divide-y divide-line">{q.data!.by_product.map((p) => (
                <tr key={p.name}><td className="px-3 py-2">{p.name}</td><td className="px-3 py-2 text-center tabular">{num(p.qty)}</td>
                  <td className="px-3 py-2 text-center tabular">{toman(p.revenue, false)}</td>
                  <td className={`px-3 py-2 text-center tabular ${p.profit < 0 ? "text-danger" : "text-ok"}`}>{toman(p.profit, false)}</td>
                  <td className="px-3 py-2 text-center tabular">{num(p.margin, 1)}٪</td></tr>
              ))}</tbody></table></div>
          )}
        </Card>
        <div className="grid gap-4 sm:grid-cols-2">
          <Card className="p-4"><h2 className="mb-2 font-semibold">روش‌های پرداخت</h2>
            {q.data!.by_method.map((m) => <div key={m.payment_method} className="flex justify-between border-b border-line py-1.5 text-sm last:border-0"><span>{METHOD[m.payment_method] ?? m.payment_method} ({num(m.count)})</span><b className="tabular">{toman(m.total)}</b></div>)}
            {!q.data!.by_method.length && <p className="text-sm text-muted">—</p>}</Card>
          <Card className="p-4"><h2 className="mb-2 font-semibold">هزینه‌ها به تفکیک دسته</h2>
            {q.data!.expenses_by_category.map((m) => <div key={m.category} className="flex justify-between border-b border-line py-1.5 text-sm last:border-0"><span>{CAT[m.category] ?? m.category}</span><b className="tabular">{toman(m.total)}</b></div>)}
            {!q.data!.expenses_by_category.length && <p className="text-sm text-muted">—</p>}</Card>
        </div>
      </>)}
    </div>
  );
}

function Line({ label, v, bold, tone, big, muted }: { label: string; v: number; bold?: boolean; tone?: boolean; big?: boolean; muted?: boolean }) {
  const color = tone ? (v >= 0 ? "text-ok" : "text-danger") : muted ? "text-muted" : "";
  return (
    <div className={`flex items-center justify-between gap-3 px-4 py-2.5 ${bold ? "font-semibold" : ""} ${big ? "bg-surface-2 text-base" : ""} ${muted ? "text-muted" : ""}`}>
      <span>{label}</span><span className={`tabular ${color}`}>{v < 0 ? `(${toman(Math.abs(v))})` : toman(v)}</span>
    </div>
  );
}
