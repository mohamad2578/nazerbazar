import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Banknote, Bike, CheckCircle2, ChevronDown, LogOut, MapPin, Navigation, Package, Phone, RefreshCw, Store, XCircle } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
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
  const [tab, setTab] = useState<"active" | "done">("active");
  const [failing, setFailing] = useState<CourierOrder | null>(null);
  const me = useQuery({ queryKey: ["courier-me"], queryFn: () => api.get<{ name: string; store: string }>("/courier/me/"), retry: false });
  const q = useQuery({
    queryKey: ["courier-orders", tab],
    queryFn: () => api.get<CourierOrder[]>("/courier/orders/", { scope: tab }),
    refetchInterval: 20_000,
    enabled: me.isSuccess,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["courier-orders"] });

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
        <Segmented value={tab} onChange={setTab} options={[{ value: "active", label: "در جریان" }, { value: "done", label: "تحویل‌شده‌ها" }]} />
        {tab === "active" && cash > 0 && (
          <Card className="flex items-center gap-2 border-warn/40 bg-warn-soft p-3 text-sm text-warn">
            <Banknote className="size-5" /> وجه نقد دریافتی از مشتریانِ در مسیر: <b className="tabular">{toman(cash)}</b>
          </Card>
        )}
        {q.isLoading ? <Loading /> : q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : !rows.length ? (
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
