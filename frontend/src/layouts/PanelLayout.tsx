import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, BarChart3, Bell, Boxes, Building2, ClipboardCheck, ClipboardList, DatabaseBackup, FileSpreadsheet, GalleryHorizontal, Globe2, Home, Landmark, LogOut, Map, Menu, MessageSquareWarning,
  Package, Settings2, ShoppingBag, ShoppingCart, Store, Tags, Truck, Users, X,
} from "lucide-react";
import { useState, type ComponentType } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { cx } from "../components/ui";
import { api } from "../lib/api";
import { useAuth, type Role } from "../lib/auth";
import { num } from "../lib/format";
import { Logo } from "./PublicLayout";

type Item = { to: string; label: string; icon: ComponentType<{ className?: string }>; roles: Role[]; end?: boolean; mobile?: boolean };

const G: Role[] = ["governorate", "samt"];
const GC: Role[] = ["governorate", "samt", "chamber"];
const M: Role[] = ["governorate", "samt", "chamber", "union"];
// بررسی و بارگذاری نرخ مصوب
const REVIEW: Role[] = ["chamber", "samt", "governorate"];
const LOAD: Role[] = ["samt", "governorate"];

export const NAV: Item[] = [
  { to: "/panel", label: "داشبورد", icon: Home, roles: [...M, "store"], end: true, mobile: true },
  { to: "/panel/prices", label: "قیمت‌های من", icon: Tags, roles: ["store"], mobile: true },
  { to: "/panel/stores", label: "فروشگاه‌ها", icon: Store, roles: M, mobile: true },
  { to: "/panel/products", label: "کالاها و نرخ مصوب", icon: Package, roles: M, mobile: true },
  { to: "/panel/price-approvals", label: "تایید نرخ‌ها", icon: ClipboardCheck, roles: REVIEW, mobile: true },
  { to: "/panel/price-upload", label: "بارگذاری نرخ‌ها", icon: FileSpreadsheet, roles: LOAD },
  { to: "/panel/orders", label: "سفارش‌ها", icon: ShoppingCart, roles: [...M, "store"], mobile: true },
  { to: "/panel/my-shop", label: "فروشگاه اینترنتی من", icon: ShoppingBag, roles: ["store"], mobile: true },
  { to: "/panel/complaints", label: "شکایات", icon: MessageSquareWarning, roles: [...M, "store"], mobile: true },
  { to: "/panel/quotas", label: "سهمیه‌ها", icon: Truck, roles: ["union", "store"] },
  { to: "/panel/allocations", label: "تخصیص و توزیع", icon: Boxes, roles: M },
  { to: "/panel/alerts", label: "هشدارها", icon: AlertTriangle, roles: M },
  { to: "/panel/reports", label: "گزارش‌های تحلیلی", icon: BarChart3, roles: M },
  { to: "/panel/observatory", label: "رصدخانه کالای اساسی", icon: Globe2, roles: M },
  { to: "/panel/org/provinces", label: "استان‌ها", icon: Map, roles: [] },
  { to: "/panel/org/counties", label: "شهرستان‌ها", icon: Map, roles: G },
  { to: "/panel/org/chambers", label: "اتاق‌های اصناف", icon: Landmark, roles: G },
  { to: "/panel/org/unions", label: "اتحادیه‌ها", icon: Building2, roles: GC },
  { to: "/panel/org/users", label: "کاربران سازمانی", icon: Users, roles: GC },
  { to: "/panel/org/commodities", label: "کالاهای اساسی و سبد", icon: ClipboardList, roles: [] },
  { to: "/panel/org/categories", label: "دسته‌بندی‌ها", icon: Settings2, roles: [] },
  { to: "/panel/slides", label: "اسلایدهای صفحه اصلی", icon: GalleryHorizontal, roles: [] },
  { to: "/panel/backup", label: "پشتیبان‌گیری و بازیابی", icon: DatabaseBackup, roles: [] },
  { to: "/panel/profile", label: "مشخصات فروشگاه", icon: Settings2, roles: ["store"] },
];

