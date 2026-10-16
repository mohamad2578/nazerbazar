import { useQuery } from "@tanstack/react-query";
import { Eye, MousePointerClick, Search, Smartphone, Users, X } from "lucide-react";
import { useMemo, useState } from "react";
import { BarsChart } from "../../components/charts";
import { Card, DataTable, Empty, Input, Loading, PageHeader, Segmented, Stat } from "../../components/ui";
import { api } from "../../lib/api";
import { dateShort, num } from "../../lib/format";

type Report = {
  granularity: "hour" | "day";
  page_views: number; visitors: number; product_views: number; logged_in_visitors: number;
  platform: { web: number; app: number };
  series: { t: string; views: number; visitors: number }[];
  by_hour: { h: number; views: number }[];
  focus_product: number | null;
  top_products: { id: number; name: string; union: string; views: number; visitors: number }[];
  top_stores: { id: number; name: string; views: number; visitors: number }[];
  top_pages: { path: string; views: number }[];
};

const PRESETS: [string, string, number][] = [["1h", "یک ساعت", 1], ["24h", "۲۴ ساعت", 24], ["7d", "۷ روز", 24 * 7], ["30d", "۳۰ روز", 24 * 30]];

/** نام خوانا برای مسیرهای سایت */
const PAGE_NAMES: Record<string, string> = { "/": "صفحه اصلی", "/map": "نقشه", "/news": "اخبار", "/rates": "نرخ‌نامه", "/track": "پیگیری", "/login": "ورود", "/suppliers": "ثبت‌نام تامین‌کننده", "/register-store": "ثبت‌نام فروشگاه", "/report": "گزارش تخلف" };
const pageName = (p: string) => PAGE_NAMES[p] ?? (p.startsWith("/p/") ? "صفحه کالا" : p.startsWith("/s/") ? "صفحه فروشگاه" : p.startsWith("/news/") ? "خبر" : p);

const toLocalInput = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

