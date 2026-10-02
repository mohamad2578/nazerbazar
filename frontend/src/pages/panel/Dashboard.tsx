import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clock, MessageSquareWarning, Package, ShieldCheck, Store, Tags } from "lucide-react";
import { Link } from "react-router-dom";
import { TrendChart } from "../../components/charts";
import { Badge, Card, Loading, PageHeader, Stat, STATUS_TONE } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { ago, hoursLeft, num, pct } from "../../lib/format";

export default function Dashboard() {
  const { user } = useAuth();
  return user!.role === "store" ? <StoreDashboard /> : <ManagerDashboard />;
}

function StoreDashboard() {
  const { user } = useAuth();
  const store = user!.store;
  const cat = useQuery({ queryKey: ["catalog"], queryFn: () => api.get("/store/catalog/"), enabled: store?.status === "active" });
  const ov = useQuery({ queryKey: ["overview"], queryFn: () => api.get("/analytics/overview/") });
  if (!store) return <Card className="p-6">فروشگاهی ثبت نشده است. <Link to="/register-store" className="text-brand">ثبت‌نام</Link></Card>;
  const items: any[] = cat.data?.items ?? [];
  const stale = items.filter((i) => i.is_stale);
  const unpriced = items.filter((i) => i.offer_price == null);
  return (
    <div className="space-y-5">
      <PageHeader title={store.name} subtitle={`عضو ${store.union_name}`} actions={<Badge tone={STATUS_TONE[store.status]}>{store.status_display}</Badge>} />
      {store.status !== "active" && (
        <Card className="border-warn/40 bg-warn-soft p-4 text-sm text-warn">
          {store.status === "pending" ? "درخواست شما در کارتابل اتحادیه در انتظار بررسی است." : `وضعیت: ${store.status_display}. ${store.status_reason}`}
          {store.status === "rejected" && <> پس از اصلاح <Link to="/panel/profile" className="underline">مشخصات فروشگاه</Link> درخواست دوباره ارسال می‌شود.</>}
        </Card>
      )}
      {stale.length > 0 && (
        <Card className="border-danger/30 bg-danger-soft p-4">
          <div className="flex items-center gap-2 font-medium text-danger"><AlertTriangle className="size-5" /> نرخ {num(stale.length)} کالا تغییر کرده است</div>
          <ul className="mt-2 space-y-1 text-sm">
            {stale.slice(0, 5).map((s) => {
              const h = hoursLeft(s.deadline);
              return <li key={s.product}>{s.name} — {s.hidden ? <b className="text-danger">از فهرست عمومی حذف شد</b> : <>مهلت: {num(Math.max(0, Math.floor(h ?? 0)))} ساعت</>}</li>;
            })}
          </ul>
          <Link to="/panel/prices" className="mt-3 inline-block text-sm font-medium text-danger underline">به‌روزرسانی قیمت‌ها</Link>
        </Card>
      )}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="کالاهای اتحادیه" value={num(items.length)} icon={<Package className="size-4" />} />
        <Stat label="قیمت ثبت‌شده" value={num(items.length - unpriced.length)} icon={<Tags className="size-4" />} tone="ok" />
        <Stat label="نیازمند به‌روزرسانی" value={num(stale.length)} icon={<Clock className="size-4" />} tone={stale.length ? "danger" : "ok"} />
        <Stat label="شکایات" value={num(ov.data?.complaints.total)} sub={`${num(ov.data?.complaints.open)} باز`} icon={<MessageSquareWarning className="size-4" />} tone="warn" />
      </div>
      {unpriced.length > 0 && store.status === "active" && (
        <Card className="p-4 text-sm">
          {num(unpriced.length)} کالای اتحادیه هنوز در فروشگاه شما قیمت ندارد. <Link to="/panel/prices" className="text-brand underline">ثبت قیمت</Link>
        </Card>
      )}
    </div>
  );
}

