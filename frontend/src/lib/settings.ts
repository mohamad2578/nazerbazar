import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { useAuth } from "./auth";

export type SystemSettings = {
  union_can_set_prices: boolean;
  snap_store_prices: boolean;
  union_sections: string[];
  sections: { key: string; label: string }[];
  samt_reports: string[];
  reports: { key: string; label: string }[];
  updated_at: string;
  updated_by: string;
};

/** تنظیمات سامانه (مدیر کل تعیین می‌کند)؛ برای نمایش منو و بخش‌های مجاز هر نقش. */
export function useSystemSettings() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["system-settings"],
    queryFn: () => api.get<SystemSettings>("/settings/"),
    enabled: !!user,
    staleTime: 60_000,
  });
}

/** آیا کاربر فعلی به این بخش دسترسی دارد؟ (فقط برای اتحادیه و اداره صمت محدودیت اعمال می‌شود) */
export function useAccess() {
  const { user } = useAuth();
  const s = useSystemSettings().data;
  return {
    settings: s,
    unionSection: (key: string) => user?.role !== "union" || !s || s.union_sections.includes(key),
    samtReport: (key: string) => user?.role !== "samt" || !s || s.samt_reports.includes(key),
    canSetPrices: user?.role !== "union" || !s || s.union_can_set_prices,
  };
}
