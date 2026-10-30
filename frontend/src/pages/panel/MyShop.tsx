import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Gift, Info, Package, Pencil, Plus, Search, Store as StoreIcon, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import ImageUpload from "../../components/ImageUpload";
import { Badge, Button, Card, cx, Empty, ErrorBox, Field, Input, Loading, PageHeader, PriceInput, Segmented, Select, Sheet, Textarea, useToast } from "../../components/ui";
import { api, fieldErrors, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { num, toman, toRial, toToman } from "../../lib/format";

type ShopProductT = {
  id: number; store: number; store_name: string; category: number | null; category_name: string;
  name: string; description: string; image: string | null; price: number; old_price: number | null;
  discount_percent: number | null; unit: string; unit_display: string; brand: string;
  is_available: boolean; is_active: boolean; order: number;
  status: string; status_display: string; review_note: string;
  stock?: number | null; per_user_limit?: number | null; sold_out?: boolean;
};
type Category = { id: number; name: string };

const UNITS = [["piece", "عدد"], ["kg", "کیلوگرم"], ["g", "گرم"], ["pack", "بسته"], ["l", "لیتر"], ["m", "متر"], ["service", "خدمت"]];

/** فروشگاه اینترنتی: محصولات اختصاصی خود فروشگاه، مستقل از کالاهای اساسی و حداکثر قیمت اتحادیه. */
export default function MyShop() {
  const { user } = useAuth();
  const store = user!.store;
  const featured = !!store?.is_featured;
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState<ShopProductT | "new" | null>(null);
  const qc = useQueryClient();
  const toast = useToast();

  const q = useQuery({
    queryKey: ["shop-products", search, filter, featured],
    queryFn: () => api.get<Page<ShopProductT>>("/shop-products/", { search, is_active: filter || undefined, is_special: featured ? undefined : false, page_size: 100 }),
  });
  const del = useMutation({
    mutationFn: (id: number) => api.del(`/shop-products/${id}/`),
    onSuccess: () => { toast("حذف شد"); qc.invalidateQueries({ queryKey: ["shop-products"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const toggle = useMutation({
    mutationFn: (p: ShopProductT) => api.patch(`/shop-products/${p.id}/`, { is_active: !p.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["shop-products"] }),
  });

  if (store && store.status !== "active")
    return <Card><Empty title="فروشگاه شما هنوز فعال نشده است">پس از تایید اتحادیه، می‌توانید محصولات فروشگاه خود را اضافه کنید.</Empty></Card>;

  const rows = q.data?.results ?? [];
  return (
    <div className="space-y-4">
      <PageHeader
        title="فروشگاه اینترنتی من"
        subtitle="محصولات خودتان را با قیمت دلخواه عرضه کنید — مستقل از کالاهای اساسی اتحادیه."
        actions={<>
          {store && <Link to={`/s/${store.id}`} className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-line px-3 text-sm"><StoreIcon className="size-4" /> نمای عمومی</Link>}
          <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>محصول جدید</Button>
        </>}
      />

      <Card className="flex items-start gap-2 border-brand/30 bg-brand-soft/60 p-3 text-xs leading-6 text-brand">
        <Info className="mt-0.5 size-4 shrink-0" />
        <span>
          {featured
            ? "فروشگاه ویژه: هر محصولی را بدون تایید اداره صمت عرضه می‌کنید. برای هر کالا قیمت مصرف‌کننده، قیمت با تخفیف، موجودی، سقف خرید هر کاربر و الویت نمایش (عدد کمتر = بالاتر) را مشخص کنید."
            : "این بخش با «کالاهای اساسی» فرق دارد: آن‌ها را اتحادیه تعریف می‌کند و قیمتشان باید برابر حداکثر قیمت یا حداکثر ۲۰٪ کمتر باشد. اینجا محصولات خودتان را آزادانه و با قیمت دلخواه ثبت می‌کنید."}
        </span>
      </Card>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Segmented value={filter} onChange={setFilter} options={[
          { value: "", label: `همه (${num(rows.length)})` },
          { value: "true", label: "نمایش‌داده‌شده" },
          { value: "false", label: "پنهان" },
        ]} />
        <div className="relative sm:mr-auto sm:w-64">
          <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="جستجوی محصول" className="pr-9" />
        </div>
      </div>

      {q.isLoading ? <Loading /> : q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : !rows.length ? (
        <Card>
          <Empty title="هنوز محصولی اضافه نکرده‌اید" icon={<Package className="size-7" />}>
            با «محصول جدید» اولین کالای فروشگاه خود را ثبت کنید؛ بلافاصله در صفحه فروشگاه شما به مشتریان نمایش داده می‌شود.
          </Empty>
        </Card>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(9.25rem,1fr))] gap-3">
          {rows.map((p) => (
            <Card key={p.id} className={cx("overflow-hidden", !p.is_active && "opacity-60")}>
              <div className="relative aspect-square bg-surface-2">
                {p.image
                  ? <img src={p.image} alt="" className="size-full object-contain p-2" />
                  : <span className="grid size-full place-items-center text-muted"><Package className="size-8" /></span>}
                <div className="absolute right-2 top-2 flex gap-1">
                  {!p.is_active && <Badge tone="neutral">پنهان</Badge>}
                  <Badge tone={p.status === "approved" ? "ok" : p.status === "rejected" ? "danger" : "warn"}>{p.status_display}</Badge>
                  {!p.is_available && <Badge tone="warn">ناموجود</Badge>}
                  {p.discount_percent ? <Badge tone="ok">{num(p.discount_percent)}٪ تخفیف</Badge> : null}
                  {featured && p.sold_out && <Badge tone="danger">تمام شد</Badge>}
                </div>
              </div>
              <div className="p-3.5">
                <div className="truncate font-medium">{p.name}</div>
                <div className="mt-0.5 truncate text-xs text-muted">
                  {p.category_name || "بدون دسته"} · هر {p.unit_display}{p.brand && ` · ${p.brand}`}
                </div>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="font-bold tabular">{toman(p.price)}</span>
                  {p.old_price ? <span className="text-xs text-muted line-through tabular">{toman(p.old_price, false)}</span> : null}
                </div>
                {featured && (
                  <div className="mt-1.5 flex flex-wrap gap-x-3 text-[11px] text-muted">
                    <span>الویت: {num(p.order)}</span>
                    <span>موجودی: {p.stock == null ? "نامحدود" : num(p.stock)}</span>
                    <span>سقف خرید: {p.per_user_limit == null ? "ندارد" : num(p.per_user_limit)}</span>
                  </div>
                )}
                <div className="mt-3 flex gap-2">
                  <Button size="sm" variant="secondary" icon={<Pencil className="size-4" />} onClick={() => setEditing(p)}>ویرایش</Button>
                  <Button size="sm" variant="ghost" icon={p.is_active ? <EyeOff className="size-4" /> : <Eye className="size-4" />} onClick={() => toggle.mutate(p)}>
                    {p.is_active ? "پنهان" : "نمایش"}
                  </Button>
                  <Button size="sm" variant="ghost" className="text-danger" icon={<Trash2 className="size-4" />} onClick={() => confirm(`«${p.name}» حذف شود؟`) && del.mutate(p.id)} />
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing && <ProductForm product={editing === "new" ? null : editing} featured={featured} onClose={() => setEditing(null)} />}
      {featured && <BundlesSection products={rows} />}
    </div>
  );
}

function ProductForm({ product, featured, onClose }: { product: ShopProductT | null; featured: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const cats = useQuery({ queryKey: ["shop-categories"], queryFn: () => api.get<Category[]>("/shop-categories/"), staleTime: 3600_000 });
  const [f, setF] = useState({
    name: product?.name ?? "", description: product?.description ?? "", category: product?.category ?? "",
    price: product ? String(toToman(product.price)) : "", old_price: product?.old_price ? String(toToman(product.old_price)) : "",
    unit: product?.unit ?? "piece", brand: product?.brand ?? "",
    is_available: product?.is_available ?? true, is_active: product?.is_active ?? true,
    stock: product?.stock == null ? "" : String(product.stock), per_user_limit: product?.per_user_limit == null ? "" : String(product.per_user_limit),
    order: String(product?.order ?? 0),
  });
  const [image, setImage] = useState<File | null | undefined>(undefined);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const m = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.set("name", f.name);
      fd.set("description", f.description);
      fd.set("unit", f.unit);
      fd.set("brand", f.brand);
      fd.set("price", String(toRial(f.price || "0")));
      if (f.old_price) fd.set("old_price", String(toRial(f.old_price)));
      if (f.category) fd.set("category", String(f.category));
      fd.set("is_available", String(f.is_available));
      fd.set("is_active", String(f.is_active));
      if (featured) {
        fd.set("stock", f.stock);
        fd.set("per_user_limit", f.per_user_limit);
        fd.set("order", f.order || "0");
      }
      if (image !== undefined) fd.set("image", image ?? "");
      return product ? api.patch(`/shop-products/${product.id}/`, fd) : api.post("/shop-products/", fd);
    },
    onSuccess: () => { toast("ذخیره شد"); qc.invalidateQueries({ queryKey: ["shop-products"] }); onClose(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const err = fieldErrors(m.error);

  return (
    <Sheet
      open
      onClose={onClose}
      title={product ? "ویرایش محصول" : "محصول جدید فروشگاه"}
      footer={<Button className="w-full" loading={m.isPending} disabled={!f.name || !f.price} onClick={() => m.mutate()}>ذخیره</Button>}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="تصویر محصول" error={err.image} className="sm:col-span-2">
          <div className="max-w-56">
            <ImageUpload value={product?.image} onChange={setImage} aspect="4/3" />
          </div>
        </Field>
        <Field label="نام محصول" error={err.name} className="sm:col-span-2"><Input value={f.name} onChange={set("name")} /></Field>
        <Field label="قیمت" error={err.price}><PriceInput value={f.price} onChange={(v) => setF({ ...f, price: v })} /></Field>
        <Field label="قیمت پیش از تخفیف" hint="اختیاری؛ خط‌خورده نمایش داده می‌شود" error={err.old_price}>
          <PriceInput value={f.old_price} onChange={(v) => setF({ ...f, old_price: v })} />
        </Field>
        <Field label="واحد"><Select value={f.unit} onChange={set("unit")}>{UNITS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
        <Field label="دسته">
          <Select value={String(f.category)} onChange={set("category")}>
            <option value="">—</option>
            {cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
        <Field label="برند / تولیدکننده" className="sm:col-span-2"><Input value={f.brand} onChange={set("brand")} /></Field>
        {featured && (<>
          <Field label="موجودی انبار" hint="خالی = نامحدود. به مشتری نمایش داده نمی‌شود؛ با تمام شدن، خرید بسته می‌شود." error={err.stock}>
            <Input type="number" min={0} value={f.stock} onChange={set("stock")} dir="ltr" className="text-left" />
          </Field>
          <Field label="سقف خرید هر کاربر" hint="خالی = بدون سقف" error={err.per_user_limit}>
            <Input type="number" min={1} value={f.per_user_limit} onChange={set("per_user_limit")} dir="ltr" className="text-left" />
          </Field>
          <Field label="الویت نمایش" hint="عدد کمتر = بالاتر در صفحه فروشگاه" error={err.order} className="sm:col-span-2">
            <Input type="number" min={0} value={f.order} onChange={set("order")} dir="ltr" className="text-left" />
          </Field>
        </>)}
        <Field label="توضیحات" className="sm:col-span-2"><Textarea value={f.description} onChange={set("description")} className="min-h-20" /></Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4" checked={f.is_available} onChange={(e) => setF({ ...f, is_available: e.target.checked })} /> موجود است
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> در فروشگاه نمایش داده شود
        </label>
      </div>
      {m.error && !Object.keys(err).length && <p className="mt-3 text-sm text-danger">{(m.error as Error).message}</p>}
    </Sheet>
  );
}

type BundleT = {
  id: number; title: string; description: string; image: string | null; price: number; order: number; is_active: boolean;
  items: { product: number; quantity: number; name: string; price: number }[]; items_total: number; list_total: number; sold_out: boolean;
};

/** بسته‌های پیشنهادی فروشگاه ویژه: چند کالا با قیمت یکجا (مثلا برنج + گوشت + مرغ). */
function BundlesSection({ products }: { products: ShopProductT[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState<BundleT | "new" | null>(null);
  const q = useQuery({ queryKey: ["shop-bundles"], queryFn: () => api.get<BundleT[]>("/shop-bundles/") });
  const del = useMutation({
    mutationFn: (id: number) => api.del(`/shop-bundles/${id}/`),
    onSuccess: () => { toast("حذف شد"); qc.invalidateQueries({ queryKey: ["shop-bundles"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const rows = q.data ?? [];
  return (
    <section className="space-y-3 pt-2">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-semibold"><Gift className="size-5 text-accent" /> بسته‌های پیشنهادی</h2>
        <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setEditing("new")} disabled={!products.length}>بسته جدید</Button>
      </div>
      {!rows.length ? (
        <Card><Empty title="هنوز بسته‌ای تعریف نشده" icon={<Gift className="size-7" />}>چند کالا را در یک بسته با قیمت ویژه عرضه کنید.</Empty></Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {rows.map((b) => (
            <Card key={b.id} className={cx("p-4", !b.is_active && "opacity-60")}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-medium">{b.title}</div>
                  <div className="mt-0.5 text-xs text-muted">{b.items.map((i) => `${i.name} ×${num(i.quantity)}`).join("، ")}</div>
                </div>
                <div className="flex shrink-0 gap-1">
                  {!b.is_active && <Badge>پنهان</Badge>}
                  {b.sold_out && <Badge tone="danger">ناموجود</Badge>}
                </div>
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <b className="tabular">{toman(b.price)}</b>
                <s className="text-xs text-muted tabular">{toman(b.list_total, false)}</s>
              </div>
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="secondary" icon={<Pencil className="size-4" />} onClick={() => setEditing(b)}>ویرایش</Button>
                <Button size="sm" variant="ghost" className="text-danger" icon={<Trash2 className="size-4" />} onClick={() => confirm(`بسته «${b.title}» حذف شود؟`) && del.mutate(b.id)} />
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing && <BundleForm bundle={editing === "new" ? null : editing} products={products} onClose={() => setEditing(null)} />}
    </section>
  );
}

function BundleForm({ bundle, products, onClose }: { bundle: BundleT | null; products: ShopProductT[]; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState({
    title: bundle?.title ?? "", description: bundle?.description ?? "", price: bundle ? String(toToman(bundle.price)) : "",
    order: String(bundle?.order ?? 0), is_active: bundle?.is_active ?? true,
  });
  const [qty, setQty] = useState<Record<number, number>>(() => Object.fromEntries((bundle?.items ?? []).map((i) => [i.product, i.quantity])));
  const [image, setImage] = useState<File | null | undefined>(undefined);
  const chosen = products.filter((p) => qty[p.id]);
  const sum = chosen.reduce((s, p) => s + p.price * qty[p.id], 0);
  const m = useMutation({
    mutationFn: () => {
      const items = chosen.map((p) => ({ product: p.id, quantity: qty[p.id] }));
      if (image !== undefined) {
        // با تصویر: multipart؛ اقلام به‌صورت JSON درون فیلد items
        const fd = new FormData();
        for (const [k, v] of Object.entries({ title: f.title, description: f.description, price: toRial(f.price || "0"), order: f.order || "0", is_active: f.is_active })) fd.set(k, String(v));
        fd.set("image", image ?? "");
        fd.set("items", JSON.stringify(items));
        return bundle ? api.patch(`/shop-bundles/${bundle.id}/`, fd) : api.post("/shop-bundles/", fd);
      }
      const body = { title: f.title, description: f.description, price: toRial(f.price || "0"), order: Number(f.order || 0), is_active: f.is_active, items };
      return bundle ? api.patch(`/shop-bundles/${bundle.id}/`, body) : api.post("/shop-bundles/", body);
    },
    onSuccess: () => { toast("بسته ذخیره شد"); qc.invalidateQueries({ queryKey: ["shop-bundles"] }); onClose(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const err = fieldErrors(m.error);
  return (
    <Sheet open onClose={onClose} title={bundle ? "ویرایش بسته" : "بسته پیشنهادی جدید"}
      footer={<Button className="w-full" loading={m.isPending} disabled={!f.title || !f.price || !chosen.length} onClick={() => m.mutate()}>ذخیره بسته</Button>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="عنوان بسته" error={err.title} className="sm:col-span-2"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="مثلا بسته خانواده" /></Field>
        <Field label="توضیح کوتاه" className="sm:col-span-2"><Input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="کالاهای بسته" error={err.items} className="sm:col-span-2" hint={sum ? `جمع قیمت کالاها: ${toman(sum)}` : "تعداد هر کالای دلخواه را بالای صفر بگذارید"}>
          <div className="max-h-64 divide-y divide-line overflow-y-auto rounded-xl border border-line">
            {products.map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                <span className="min-w-0 truncate">{p.name} <span className="text-xs text-muted">{toman(p.price)}</span></span>
                <input type="number" min={0} max={99} value={qty[p.id] ?? 0} onChange={(e) => setQty({ ...qty, [p.id]: Math.max(0, Number(e.target.value)) })}
                  className="h-9 w-16 rounded-lg border border-line bg-surface text-center tabular" dir="ltr" />
              </div>
            ))}
          </div>
        </Field>
        <Field label="قیمت بسته" error={err.price}><PriceInput value={f.price} onChange={(v) => setF({ ...f, price: v })} /></Field>
        <Field label="الویت نمایش" hint="عدد کمتر = بالاتر"><Input type="number" min={0} value={f.order} onChange={(e) => setF({ ...f, order: e.target.value })} dir="ltr" className="text-left" /></Field>
        <Field label="تصویر بسته (اختیاری)" className="sm:col-span-2"><div className="max-w-56"><ImageUpload value={bundle?.image} onChange={setImage} aspect="4/3" /></div></Field>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" className="size-4" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> در فروشگاه نمایش داده شود
        </label>
      </div>
      {m.error && !Object.keys(err).length && <p className="mt-3 text-sm text-danger">{(m.error as Error).message}</p>}
    </Sheet>
  );
}