export default function PanelLayout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const nav = useNavigate();
  const role = user!.role;
  const items = NAV.filter((i) => role === "admin" || i.roles.includes(role));
  const notif = useQuery({ queryKey: ["notifications-count"], queryFn: () => api.get<{ unread: number }>("/notifications/", { is_read: false, page_size: 1 }), refetchInterval: 60_000 });
  const pendingStores = useQuery({
    queryKey: ["pending-stores"],
    queryFn: () => api.get<{ count: number }>("/stores/", { status: "pending", page_size: 1 }),
    enabled: role === "union" || role === "admin",
    refetchInterval: 120_000,
  });
  const badges: Record<string, number | undefined> = { "/panel/stores": pendingStores.data?.count };

  const Sidebar = (
    <nav className="flex h-full flex-col">
      <div className="flex h-16 items-center justify-between px-4">
        <Logo small />
        <button className="lg:hidden" onClick={() => setOpen(false)} aria-label="بستن منو"><X className="size-6" /></button>
      </div>
      <div className="mx-3 mb-3 rounded-xl bg-surface-2 px-3 py-2.5 text-sm">
        <div className="font-medium">{user!.first_name ? `${user!.first_name} ${user!.last_name}` : user!.mobile}</div>
        <div className="text-xs text-muted">{user!.role_display}{user!.scope_name && ` · ${user!.scope_name}`}{user!.store && ` · ${user!.store.name}`}</div>
      </div>
      <div className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
        {items.map((i) => (
          <NavLink
            key={i.to}
            to={i.to}
            end={i.end}
            onClick={() => setOpen(false)}
            className={({ isActive }) => cx("flex h-10 items-center gap-3 rounded-xl px-3 text-sm", isActive ? "bg-brand text-brand-ink" : "text-ink hover:bg-surface-2")}
          >
            <i.icon className="size-[18px] shrink-0" />
            <span className="flex-1">{i.label}</span>
            {!!badges[i.to] && <span className="rounded-full bg-accent px-1.5 text-[11px] font-bold text-white">{num(badges[i.to])}</span>}
          </NavLink>
        ))}
        {role === "admin" && (
          <a href="/django-admin/" className="flex h-10 items-center gap-3 rounded-xl px-3 text-sm text-muted hover:bg-surface-2">
            <Settings2 className="size-[18px]" /> پنل فنی (Django)
          </a>
        )}
      </div>
      <div className="border-t border-line p-3">
        <Link to="/" className="flex h-10 items-center gap-3 rounded-xl px-3 text-sm text-muted hover:bg-surface-2"><Globe2 className="size-[18px]" /> سایت عمومی</Link>
        <button onClick={() => { logout(); nav("/"); }} className="flex h-10 w-full items-center gap-3 rounded-xl px-3 text-sm text-danger hover:bg-danger-soft">
          <LogOut className="size-[18px]" /> خروج
        </button>
      </div>
    </nav>
  );

  const mobileItems = items.filter((i) => i.mobile).slice(0, 4);
  return (
    <div className="min-h-dvh lg:pr-64">
      <aside className="fixed inset-y-0 right-0 z-[800] hidden w-64 border-l border-line bg-surface lg:block">{Sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-[900] lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 right-0 w-72 bg-surface shadow-xl">{Sidebar}</aside>
        </div>
      )}
      <header className="sticky top-0 z-[700] flex h-14 items-center gap-2 border-b border-line bg-bg/90 px-4 backdrop-blur">
        <button className="lg:hidden" onClick={() => setOpen(true)} aria-label="منو"><Menu className="size-6" /></button>
        <div className="font-semibold lg:hidden">پنل {user!.role_display}</div>
        <Link to="/panel/notifications" className="relative mr-auto grid size-10 place-items-center rounded-full hover:bg-surface-2" aria-label="اعلان‌ها">
          <Bell className="size-5" />
          {!!notif.data?.unread && <span className="absolute right-1.5 top-1.5 grid min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">{num(notif.data.unread)}</span>}
        </Link>
      </header>
      <main key={loc.pathname} className="mx-auto max-w-6xl px-4 py-5 pb-24 lg:pb-8">
        <Outlet />
      </main>
      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-[600] border-t border-line bg-surface/95 backdrop-blur lg:hidden">
        <div className="grid pt-1.5" style={{ gridTemplateColumns: `repeat(${mobileItems.length + 1}, 1fr)` }}>
          {mobileItems.map((i) => (
            <NavLink key={i.to} to={i.to} end={i.end} className={({ isActive }) => cx("relative flex flex-col items-center gap-0.5 py-1 text-[11px]", isActive ? "text-brand" : "text-muted")}>
              <i.icon className="size-5" />
              <span className="max-w-full truncate px-1">{i.label.split(" ")[0]}</span>
              {!!badges[i.to] && <span className="absolute right-1/4 top-0 size-2 rounded-full bg-accent" />}
            </NavLink>
          ))}
          <button onClick={() => setOpen(true)} className="flex flex-col items-center gap-0.5 py-1 text-[11px] text-muted">
            <Menu className="size-5" /> بیشتر
          </button>
        </div>
      </nav>
    </div>
  );
}
