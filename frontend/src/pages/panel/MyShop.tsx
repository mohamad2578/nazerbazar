import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Info, Package, Pencil, Plus, Search, Store as StoreIcon, Trash2 } from "lucide-react";
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
};
type Category = { id: number; name: string };

const UNITS = [["piece", "عدد"], ["kg", "کیلوگرم"], ["g", "گرم"], ["pack", "بسته"], ["l", "لیتر"], ["m", "متر"], ["service", "خدمت"]];

/** فروشگاه اینترنتی: محصولات اختصاصی خود فروشگاه، مستقل از کالاهای اساسی و نرخ مصوب اتحادیه. */
export default function MyShop() {
  const { user } = useAuth();
  const store = user!.store;
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState<ShopProductT | "new" | null>(null);
  const qc = useQueryClient();
  const toast = useToast();

  const q = useQuery({
    queryKey: ["shop-products", search, filter],
    queryFn: () => api.get<Page<ShopProductT>>("/shop-products/", { search, is_active: filter || undefined, page_size: 100 }),
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
          این بخش با «کالاهای اساسی» فرق دارد: آن‌ها را اتحادیه تعریف می‌کند و قیمتشان باید برابر نرخ مصوب یا حداکثر ۲۰٪ کمتر باشد.
          اینجا محصولات خودتان را آزادانه و با قیمت دلخواه ثبت می‌کنید.
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
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((p) => (
            <Card key={p.id} className={cx("overflow-hidden", !p.is_active && "opacity-60")}>
              <div className="relative aspect-[4/3] bg-surface-2">
                {p.image
                  ? <img src={p.image} alt="" className="size-full object-cover" />
                  : <span className="grid size-full place-items-center text-muted"><Package className="size-8" /></span>}
                <div className="absolute right-2 top-2 flex gap-1">
                  {!p.is_active && <Badge tone="neutral">پنهان</Badge>}
                  <Badge tone={p.status === "approved" ? "ok" : p.status === "rejected" ? "danger" : "warn"}>{p.status_display}</Badge>
                  {!p.is_available && <Badge tone="warn">ناموجود</Badge>}
                  {p.discount_percent ? <Badge tone="ok">{num(p.discount_percent)}٪ تخفیف</Badge> : null}
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
      {editing && <ProductForm product={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ProductForm({ product, onClose }: { product: ShopProductT | null; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const cats = useQuery({ queryKey: ["shop-categories"], queryFn: () => api.get<Category[]>("/shop-categories/"), staleTime: 3600_000 });
  const [f, setF] = useState({
    name: product?.name ?? "", description: product?.description ?? "", category: product?.category ?? "",
    price: product ? String(toToman(product.price)) : "", old_price: product?.old_price ? String(toToman(product.old_price)) : "",
    unit: product?.unit ?? "piece", brand: product?.brand ?? "",
    is_available: product?.is_available ?? true, is_active: product?.is_active ?? true,
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