function ManagerDashboard() {
  const { user } = useAuth();
  const ov = useQuery({ queryKey: ["overview"], queryFn: () => api.get("/analytics/overview/") });
  const trend = useQuery({ queryKey: ["trend-index"], queryFn: () => api.get("/analytics/trends/", { days: 45 }) });
  const alerts = useQuery({ queryKey: ["alerts-top"], queryFn: () => api.get("/alerts/", { is_resolved: false, page_size: 5 }) });
  if (ov.isLoading) return <Loading />;
  const d = ov.data;
  return (
    <div className="space-y-5">
      <PageHeader title="داشبورد" subtitle={`${user!.role_display}${user!.scope_name ? ` · ${user!.scope_name}` : ""}`} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="فروشگاه فعال" value={num(d.stores.active)} sub={<Link to="/panel/stores?status=pending" className="text-warn">{num(d.stores.pending)} در انتظار تایید</Link>} icon={<Store className="size-4" />} />
        <Stat label="کالای نرخ‌گذاری‌شده" value={num(d.products.priced)} sub={`${num(d.price_changes.last_7_days)} تغییر نرخ در ۷ روز`} icon={<Package className="size-4" />} />
        <Stat label="انطباق قیمت فروشگاه‌ها" value={pct(d.offers.compliance_percent)} sub={`${num(d.offers.hidden_stale)} قیمت به‌روزنشده (پنهان)`} icon={<ShieldCheck className="size-4" />} tone={d.offers.compliance_percent >= 90 ? "ok" : "warn"} />
        <Stat label="شکایات باز" value={num(d.complaints.open)} sub={`میانگین رسیدگی ${d.complaints.avg_resolution_hours != null ? num(d.complaints.avg_resolution_hours, 1) + " ساعت" : "—"}`} icon={<MessageSquareWarning className="size-4" />} tone={d.complaints.open ? "danger" : "ok"} />
      </div>
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card className="p-4">
          <h2 className="font-semibold">شاخص قیمت (پایه = ۱۰۰)</h2>
          <p className="mb-2 text-xs text-muted">میانگین تغییر نرخ مصوب و قیمت واقعی فروشگاه‌ها طی ۴۵ روز</p>
          {trend.data?.series?.length ? (
            <TrendChart data={trend.data.series} series={[{ key: "official_index", label: "نرخ مصوب" }, { key: "market_index", label: "قیمت فروشگاه‌ها" }]} format={(v) => num(v, 1)} />
          ) : <p className="py-10 text-center text-sm text-muted">داده روزانه هنوز ثبت نشده است.</p>}
        </Card>
        <Card className="p-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">هشدارهای باز</h2>
            <Link to="/panel/alerts" className="text-xs text-brand">همه</Link>
          </div>
          <div className="space-y-2">
            {alerts.data?.results?.map((a: any) => (
              <div key={a.id} className="rounded-xl bg-surface-2 p-3 text-sm">
                <div className="flex items-start gap-2">
                  <AlertTriangle className={`mt-0.5 size-4 shrink-0 ${a.level === "critical" ? "text-danger" : "text-warn"}`} />
                  <span>{a.title}</span>
                </div>
                <div className="mt-1 text-[11px] text-muted">{a.kind_display} · {ago(a.created_at)}</div>
              </div>
            ))}
            {!alerts.data?.results?.length && <p className="flex items-center gap-2 py-6 text-sm text-ok"><CheckCircle2 className="size-4" /> هشدار بازی وجود ندارد</p>}
          </div>
        </Card>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="کل شکایات" value={num(d.complaints.total)} sub={`${num(d.complaints.last_7_days)} در ۷ روز اخیر`} />
        <Stat label="تخلف محرز" value={num(d.complaints.violations)} tone="danger" />
        <Stat label="میانگین تخفیف فروشگاه‌ها" value={pct(d.offers.avg_discount_percent)} sub="نسبت به نرخ مصوب" />
        <Stat label="میانگین امتیاز مشتریان" value={d.rating_avg ? num(d.rating_avg, 1) : "—"} sub="از ۵" />
      </div>
    </div>
  );
}
