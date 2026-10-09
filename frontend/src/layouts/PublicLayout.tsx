import { Home, LayoutDashboard, Map, Search, ShieldAlert, User } from "lucide-react";
import { NavLink, Link, Outlet } from "react-router-dom";
import CountyPicker from "../components/CountyPicker";
import InstallPrompt from "../components/InstallPrompt";
import { cx } from "../components/ui";
import { isPanelUser, useAuth } from "../lib/auth";

export function Logo({ small }: { small?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2">
      <img src="/icon.svg" alt="" className={small ? "size-8" : "size-9"} />
      <div className="leading-tight">
        <div className="font-bold">ناظر ۷۲۴</div>
        {!small && <div className="text-[11px] text-muted">شفافیت قیمت کالاهای اساسی</div>}
      </div>
    </Link>
  );
}

// ترتیب نوار پایین: نقشه، خانه (وسط)، پیگیری، حساب
const NAV = [
  { to: "/map", label: "نقشه", icon: Map },
  { to: "/", label: "خانه", icon: Home, end: true },
  { to: "/track", label: "پیگیری", icon: Search },
];

export default function PublicLayout() {
  const { user } = useAuth();
  const panel = isPanelUser(user);
  return (
    <div className="min-h-dvh pb-20 lg:pb-0">
      <header className="sticky top-0 z-[500] border-b border-line bg-bg/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4">
          <Logo />
          <nav className="mr-6 hidden items-center gap-1 lg:flex">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) => cx("rounded-lg px-3 py-2 text-sm", isActive ? "bg-brand-soft text-brand" : "text-muted hover:text-ink")}
              >
                {n.label}
              </NavLink>
            ))}
            <NavLink to="/subsidized" className={({ isActive }) => cx("rounded-lg px-3 py-2 text-sm", isActive ? "bg-brand-soft text-brand" : "text-muted hover:text-ink")}>
              کالای تنظیم بازار
            </NavLink>
            <NavLink to="/register-store" className={({ isActive }) => cx("rounded-lg px-3 py-2 text-sm", isActive ? "bg-brand-soft text-brand" : "text-muted hover:text-ink")}>
              ثبت‌نام فروشگاه
            </NavLink>
            <NavLink to="/news" className={({ isActive }) => cx("rounded-lg px-3 py-2 text-sm", isActive ? "bg-brand-soft text-brand" : "text-muted hover:text-ink")}>
              اخبار
            </NavLink>
          </nav>
          <div className="mr-auto flex items-center gap-2">
            <CountyPicker compact />
            <Link
              to={panel ? "/panel" : user ? "/account" : "/login"}
              className="hidden h-9 items-center gap-1.5 rounded-full bg-brand px-4 text-sm font-medium text-brand-ink lg:inline-flex"
            >
              {panel ? <LayoutDashboard className="size-4" /> : <User className="size-4" />}
              {panel ? "پنل من" : user ? "حساب من" : "ورود / ثبت‌نام"}
            </Link>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-5">
        <Outlet />
      </main>
      <footer className="mx-auto hidden max-w-6xl px-4 py-10 text-sm text-muted lg:block">
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6">
          <span>سامانه ناظر ۷۲۴</span>
          <div className="flex gap-4">
            <Link to="/register-store" className="hover:text-ink">ثبت‌نام فروشگاه</Link>
            <Link to="/report" className="hover:text-ink">گزارش تخلف</Link>
          </div>
        </div>
      </footer>
      <InstallPrompt />
      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-[600] border-t border-line bg-surface/95 backdrop-blur lg:hidden">
        <div className="mx-auto grid max-w-md grid-cols-4 pt-1.5">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cx("flex flex-col items-center gap-0.5 py-1 text-[11px]", isActive ? "text-brand" : "text-muted")}>
              <n.icon className="size-5" />
              {n.label}
            </NavLink>
          ))}
          <NavLink
            to={panel ? "/panel" : user ? "/account" : "/login"}
            className={({ isActive }) => cx("flex flex-col items-center gap-0.5 py-1 text-[11px]", isActive ? "text-brand" : "text-muted")}
          >
            {panel ? <LayoutDashboard className="size-5" /> : <User className="size-5" />}
            {panel ? "پنل" : "حساب"}
          </NavLink>
        </div>
      </nav>
    </div>
  );
}

export function ReportFab() {
  return (
    <Link
      to="/report"
      className="fixed bottom-24 left-4 z-[550] inline-flex h-12 items-center gap-2 rounded-full bg-danger px-5 text-sm font-medium text-white shadow-lg lg:bottom-8"
    >
      <ShieldAlert className="size-5" /> گزارش تخلف
    </Link>
  );
}
