import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Minus, Plus, ShoppingCart, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, fieldErrors } from "../lib/api";
import { useAuth } from "../lib/auth";
import { num, toman } from "../lib/format";
import { Badge, Button, Field, Input, Sheet, Textarea, useToast } from "./ui";

export type CartLine = { id: number; name: string; price: number; unit_display: string; image: string | null; qty: number };

/** نوار شناور سبد خرید + فرم نهایی‌سازی سفارش برای ویترین یک فروشگاه. */
export default function ShopCart({
  storeId,
  storeName,
  lines,
  setQty,
  clear,
}: {
  storeId: number;
  storeName: string;
  lines: CartLine[];
  setQty: (id: number, qty: number) => void;
  clear: () => void;
}) {
  const { user } = useAuth();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState<{ code: string } | null>(null);
  const [f, setF] = useState({
    customer_name: user ? `${user.first_name} ${user.last_name}`.trim() : "",
    customer_phone: user?.mobile ?? "",
    delivery: "pickup",
    address: "",
    note: "",
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const count = lines.reduce((s, l) => s + l.qty, 0);
  const total = lines.reduce((s, l) => s + l.price * l.qty, 0);

  const m = useMutation({
    mutationFn: () =>
      api.post<{ code: string }>(`/public/stores/${storeId}/order/`, {
        ...f,
        items: lines.map((l) => ({ product: l.id, quantity: l.qty })),
      }),
    onSuccess: (r) => {
      setDone(r);
      clear();
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const err = fieldErrors(m.error);

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
            <Button className="w-full" loading={m.isPending} disabled={!count || !f.customer_name || !f.customer_phone} onClick={() => m.mutate()}>
              ثبت سفارش ({toman(total)})
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
            <div key={l.id} className="flex items-center gap-3 rounded-xl border border-line p-2.5">
              {l.image ? (
                <img src={l.image} alt="" className="size-12 shrink-0 rounded-lg object-cover" />
              ) : (
                <span className="size-12 shrink-0 rounded-lg bg-surface-2" />
              )}
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{l.name}</div>
                <div className="text-xs text-muted">{toman(l.price)} / {l.unit_display}</div>
              </div>
              <div className="flex items-center gap-1.5">
                <button onClick={() => setQty(l.id, l.qty - 1)} className="grid size-8 place-items-center rounded-lg bg-surface-2" aria-label="کمتر">
                  {l.qty === 1 ? <Trash2 className="size-4 text-danger" /> : <Minus className="size-4" />}
                </button>
                <span className="w-6 text-center tabular text-sm">{num(l.qty)}</span>
                <button onClick={() => setQty(l.id, l.qty + 1)} className="grid size-8 place-items-center rounded-lg bg-surface-2" aria-label="بیشتر">
                  <Plus className="size-4" />
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between rounded-xl bg-surface-2 px-4 py-3">
          <span className="text-sm">مبلغ کل</span>
          <b className="tabular">{toman(total)}</b>
        </div>

        {user && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="نام و نام خانوادگی" error={err.customer_name}><Input value={f.customer_name} onChange={set("customer_name")} /></Field>
            <Field label="تلفن تماس" error={err.customer_phone}><Input value={f.customer_phone} onChange={set("customer_phone")} inputMode="tel" dir="ltr" className="text-left" /></Field>
            <Field label="نحوه تحویل" className="sm:col-span-2">
              <div className="grid grid-cols-2 gap-2">
                {[["pickup", "حضوری از فروشگاه"], ["delivery", "ارسال به نشانی من"]].map(([v, l]) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setF({ ...f, delivery: v })}
                    className={`h-11 rounded-xl border text-sm ${f.delivery === v ? "border-brand bg-brand-soft text-brand" : "border-line"}`}
                  >
                    {l}
                  </button>
                ))}
              </div>
            </Field>
            {f.delivery === "delivery" && (
              <Field label="نشانی تحویل" className="sm:col-span-2" error={err.address}>
                <Textarea value={f.address} onChange={set("address")} className="min-h-16" />
              </Field>
            )}
            <Field label="توضیحات (اختیاری)" className="sm:col-span-2">
              <Textarea value={f.note} onChange={set("note")} className="min-h-16" />
            </Field>
            <p className="rounded-xl bg-warn-soft p-3 text-xs leading-6 text-warn sm:col-span-2">
              پرداخت آنلاین نداریم؛ تسویه حضوری یا هنگام تحویل انجام می‌شود. پس از ثبت، سفارش در کارتابل فروشگاه قرار می‌گیرد و فروشنده با شما تماس می‌گیرد.
            </p>
          </div>
        )}
      </Sheet>

      <Sheet open={!!done} onClose={() => { setDone(null); setOpen(false); }} title="سفارش ثبت شد">
        <div className="py-2 text-center">
          <CheckCircle2 className="mx-auto size-14 text-ok" />
          <p className="mt-3 text-sm text-muted">سفارش شما برای «{storeName}» ارسال شد و در کارتابل فروشنده قرار گرفت.</p>
          <div className="mt-4 rounded-2xl bg-surface-2 p-4">
            <div className="text-xs text-muted">کد سفارش</div>
            <div className="mt-1 text-2xl font-bold tracking-widest" dir="ltr">{done?.code}</div>
          </div>
          <Badge tone="warn" className="mt-3">در انتظار تایید فروشگاه</Badge>
          <Link to="/orders" className="mt-4 block text-sm text-brand underline">پیگیری سفارش‌های من</Link>
        </div>
      </Sheet>
    </>
  );
}
