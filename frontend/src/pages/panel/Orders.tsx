import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MapPin, Package, Phone, ShoppingCart, User } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Field, Loading, PageHeader, Segmented, Sheet, Stat, Textarea, useToast } from "../../components/ui";
import { api, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { ago, dateTime, num, telLink, toman } from "../../lib/format";

type OrderT = {
  id: number; code: string; store_name: string; customer_name: string; customer_phone: string;
  delivery: string; delivery_display: string; address: string; note: string; total: number;
  status: string; status_display: string; store_note: string; created_at: string;
  items: { name: string; unit_display: string; price: number; quantity: number; line_total: number }[];
  events: { status_display: string; note: string; created_at: string }[];
};

const ORDER_TONE: Record<string, "neutral" | "brand" | "ok" | "warn" | "danger"> = {
  new: "warn", confirmed: "brand", preparing: "brand", ready: "ok", delivered: "neutral", canceled: "danger",
};

/** اقدام بعدی مجاز فروشنده در هر وضعیت */
const NEXT: Record<string, { status: string; label: string }[]> = {
  new: [{ status: "confirmed", label: "تایید سفارش" }, { status: "canceled", label: "رد سفارش" }],
  confirmed: [{ status: "preparing", label: "شروع آماده‌سازی" }, { status: "ready", label: "آماده تحویل" }, { status: "canceled", label: "لغو" }],
  preparing: [{ status: "ready", label: "آماده تحویل" }, { status: "canceled", label: "لغو" }],
  ready: [{ status: "delivered", label: "تحویل شد" }, { status: "canceled", label: "لغو" }],
};

export default function Orders() {
  const { user } = useAuth();
  const [status, setStatus] = useState("");
  const [sel, setSel] = useState<OrderT | null>(null);
  const q = useQuery({
    queryKey: ["orders", status],
    queryFn: () => api.get<Page<OrderT>>("/orders/", { status: status || undefined, page_size: 100 }),
    refetchInterval: 60_000,
  });
  const sum = useQuery({ queryKey: ["orders-summary"], queryFn: () => api.get("/orders/summary/") });
  const rows = q.data?.results ?? [];
  const isStore = user!.role === "store";

  return (
    <div className="space-y-4">
      <PageHeader
        title={isStore ? "سفارش‌های فروشگاه" : "سفارش‌های فروشگاه‌ها"}
        subtitle={isStore ? "سفارش‌هایی که مشتریان از ویترین اینترنتی شما ثبت کرده‌اند." : undefined}
      />
      {sum.data && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="سفارش جدید" value={num(sum.data.new)} tone={sum.data.new ? "warn" : "ok"} icon={<ShoppingCart className="size-4" />} />
          <Stat label="در جریان" value={num(sum.data.open)} icon={<Package className="size-4" />} />
          <Stat label="تحویل‌شده" value={num(sum.data.delivered)} tone="ok" />
          <Stat label="فروش تحویل‌شده" value={toman(sum.data.revenue)} />
        </div>
      )}
      <Segmented value={status} onChange={setStatus} options={[
        { value: "", label: "همه" }, { value: "new", label: "جدید" }, { value: "confirmed", label: "تاییدشده" },
        { value: "preparing", label: "آماده‌سازی" }, { value: "ready", label: "آماده تحویل" },
        { value: "delivered", label: "تحویل‌شده" }, { value: "canceled", label: "لغوشده" },
      ]} />

      {q.isLoading ? <Loading /> : !rows.length ? (
        <Card><Empty title="سفارشی در این وضعیت نیست" icon={<ShoppingCart className="size-7" />}>
          {isStore ? "به‌محض ثبت سفارش توسط مشتری، اینجا نمایش داده می‌شود و اعلان دریافت می‌کنید." : undefined}
        </Empty></Card>
      ) : (
        <div className="space-y-2">
          {rows.map((o) => (
            <Card key={o.id} className="cursor-pointer p-4 hover:border-brand/40" onClick={() => setSel(o)}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium" dir="ltr">{o.code}</span>
                    <Badge tone={ORDER_TONE[o.status]}>{o.status_display}</Badge>
                  </div>
                  <div className="mt-1 truncate text-sm text-muted">
                    {o.customer_name} · {num(o.items.length)} قلم · {o.delivery_display}
                  </div>
                  <div className="mt-0.5 text-xs text-muted">{ago(o.created_at)}</div>
                </div>
                <div className="shrink-0 text-left font-bold tabular">{toman(o.total)}</div>
              </div>
            </Card>
          ))}
        </div>
      )}
      {sel && <OrderSheet order={sel} canAct={isStore || user!.role === "admin"} onClose={() => setSel(null)} />}
    </div>
  );
}

