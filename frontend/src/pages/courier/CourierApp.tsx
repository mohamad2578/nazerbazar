import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Banknote, Bike, CheckCircle2, ChevronDown, LogOut, MapPin, Navigation, Package, Phone, Power, RefreshCw, Store, TrendingUp, XCircle } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BarsChart } from "../../components/charts";
import { Badge, Button, Card, cx, Empty, ErrorBox, Field, Loading, Segmented, Sheet, Textarea, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { ago, directionsLink, num, telLink, toman, webMapLink } from "../../lib/format";

type CourierOrder = {
  id: number; code: string; status: string; status_display: string; store_name: string; store_phone: string;
  store_address: string; store_lat: string | null; store_lng: string | null; customer_name: string; customer_phone: string;
  address: string; lat: string | null; lng: string | null; note: string; store_note: string; total: number;
  payment_method_display: string; payment_status: string; cash_due: number; assigned_at: string | null; delivered_at: string | null;
  items: { name: string; quantity: number; unit_display: string }[];
};

const TONE: Record<string, "warn" | "brand" | "ok" | "neutral"> = {
  confirmed: "warn", preparing: "warn", ready: "ok", out_for_delivery: "brand", delivered: "neutral",
};

/** اپلیکیشن پیک: سفارش‌هایی که مدیر فروشگاه به پیک سپرده را می‌بیند، از فروشگاه تحویل می‌گیرد و به مشتری می‌رساند. */
export default function CourierApp() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState<"active" | "done" | "stats">("active");
  const [failing, setFailing] = useState<CourierOrder | null>(null);
  const me = useQuery({ queryKey: ["courier-me"], queryFn: () => api.get<{ name: string; store: string; is_online: boolean; fee_per_delivery: number }>("/courier/me/"), retry: false });
  const q = useQuery({
    queryKey: ["courier-orders", tab],
    queryFn: () => api.get<CourierOrder[]>("/courier/orders/", { scope: tab === "done" ? "done" : "active" }),
    refetchInterval: 20_000,
    enabled: me.isSuccess && tab !== "stats",
  });
  const stats = useQuery({ queryKey: ["courier-stats"], queryFn: () => api.get<Stats>("/courier/stats/"), refetchInterval: 30_000, enabled: me.isSuccess });
  const toast = useToast();
  const online = useMutation({
    mutationFn: (v: boolean) => api.post<{ is_online: boolean }>("/courier/online/", { online: v }),
    onSuccess: (r) => { toast(r.is_online ? "آنلاین شدید؛ مدیر فروشگاه می‌تواند سفارش بفرستد" : "آفلاین شدید"); qc.invalidateQueries({ queryKey: ["courier-me"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["courier-orders"] }); qc.invalidateQueries({ queryKey: ["courier-stats"] }); };

  if (me.isLoading) return <Loading />;
  if (me.error || !user?.is_courier)
    return (
      <div className="mx-auto max-w-md p-6">
        <Card className="p-6 text-center">
          <Bike className="mx-auto size-10 text-muted" />
          <h1 className="mt-3 font-bold">پیک فعالی ثبت نشده است</h1>
          <p className="mt-2 text-sm text-muted">
            مدیر فروشگاه باید شماره موبایل شما ({user?.mobile}) را در بخش «پیک‌ها» ثبت کند؛ سپس با همین شماره وارد شوید.
          </p>
          <Link to="/" className="mt-4 inline-block text-sm text-brand underline">بازگشت به سایت</Link>
        </Card>
      </div>
    );

  const rows = q.data ?? [];
  const cash = rows.reduce((s, o) => s + (o.status === "out_for_delivery" ? o.cash_due : 0), 0);
  return (
    <div className="mx-auto min-h-dvh max-w-lg bg-bg pb-10">
      <header className="sticky top-0 z-[500] flex items-center gap-3 border-b border-line bg-brand px-4 py-3 text-brand-ink">
        <span className="grid size-10 place-items-center rounded-xl bg-white/20"><Bike className="size-6" /></span>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="truncate font-bold">{me.data?.name}</div>
          <div className="truncate text-xs opacity-90">پیک «{me.data?.store}»</div>
        </div>
        <button onClick={refresh} className="grid size-9 place-items-center rounded-lg bg-white/15" aria-label="تازه‌سازی"><RefreshCw className="size-4" /></button>
        <button onClick={() => { logout(); nav("/login?next=/courier"); }} className="grid size-9 place-items-center rounded-lg bg-white/15" aria-label="خروج"><LogOut className="size-4" /></button>
      </header>

      <div className="space-y-3 p-4">
        <button
          onClick={() => online.mutate(!me.data?.is_online)}
          className={cx("flex w-full items-center justify-between gap-3 rounded-2xl border px-4 py-3 text-sm", me.data?.is_online ? "border-ok/40 bg-ok-soft text-ok" : "border-line bg-surface-2 text-muted")}
        >
          <span className="flex items-center gap-2 font-medium"><Power className="size-5" /> {me.data?.is_online ? "آنلاین — آماده دریافت سفارش" : "آفلاین — برای دریافت سفارش آنلاین شوید"}</span>
          <span className={cx("relative h-6 w-11 rounded-full transition", me.data?.is_online ? "bg-ok" : "bg-line")}><span className={cx("absolute top-0.5 size-5 rounded-full bg-white shadow transition-all", me.data?.is_online ? "right-0.5" : "right-[1.375rem]")} /></span>
        </button>
        {stats.data && (
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-2xl bg-brand-soft p-2.5 text-brand"><div className="text-xl font-bold tabular">{num(stats.data.today)}</div><div className="text-[11px]">تحویل امروز</div></div>
            <div className="rounded-2xl bg-ok-soft p-2.5 text-ok"><div className="text-sm font-bold tabular leading-7">{toman(stats.data.fee_today, false)}</div><div className="text-[11px]">کارمزد امروز</div></div>
            <div className="rounded-2xl bg-warn-soft p-2.5 text-warn"><div className="text-xl font-bold tabular">{num(stats.data.active)}</div><div className="text-[11px]">سفارش فعال</div></div>
          </div>
        )}
        <Segmented value={tab} onChange={setTab} options={[{ value: "active", label: "در جریان" }, { value: "done", label: "تحویل‌شده‌ها" }, { value: "stats", label: "آمار من" }]} />
        {tab === "stats" && stats.data && <StatsPanel s={stats.data} fee={me.data?.fee_per_delivery ?? 0} />}
        {tab === "active" && cash > 0 && (
          <Card className="flex items-center gap-2 border-warn/40 bg-warn-soft p-3 text-sm text-warn">
            <Banknote className="size-5" /> وجه نقد دریافتی از مشتریانِ در مسیر: <b className="tabular">{toman(cash)}</b>
          </Card>
        )}
        {tab === "stats" ? null : q.isLoading ? <Loading /> : q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : !rows.length ? (
          <Card><Empty title={tab === "active" ? "سفارشی به شما سپرده نشده" : "هنوز سفارشی تحویل نداده‌اید"} icon={<Package className="size-7" />}>
            {tab === "active" ? "وقتی مدیر فروشگاه لیست سفارش‌ها را بفرستد، همین‌جا می‌آید (هر ۲۰ ثانیه به‌روز می‌شود)." : undefined}
          </Empty></Card>
        ) : rows.map((o) => <OrderCard key={o.id} o={o} done={tab === "done"} onChanged={refresh} onFail={() => setFailing(o)} />)}
      </div>
      {failing && <FailSheet order={failing} onClose={() => setFailing(null)} onDone={() => { setFailing(null); refresh(); }} />}
    </div>
  );
}

function OrderCard({ o, done, onChanged, onFail }: { o: CourierOrder; done: boolean; onChanged: () => void; onFail: () => void }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const act = useMutation({
    mutationFn: (what: "pickup" | "deliver") => api.post(`/courier/orders/${o.id}/${what}/`),
    onSuccess: (_, what) => { toast(what === "pickup" ? "ثبت شد؛ سفارش در مسیر است" : "تحویل ثبت شد"); onChanged(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const toCustomer = directionsLink(o.lat, o.lng);
  const toStore = directionsLink(o.store_lat, o.store_lng);
  const ready = o.status === "ready";
  const road = o.status === "out_for_delivery";
  return (
    <Card className={cx("overflow-hidden", road && "border-brand/50")}>
      <div className="flex items-center justify-between gap-2 border-b border-line bg-surface-2 px-4 py-2.5">
        <span className="font-medium" dir="ltr">{o.code}</span>
        <Badge tone={TONE[o.status] ?? "neutral"}>{o.status_display}</Badge>
      </div>
      <div className="space-y-3 p-4 text-sm">
        {!done && !road && (
          <div className="rounded-xl bg-surface-2 p-3">
            <div className="flex items-center gap-1.5 text-xs text-muted"><Store className="size-3.5" /> دریافت از فروشگاه</div>
            <div className="mt-1 font-medium">{o.store_name}</div>
            <div className="text-muted">{o.store_address}</div>
            <div className="mt-2 flex gap-2">
              {o.store_phone && <a href={telLink(o.store_phone)} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-surface px-3 text-xs"><Phone className="size-3.5" /> تماس</a>}
              {toStore && <a href={toStore} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-surface px-3 text-xs"><Navigation className="size-3.5" /> مسیر فروشگاه</a>}
            </div>
          </div>
        )}

        <div>
          <div className="flex items-center gap-1.5 text-xs text-muted"><MapPin className="size-3.5" /> تحویل به مشتری</div>
          <div className="mt-1 text-base font-bold">{o.customer_name}</div>
          <div className="mt-0.5 leading-6">{o.address}</div>
          {o.note && <div className="mt-1 rounded-lg bg-warn-soft p-2 text-xs text-warn">یادداشت مشتری: {o.note}</div>}
          {o.store_note && <div className="mt-1 rounded-lg bg-brand-soft p-2 text-xs text-brand">پیام فروشگاه: {o.store_note}</div>}
          {!done && (
            <div className="mt-2 flex gap-2">
              <a href={telLink(o.customer_phone)} className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-xl bg-brand text-brand-ink"><Phone className="size-4" /> تماس با مشتری</a>
              {toCustomer ? (
                <a href={toCustomer} className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-xl bg-surface-2"><Navigation className="size-4" /> مسیریابی</a>
              ) : (
                <span className="inline-flex h-10 flex-1 items-center justify-center rounded-xl bg-surface-2 text-xs text-muted">موقعیت نقشه ثبت نشده</span>
              )}
            </div>
          )}
          {!done && o.lat && o.lng && <a href={webMapLink(o.lat, o.lng)} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs text-brand underline">باز کردن در نقشه (مرورگر)</a>}
        </div>

        {o.cash_due > 0 && (
          <div className="flex items-center justify-between rounded-xl bg-warn-soft px-3 py-2.5 text-warn">
            <span className="flex items-center gap-1.5"><Banknote className="size-4" /> دریافت نقدی از مشتری</span>
            <b className="tabular text-base">{toman(o.cash_due)}</b>
          </div>
        )}
        {o.cash_due === 0 && !done && <div className="text-xs text-ok">پرداخت‌شده ({o.payment_method_display}) — وجهی دریافت نکنید.</div>}

        <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between text-xs text-brand">
          اقلام سفارش ({num(o.items.length)} قلم) <ChevronDown className={cx("size-4 transition", open && "rotate-180")} />
        </button>
        {open && (
          <ul className="divide-y divide-line rounded-xl bg-surface-2 px-3">
            {o.items.map((it, i) => <li key={i} className="flex justify-between py-2"><span>{it.name}</span><span className="tabular text-muted">× {num(it.quantity)}</span></li>)}
          </ul>
        )}

        {!done && (
          <div className="space-y-2 pt-1">
            {ready && <Button className="w-full" size="lg" loading={act.isPending} icon={<Package className="size-5" />} onClick={() => act.mutate("pickup")}>سفارش را از فروشگاه تحویل گرفتم</Button>}
            {!ready && !road && <div className="rounded-xl bg-surface-2 p-3 text-center text-xs text-muted">فروشگاه هنوز سفارش را آماده نکرده؛ پس از «آماده تحویل» شدن می‌توانید تحویل بگیرید.</div>}
            {road && (<>
              <Button className="w-full" size="lg" loading={act.isPending} icon={<CheckCircle2 className="size-5" />} onClick={() => confirm("تحویل به مشتری انجام شد؟") && act.mutate("deliver")}>به مشتری تحویل دادم</Button>
              <Button className="w-full" variant="secondary" icon={<XCircle className="size-4" />} onClick={onFail}>تحویل ناموفق بود</Button>
            </>)}
          </div>
        )}
        {done && <div className="text-xs text-muted">تحویل {ago(o.delivered_at)}</div>}
      </div>
    </Card>
  );
}

function FailSheet({ order, onClose, onDone }: { order: CourierOrder; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const m = useMutation({
    mutationFn: () => api.post(`/courier/orders/${order.id}/fail/`, { reason }),
    onSuccess: () => { toast("سفارش به فروشگاه برگشت"); onDone(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <Sheet open onClose={onClose} title={`تحویل ناموفق ${order.code}`}
      footer={<Button className="w-full" variant="danger" loading={m.isPending} disabled={!reason.trim()} onClick={() => m.mutate()}>ثبت و بازگرداندن به فروشگاه</Button>}>
      <Field label="دلیل" hint="مثلا: مشتری پاسخ نداد، نشانی اشتباه است">
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} className="min-h-24" />
      </Field>
    </Sheet>
  );
}

type Stats = {
  today: number; week: number; month: number; total: number; fee_today: number; cash_on_hand: number; fee_due: number; fee_earned: number; active: number;
  days: { date: string; deliveries: number }[];
};

function StatsPanel({ s, fee }: { s: Stats; fee: number }) {
  const days = s.days.map((d) => ({ ...d, label: d.date.slice(5) }));
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2 text-center text-sm">
        <Card className="p-3"><div className="text-xl font-bold tabular">{num(s.week)}</div><div className="text-[11px] text-muted">تحویل ۷ روز</div></Card>
        <Card className="p-3"><div className="text-xl font-bold tabular">{num(s.month)}</div><div className="text-[11px] text-muted">تحویل ۳۰ روز</div></Card>
        <Card className="p-3"><div className="text-xl font-bold tabular">{num(s.total)}</div><div className="text-[11px] text-muted">کل تحویل‌ها</div></Card>
      </div>
      <Card className="p-4">
        <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold"><TrendingUp className="size-4 text-brand" /> تحویل‌های ۷ روز اخیر</h3>
        <BarsChart data={days} x="label" series={[{ key: "deliveries", label: "تحویل" }]} height={170} />
      </Card>
      <Card className="divide-y divide-line text-sm">
        <div className="flex items-center justify-between px-4 py-3"><span>کارمزد هر تحویل</span><b className="tabular">{toman(fee)}</b></div>
        <div className="flex items-center justify-between px-4 py-3"><span>کل کارمزد کسب‌شده</span><b className="tabular">{toman(s.fee_earned)}</b></div>
        <div className="flex items-center justify-between px-4 py-3 text-warn"><span>کارمزد دریافت‌نشده از فروشگاه</span><b className="tabular">{toman(s.fee_due)}</b></div>
        <div className="flex items-center justify-between px-4 py-3 text-warn"><span>وجه نقد دردست شما (باید تحویل فروشگاه شود)</span><b className="tabular">{toman(s.cash_on_hand)}</b></div>
      </Card>
    </div>
  );
}
