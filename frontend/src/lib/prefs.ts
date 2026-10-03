import { useEffect, useState } from "react";

/** تنظیمات محلی کاربر (شهرستان انتخابی و ...) — در حالت خصوصی مرورگر بدون خطا کار می‌کند */
function read<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function usePref<T>(key: string, fallback: T) {
  const [value, setValue] = useState<T>(() => read(key, fallback));
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* ignore */
    }
    window.dispatchEvent(new CustomEvent("nb:pref", { detail: key }));
  }, [key, value]);
  useEffect(() => {
    const on = (e: Event) => {
      if ((e as CustomEvent).detail === key) setValue(read(key, fallback));
    };
    window.addEventListener("nb:pref", on);
    return () => window.removeEventListener("nb:pref", on);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return [value, setValue] as const;
}

export type County = { id: number; name: string; lat?: string; lng?: string };

/** شهرستان پیش‌فرض سایت تا زمانی که کاربر خودش انتخاب کند. */
export const DEFAULT_COUNTY: County = { id: 1, name: "همدان" };

// کاربرانی که پیش از تعیین پیش‌فرض، مقدار «همه شهرستان‌ها» (null) ذخیره کرده بودند
// یک‌بار به شهرستان پیش‌فرض منتقل می‌شوند؛ پس از آن انتخاب خودشان محترم است.
try {
  if (!localStorage.getItem("nb.county.init")) {
    localStorage.setItem("nb.county.init", "1");
    if (!localStorage.getItem("nb.county") || localStorage.getItem("nb.county") === "null")
      localStorage.setItem("nb.county", JSON.stringify(DEFAULT_COUNTY));
  }
} catch {
  /* حالت خصوصی مرورگر */
}

export const useCounty = () => usePref<County | null>("nb.county", DEFAULT_COUNTY);

/** موقعیت فعلی کاربر برای محاسبه فاصله فروشگاه‌ها */
export function useGeo() {
  const [pos, setPos] = useState<{ lat: number; lng: number } | null>(() => read("nb.geo", null));
  const [asking, setAsking] = useState(false);
  const ask = () => {
    if (!navigator.geolocation) return;
    setAsking(true);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        const v = { lat: +p.coords.latitude.toFixed(5), lng: +p.coords.longitude.toFixed(5) };
        setPos(v);
        try {
          localStorage.setItem("nb.geo", JSON.stringify(v));
        } catch {
          /* ignore */
        }
        setAsking(false);
      },
      () => setAsking(false),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
    );
  };
  return { pos, ask, asking };
}