function OrderSheet({ order, canAct, onClose }: { order: OrderT; canAct: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [note, setNote] = useState("");
  const m = useMutation({
    mutationFn: (status: string) => api.post(`/orders/${order.id}/transition/`, { status, note }),
    onSuccess: () => {
      toast("وضعیت سفارش به‌روز شد");
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["orders-summary"] });
      onClose();
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const actions = NEXT[order.status] ?? [];

  return (
    <Sheet open onClose={onClose} title={`سفارش ${order.code}`}>
      <div className="flex items-center justify-between">
        <Badge tone={ORDER_TONE[order.status]}>{order.status_display}</Badge>
        <span className="text-xs text-muted">{dateTime(order.created_at)}</span>
      </div>

      <div className="mt-4 space-y-1.5 rounded-xl bg-surface-2 p-3 text-sm">
        <p className="flex items-center gap-1.5"><User className="size-4 text-muted" /> {order.customer_name}</p>
        <p className="flex items-center gap-1.5">
          <Phone className="size-4 text-muted" />
          <a href={telLink(order.customer_phone)} className="text-brand" dir="ltr">{order.customer_phone}</a>
        </p>
        <p className="flex items-start gap-1.5">
          <MapPin className="mt-0.5 size-4 shrink-0 text-muted" />
          <span>{order.delivery_display}{order.address && ` — ${order.address}`}</span>
        </p>
        {order.note && <p className="pt-1 text-muted">یادداشت مشتری: {order.note}</p>}
      </div>

      <div className="mt-4 divide-y divide-line rounded-xl border border-line">
        {order.items.map((it, i) => (
          <div key={i} className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
            <div className="min-w-0">
              <div className="truncate">{it.name}</div>
              <div className="text-xs text-muted">{toman(it.price)} × {num(it.quantity)} {it.unit_display}</div>
            </div>
            <b className="shrink-0 tabular">{toman(it.line_total)}</b>
          </div>
        ))}
        <div className="flex items-center justify-between px-3 py-2.5">
          <span className="text-sm font-medium">مبلغ کل</span>
          <b className="tabular">{toman(order.total)}</b>
        </div>
      </div>

      {canAct && actions.length > 0 && (
        <div className="mt-5 space-y-3 border-t border-line pt-4">
          <Field label="یادداشت برای مشتری (اختیاری)">
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} className="min-h-16" placeholder="مثلا: سفارش شما تا یک ساعت دیگر آماده است." />
          </Field>
          <div className="flex flex-wrap gap-2">
            {actions.map((a) => (
              <Button
                key={a.status}
                variant={a.status === "canceled" ? "danger" : "primary"}
                loading={m.isPending}
                onClick={() => m.mutate(a.status)}
              >
                {a.label}
              </Button>
            ))}
          </div>
        </div>
      )}

      <ol className="mt-5 space-y-3 border-r-2 border-line pr-4">
        {order.events.map((e, i) => (
          <li key={i} className="relative">
            <span className="absolute -right-[23px] top-1.5 size-3 rounded-full border-2 border-surface bg-brand" />
            <div className="text-sm font-medium">{e.status_display}</div>
            {e.note && <div className="text-sm text-muted">{e.note}</div>}
            <div className="text-[11px] text-muted">{dateTime(e.created_at)}</div>
          </li>
        ))}
      </ol>
    </Sheet>
  );
}
