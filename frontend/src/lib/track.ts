/** ثبت بازدید برای گزارش آمار مدیریت.
 *  فقط یک شناسه تصادفی در مرورگر نگه داشته می‌شود تا بازدیدکننده یکتا شمرده شود؛
 *  هیچ اطلاعات شخصی ارسال نمی‌شود. خطاها عمدا نادیده گرفته می‌شوند تا مرور سایت مختل نشود. */
const KEY = "nb.visitor";
const BASE = (import.meta.env.VITE_API_URL as string | undefined) || "/api";

function visitorId(): string {
  try {
    let id = localStorage.getItem(KEY);
    if (!id) {
      id = crypto.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
      localStorage.setItem(KEY, id);
    }
    return id;
  } catch {
    return "anon";
  }
}

// یک رویداد تکراری در کمتر از یک ثانیه (مثلا رندر دوباره صفحه) دو بار شمرده نمی‌شود
let last = { key: "", at: 0 };

function send(body: Record<string, unknown>) {
  const key = JSON.stringify(body);
  const now = Date.now();
  if (key === last.key && now - last.at < 1000) return;
  last = { key, at: now };
  try {
    const token = JSON.parse(localStorage.getItem("nb.tokens") || "null")?.access;
    fetch(`${BASE}/public/track/`, {
      method: "POST",
      keepalive: true,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ visitor: visitorId(), ...body }),
    }).catch(() => undefined);
  } catch {
    /* آمار نباید هیچ‌وقت سایت را خراب کند */
  }
}

export const trackPage = (path: string) => send({ kind: "page", path });
export const trackProduct = (productId: number, path: string) => send({ kind: "product", product: productId, path });
