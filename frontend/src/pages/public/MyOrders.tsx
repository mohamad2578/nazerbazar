import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Phone, ShoppingCart, Store } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, Button, Card, Empty, Loading, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { ago, dateTime, num, telLink, toman } from "../../lib/format";

type OrderT = {
  id: number; code: string; store: number; store_name: string; store_phone: string; store_address: string;
  delivery_display: string; address: string; total: number; status: string; status_display: string;
  store_note: string; created_at: string;
  items: { name: string; unit_display: string; price: number; quantity: number; line_total: number }[];
  events: { status_display: string; note: string; created_at: string }[];
};

const TONE: Record<string, "neutral" | "brand" | "ok" | "warn" | "danger"> = {
  new: "warn", confirmed: "brand", preparing: "brand", ready: "ok", delivered: "neutral", canceled: "danger",
};

/** سفارش‌های ثبت‌شده شهروند از فروشگاه‌های اینترنتی. */
export default function MyOrders() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["my-orders"], queryFn: () => api.get<OrderT[]>("/public/orders/mine/") });
  const cancel = useMutation({
    mutationFn: (code: string) => api.post(`/public/orders/${code}/cancel/`),
    onSuccess: () => { toast("سفارش لغو شد"); qc.invalidateQueries({ queryKey: ["my-orders"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });

  if (q.isLoading) return <Loading />;
  const rows = q.data ?? [];

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-lg font-bold">سفارش‌های من</h1>
      {!rows.length ? (
        <Card>
          <Empty title="هنوز سفارشی ثبت نکرده‌اید" icon={<ShoppingCart className="size-7" />}>
            از صفحه هر فروشگاه می‌توانید محصولات آن را سفارش دهید.
          </Empty>
        </Card>
      ) : (
        rows.map((o) => (
          <Card key={o.id} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <Link to={`/s/${o.store}`} className="inline-flex items-center gap-1.5 font-medium">
                  <Store className="size-4 text-brand" /> {o.store_name}
                </Link>
                <div className="mt-0.5 text-xs text-muted" dir="ltr">{o.code}</div>
              </div>
              <Badge tone={TONE[o.status]}>{o.status_display}</Badge>
            </div>

            <div className="mt-3 divide-y divide-line rounded-xl bg-surface-2 px-3">
              {o.items.map((it, i) => (
                <div key={i} className="flex justify-between py-2 text-sm">
                  <span className="truncate">{it.name} <span className="text-xs text-muted">× {num(it.quantity)}</span></span>
                  <b className="shrink-0 tabular">{toman(it.line_total)}</b>
                </div>
              ))}
            </div>

            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
              <span>{o.delivery_display} · {ago(o.created_at)}</span>
              <b className="tabular text-sm text-ink">{toman(o.total)}</b>
            </div>

            {o.store_note && <p className="mt-2 rounded-xl bg-brand-soft p-2.5 text-xs text-brand">پیام فروشگاه: {o.store_note}</p>}

            <div className="mt-3 flex gap-2">
              <a href={telLink(o.store_phone)} className={`inline-flex h-9 items-center gap-1.5 rounded-xl bg-surface-2 px-3 text-sm ${!o.store_phone && "pointer-events-none opacity-40"}`}>
                <Phone className="size-4" /> تماس با فروشگاه
              </a>
              {(o.status === "new" || o.status === "confirmed") && (
                <Button size="sm" variant="secondary" loading={cancel.isPending} onClick={() => confirm("سفارش لغو شود؟") && cancel.mutate(o.code)}>
                  لغو سفارش
                </Button>
              )}
            </div>

            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-brand">سوابق سفارش</summary>
              <ol className="mt-2 space-y-2 border-r-2 border-line pr-3">
                {o.events.map((e, i) => (
                  <li key={i} className="relative text-xs">
                    <span className="absolute -right-[19px] top-1 size-2.5 rounded-full border-2 border-surface bg-brand" />
                    <div className="font-medium">{e.status_display}</div>
                    {e.note && <div className="text-muted">{e.note}</div>}
                    <div className="text-[11px] text-muted">{dateTime(e.created_at)}</div>
                  </li>
                ))}
              </ol>
            </details>
          </Card>
        ))
      )}
    </div>
  );
}
