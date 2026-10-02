const nf = new Intl.NumberFormat("fa-IR");
const dateFmt = new Intl.DateTimeFormat("fa-IR", { year: "numeric", month: "long", day: "numeric" });
const shortDate = new Intl.DateTimeFormat("fa-IR", { month: "short", day: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("fa-IR", {
  year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
});

/** قیمت‌ها در سرور به ریال ذخیره می‌شوند و به کاربر به تومان نمایش داده می‌شوند */
export const toToman = (rial?: number | null) => (rial == null ? null : Math.round(rial / 10));
export const toRial = (toman: number | string) => Math.round(Number(toEn(String(toman)).replace(/[,،٬\s]/g, "")) * 10);

export function toman(rial?: number | null, withUnit = true) {
  if (rial == null) return "—";
  return nf.format(Math.round(rial / 10)) + (withUnit ? " تومان" : "");
}

export const num = (n?: number | string | null, digits = 0) =>
  n == null || n === "" ? "—" : new Intl.NumberFormat("fa-IR", { maximumFractionDigits: digits }).format(Number(n));

export const pct = (n?: number | null) => (n == null ? "—" : `${num(n, 1)}٪`);

export function toEn(s: string) {
  return s.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))).replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)));
}

/** نمایش عدد در حال تایپ با جداکننده هزارگان */
export function groupDigits(v: string) {
  const clean = toEn(v).replace(/[^\d]/g, "");
  return clean ? nf.format(Number(clean)) : "";
}

export const date = (v?: string | Date | null) => (v ? dateFmt.format(new Date(v)) : "—");
export const dateShort = (v?: string | Date | null) => (v ? shortDate.format(new Date(v)) : "");
export const dateTime = (v?: string | Date | null) => (v ? dateTimeFmt.format(new Date(v)) : "—");

export function ago(v?: string | null) {
  if (!v) return "";
  const s = (Date.now() - new Date(v).getTime()) / 1000;
  if (s < 60) return "لحظاتی پیش";
  if (s < 3600) return `${num(Math.floor(s / 60))} دقیقه پیش`;
  if (s < 86400) return `${num(Math.floor(s / 3600))} ساعت پیش`;
  if (s < 86400 * 30) return `${num(Math.floor(s / 86400))} روز پیش`;
  return date(v);
}

export function hoursLeft(deadline?: string | null) {
  if (!deadline) return null;
  return (new Date(deadline).getTime() - Date.now()) / 3600000;
}

export const telLink = (phone?: string) => (phone ? `tel:${toEn(phone).replace(/[^\d+]/g, "")}` : undefined);

/** مسیریابی با اپ نقشه پیش‌فرض گوشی (نشان/بلد/گوگل) */
export const directionsLink = (lat?: number | string | null, lng?: number | string | null) =>
  lat && lng ? `geo:${lat},${lng}?q=${lat},${lng}` : undefined;
export const webMapLink = (lat?: number | string | null, lng?: number | string | null) =>
  lat && lng ? `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=17/${lat}/${lng}` : undefined;

export const km = (d?: number | null) => (d == null ? "" : d < 1 ? `${num(Math.round(d * 1000))} متر` : `${num(d, 1)} کیلومتر`);
