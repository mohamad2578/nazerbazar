import { date, dateTime, toEn, webMapLink } from "./format";
import type { OrderT } from "./orders";

const fa = new Intl.NumberFormat("fa-IR");
const ONES = ["", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه", "ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"];
const TENS = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"];
const HUNDREDS = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"];
const SCALES = ["", "هزار", "میلیون", "میلیارد", "تریلیون"];

function triple(n: number): string {
  const parts: string[] = [];
  if (n >= 100) parts.push(HUNDREDS[Math.floor(n / 100)]);
  const r = n % 100;
  if (r >= 20) parts.push(TENS[Math.floor(r / 10)] + (r % 10 ? " و " + ONES[r % 10] : ""));
  else if (r) parts.push(ONES[r]);
  return parts.join(" و ");
}

/** عدد را به حروف فارسی می‌نویسد (۱٬۲۵۰٬۰۰۰ ← «یک میلیون و دویست و پنجاه هزار»). */
export function toWords(n: number): string {
  n = Math.round(Math.abs(n));
  if (n === 0) return "صفر";
  const groups: string[] = [];
  let i = 0;
  while (n > 0 && i < SCALES.length) {
    const t = n % 1000;
    if (t) groups.unshift(triple(t) + (SCALES[i] ? " " + SCALES[i] : ""));
    n = Math.floor(n / 1000);
    i++;
  }
  return groups.join(" و ");
}

/** مبلغ ریالی را به «… تومان» با حروف تبدیل می‌کند. */
export const rialWords = (rial: number) => `${toWords(Math.round(rial / 10))} تومان`;

export const faNum = (n: number) => fa.format(Math.round(n));
const t = (rial: number) => `${fa.format(Math.round(rial / 10))}`;
const esc = (s: string) => (s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

export type InvoiceData = OrderT & {
  seller: { name: string; address: string; phone: string; photo: string | null; economic_code: string; national_id: string; postal_code: string; footer: string; vat_percent: number };
  buyer: { name: string; phone: string; address: string };
};

const BASE_CSS = `
 *{box-sizing:border-box} body{font-family:Vazirmatn,Tahoma,sans-serif;margin:0;padding:24px;color:#111;font-size:12.5px;background:#f3f4f6}
 .sheet{max-width:820px;margin:0 auto;background:#fff;padding:28px;border:1px solid #d1d5db}
 .head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;border-bottom:3px solid #0f766e;padding-bottom:14px}
 .brand{display:flex;gap:12px;align-items:center} .brand img{width:62px;height:62px;object-fit:cover;border-radius:10px}
 h1{margin:0;font-size:20px} h2{margin:0;font-size:15px;color:#0f766e}
 .muted{color:#6b7280} .meta{text-align:left;line-height:1.9}
 .meta b{font-size:15px}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0}
 .box{border:1px solid #d1d5db;border-radius:8px;padding:10px 12px;line-height:1.9}
 .box h3{margin:0 0 4px;font-size:12px;color:#0f766e}
 table{width:100%;border-collapse:collapse;margin-top:6px}
 th{background:#0f766e;color:#fff;font-weight:600} th,td{border:1px solid #cbd5e1;padding:6px 8px;text-align:right;vertical-align:top}
 tbody tr:nth-child(even){background:#f8fafc}
 .num{text-align:left;white-space:nowrap;font-variant-numeric:tabular-nums}
 .tot{margin-right:auto;width:340px;margin-top:10px} .tot div{display:flex;justify-content:space-between;padding:4px 8px;border-bottom:1px dashed #cbd5e1}
 .tot .grand{background:#0f766e;color:#fff;font-weight:700;font-size:14px;border:0;border-radius:6px;margin-top:4px;padding:8px}
 .words{margin-top:10px;padding:8px 12px;border:1px dashed #0f766e;border-radius:6px}
 .sign{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:26px} .sign div{border:1px solid #cbd5e1;border-radius:8px;height:86px;padding:8px;color:#6b7280}
 .foot{margin-top:16px;text-align:center;color:#6b7280;font-size:11px}
 .stamp{display:inline-block;border:2px solid #16a34a;color:#16a34a;border-radius:6px;padding:2px 10px;font-weight:700;transform:rotate(-4deg)}
 .stamp.un{border-color:#d97706;color:#d97706}
 button{margin:0 auto 14px;display:block;padding:8px 22px;font-family:inherit;cursor:pointer}
 @media print{body{background:#fff;padding:0}.sheet{border:0;padding:0;max-width:none}button{display:none}}
`;

function open(title: string, body: string): boolean {
  const w = window.open("", "_blank");
  if (!w) return false;
  w.document.write(`<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>${esc(title)}</title><style>${BASE_CSS}</style></head><body>
<button onclick="window.print()">چاپ فاکتور</button><div class="sheet">${body}</div></body></html>`);
  w.document.close();
  return true;
}

/** فاکتور رسمی فروش (شماره ترتیبی، مشخصات فروشنده و خریدار، مالیات، ارسال، مبلغ به حروف). */
export function printSalesInvoice(o: InvoiceData): boolean {
  const s = o.seller;
  const rows = o.items.map((it, i) => `<tr><td>${faNum(i + 1)}</td>
    <td>${esc(it.name)}${it.bundle_name ? `<br><small class="muted">از بسته «${esc(it.bundle_name)}»</small>` : ""}</td>
    <td class="num">${faNum(it.quantity)} ${esc(it.unit_display)}</td>
    <td class="num">${it.list_price > it.price ? `<s class="muted">${t(it.list_price)}</s><br>` : ""}${t(it.price)}</td>
    <td class="num">${it.list_price > it.price ? t((it.list_price - it.price) * it.quantity) : "—"}</td>
    <td class="num">${t(it.line_total)}</td></tr>`).join("");
  const goods = o.total - o.tax - o.delivery_fee;
  const paid = o.payment_status === "paid";
  const mapLink = o.lat && o.lng ? webMapLink(o.lat, o.lng) : "";
  return open(`فاکتور ${o.invoice_no || o.code}`, `
  <div class="head">
    <div class="brand">${s.photo ? `<img src="${s.photo}" alt="">` : ""}<div><h1>${esc(s.name)}</h1>
      <div class="muted">${esc(s.address)}${s.phone ? ` — تلفن: ${esc(s.phone)}` : ""}</div>
      <div class="muted">${[s.economic_code && `کد اقتصادی: ${esc(s.economic_code)}`, s.national_id && `شناسه ملی: ${esc(s.national_id)}`, s.postal_code && `کد پستی: ${esc(s.postal_code)}`].filter(Boolean).join(" · ")}</div></div></div>
    <div class="meta"><h2>صورت‌حساب فروش</h2><div>شماره فاکتور: <b dir="ltr">${esc(o.invoice_no || o.code)}</b></div>
      <div>تاریخ: ${esc(date(o.created_at))}</div><div>کد سفارش: <span dir="ltr">${esc(o.code)}</span></div>
      <div><span class="stamp ${paid ? "" : "un"}">${paid ? "پرداخت‌شده" : "پرداخت‌نشده"}</span></div></div>
  </div>
  <div class="grid">
    <div class="box"><h3>مشخصات خریدار</h3><div>${esc(o.buyer.name)}</div><div class="muted" dir="ltr" style="text-align:right">${esc(o.buyer.phone)}</div>
      ${o.buyer.address ? `<div>${esc(o.buyer.address)}${mapLink ? ` — <a href="${mapLink}">موقعیت روی نقشه</a>` : ""}</div>` : ""}</div>
    <div class="box"><h3>شرایط</h3><div>نحوه تحویل: ${esc(o.delivery_display)}</div><div>روش پرداخت: ${esc(o.payment_method_display)}</div>
      ${o.courier_name ? `<div>پیک: ${esc(o.courier_name)}</div>` : ""}${o.note ? `<div>توضیح مشتری: ${esc(o.note)}</div>` : ""}</div>
  </div>
  <table><thead><tr><th>ردیف</th><th>شرح کالا</th><th>تعداد</th><th>قیمت واحد (تومان)</th><th>تخفیف (تومان)</th><th>مبلغ (تومان)</th></tr></thead><tbody>${rows}</tbody></table>
  <div class="tot">
    <div><span>جمع قیمت کالاها</span><span class="num">${t(o.list_total)}</span></div>
    <div><span>جمع تخفیف‌ها</span><span class="num">${t(o.savings)}</span></div>
    <div><span>مبلغ کالاهای خریداری‌شده</span><span class="num">${t(goods)}</span></div>
    ${o.tax ? `<div><span>مالیات بر ارزش افزوده (${faNum(s.vat_percent)}٪)</span><span class="num">${t(o.tax)}</span></div>` : ""}
    ${o.delivery_fee ? `<div><span>هزینه ارسال</span><span class="num">${t(o.delivery_fee)}</span></div>` : ""}
    <div class="grand"><span>مبلغ قابل پرداخت (تومان)</span><span class="num">${t(o.total)}</span></div>
  </div>
  <div class="words">مبلغ به حروف: <b>${esc(rialWords(o.total))}</b></div>
  <div class="sign"><div>مهر و امضای فروشنده</div><div>امضای خریدار</div></div>
  <div class="foot">${esc(s.footer || "از خرید شما سپاسگزاریم")} — صادرشده از سامانه ناظر ۷۲۴ در ${esc(dateTime(o.created_at))}</div>`);
}

export type PurchaseData = {
  id: number; supplier_name: string; number: string; date: string; note: string; discount: number; tax: number; shipping: number; total: number; paid: number;
  items: { product_name: string; qty: number; unit_cost: number; line_total: number }[];
};

/** فاکتور خرید از تامین‌کننده (برای بایگانی). */
export function printPurchaseInvoice(p: PurchaseData, storeName: string): boolean {
  const rows = p.items.map((it, i) => `<tr><td>${faNum(i + 1)}</td><td>${esc(it.product_name)}</td><td class="num">${faNum(it.qty)}</td>
    <td class="num">${t(it.unit_cost)}</td><td class="num">${t(it.line_total)}</td></tr>`).join("");
  const goods = p.items.reduce((s, i) => s + i.line_total, 0);
  return open(`فاکتور خرید ${p.number || p.id}`, `
  <div class="head"><div class="brand"><div><h1>${esc(storeName)}</h1><div class="muted">خریدار</div></div></div>
    <div class="meta"><h2>فاکتور خرید</h2><div>شماره: <b dir="ltr">${esc(p.number || String(p.id))}</b></div><div>تاریخ: ${esc(date(p.date))}</div></div></div>
  <div class="grid"><div class="box"><h3>تامین‌کننده</h3><div>${esc(p.supplier_name)}</div></div>
    <div class="box"><h3>وضعیت پرداخت</h3><div>پرداخت‌شده: ${t(p.paid)} تومان</div><div>مانده: <b>${t(p.total - p.paid)}</b> تومان</div></div></div>
  <table><thead><tr><th>ردیف</th><th>شرح کالا</th><th>تعداد</th><th>قیمت واحد (تومان)</th><th>مبلغ (تومان)</th></tr></thead><tbody>${rows}</tbody></table>
  <div class="tot"><div><span>جمع کالاها</span><span class="num">${t(goods)}</span></div>
    ${p.discount ? `<div><span>تخفیف</span><span class="num">−${t(p.discount)}</span></div>` : ""}
    ${p.tax ? `<div><span>مالیات</span><span class="num">${t(p.tax)}</span></div>` : ""}
    ${p.shipping ? `<div><span>هزینه حمل</span><span class="num">${t(p.shipping)}</span></div>` : ""}
    <div class="grand"><span>جمع کل (تومان)</span><span class="num">${t(p.total)}</span></div></div>
  <div class="words">مبلغ به حروف: <b>${esc(rialWords(p.total))}</b></div>
  ${p.note ? `<div class="words">توضیح: ${esc(p.note)}</div>` : ""}
  <div class="sign"><div>مهر و امضای تامین‌کننده</div><div>تحویل‌گیرنده انبار</div></div>`);
}

/** تاریخ شمسی امروز به‌صورت ISO میلادی برای فیلدهای تاریخ فرم‌ها (YYYY-MM-DD). */
export const todayIso = () => new Date().toLocaleDateString("en-CA");
export const isoDaysAgo = (d: number) => new Date(Date.now() - d * 86400000).toLocaleDateString("en-CA");
export const toIntRial = (tomanStr: string) => Math.round(Number(toEn(tomanStr).replace(/[,،٬\s]/g, "") || 0) * 10);

/** مبلغ ریالی را برای کارت‌های آماری کوتاه می‌کند: ۵۸۵٬۵۰۰٬۰۰۰ تومان ← «۵۸۵٫۵ میلیون تومان». */
export function moneyCompact(rial: number): string {
  const tm = Math.round(rial / 10);
  const a = Math.abs(tm);
  const f = (x: number) => new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 }).format(x);
  const sign = tm < 0 ? "−" : "";
  if (a >= 1e9) return `${sign}${f(a / 1e9)} میلیارد تومان`;
  if (a >= 1e6) return `${sign}${f(a / 1e6)} میلیون تومان`;
  return `${sign}${fa.format(a)} تومان`;
}