/** آمار بازدید سامانه: تعداد بازدید و بازدیدکننده در بازه دلخواه، کالاهای پربازدید و ساعات اوج. */
export default function Visits() {
  const [preset, setPreset] = useState("7d");
  const [custom, setCustom] = useState(() => ({ from: toLocalInput(new Date(Date.now() - 86400000)), to: toLocalInput(new Date()) }));

  const [focus, setFocus] = useState<{ id: number; name: string } | null>(null);
  const [search, setSearch] = useState("");
  const range = useMemo(() => {
    if (preset === "custom") return { from: custom.from, to: custom.to };
    const hours = PRESETS.find((p) => p[0] === preset)![2];
    // بازه روی ساعت گرد می‌شود تا کلید کش در هر بار رندر عوض نشود
    const end = new Date(); end.setMinutes(59, 59, 0);
    return { from: toLocalInput(new Date(end.getTime() - hours * 3600000)), to: toLocalInput(end) };
  }, [preset, custom]);

  const q = useQuery({
    queryKey: ["visits", range, focus?.id],
    queryFn: () => api.get<Report>("/analytics/visits/", { ...range, product: focus?.id }),
    refetchInterval: 60_000,
  });
  const d = q.data;

  const series = (d?.series ?? []).map((r) => ({
    ...r,
    label: d!.granularity === "hour"
      ? new Date(r.t).toLocaleTimeString("fa-IR", { hour: "2-digit", minute: "2-digit" })
      : dateShort(r.t),
  }));
  const hours = Array.from({ length: 24 }, (_, h) => ({ label: num(h), views: d?.by_hour.find((x) => x.h === h)?.views ?? 0 }));
  const appShare = d && d.page_views ? Math.round((d.platform.app / d.page_views) * 100) : 0;

  return (
    <div className="space-y-4">
      <PageHeader title="آمار بازدید" subtitle="تعداد بازدید و بازدیدکننده سامانه و کالاهایی که کاربران بیشتر دیده‌اند" />

      <Card className="space-y-3 p-4">
        <Segmented value={preset} onChange={setPreset} options={[...PRESETS.map(([v, l]) => ({ value: v, label: l })), { value: "custom", label: "بازه دلخواه" }]} />
        {preset === "custom" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">از
              <Input type="datetime-local" value={custom.from} onChange={(e) => setCustom({ ...custom, from: e.target.value })} dir="ltr" className="mt-1" />
            </label>
            <label className="text-sm">تا
              <Input type="datetime-local" value={custom.to} onChange={(e) => setCustom({ ...custom, to: e.target.value })} dir="ltr" className="mt-1" />
            </label>
          </div>
        )}
      </Card>

      {q.isLoading || !d ? <Loading /> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="بازدید صفحات" value={num(d.page_views)} icon={<Eye className="size-5" />} />
            <Stat label="بازدیدکننده یکتا" value={num(d.visitors)} sub={`${num(d.logged_in_visitors)} کاربر واردشده`} icon={<Users className="size-5" />} />
            <Stat label="کلیک روی کالاها" value={num(d.product_views)} icon={<MousePointerClick className="size-5" />} />
            <Stat label="از اپلیکیشن" value={`${num(appShare)}٪`} sub={`${num(d.platform.app)} بازدید`} icon={<Smartphone className="size-5" />} />
          </div>

          <Card className="p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold">
                {focus ? `روند کلیک روی «${focus.name}»` : "روند بازدید سامانه"} ({d.granularity === "hour" ? "ساعتی" : "روزانه"})
              </h2>
              {focus && (
                <button onClick={() => setFocus(null)} className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-3 py-1 text-xs">
                  <X className="size-3.5" /> نمایش کل سامانه
                </button>
              )}
            </div>
            {series.length ? (
              <BarsChart data={series} x="label" series={focus
                ? [{ key: "views", label: "کلیک" }, { key: "visitors", label: "نفر" }]
                : [{ key: "views", label: "بازدید" }, { key: "visitors", label: "بازدیدکننده" }]} />
            ) : <Empty title="در این بازه بازدیدی ثبت نشده است" />}
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <div className="flex flex-wrap items-center justify-between gap-2 p-4 pb-2">
                <h2 className="font-semibold">کلیک روی هر کالا</h2>
                <div className="relative w-full sm:w-48">
                  <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
                  <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="جستجوی کالا" className="h-9 pr-9" />
                </div>
              </div>
              <p className="px-4 pb-2 text-xs text-muted">همه کالاها، حتی بدون کلیک. روی هر کالا بزنید تا روند کلیک همان کالا در نمودار بالا نمایش داده شود.</p>
              <DataTable
                rows={d.top_products.filter((r) => !search || r.name.includes(search))}
                onRowClick={(r) => setFocus({ id: r.id, name: r.name })}
                columns={[
                  { key: "name", label: "کالا", render: (r) => <span className={focus?.id === r.id ? "font-bold text-brand" : ""}>{r.name}</span> },
                  { key: "union", label: "اتحادیه", hideOnMobile: true },
                  { key: "views", label: "کلیک", render: (r) => <b className="tabular">{num(r.views)}</b> },
                  { key: "visitors", label: "نفر", render: (r) => num(r.visitors) },
                ]}
              />
            </Card>
            <Card className="p-4">
              <h2 className="mb-3 font-semibold">ساعات اوج بازدید</h2>
              <BarsChart data={hours} x="label" series={[{ key: "views", label: "بازدید" }]} height={220} />
            </Card>
          </div>

          <Card>
            <h2 className="p-4 pb-2 font-semibold">بازدید صفحه فروشگاه‌ها</h2>
            {d.top_stores.length ? (
              <DataTable
                rows={d.top_stores}
                columns={[
                  { key: "name", label: "فروشگاه" },
                  { key: "views", label: "بازدید", render: (r) => <b className="tabular">{num(r.views)}</b> },
                  { key: "visitors", label: "نفر", render: (r) => num(r.visitors) },
                ]}
              />
            ) : <Empty title="هنوز صفحه فروشگاهی دیده نشده است" />}
          </Card>

          <Card>
            <h2 className="p-4 pb-2 font-semibold">صفحات پربازدید</h2>
            {d.top_pages.length ? (
              <DataTable
                rows={d.top_pages.map((p, i) => ({ ...p, id: i }))}
                columns={[
                  { key: "path", label: "صفحه", render: (r) => pageName(r.path) },
                  { key: "views", label: "بازدید", render: (r) => num(r.views) },
                ]}
              />
            ) : <Empty title="داده‌ای نیست" />}
          </Card>
        </>
      )}
    </div>
  );
}
