import { useMutation, useQuery } from "@tanstack/react-query";
import { Bike, CheckCircle2, LayoutDashboard, LogOut, MapPin, Search, ShieldAlert, ShoppingCart, Store, Wallet, XCircle } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import AddressBook from "../../components/AddressBook";
import { Badge, Button, Card, Field, Input, PriceInput, useToast } from "../../components/ui";
import { api, fieldErrors } from "../../lib/api";
import { isPanelUser, useAuth } from "../../lib/auth";
import { dateTime, toman } from "../../lib/format";

type WalletT = { balance: number; txs: { id: number; amount: number; kind_display: string; note: string; created_at: string }[] };

export default function Account() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const walletResult = params.get("wallet");
  if (!user) return null;
  return (
    <div className="mx-auto max-w-md space-y-4">
      <Card className="p-5">
        <div className="text-lg font-bold">{user.first_name || user.last_name ? `${user.first_name} ${user.last_name}` : "کاربر ناظر ۷۲۴"}</div>
        <div className="mt-1 text-sm text-muted" dir="ltr">{user.mobile}</div>
        <Badge tone="brand" className="mt-2">{user.role_display}</Badge>
      </Card>
      {walletResult && (
        <Card className={`flex items-center gap-2 p-3 text-sm ${walletResult === "ok" ? "border-ok/40 bg-ok-soft text-ok" : "border-danger/40 bg-danger-soft text-danger"}`}>
          {walletResult === "ok" ? <CheckCircle2 className="size-5" /> : <XCircle className="size-5" />}
          {walletResult === "ok" ? "کیف پول شما شارژ شد." : "شارژ کیف پول انجام نشد؛ مبلغی از حساب شما کسر نشده است."}
        </Card>
      )}
      <WalletCard />
      <Card className="p-4">
        <h2 className="mb-3 flex items-center gap-2 font-semibold"><MapPin className="size-5 text-brand" /> نشانی‌های من</h2>
        <p className="mb-3 text-xs text-muted">نشانی‌ها و موقعیت روی نقشه، هنگام سفارش با پیک برای تحویل کالا استفاده می‌شود.</p>
        <AddressBook />
      </Card>
      <Card className="divide-y divide-line">
        {user.is_courier && <Row to="/courier" icon={<Bike className="size-5" />} label="اپلیکیشن پیک (سفارش‌های تحویلی من)" />}
        {isPanelUser(user) && <Row to="/panel" icon={<LayoutDashboard className="size-5" />} label="ورود به پنل" />}
        <Row to="/orders" icon={<ShoppingCart className="size-5" />} label="سفارش‌های من و فاکتورها" />
        <Row to="/track" icon={<Search className="size-5" />} label="گزارش‌های من و پیگیری" />
        <Row to="/report" icon={<ShieldAlert className="size-5" />} label="ثبت گزارش تخلف" />
        {user.role === "citizen" && !user.store && <Row to="/register-store" icon={<Store className="size-5" />} label="ثبت‌نام فروشگاه (صاحبان صنف)" />}
      </Card>
      {user.role === "admin" && <WalletAdmin />}
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

/** موجودی کیف پول، شارژ اینترنتی و آخرین تراکنش‌ها. */
function WalletCard() {
  const toast = useToast();
  const [amount, setAmount] = useState("");
  const q = useQuery({ queryKey: ["wallet"], queryFn: () => api.get<WalletT>("/wallet/") });
  const topup = useMutation({
    mutationFn: () => api.post<{ payment_url: string }>("/wallet/topup/", { amount: Number(amount) }),
    onSuccess: (r) => { window.location.href = r.payment_url; },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const txs = q.data?.txs ?? [];
  return (
    <Card className="p-4">
      <h2 className="mb-3 flex items-center gap-2 font-semibold"><Wallet className="size-5 text-brand" /> کیف پول</h2>
      <div className="rounded-xl bg-brand-soft p-4 text-center">
        <div className="text-xs text-brand">موجودی شما</div>
        <div className="mt-1 text-2xl font-bold tabular text-brand">{toman(q.data?.balance ?? 0)}</div>
      </div>
      <div className="mt-3 flex gap-2">
        <div className="flex-1"><PriceInput value={amount} onChange={setAmount} placeholder="مبلغ شارژ" /></div>
        <Button loading={topup.isPending} disabled={!amount} onClick={() => topup.mutate()}>شارژ</Button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {[500_000, 1_000_000, 2_000_000].map((v) => (
          <button key={v} onClick={() => setAmount(String(v / 10))} className="rounded-full border border-line px-3 py-1 text-xs text-muted hover:border-brand">
            {toman(v)}
          </button>
        ))}
      </div>
      {!!txs.length && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs text-brand">تراکنش‌های اخیر</summary>
          <div className="mt-2 divide-y divide-line text-sm">
            {txs.slice(0, 15).map((t) => (
              <div key={t.id} className="flex items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <div className="truncate">{t.kind_display}</div>
                  <div className="truncate text-[11px] text-muted">{t.note} · {dateTime(t.created_at)}</div>
                </div>
                <b className={`shrink-0 tabular ${t.amount > 0 ? "text-ok" : "text-danger"}`} dir="ltr">{t.amount > 0 ? "+" : "−"}{toman(Math.abs(t.amount), false)}</b>
              </div>
            ))}
          </div>
        </details>
      )}
    </Card>
  );
}

/** ابزار مدیر کل: افزایش یا کاهش اعتبار کیف پول یک کاربر (مثلا اعتبار هدیه یا اصلاح خطا). */
function WalletAdmin() {
  const toast = useToast();
  const [f, setF] = useState({ mobile: "", amount: "", note: "" });
  const m = useMutation({
    mutationFn: () => api.post<{ mobile: string; balance: number }>("/wallet/admin-credit/", { ...f, amount: Number(f.amount) }),
    onSuccess: (r) => { toast(`انجام شد؛ موجودی ${r.mobile}: ${toman(r.balance)}`); setF({ mobile: "", amount: "", note: "" }); },
  });
  const err = fieldErrors(m.error);
  return (
    <Card className="space-y-3 p-4">
      <h2 className="flex items-center gap-2 font-semibold"><Wallet className="size-5 text-brand" /> اعتبار کیف پول کاربران (مدیر کل)</h2>
      <Field label="موبایل کاربر" error={err.mobile}><Input value={f.mobile} onChange={(e) => setF({ ...f, mobile: e.target.value })} dir="ltr" inputMode="numeric" className="text-left" /></Field>
      <Field label="مبلغ (تومان؛ منفی = کاهش)" error={err.amount}><Input value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} dir="ltr" inputMode="numeric" className="text-left" /></Field>
      <Field label="توضیح"><Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="مثلا اعتبار هدیه" /></Field>
      <Button className="w-full" loading={m.isPending} disabled={!f.mobile || !f.amount} onClick={() => m.mutate()}>ثبت</Button>
      {m.error && !Object.keys(err).length && <p className="text-sm text-danger">{(m.error as Error).message}</p>}
    </Card>
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
