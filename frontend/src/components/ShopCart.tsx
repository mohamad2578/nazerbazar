import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, CreditCard, HandCoins, Minus, Plus, ShoppingCart, Trash2, Wallet } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, fieldErrors } from "../lib/api";
import { useAuth } from "../lib/auth";
import { num, toman } from "../lib/format";
import type { OrderT } from "../lib/orders";
import AddressBook from "./AddressBook";
import { Badge, Button, cx, Field, Input, Sheet, Textarea, useToast } from "./ui";

/** یک سطر سبد: کالای تکی یا یک بسته پیشنهادی. key یکتاست («p12» / «b3»). */
export type CartLine = {
  key: string; kind: "product" | "bundle"; id: number; name: string; price: number; unit_display: string;
  image: string | null; qty: number; max?: number | null;
};

const PAYMENTS = [
  { value: "online", label: "پرداخت اینترنتی", sub: "درگاه بانکی", icon: CreditCard },
  { value: "wallet", label: "کیف پول", sub: "", icon: Wallet },
  { value: "cash", label: "پرداخت نقدی", sub: "هنگام تحویل", icon: HandCoins },
];

/** نوار شناور سبد خرید + فرم نهایی‌سازی سفارش برای ویترین یک فروشگاه. */
export default function ShopCart({
  storeId, storeName, lines, setQty, clear, listTotal, featured,
}: {
  storeId: number;
  storeName: string;
  lines: CartLine[];
  setQty: (key: string, qty: number) => void;
  clear: () => void;
  /** جمع قیمت مصرف‌کننده برای نمایش میزان صرفه‌جویی (اختیاری) */
  listTotal?: number;
  /** فروشگاه ویژه: فقط پرداخت اینترنتی و ارسال با پیک */
  featured?: boolean;
}) {
  const { user } = useAuth();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState<OrderT | null>(null);
  const [addressId, setAddressId] = useState<number | null>(null);
  const [f, setF] = useState({
    customer_name: user ? `${user.first_name} ${user.last_name}`.trim() : "",
    customer_phone: user?.mobile ?? "",
    delivery: featured ? "delivery" : "pickup",
    payment_method: "online",
    note: "",
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const wallet = useQuery({ queryKey: ["wallet"], queryFn: () => api.get<{ balance: number }>("/wallet/"), enabled: !!user && open && !featured });
  const count = lines.reduce((s, l) => s + l.qty, 0);
  const total = lines.reduce((s, l) => s + l.price * l.qty, 0);
  const saving = listTotal && listTotal > total ? listTotal - total : 0;
  const balance = wallet.data?.balance ?? 0;

  const m = useMutation({
    mutationFn: () =>
      api.post<OrderT>(`/public/stores/${storeId}/order/`, {
        ...f,
        address_id: f.delivery === "delivery" ? addressId : undefined,
        items: lines.filter((l) => l.kind === "product").map((l) => ({ product: l.id, quantity: l.qty })),
        bundles: lines.filter((l) => l.kind === "bundle").map((l) => ({ bundle: l.id, quantity: l.qty })),
      }),
    onSuccess: (r) => {
      clear();
      if (r.payment_url) {
        window.location.href = r.payment_url; // انتقال به درگاه پرداخت
        return;
      }
      setDone(r);
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const err = fieldErrors(m.error);
  const needAddress = f.delivery === "delivery" && !addressId;
  const walletShort = f.payment_method === "wallet" && wallet.data && balance < total * 1;

  if (!count && !done) return null;

  return (
    <>
      {!!count && (
        <div className="safe-bottom fixed inset-x-0 bottom-16 z-[640] px-4 lg:bottom-5">
          <button
            onClick={() => setOpen(true)}
            className="mx-auto flex w-full max-w-md items-center justify-between gap-3 rounded-2xl bg-brand px-4 py-3 text-brand-ink shadow-xl"
          >
            <span className="inline-flex items-center gap-2 text-sm font-medium">
              <ShoppingCart className="size-5" /> {num(count)} قلم در سبد
            </span>
            <span className="tabular font-bold">{toman(total)}</span>
          </button>
        </div>
      )}

      <Sheet
        open={open && !done}
        onClose={() => setOpen(false)}
        title={`سفارش از ${storeName}`}
        footer={
          user ? (
            <Button
              className="w-full"
              loading={m.isPending}
              disabled={!count || !f.customer_name || !f.customer_phone || needAddress || !!walletShort}
              onClick={() => m.mutate()}
            >
              {f.payment_method === "online" ? "ادامه و پرداخت" : "ثبت سفارش"} ({toman(total)})
            </Button>
          ) : (
            <Link to={`/login?next=/s/${storeId}`} className="inline-flex h-11 w-full items-center justify-center rounded-xl bg-brand text-sm font-medium text-brand-ink">
              برای ثبت سفارش وارد شوید
            </Link>
          )
        }
      >
        <div className="space-y-2">
          {lines.map((l) => (
            <div key={l.key} className="flex items-center gap-3 rounded-xl border border-line p-2.5">
              {l.image ? (
                <img src={l.image} alt="" className="size-12 shrink-0 rounded-lg object-cover" />
              ) : (
                <span className="size-12 shrink-0 rounded-lg bg-surface-2" />
              )}
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">
                  {l.kind === "bundle" && <Badge tone="brand" className="ml-1">بسته</Badge>}
                  {l.name}
                </div>
                <div className="text-xs text-muted">{toman(l.price)}{l.unit_display && ` / ${l.unit_display}`}</div>
              </div>
              <div className="flex items-center gap-1.5">
                <button onClick={() => setQty(l.key, l.qty - 1)} className="grid size-8 place-items-center rounded-lg bg-surface-2" aria-label="کمتر">
                  {l.qty === 1 ? <Trash2 className="size-4 text-danger" /> : <Minus className="size-4" />}
                </button>
                <span className="w-6 text-center tabular text-sm">{num(l.qty)}</span>
                <button
                  onClick={() => setQty(l.key, l.qty + 1)}
                  disabled={l.max != null && l.qty >= l.max}
                  className="grid size-8 place-items-center rounded-lg bg-surface-2 disabled:opacity-40"
                  aria-label="بیشتر"
                >
                  <Plus className="size-4" />
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 space-y-1 rounded-xl bg-surface-2 px-4 py-3 text-sm">
          {saving > 0 && (
            <div className="flex items-center justify-between text-ok">
              <span>سود شما از این خرید</span>
              <b className="tabular">{toman(saving)}</b>
            </div>
          )}
          <div className="flex items-center justify-between">
            <span>مبلغ قابل پرداخت</span>
            <b className="tabular text-base">{toman(total)}</b>
          </div>
        </div>

        {user && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="نام و نام خانوادگی" error={err.customer_name}><Input value={f.customer_name} onChange={set("customer_name")} /></Field>
            <Field label="تلفن تماس" error={err.customer_phone}><Input value={f.customer_phone} onChange={set("customer_phone")} inputMode="tel" dir="ltr" className="text-left" /></Field>
            {!featured && <Field label="نحوه تحویل" className="sm:col-span-2">
              <div className="grid grid-cols-2 gap-2">
                {[["pickup", "حضوری از فروشگاه"], ["delivery", "ارسال با پیک"]].map(([v, l]) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setF({ ...f, delivery: v })}
                    className={cx("h-11 rounded-xl border text-sm", f.delivery === v ? "border-brand bg-brand-soft text-brand" : "border-line")}
                  >
                    {l}
                  </button>
                ))}
              </div>
            </Field>}
            {f.delivery === "delivery" && (
              <div className="sm:col-span-2">
                <div className="mb-1.5 text-sm font-medium">نشانی تحویل</div>
                <AddressBook selected={addressId} onSelect={(a) => setAddressId(a?.id ?? null)} />
                {err.address && <p className="mt-1 text-xs text-danger">{err.address}</p>}
              </div>
            )}
            {featured ? (
              <div className="flex items-center gap-2 rounded-xl bg-brand-soft p-3 text-xs leading-6 text-brand sm:col-span-2">
                <CreditCard className="size-5 shrink-0" />
                <span>سفارش‌های طرح ویژه با <b>پیک</b> ارسال می‌شود و پرداخت فقط به‌صورت <b>اینترنتی</b> (درگاه بانکی) است.</span>
              </div>
            ) : (
            <Field label="روش پرداخت" className="sm:col-span-2" error={err.payment_method}>
              <div className="grid grid-cols-3 gap-2">
                {PAYMENTS.map(({ value, label, sub, icon: Icon }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setF({ ...f, payment_method: value })}
                    className={cx("flex flex-col items-center gap-1 rounded-xl border px-1 py-2.5 text-xs", f.payment_method === value ? "border-brand bg-brand-soft text-brand" : "border-line")}
                  >
                    <Icon className="size-5" />
                    <span className="font-medium">{label}</span>
                    <span className="text-[10px] text-muted">{value === "wallet" ? (wallet.data ? toman(balance) : "موجودی…") : sub}</span>
                  </button>
                ))}
              </div>
              {walletShort && (
                <p className="mt-2 text-xs text-danger">
                  موجودی کیف پول کافی نیست. از «حساب من» کیف پول را شارژ کنید یا روش دیگری انتخاب کنید.
                </p>
              )}
            </Field>
            )}
            <Field label="توضیحات (اختیاری)" className="sm:col-span-2">
              <Textarea value={f.note} onChange={set("note")} className="min-h-16" />
            </Field>
          </div>
        )}
      </Sheet>

      <Sheet open={!!done} onClose={() => { setDone(null); setOpen(false); }} title="سفارش ثبت شد">
        {done && (
          <div className="py-2 text-center">
            <CheckCircle2 className="mx-auto size-14 text-ok" />
            <p className="mt-3 text-sm text-muted">سفارش شما برای «{storeName}» ثبت شد و فاکتور آن در کارتابل کارشناس فروشگاه قرار گرفت.</p>
            <div className="mt-4 rounded-2xl bg-surface-2 p-4">
              <div className="text-xs text-muted">کد سفارش</div>
              <div className="mt-1 text-2xl font-bold tracking-widest" dir="ltr">{done.code}</div>
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
              <Badge tone="warn">در انتظار تایید فروشگاه</Badge>
              <Badge tone={done.payment_status === "paid" ? "ok" : "neutral"}>{done.payment_method_display} · {done.payment_status_display}</Badge>
            </div>
            {done.savings > 0 && <p className="mt-3 text-sm text-ok">با این خرید {toman(done.savings)} صرفه‌جویی کردید.</p>}
            <Link to="/orders" className="mt-4 block text-sm text-brand underline">مشاهده فاکتور و پیگیری سفارش</Link>
          </div>
        )}
      </Sheet>
    </>
  );
}
