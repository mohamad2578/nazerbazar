import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bike, CheckCircle2, CreditCard, MapPin, Phone, Printer, ShoppingCart, Store, XCircle } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge, Button, Card, Empty, Loading, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { ago, dateTime, num, telLink, toman, webMapLink } from "../../lib/format";
import { printSalesInvoice, type InvoiceData } from "../../lib/erp";
import { ORDER_TONE, PAY_TONE, type OrderT } from "../../lib/orders";

/** سفارش‌های ثبت‌شده شهروند: شرح اقلام، میزان تخفیف، وضعیت پرداخت و فاکتور. */
export default function MyOrders() {
  const qc = useQueryClient();
  const toast = useToast();
  const [params] = useSearchParams();
  const pay = params.get("pay");
  const q = useQuery({ queryKey: ["my-orders"], queryFn: () => api.get<OrderT[]>("/public/orders/mine/") });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["my-orders"] });
    qc.invalidateQueries({ queryKey: ["wallet"] });
  };
  const cancel = useMutation({
    mutationFn: (code: string) => api.post(`/public/orders/${code}/cancel/`),
    onSuccess: () => { toast("سفارش لغو شد"); refresh(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const payNow = useMutation({
    mutationFn: (code: string) => api.post<OrderT>(`/public/orders/${code}/pay/`),
    onSuccess: (o) => { if (o.payment_url) window.location.href = o.payment_url; },
    onError: (e: Error) => toast(e.message, "danger"),
  });

  if (q.isLoading) return <Loading />;
  const rows = q.data ?? [];

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-lg font-bold">سفارش‌های من</h1>
      {pay && (
        <Card className={`flex items-center gap-2 p-3 text-sm ${pay === "ok" ? "border-ok/40 bg-ok-soft text-ok" : "border-danger/40 bg-danger-soft text-danger"}`}>
          {pay === "ok" ? <CheckCircle2 className="size-5" /> : <XCircle className="size-5" />}
          {pay === "ok" ? "پرداخت با موفقیت انجام شد و سفارش شما برای فروشگاه ارسال شد." : "پرداخت انجام نشد؛ سفارش لغو و هزینه‌ای از شما کسر نشد."}
        </Card>
      )}
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
              <div className="flex flex-col items-end gap-1">
                <Badge tone={ORDER_TONE[o.status]}>{o.status_display}</Badge>
                <Badge tone={PAY_TONE[o.payment_status]}>{o.payment_method_display} · {o.payment_status_display}</Badge>
              </div>
            </div>

            <div className="mt-3 divide-y divide-line rounded-xl bg-surface-2 px-3">
              {o.items.map((it, i) => (
                <div key={i} className="flex items-start justify-between gap-2 py-2 text-sm">
                  <span className="min-w-0">
                    <span className="block truncate">{it.name} <span className="text-xs text-muted">× {num(it.quantity)}</span></span>
                    {it.bundle_name && <span className="text-[11px] text-brand">از بسته «{it.bundle_name}»</span>}
                  </span>
                  <span className="shrink-0 text-left">
                    {it.list_price > it.price && <s className="block text-[11px] text-muted tabular">{toman(it.list_price * it.quantity, false)}</s>}
                    <b className="tabular">{toman(it.line_total)}</b>
                  </span>
                </div>
              ))}
            </div>

            <div className="mt-3 space-y-1 text-sm">
              {o.savings > 0 && (
                <div className="flex justify-between text-ok">
                  <span>میزان تخفیف شما{o.discount > 0 && " (شامل تخفیف بسته)"}</span>
                  <b className="tabular">{toman(o.savings)}</b>
                </div>
              )}
              <div className="flex justify-between">
                <span>مبلغ پرداختی</span>
                <b className="tabular">{toman(o.total)}</b>
              </div>
            </div>
            <div className="mt-2 text-xs text-muted">{o.delivery_display} · {ago(o.created_at)}</div>
            {o.delivery === "delivery" && o.address && (
              <p className="mt-1 flex items-start gap-1 text-xs text-muted">
                <MapPin className="mt-0.5 size-3.5 shrink-0" /> {o.address}
                {o.lat && o.lng && <a href={webMapLink(o.lat, o.lng)} target="_blank" rel="noreferrer" className="mr-1 text-brand">موقعیت روی نقشه</a>}
              </p>
            )}

            {o.store_note && <p className="mt-2 rounded-xl bg-brand-soft p-2.5 text-xs text-brand">پیام فروشگاه: {o.store_note}</p>}
            {o.courier_name && ["ready", "out_for_delivery"].includes(o.status) && (
              <p className="mt-2 flex flex-wrap items-center gap-2 rounded-xl bg-surface-2 p-2.5 text-xs">
                <Bike className="size-4 text-brand" /> پیک شما: <b>{o.courier_name}</b>
                {o.status === "out_for_delivery" && <Badge tone="brand">در مسیر</Badge>}
                {o.courier_mobile && <a href={telLink(o.courier_mobile)} className="mr-auto text-brand">تماس با پیک</a>}
              </p>
            )}

            <div className="mt-3 flex flex-wrap gap-2">
              {o.status === "awaiting_payment" && (
                <Button size="sm" icon={<CreditCard className="size-4" />} loading={payNow.isPending} onClick={() => payNow.mutate(o.code)}>
                  پرداخت سفارش
                </Button>
              )}
              <Button size="sm" variant="secondary" icon={<Printer className="size-4" />} onClick={async () => { const d = await api.get<InvoiceData>(`/public/orders/${o.code}/invoice/`); printSalesInvoice(d) || toast("اجازه باز شدن پنجره جدید را بدهید", "danger"); }}>
                فاکتور
              </Button>
              <a href={telLink(o.store_phone)} className={`inline-flex h-9 items-center gap-1.5 rounded-xl bg-surface-2 px-3 text-sm ${!o.store_phone && "pointer-events-none opacity-40"}`}>
                <Phone className="size-4" /> تماس با فروشگاه
              </a>
              {(o.status === "awaiting_payment" || o.status === "new" || o.status === "confirmed") && (
                <Button size="sm" variant="secondary" loading={cancel.isPending} onClick={() => confirm("سفارش لغو شود؟" + (o.payment_status === "paid" ? " مبلغ پرداختی به کیف پول شما برمی‌گردد." : "")) && cancel.mutate(o.code)}>
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
