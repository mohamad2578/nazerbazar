import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Pencil, Plus, Search, TrendingUp } from "lucide-react";
import { useState } from "react";
import ImageUpload from "../../components/ImageUpload";
import Sparkline from "../../components/Sparkline";
import { Badge, Button, Card, DataTable, Empty, Field, Input, Loading, PageHeader, PriceInput, Select, Sheet, Textarea, useToast } from "../../components/ui";
import { api, download, fieldErrors, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { ago, dateTime, num, toman, toRial, toToman } from "../../lib/format";

type ProductT = {
  id: number; union: number; union_name: string; category: number | null; category_name: string; commodity: number | null;
  commodity_name: string; name: string; unit: string; unit_display: string; unit_amount: string; description: string;
  current_price: number; max_discount_percent: number; min_allowed_price: number; price_changed_at: string | null;
  is_active: boolean; offers_count: number; stale_count: number; image: string | null;
  pending_price: { id: number; price: number; created_at: string; note: string } | null;
};

const UNITS = [["kg", "کیلوگرم"], ["g", "گرم"], ["piece", "عدد"], ["pack", "بسته"], ["l", "لیتر"], ["carton", "کارتن"]];

export default function Products() {
  const { user } = useAuth();
  // اتحادیه، اداره صمت، اتاق اصناف و مدیر کل می‌توانند کالا تعریف و نرخ‌گذاری کنند
  const canEdit = ["union", "samt", "chamber", "admin"].includes(user!.role);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<ProductT | "new" | null>(null);
  const [pricing, setPricing] = useState<ProductT | null>(null);
  const q = useQuery({ queryKey: ["products-panel", search, page], queryFn: () => api.get<Page<ProductT>>("/products/", { search, page, is_active: true }) });
  return (
    <div className="space-y-4">
      <PageHeader
        title="کالاها و نرخ مصوب"
        subtitle={
          user!.role === "union"
            ? "نرخی که ثبت می‌کنید پس از تایید اتاق اصناف اعمال می‌شود."
            : canEdit
              ? "تعریف کالا برای هر اتحادیه و نرخ‌گذاری؛ نرخ شما بی‌درنگ اعمال می‌شود."
              : undefined
        }
        actions={<>
          <Button variant="secondary" size="sm" icon={<Download className="size-4" />} onClick={() => download("/analytics/export/prices/", "prices.xlsx")}>اکسل</Button>
          {canEdit && <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>کالای جدید</Button>}
        </>}
      />
      <div className="relative sm:w-72">
        <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
        <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="جستجوی کالا" className="pr-9" />
      </div>
      <Card>
        {q.isLoading ? <Loading /> : !q.data?.results.length ? <Empty title="کالایی تعریف نشده است" /> : (
          <DataTable
            rows={q.data.results}
            onRowClick={canEdit ? setPricing : undefined}
            columns={[
              { key: "name", label: "کالا", render: (p) => (
                <div className="flex items-center gap-2.5">
                  {p.image
                    ? <img src={p.image} alt="" className="size-10 shrink-0 rounded-lg object-cover" />
                    : <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-surface-2 text-sm font-bold text-muted">{p.name.slice(0, 1)}</span>}
                  <div className="min-w-0"><div className="truncate font-medium">{p.name}</div><div className="truncate text-xs text-muted">{p.union_name} · {p.unit_display}</div></div>
                </div>
              ) },
              { key: "current_price", label: "نرخ مصوب", render: (p) => (
                <div>
                  <b className="tabular">{toman(p.current_price)}</b>
                  {p.pending_price && (
                    <div className="mt-0.5 whitespace-nowrap text-[11px] text-warn">
                      {toman(p.pending_price.price)} در انتظار تایید
                    </div>
                  )}
                </div>
              ) },
              { key: "min", label: "حداقل مجاز", render: (p) => <span className="tabular text-muted">{toman(p.min_allowed_price)}</span>, hideOnMobile: true },
              { key: "offers_count", label: "فروشگاه", render: (p) => num(p.offers_count) },
              { key: "stale_count", label: "به‌روزنشده", render: (p) => (p.stale_count ? <Badge tone="warn">{num(p.stale_count)}</Badge> : "—") },
              { key: "price_changed_at", label: "آخرین تغییر", render: (p) => ago(p.price_changed_at) },
              ...(canEdit ? [{ key: "edit", label: "", render: (p: ProductT) => <button onClick={(e) => { e.stopPropagation(); setEditing(p); }} className="text-muted hover:text-ink" aria-label="ویرایش"><Pencil className="size-4" /></button> }] : []),
            ]}
          />
        )}
      </Card>
      {q.data && q.data.count > 20 && (
        <div className="flex justify-center gap-2">
          <Button size="sm" variant="secondary" disabled={!q.data.previous} onClick={() => setPage(page - 1)}>قبلی</Button>
          <Button size="sm" variant="secondary" disabled={!q.data.next} onClick={() => setPage(page + 1)}>بعدی</Button>
        </div>
      )}
      {editing && <ProductForm product={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {pricing && <PriceSheet product={pricing} onClose={() => setPricing(null)} />}
    </div>
  );
}

function ProductForm({ product, onClose }: { product: ProductT | null; onClose: () => void }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const cats = useQuery({ queryKey: ["categories"], queryFn: () => api.get<{ id: number; name: string }[]>("/categories/") });
  const coms = useQuery({ queryKey: ["commodities"], queryFn: () => api.get<{ id: number; name: string }[]>("/commodities/") });
  // اتحادیه را فقط نقش‌های بالادستی انتخاب/تغییر می‌دهند؛ اتحادیه کالا را زیر نام خودش می‌سازد
  const canPickUnion = user!.role !== "union";
  const unions = useQuery({
    queryKey: ["unions-all"],
    queryFn: () => api.get<Page<{ id: number; name: string; county_name?: string }>>("/unions/", { page_size: 300 }),
    enabled: canPickUnion,
  });
  const [f, setF] = useState({
    name: product?.name ?? "", unit: product?.unit ?? "kg", unit_amount: product?.unit_amount ?? "1", category: product?.category ?? "",
    commodity: product?.commodity ?? "", description: product?.description ?? "", max_discount_percent: product?.max_discount_percent ?? 20,
    union: product?.union ?? "", initial_price: "",
  });
  const [image, setImage] = useState<File | null | undefined>(undefined);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const m = useMutation({
    mutationFn: () => {
      const body: any = { ...f, category: f.category || null, commodity: f.commodity || null };
      if (f.initial_price) body.initial_price = toRial(f.initial_price);
      else delete body.initial_price;
      if (!body.union) delete body.union;
      // با تصویر باید multipart بفرستیم؛ بدون تغییر تصویر، JSON ساده کافی است
      if (image !== undefined) {
        const fd = new FormData();
        for (const [k, v] of Object.entries(body)) if (v !== null && v !== "") fd.set(k, String(v));
        fd.set("image", image ?? "");
        return product ? api.patch(`/products/${product.id}/`, fd) : api.post("/products/", fd);
      }
      return product ? api.patch(`/products/${product.id}/`, body) : api.post("/products/", body);
    },
    onSuccess: () => { toast("ذخیره شد"); qc.invalidateQueries({ queryKey: ["products-panel"] }); onClose(); },
  });
  const err = fieldErrors(m.error);
  return (
    <Sheet open onClose={onClose} title={product ? "ویرایش کالا" : "تعریف کالای جدید"} footer={<Button className="w-full" loading={m.isPending} onClick={() => m.mutate()}>ذخیره</Button>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="تصویر کالا" error={err.image} className="sm:col-span-2">
          <div className="max-w-40">
            <ImageUpload value={product?.image} onChange={setImage} hint="مربعی و کوچک؛ خودکار فشرده می‌شود." />
          </div>
        </Field>
        <Field label="نام کالا" error={err.name} className="sm:col-span-2"><Input value={f.name} onChange={set("name")} /></Field>
        {canPickUnion && (
          <Field
            label="اتحادیه"
            error={err.union}
            className="sm:col-span-2"
            hint={product ? "با تغییر اتحادیه، این کالا به اتحادیه دیگری منتقل می‌شود." : "کالا زیر این اتحادیه تعریف می‌شود."}
          >
            <Select value={String(f.union)} onChange={set("union")}>
              <option value="">— انتخاب اتحادیه —</option>
              {unions.data?.results.map((u) => (
                <option key={u.id} value={u.id}>{u.name}{u.county_name ? ` (${u.county_name})` : ""}</option>
              ))}
            </Select>
          </Field>
        )}
        <Field label="واحد"><Select value={f.unit} onChange={set("unit")}>{UNITS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
        <Field label="مقدار واحد" hint="مثلا ۱۰ برای کیسه ۱۰ کیلویی"><Input value={f.unit_amount} onChange={set("unit_amount")} inputMode="decimal" dir="ltr" /></Field>
        <Field label="دسته"><Select value={String(f.category)} onChange={set("category")}><option value="">—</option>{cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Field label="کالای اساسی مرتبط" hint="برای رصدخانه و سبد خانوار"><Select value={String(f.commodity)} onChange={set("commodity")}><option value="">—</option>{coms.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Field label="حداکثر تخفیف مجاز فروشگاه (٪)" error={err.max_discount_percent}><Input type="number" value={f.max_discount_percent} onChange={set("max_discount_percent")} min={0} max={90} dir="ltr" /></Field>
        {!product && <Field label="نرخ مصوب اولیه"><PriceInput value={f.initial_price} onChange={(v) => setF({ ...f, initial_price: v })} /></Field>}
        <Field label="توضیحات" className="sm:col-span-2"><Textarea value={f.description} onChange={set("description")} className="min-h-16" /></Field>
      </div>
      {m.error && !Object.keys(err).length && <p className="mt-3 text-sm text-danger">{(m.error as Error).message}</p>}
    </Sheet>
  );
}

function PriceSheet({ product, onClose }: { product: ProductT; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { user } = useAuth();
  // نرخ اتحادیه نیاز به تایید اتاق اصناف دارد؛ صمت و بالاتر بی‌درنگ اعمال می‌شود
  const needsApproval = user!.role === "union";
  const [price, setPrice] = useState(String(toToman(product.current_price) || ""));
  const [discount, setDiscount] = useState(String(product.max_discount_percent));
  const [note, setNote] = useState("");
  const history = useQuery({ queryKey: ["history", product.id], queryFn: () => api.get<{ price: number; previous_price: number; note: string; set_by_name: string; created_at: string }[]>(`/products/${product.id}/history/`) });
  const offers = useQuery({ queryKey: ["p-offers", product.id], queryFn: () => api.get<any[]>(`/products/${product.id}/offers/`) });
  const m = useMutation({
    mutationFn: () => api.post(`/products/${product.id}/set_price/`, { price: toRial(price), max_discount_percent: +discount, note }),
    onSuccess: () => {
      toast(needsApproval ? "نرخ ثبت شد و برای تایید اتاق اصناف ارسال گردید" : "نرخ جدید ثبت و به فروشگاه‌ها اعلان شد");
      qc.invalidateQueries({ queryKey: ["products-panel"] });
      onClose();
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const newRial = price ? toRial(price) : 0;
  const change = product.current_price && newRial ? ((newRial - product.current_price) / product.current_price) * 100 : 0;
  return (
    <Sheet open onClose={onClose} title={`نرخ‌گذاری: ${product.name}`} wide footer={<Button className="w-full" loading={m.isPending} disabled={!newRial} onClick={() => m.mutate()}>{needsApproval ? "ارسال برای تایید" : "ثبت نرخ مصوب"}</Button>}>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="نرخ مصوب جدید" hint={change ? <span className={change > 0 ? "text-danger" : "text-ok"}>{change > 0 ? "افزایش" : "کاهش"} {num(Math.abs(change), 1)}٪</span> : `فعلی: ${toman(product.current_price)}`}>
          <PriceInput value={price} onChange={setPrice} />
        </Field>
        <Field label="حداکثر تخفیف (٪)" hint={newRial ? `حداقل: ${toman(Math.ceil(newRial * (100 - +discount) / 100))}` : undefined}>
          <Input type="number" value={discount} onChange={(e) => setDiscount(e.target.value)} dir="ltr" min={0} max={90} />
        </Field>
        <Field label="توضیح (اختیاری)"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="مثلا افزایش نرخ حمل" /></Field>
      </div>
      {needsApproval ? (
        <p className="mt-3 rounded-xl bg-brand-soft p-3 text-xs leading-6 text-brand">
          نرخی که ثبت می‌کنید پس از <b>تایید اتاق اصناف</b> روی سایت اعمال می‌شود.
          {product.pending_price && ` در حال حاضر نرخ ${toman(product.pending_price.price)} در انتظار تایید است و با ثبت نرخ جدید جایگزین می‌شود.`}
        </p>
      ) : (
        change !== 0 && <p className="mt-3 rounded-xl bg-warn-soft p-3 text-xs text-warn">{num(product.offers_count)} فروشگاه اعلان دریافت می‌کنند و باید ظرف ۲۴ ساعت قیمت خود را به‌روز کنند.</p>
      )}
      {(history.data?.length ?? 0) > 1 && (
        <div className="mt-5">
          <h3 className="mb-1 flex items-center gap-1 text-sm font-semibold"><TrendingUp className="size-4" /> روند نرخ</h3>
          <Sparkline values={[...history.data!].reverse().map((h) => h.price)} />
        </div>
      )}
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-semibold">تاریخچه</h3>
          <div className="max-h-56 divide-y divide-line overflow-y-auto text-sm">
            {history.data?.map((h, i) => (
              <div key={i} className="flex justify-between py-2">
                <span>{toman(h.price)} {h.note && <span className="text-xs text-muted">· {h.note}</span>}</span>
                <span className="text-xs text-muted">{dateTime(h.created_at)}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h3 className="mb-2 text-sm font-semibold">قیمت فروشگاه‌ها</h3>
          <div className="max-h-56 divide-y divide-line overflow-y-auto text-sm">
            {offers.data?.map((o) => (
              <div key={o.store} className="flex justify-between py-2">
                <span>{o.store_name} {o.is_stale && <Badge tone="warn">به‌روزنشده</Badge>}</span>
                <span className="tabular">{toman(o.price)}</span>
              </div>
            ))}
            {!offers.data?.length && <p className="py-2 text-muted">هنوز قیمتی ثبت نشده</p>}
          </div>
        </div>
      </div>
    </Sheet>
  );
}
