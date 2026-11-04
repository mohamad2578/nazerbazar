import { useQuery } from "@tanstack/react-query";
import { Flame, Gift, Minus, Package, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import ShopCart, { type CartLine } from "../../components/ShopCart";
import { Badge, Card, cx, Loading } from "../../components/ui";
import { api } from "../../lib/api";
import { num, toman } from "../../lib/format";

type Product = {
  id: number; name: string; description: string; image: string | null; price: number; old_price: number | null;
  discount_percent: number | null; unit_display: string; brand: string; is_available: boolean; sold_out: boolean;
  per_user_limit: number | null;
};
type Bundle = {
  id: number; title: string; description: string; image: string | null; price: number; items_total: number; list_total: number;
  sold_out: boolean;
  items: { product: number; quantity: number; name: string; image: string | null; unit_display: string }[];
};

const listPrice = (p: Product) => Math.max(p.old_price ?? 0, p.price);

/** ویترین «فروشگاه ویژه»: کالاهای با تخفیف، بسته‌های پیشنهادی و سبد خرید. */
export default function FeaturedStorefront({ storeId, storeName }: { storeId: number; storeName: string }) {
  const products = useQuery({ queryKey: ["featured-products", storeId], queryFn: () => api.get<Product[]>(`/public/stores/${storeId}/shop/`) });
  const bundles = useQuery({ queryKey: ["featured-bundles", storeId], queryFn: () => api.get<Bundle[]>(`/public/stores/${storeId}/bundles/`) });
  // سبد خرید با رفتن به صفحه دیگر یا برگشتن از درگاه از بین نرود (فقط در همین نشست مرورگر)
  const cartKey = `nb.cart.${storeId}`;
  const [cart, setCart] = useState<Record<string, number>>(() => {
    try {
      const v = JSON.parse(sessionStorage.getItem(cartKey) || "{}");
      return v && typeof v === "object" ? v : {};
    } catch {
      return {};
    }
  });
  useEffect(() => {
    try {
      sessionStorage.setItem(cartKey, JSON.stringify(cart));
    } catch {
      /* حالت خصوصی مرورگر */
    }
  }, [cart, cartKey]);

  const items = products.data ?? [];
  const packs = bundles.data ?? [];

  const lines = useMemo<CartLine[]>(() => {
    const out: CartLine[] = [];
    for (const [key, qty] of Object.entries(cart)) {
      const id = Number(key.slice(1));
      if (key[0] === "p") {
        const p = items.find((x) => x.id === id);
        if (p) out.push({ key, kind: "product", id, name: p.name, price: p.price, unit_display: p.unit_display, image: p.image, qty, max: p.per_user_limit });
      } else {
        const b = packs.find((x) => x.id === id);
        if (b) out.push({ key, kind: "bundle", id, name: b.title, price: b.price, unit_display: "", image: b.image, qty });
      }
    }
    return out;
  }, [cart, items, packs]);

  const listTotal = lines.reduce((s, l) => {
    if (l.kind === "product") return s + listPrice(items.find((p) => p.id === l.id)!) * l.qty;
    return s + (packs.find((b) => b.id === l.id)?.list_total ?? l.price) * l.qty;
  }, 0);

  const setQty = (key: string, qty: number) =>
    setCart((c) => {
      const next = { ...c };
      if (qty <= 0) delete next[key];
      else next[key] = qty;
      return next;
    });

  if (products.isLoading) return <Loading />;
  return (
    <div className="space-y-6">
      {!!packs.length && (
        <section>
          <div className="mb-3 flex items-center gap-2">
            <Gift className="size-5 text-accent" />
            <h2 className="font-semibold">بسته‌های پیشنهادی</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {packs.map((b) => {
              const off = b.list_total > b.price ? Math.round(((b.list_total - b.price) / b.list_total) * 100) : 0;
              const qty = cart[`b${b.id}`] ?? 0;
              return (
                <Card key={b.id} className={cx("overflow-hidden border-accent/40", b.sold_out && "opacity-70")}>
                  <div className="bg-gradient-to-l from-accent/15 to-transparent p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <h3 className="truncate font-bold">{b.title}</h3>
                        {b.description && <p className="mt-0.5 text-xs text-muted">{b.description}</p>}
                      </div>
                      {off > 0 && <Badge tone="ok">{num(off)}٪ تخفیف</Badge>}
                    </div>
                    <ul className="mt-3 space-y-1.5">
                      {b.items.map((it) => (
                        <li key={it.product} className="flex items-center gap-2 text-sm">
                          {it.image
                            ? <img src={it.image} alt="" className="size-8 shrink-0 rounded-lg object-cover" />
                            : <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-2 text-muted"><Package className="size-4" /></span>}
                          <span className="min-w-0 flex-1 truncate">{it.name}</span>
                          <span className="text-xs text-muted tabular">× {num(it.quantity)}</span>
                        </li>
                      ))}
                    </ul>
                    <div className="mt-3 flex items-end justify-between gap-2">
                      <div>
                        {b.list_total > b.price && <div className="text-xs text-muted line-through tabular">{toman(b.list_total)}</div>}
                        <div className="text-lg font-bold tabular">{toman(b.price)}</div>
                      </div>
                      {b.sold_out ? <Badge tone="warn">ناموجود</Badge> : <Stepper qty={qty} onChange={(q) => setQty(`b${b.id}`, q)} />}
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        </section>
      )}

      <section id="featured-shop" className="scroll-mt-20">
        <div className="mb-3 flex items-center gap-2">
          <Flame className="size-5 text-danger" />
          <h2 className="font-semibold">کالاهای طرح ویژه</h2>
        </div>
        {!items.length ? (
          <Card><p className="p-6 text-center text-sm text-muted">هنوز کالایی ثبت نشده است.</p></Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {items.map((p) => {
              const out = p.sold_out || !p.is_available;
              const qty = cart[`p${p.id}`] ?? 0;
              const reached = p.per_user_limit != null && qty >= p.per_user_limit;
              return (
                <Card key={p.id} className={cx("flex gap-3 p-3", out && "opacity-70")}>
                  <div className="relative size-24 shrink-0 overflow-hidden rounded-xl bg-surface-2 sm:size-28">
                    {p.image
                      ? <img src={p.image} alt="" loading="lazy" className="size-full object-contain p-1.5" />
                      : <span className="grid size-full place-items-center text-muted"><Package className="size-8" /></span>}
                    {p.discount_percent ? <Badge tone="danger" className="absolute right-1 top-1 !px-1.5 text-[10px]">{num(p.discount_percent)}٪</Badge> : null}
                    {out && <div className="absolute inset-0 grid place-items-center bg-surface/75 text-xs font-bold text-muted">ناموجود</div>}
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="line-clamp-2 text-sm font-semibold leading-5">{p.name}</div>
                    <div className="mt-0.5 truncate text-[11px] text-muted">{[p.brand, `هر ${p.unit_display}`].filter(Boolean).join(" · ")}</div>
                    <div className="mt-1.5">
                      {p.old_price && p.old_price > p.price && (
                        <div className="text-[11px] text-muted">قیمت مصرف‌کننده: <s className="tabular">{toman(p.old_price, false)}</s></div>
                      )}
                      <div className="font-bold tabular text-ok">{toman(p.price)}</div>
                    </div>
                    {p.per_user_limit != null && <div className="mt-0.5 text-[10px] text-warn">حداکثر {num(p.per_user_limit)} عدد برای هر نفر</div>}
                    <div className="mt-auto pt-2">
                      {out ? (
                        <div className="grid h-9 place-items-center rounded-xl bg-surface-2 text-xs text-muted">ناموجود</div>
                      ) : qty ? (
                        <Stepper qty={qty} max={reached ? qty : undefined} onChange={(q) => setQty(`p${p.id}`, q)} full />
                      ) : (
                        <button onClick={() => setQty(`p${p.id}`, 1)} className="inline-flex h-9 w-full items-center justify-center gap-1 rounded-xl bg-brand text-sm text-brand-ink">
                          <Plus className="size-4" /> افزودن به سبد
                        </button>
                      )}
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      <ShopCart featured storeId={storeId} storeName={storeName} lines={lines} setQty={setQty} clear={() => setCart({})} listTotal={listTotal} />
      {!!lines.length && <div className="h-16" />}
    </div>
  );
}

function Stepper({ qty, onChange, max, full }: { qty: number; onChange: (q: number) => void; max?: number; full?: boolean }) {
  return (
    <div className={cx("flex items-center justify-between gap-2 rounded-xl bg-brand-soft p-1", full ? "w-full" : "w-28")}>
      <button onClick={() => onChange(qty + 1)} disabled={max != null && qty >= max} className="grid size-8 place-items-center rounded-lg bg-brand text-brand-ink disabled:opacity-40" aria-label="بیشتر">
        <Plus className="size-4" />
      </button>
      <span className="tabular font-semibold text-brand">{num(qty)}</span>
      <button onClick={() => onChange(qty - 1)} className="grid size-8 place-items-center rounded-lg bg-surface text-ink" aria-label="کمتر">
        <Minus className="size-4" />
      </button>
    </div>
  );
}
