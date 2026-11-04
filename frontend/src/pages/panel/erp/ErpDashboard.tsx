import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Banknote, Bike, Boxes, ClipboardList, PackageX, ShoppingCart, TrendingUp, Wallet } from "lucide-react";
import { Link } from "react-router-dom";
import { BarsChart } from "../../../components/charts";
import { Badge, Card, ErrorBox, Loading, PageHeader, Stat } from "../../../components/ui";
import { moneyCompact } from "../../../lib/erp";
import { api } from "../../../lib/api";
import { num, toman } from "../../../lib/format";

type Totals = { orders: number; revenue: number; cogs: number; gross_profit: number; net_profit: number; margin: number; delivery_income: number; expenses: number; avg_order: number };
type Dash = {
  today: Totals; month: Totals; pending_orders: number; ready_orders: number; on_road_orders: number; stock_value: number; stock_sale_value: number;
  low_stock: number; out_of_stock: number; payables: number; cash_with_couriers: number;
  low_items: { id: number; name: string; stock: number; min_stock: number; status: string }[];
  top_products: { name: string; qty: number; revenue: number; profit: number; margin: number }[];
  series: { date: string; revenue: number; profit: number; orders: number }[];
};

/** داشبورد مالی و انبار فروشگاه ویژه: فروش و سود امروز و ماه، وضعیت انبار، بدهی‌ها و حساب پیک‌ها. */
export default function ErpDashboard() {
  const q = useQuery({ queryKey: ["erp-dash"], queryFn: () => api.get<Dash>("/erp/dashboard/"), refetchInterval: 60_000 });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;
  const d = q.data!;
  const chart = d.series.map((s) => ({ ...s, label: s.date.slice(5), revenue: Math.round(s.revenue / 10), profit: Math.round(s.profit / 10) }));
  return (
    <div className="space-y-5">
      <PageHeader title="داشبورد مالی و انبار" subtitle="خلاصه فروش، سود، موجودی و بدهی‌های فروشگاه ویژه (مبالغ به تومان)." />

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="فروش امروز" value={moneyCompact(d.today.revenue)} sub={`${num(d.today.orders)} سفارش`} icon={<ShoppingCart className="size-4" />} />
        <Stat label="سود ناخالص امروز" value={moneyCompact(d.today.gross_profit)} tone={d.today.gross_profit >= 0 ? "ok" : "danger"} icon={<TrendingUp className="size-4" />} />
        <Stat label="فروش این ماه" value={moneyCompact(d.month.revenue)} sub={`${num(d.month.orders)} سفارش`} />
        <Stat label="سود خالص این ماه" value={moneyCompact(d.month.net_profit)} tone={d.month.net_profit >= 0 ? "ok" : "danger"} sub={`حاشیه سود ناخالص ${num(d.month.margin, 1)}٪`} />
      </section>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="ارزش انبار (قیمت تمام‌شده)" value={moneyCompact(d.stock_value)} sub={`به قیمت فروش: ${toman(d.stock_sale_value)}`} icon={<Boxes className="size-4" />} />
        <Stat label="بدهی به تامین‌کنندگان" value={moneyCompact(d.payables)} tone={d.payables ? "warn" : "ok"} icon={<Wallet className="size-4" />} />
        <Stat label="وجه نقد دردست پیک‌ها" value={moneyCompact(d.cash_with_couriers)} tone={d.cash_with_couriers ? "warn" : "ok"} icon={<Banknote className="size-4" />} />
        <Stat label="کمبود / ناموجود" value={`${num(d.low_stock)} / ${num(d.out_of_stock)}`} tone={d.low_stock + d.out_of_stock ? "warn" : "ok"} icon={<PackageX className="size-4" />} />
      </section>

      <section className="grid grid-cols-3 gap-3">
        <Link to="/panel/orders"><Card className="p-3 text-center hover:border-brand/40"><div className="text-2xl font-bold tabular text-warn">{num(d.pending_orders)}</div><div className="text-xs text-muted">در انتظار آماده‌سازی</div></Card></Link>
        <Link to="/panel/couriers"><Card className="p-3 text-center hover:border-brand/40"><div className="text-2xl font-bold tabular text-ok">{num(d.ready_orders)}</div><div className="text-xs text-muted">آماده تحویل</div></Card></Link>
        <Link to="/panel/couriers"><Card className="p-3 text-center hover:border-brand/40"><div className="text-2xl font-bold tabular text-brand">{num(d.on_road_orders)}</div><div className="text-xs text-muted flex items-center justify-center gap-1"><Bike className="size-3" /> در مسیر</div></Card></Link>
      </section>

      <Card className="p-4">
        <h2 className="mb-2 font-semibold">فروش و سود ۱۴ روز اخیر (تومان)</h2>
        <BarsChart data={chart} x="label" series={[{ key: "revenue", label: "درآمد" }, { key: "profit", label: "سود ناخالص" }]} height={240} />
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <div className="mb-2 flex items-center justify-between"><h2 className="flex items-center gap-1.5 font-semibold"><AlertTriangle className="size-4 text-warn" /> هشدار موجودی</h2><Link to="/panel/erp/inventory" className="text-xs text-brand">انبار</Link></div>
          {!d.low_items.length ? <p className="py-4 text-center text-sm text-muted">همه کالاها موجودی کافی دارند.</p> : (
            <div className="divide-y divide-line">
              {d.low_items.map((i) => (
                <div key={i.id} className="flex items-center justify-between py-2 text-sm">
                  <span className="truncate">{i.name}</span>
                  <span className="shrink-0">{i.status === "out" ? <Badge tone="danger">ناموجود</Badge> : <Badge tone="warn">{num(i.stock)} از حداقل {num(i.min_stock)}</Badge>}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card className="p-4">
          <div className="mb-2 flex items-center justify-between"><h2 className="flex items-center gap-1.5 font-semibold"><ClipboardList className="size-4 text-brand" /> پرفروش‌ترین‌های ماه</h2><Link to="/panel/erp/reports" className="text-xs text-brand">گزارش‌ها</Link></div>
          {!d.top_products.length ? <p className="py-4 text-center text-sm text-muted">هنوز فروشی در این ماه ثبت نشده.</p> : (
            <div className="divide-y divide-line">
              {d.top_products.map((p) => (
                <div key={p.name} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span className="truncate">{p.name} <span className="text-xs text-muted">× {num(p.qty)}</span></span>
                  <span className="shrink-0 text-left tabular"><b>{toman(p.revenue)}</b><span className="mr-2 text-xs text-ok">{num(p.margin, 1)}٪</span></span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
