import { dateTime, toEn, webMapLink } from "./format";

export type OrderItemT = {
  name: string; unit_display: string; price: number; list_price: number; bundle_name: string; quantity: number; line_total: number;
};

export type OrderT = {
  id: number; code: string; store: number; store_name: string; store_phone: string; store_address: string;
  customer_name: string; customer_phone: string; delivery: string; delivery_display: string; address: string;
  lat: string | null; lng: string | null; note: string; total: number; discount: number; tax: number; delivery_fee: number; invoice_no: string;
  list_total: number; savings: number;
  payment_method: string; payment_method_display: string; payment_status: string; payment_status_display: string;
  status: string; status_display: string; store_note: string; created_at: string; payment_url?: string;
  courier: number | null; courier_name: string; courier_mobile: string; assigned_at: string | null; delivered_at: string | null;
  items: OrderItemT[];
  events: { status_display: string; note: string; created_at: string }[];
};

export const ORDER_TONE: Record<string, "neutral" | "brand" | "ok" | "warn" | "danger"> = {
  awaiting_payment: "warn", new: "warn", confirmed: "brand", preparing: "brand", ready: "ok", out_for_delivery: "brand", delivered: "neutral", canceled: "danger",
};

export const PAY_TONE: Record<string, "neutral" | "ok" | "warn"> = { paid: "ok", unpaid: "warn", refunded: "neutral" };

const fa = new Intl.NumberFormat("fa-IR");
const t = (rial: number) => `${fa.format(Math.round(rial / 10))} تومان`;
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

/** فاکتور قابل چاپ سفارش (برای کارشناس فروشگاه و مشتری) در پنجره‌ای جدا باز و چاپ می‌شود. */
export function printInvoice(o: OrderT) {
  const rows = o.items
    .map(
      (it, i) => `<tr><td>${fa.format(i + 1)}</td><td>${esc(it.name)}${it.bundle_name ? `<br><small>بسته: ${esc(it.bundle_name)}</small>` : ""}</td>
      <td>${fa.format(it.quantity)} ${esc(it.unit_display)}</td><td>${it.list_price > it.price ? `<s>${t(it.list_price)}</s><br>` : ""}${t(it.price)}</td>
      <td>${t(it.line_total)}</td></tr>`,
    )
    .join("");
  const map = o.lat && o.lng ? webMapLink(o.lat, o.lng) : "";
  const html = `<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>فاکتور ${esc(o.code)}</title>
<style>
 body{font-family:Tahoma,"Vazirmatn",sans-serif;margin:24px;color:#111;font-size:13px}
 h1{font-size:18px;margin:0 0 4px} .muted{color:#666} .box{border:1px solid #bbb;border-radius:8px;padding:10px;margin:10px 0}
 table{width:100%;border-collapse:collapse;margin-top:8px} th,td{border:1px solid #bbb;padding:6px 8px;text-align:right;vertical-align:top}
 th{background:#f1f1f1} .tot td{font-weight:bold} .grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
 small{color:#666} @media print{button{display:none}}
</style></head><body>
<button onclick="window.print()" style="margin-bottom:12px;padding:6px 14px">چاپ</button>
<h1>فاکتور سفارش ${esc(o.code)}</h1>
<div class="muted">${esc(o.store_name)} — ${esc(dateTime(o.created_at))}</div>
<div class="box grid">
 <div><b>مشتری:</b> ${esc(o.customer_name)}</div><div><b>تلفن:</b> <span dir="ltr">${esc(o.customer_phone)}</span></div>
 <div><b>نحوه تحویل:</b> ${esc(o.delivery_display)}</div><div><b>پرداخت:</b> ${esc(o.payment_method_display)} (${esc(o.payment_status_display)})</div>
 ${o.address ? `<div style="grid-column:1/-1"><b>نشانی تحویل:</b> ${esc(o.address)}${map ? ` — <a href="${map}">موقعیت روی نقشه</a><br><small dir="ltr">${esc(toEn(o.lat!))}, ${esc(toEn(o.lng!))}</small>` : ""}</div>` : ""}
 ${o.note ? `<div style="grid-column:1/-1"><b>یادداشت مشتری:</b> ${esc(o.note)}</div>` : ""}
</div>
<table><thead><tr><th>#</th><th>شرح کالا</th><th>تعداد</th><th>قیمت واحد</th><th>مبلغ</th></tr></thead><tbody>${rows}
<tr class="tot"><td colspan="4">جمع قیمت مصرف‌کننده</td><td>${t(o.list_total)}</td></tr>
<tr class="tot"><td colspan="4">مجموع تخفیف</td><td>${t(o.savings)}</td></tr>
<tr class="tot"><td colspan="4">مبلغ قابل پرداخت</td><td>${t(o.total)}</td></tr></tbody></table>
<p class="muted">صادرشده از سامانه ناظر ۷۲۴</p></body></html>`;
  const w = window.open("", "_blank");
  if (!w) return false;
  w.document.write(html);
  w.document.close();
  return true;
}
