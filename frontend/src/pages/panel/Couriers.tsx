import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bike, MapPin, PackageCheck, Phone, Plus, Send, UserX } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, cx, Empty, Field, Input, Loading, PageHeader, Select, Sheet, useToast } from "../../components/ui";
import { api, fieldErrors, type Page } from "../../lib/api";
import { ago, num, telLink, toman } from "../../lib/format";
import { ORDER_TONE, type OrderT } from "../../lib/orders";

type CourierT = { id: number; name: string; mobile: string; is_active: boolean; to_deliver: number; on_road: number; delivered_today: number };

/** مدیریت پیک‌های فروشگاه + ارسال لیست سفارش‌های ارسالی به پیک. */
export default function Couriers() {
  const qc = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [picked, setPicked] = useState<number[]>([]);
  const [courierId, setCourierId] = useState("");
  const couriers = useQuery({ queryKey: ["couriers"], queryFn: () => api.get<CourierT[]>("/couriers/") });
  const orders = useQuery({
    queryKey: ["courier-orders-mgr"],
    queryFn: () => api.get<Page<OrderT>>("/orders/", { delivery: "delivery", page_size: 100 }),
    refetchInterval: 30_000,
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["couriers"] });
    qc.invalidateQueries({ queryKey: ["courier-orders-mgr"] });
    qc.invalidateQueries({ queryKey: ["orders"] });
  };
  const send = useMutation({
    mutationFn: () => api.post<{ assigned: number }>("/orders/assign/", { courier: courierId ? Number(courierId) : null, orders: picked }),
    onSuccess: (r) => { toast(r.assigned ? `${num(r.assigned)} سفارش برای پیک ارسال شد` : "پیک از سفارش‌ها برداشته شد"); setPicked([]); refresh(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const toggle = useMutation({
    mutationFn: (c: CourierT) => api.patch(`/couriers/${c.id}/`, { is_active: !c.is_active }),
    onSuccess: refresh,
    onError: (e: Error) => toast(e.message, "danger"),
  });

  const active = (couriers.data ?? []).filter((c) => c.is_active);
  const open = (orders.data?.results ?? []).filter((o) => ["confirmed", "preparing", "ready", "out_for_delivery"].includes(o.status));
  const assignable = open.filter((o) => o.status !== "out_for_delivery");
  const flip = (id: number) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  return (
    <div className="space-y-5">
      <PageHeader
        title="مدیریت پیک"
        subtitle="پیک‌های فروشگاه را تعریف کنید و لیست سفارش‌های ارسالی را برایشان بفرستید؛ پیک با اپلیکیشن پیک (همین شماره موبایل) سفارش‌ها را می‌بیند."
        actions={<Button size="sm" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>پیک جدید</Button>}
      />

      <section className="space-y-2">
        <h2 className="font-semibold">پیک‌های من</h2>
        {couriers.isLoading ? <Loading /> : !couriers.data?.length ? (
          <Card><Empty title="هنوز پیکی ثبت نکرده‌اید" icon={<Bike className="size-7" />}>با «پیک جدید» شماره موبایل پیک را ثبت کنید.</Empty></Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {couriers.data.map((c) => (
              <Card key={c.id} className={cx("p-4", !c.is_active && "opacity-60")}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 font-medium"><Bike className="size-4 text-brand" /> {c.name || "—"} {!c.is_active && <Badge>غیرفعال</Badge>}</div>
                    <a href={telLink(c.mobile)} className="mt-0.5 inline-flex items-center gap-1 text-xs text-brand" dir="ltr"><Phone className="size-3" /> {c.mobile}</a>
                  </div>
                  <Button size="sm" variant="ghost" className="text-danger" icon={<UserX className="size-4" />} loading={toggle.isPending}
                    onClick={() => (c.is_active ? confirm(`«${c.name || c.mobile}» غیرفعال شود؟ سفارش‌های تحویل‌نگرفته‌اش بدون پیک می‌ماند.`) : true) && toggle.mutate(c)}>
                    {c.is_active ? "غیرفعال‌سازی" : "فعال‌سازی"}
                  </Button>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                  <Stat label="در انتظار تحویل" value={c.to_deliver} tone="warn" />
                  <Stat label="در مسیر" value={c.on_road} tone="brand" />
                  <Stat label="تحویل امروز" value={c.delivered_today} tone="ok" />
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">سفارش‌های ارسالی ({num(open.length)})</h2>
          {!!assignable.length && (
            <button className="text-xs text-brand" onClick={() => setPicked(picked.length === assignable.length ? [] : assignable.map((o) => o.id))}>
              {picked.length === assignable.length ? "برداشتن انتخاب همه" : "انتخاب همه"}
            </button>
          )}
        </div>
        {orders.isLoading ? <Loading /> : !open.length ? (
          <Card><Empty title="سفارش ارسالی در جریان نیست" icon={<PackageCheck className="size-7" />}>سفارش‌های «ارسال با پیک» پس از تایید فروشگاه اینجا می‌آیند.</Empty></Card>
        ) : (
          <div className="space-y-2">
            {open.map((o) => {
              const locked = o.status === "out_for_delivery";
              return (
                <Card key={o.id} className={cx("flex items-start gap-3 p-3", picked.includes(o.id) && "border-brand bg-brand-soft/40")}>
                  <input type="checkbox" className="mt-1.5 size-5 shrink-0" disabled={locked} checked={picked.includes(o.id)} onChange={() => flip(o.id)} />
                  <div className="min-w-0 flex-1 text-sm">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium" dir="ltr">{o.code}</span>
                      <Badge tone={ORDER_TONE[o.status]}>{o.status_display}</Badge>
                      {o.courier_name ? <Badge tone="brand"><Bike className="ml-1 inline size-3" />{o.courier_name}</Badge> : <Badge tone="warn">بدون پیک</Badge>}
                    </div>
                    <div className="mt-1 text-muted">{o.customer_name} · {toman(o.total)} · {o.payment_method_display}</div>
                    <div className="mt-0.5 flex items-start gap-1 text-xs text-muted"><MapPin className="mt-0.5 size-3.5 shrink-0" /> {o.address}</div>
                    <div className="mt-0.5 text-[11px] text-muted">{ago(o.created_at)}</div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
        {!!picked.length && (
          <div className="sticky bottom-3 z-10 flex flex-wrap items-center gap-2 rounded-2xl border border-brand/40 bg-surface p-3 shadow-xl">
            <span className="text-sm font-medium">{num(picked.length)} سفارش انتخاب شد</span>
            <Select value={courierId} onChange={(e) => setCourierId(e.target.value)} className="min-w-40 flex-1">
              <option value="">— برداشتن پیک —</option>
              {active.map((c) => <option key={c.id} value={c.id}>{c.name || c.mobile}</option>)}
            </Select>
            <Button icon={<Send className="size-4" />} loading={send.isPending} onClick={() => send.mutate()}>
              {courierId ? "ارسال به پیک" : "برداشتن پیک"}
            </Button>
          </div>
        )}
      </section>

      {adding && <CourierForm onClose={() => setAdding(false)} onDone={() => { setAdding(false); refresh(); }} />}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: "warn" | "brand" | "ok" }) {
  const cls = { warn: "bg-warn-soft text-warn", brand: "bg-brand-soft text-brand", ok: "bg-ok-soft text-ok" }[tone];
  return (
    <div className={cx("rounded-xl px-1 py-2", cls)}>
      <div className="text-lg font-bold tabular">{num(value)}</div>
      <div className="text-[10px]">{label}</div>
    </div>
  );
}

function CourierForm({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ mobile: "", first_name: "", last_name: "" });
  const m = useMutation({
    mutationFn: () => api.post("/couriers/", f),
    onSuccess: () => { toast("پیک ثبت شد؛ با همین شماره وارد اپلیکیشن پیک می‌شود"); onDone(); },
  });
  const err = fieldErrors(m.error);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <Sheet open onClose={onClose} title="ثبت پیک جدید"
      footer={<Button className="w-full" loading={m.isPending} disabled={!f.mobile} onClick={() => m.mutate()}>ثبت پیک</Button>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="موبایل پیک" error={err.mobile} className="sm:col-span-2" hint="پیک با همین شماره و کد پیامکی وارد اپلیکیشن پیک می‌شود.">
          <Input value={f.mobile} onChange={set("mobile")} dir="ltr" inputMode="numeric" className="text-left" placeholder="09…" />
        </Field>
        <Field label="نام"><Input value={f.first_name} onChange={set("first_name")} /></Field>
        <Field label="نام خانوادگی"><Input value={f.last_name} onChange={set("last_name")} /></Field>
      </div>
      {m.error && !Object.keys(err).length && <p className="mt-3 text-sm text-danger">{(m.error as Error).message}</p>}
    </Sheet>
  );
}
