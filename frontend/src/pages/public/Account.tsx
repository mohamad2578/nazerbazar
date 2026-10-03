import { LayoutDashboard, LogOut, Search, ShieldAlert, ShoppingCart, Store } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Badge, Button, Card } from "../../components/ui";
import { isPanelUser, useAuth } from "../../lib/auth";

export default function Account() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  if (!user) return null;
  return (
    <div className="mx-auto max-w-md space-y-4">
      <Card className="p-5">
        <div className="text-lg font-bold">{user.first_name || user.last_name ? `${user.first_name} ${user.last_name}` : "کاربر ناظر ۷۲۴"}</div>
        <div className="mt-1 text-sm text-muted" dir="ltr">{user.mobile}</div>
        <Badge tone="brand" className="mt-2">{user.role_display}</Badge>
      </Card>
      <Card className="divide-y divide-line">
        {isPanelUser(user) && <Row to="/panel" icon={<LayoutDashboard className="size-5" />} label="ورود به پنل" />}
        <Row to="/orders" icon={<ShoppingCart className="size-5" />} label="سفارش‌های من" />
        <Row to="/track" icon={<Search className="size-5" />} label="گزارش‌های من و پیگیری" />
        <Row to="/report" icon={<ShieldAlert className="size-5" />} label="ثبت گزارش تخلف" />
        {user.role === "citizen" && !user.store && <Row to="/register-store" icon={<Store className="size-5" />} label="ثبت‌نام فروشگاه (صاحبان صنف)" />}
      </Card>
      {user.store && user.store.status !== "active" && (
        <Card className="p-4 text-sm">
          وضعیت فروشگاه «{user.store.name}»: <Badge tone="warn">{user.store.status_display}</Badge>
          {user.store.status_reason && <p className="mt-2 text-danger">دلیل: {user.store.status_reason}</p>}
        </Card>
      )}
      <Button variant="secondary" className="w-full" icon={<LogOut className="size-4" />} onClick={() => { logout(); nav("/"); }}>
        خروج از حساب
      </Button>
    </div>
  );
}

function Row({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <Link to={to} className="flex items-center gap-3 px-4 py-4 hover:bg-surface-2">
      <span className="text-brand">{icon}</span>
      {label}
    </Link>
  );
}
