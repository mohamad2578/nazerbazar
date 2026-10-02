const BASE = (import.meta.env.VITE_API_URL as string | undefined) || "/api";
const KEY = "nb.tokens";

type Tokens = { access: string; refresh: string };

export class ApiError extends Error {
  status: number;
  data: any;
  constructor(status: number, data: any) {
    super(firstError(data) || "خطا در ارتباط با سرور");
    this.status = status;
    this.data = data;
  }
}

/** اولین پیام خطای قابل نمایش از پاسخ DRF */
export function firstError(data: any): string {
  if (!data) return "";
  if (typeof data === "string") return data.length > 200 ? "" : data;
  if (Array.isArray(data)) return firstError(data[0]);
  if (data.detail) return firstError(data.detail);
  const k = Object.keys(data)[0];
  return k ? firstError(data[k]) : "";
}

export function fieldErrors(err: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (err instanceof ApiError && err.data && typeof err.data === "object" && !Array.isArray(err.data)) {
    for (const [k, v] of Object.entries(err.data)) out[k] = firstError(v);
  }
  return out;
}

export const tokens = {
  get(): Tokens | null {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },
  set(t: Tokens | null) {
    try {
      if (t) localStorage.setItem(KEY, JSON.stringify(t));
      else localStorage.removeItem(KEY);
    } catch {
      /* حالت خصوصی مرورگر */
    }
  },
};

let refreshing: Promise<boolean> | null = null;

async function refresh(): Promise<boolean> {
  const t = tokens.get();
  if (!t) return false;
  refreshing ??= fetch(`${BASE}/auth/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: t.refresh }),
  })
    .then(async (r) => {
      if (!r.ok) return false;
      const d = await r.json();
      tokens.set({ access: d.access, refresh: d.refresh || t.refresh });
      return true;
    })
    .catch(() => false)
    .finally(() => (refreshing = null));
  return refreshing;
}

export type Query = Record<string, string | number | boolean | undefined | null>;

export function qs(params?: Query) {
  if (!params) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export async function request<T = any>(method: string, path: string, body?: unknown, retry = true): Promise<T> {
  const headers: Record<string, string> = {};
  const t = tokens.get();
  if (t) headers.Authorization = `Bearer ${t.access}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}${path}`, { method, headers, body: payload });
  if (res.status === 401 && retry && t) {
    if (await refresh()) return request<T>(method, path, body, false);
    tokens.set(null);
    window.dispatchEvent(new Event("nb:logout"));
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok && res.status !== 207) throw new ApiError(res.status, data);
  return data as T;
}

export const api = {
  get: <T = any>(path: string, params?: Query) => request<T>("GET", path + qs(params)),
  post: <T = any>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T = any>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  put: <T = any>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: <T = any>(path: string) => request<T>("DELETE", path),
};

/** دانلود فایل (اکسل) با توکن */
export async function download(path: string, filename: string) {
  const t = tokens.get();
  const res = await fetch(`${BASE}${path}`, { headers: t ? { Authorization: `Bearer ${t.access}` } : {} });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] };
