import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, History, Package, Search, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, Loading, PageHeader, PriceInput, Segmented, Select, Sheet, Stat, Textarea, useToast } from "../../../components/ui";
import { api, download, fieldErrors, type Page } from "../../../lib/api";
import { moneyCompact, toIntRial } from "../../../lib/erp";
import { dateTime, num, toman, toToman } from "../../../lib/format";

type Row = {
  id: number; name: string; brand: string; sku: string; shelf: string; image: string | null; unit_display: string; stock: number | null;
  min_stock: number; cost_price: number; price: number; value: number; sale_value: number; status: string; sold_30d: number; margin: number | null;
};
type Move = { id: number; kind: string; kind_display: string; qty: number; unit_cost: number; balance_after: number; ref: string; note: string; by_name: string; created_at: string; product_name: string };

const STATUS: Record<string, { label: string; tone: "ok" | "warn" | "danger" | "neutral" }> = {
  ok: { label: "موجود", tone: "ok" }, low: { label: "کمبود", tone: "warn" }, out: { label: "ناموجود", tone: "danger" }, unlimited: { label: "نامحدود", tone: "neutral" },
};

/** موجودی انبار: ارزش‌گذاری به قیمت تمام‌شده، هشدار کمبود، تعدیل/انبارگردانی و دفتر حرکت کالا. */
export default function Inventory() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [sel, setSel] = useState<Row | null>(null);
  const list = useQuery({
    queryKey: ["erp-inventory", q, status],
    queryFn: () => api.get<{ results: Row[]; summary: { items: number; cost_value: number; sale_value: number; low: number; out: number } }>("/erp/inventory/", { q, status }),
  });
  const rows = list.data?.results ?? [];
  const sm = list.data?.summary;
  return (
    <div className="space-y-4">
      <PageHeader
        title="موجودی انبار"
        subtitle="موجودی هر کالا، قیمت تمام‌شده، حد سفارش مجدد و تاریخچه کامل ورود و خروج."
        actions={<Button size="sm" variant="secondary" icon={<Download className="size-4" />} onClick={() => download("/erp/export/inventory/", "inventory.csv")}>خروجی اکسل</Button>}
      />
      {sm && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="تعداد کالا" value={num(sm.items)} />
          <Stat label="ارزش انبار (تمام‌شده)" value={moneyCompact(sm.cost_value)} />
          <Stat label="ارزش به قیمت فروش" value={moneyCompact(sm.sale_value)} tone="ok" />
          <Stat label="کمبود / ناموجود" value={`${num(sm.low)} / ${num(sm.out)}`} tone={sm.low + sm.out ? "warn" : "ok"} />
        </div>
      )}
      <div className="flex flex-col gap-2 sm:flex-row">
        <Segmented value={status} onChange={setStatus} options={[{ value: "", label: "همه" }, { value: "low", label: "کمبود" }, { value: "out", label: "ناموجود" }, { value: "ok", label: "موجود" }]} />
        <div className="relative sm:mr-auto sm:w-64">
          <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="جستجوی نام، برند یا کد کالا" className="pr-9" />
        </div>
      </div>
      {list.isLoading ? <Loading /> : list.error ? <ErrorBox error={list.error} /> : !rows.length ? (
        <Card><Empty title="کالایی پیدا نشد" icon={<Package className="size-7" />}>کالاها را از «فروشگاه اینترنتی من» تعریف کنید و با «خرید و تامین‌کنندگان» موجودی بدهید.</Empty></Card>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <Card key={r.id} className="cursor-pointer p-3 hover:border-brand/40" onClick={() => setSel(r)}>
              <div className="flex items-center gap-3">
                {r.image ? <img src={r.image} alt="" className="size-14 shrink-0 rounded-xl bg-surface-2 object-contain" />
                  : <span className="grid size-14 shrink-0 place-items-center rounded-xl bg-surface-2 text-muted"><Package className="size-6" /></span>}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="truncate font-medium">{r.name}</span>
                    <Badge tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Badge>
                  </div>
                  <div className="mt-0.5 truncate text-xs text-muted">{[r.sku && `کد ${r.sku}`, r.shelf && `قفسه ${r.shelf}`, r.brand].filter(Boolean).join(" · ") || "—"}</div>
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted">
                    <span>تمام‌شده: <b className="tabular text-ink">{toman(r.cost_price, false)}</b></span>
                    <span>فروش: <b className="tabular text-ink">{toman(r.price, false)}</b></span>
                    {r.margin != null && <span className={r.margin < 0 ? "text-danger" : "text-ok"}>حاشیه {num(r.margin, 1)}٪</span>}
                    <span>فروش ۳۰ روز: {num(r.sold_30d)}</span>
                  </div>
                </div>
                <div className="shrink-0 text-center">
                  <div className="text-2xl font-bold tabular">{r.stock == null ? "∞" : num(r.stock)}</div>
                  <div className="text-[10px] text-muted">{r.unit_display}</div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
      {sel && <ProductSheet row={sel} onClose={() => setSel(null)} />}
    </div>
  );
}

function ProductSheet({ row, onClose }: { row: Row; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [mode, setMode] = useState<"set" | "delta">("set");
  const [kind, setKind] = useState("adjust");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [f, setF] = useState({ sku: row.sku, shelf: row.shelf, min_stock: String(row.min_stock), cost_price: String(toToman(row.cost_price) ?? 0) });
  const moves = useQuery({ queryKey: ["erp-moves", row.id], queryFn: () => api.get<Page<Move>>("/erp/movements/", { product: row.id, page_size: 30 }) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["erp-inventory"] });
    qc.invalidateQueries({ queryKey: ["erp-moves"] });
    qc.invalidateQueries({ queryKey: ["erp-dash"] });
  };
  const adj = useMutation({
    mutationFn: () => api.post<{ stock: number }>(`/erp/inventory/${row.id}/adjust/`, { mode: kind === "adjust" || kind === "opening" ? mode : "delta", value: Number(value), kind, note }),
    onSuccess: (r) => { toast(`موجودی جدید: ${num(r.stock)}`); setValue(""); setNote(""); refresh(); },
  });
  const save = useMutation({
    mutationFn: () => api.patch(`/erp/inventory/${row.id}/`, { sku: f.sku, shelf: f.shelf, min_stock: Number(f.min_stock || 0), cost_price: toIntRial(f.cost_price) }),
    onSuccess: () => { toast("ذخیره شد"); refresh(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const err = fieldErrors(adj.error);
  const needNote = kind === "damage" || kind === "supplier_return";
  return (
    <Sheet open onClose={onClose} title={row.name} wide>
      <div className="grid grid-cols-3 gap-2 text-center text-sm">
        <div className="rounded-xl bg-surface-2 p-2"><div className="text-xs text-muted">موجودی</div><b className="text-lg tabular">{row.stock == null ? "نامحدود" : num(row.stock)}</b></div>
        <div className="rounded-xl bg-surface-2 p-2"><div className="text-xs text-muted">قیمت تمام‌شده</div><b className="tabular">{toman(row.cost_price, false)}</b></div>
        <div className="rounded-xl bg-surface-2 p-2"><div className="text-xs text-muted">ارزش موجودی</div><b className="tabular">{toman(row.value, false)}</b></div>
      </div>

      <h3 className="mb-2 mt-5 flex items-center gap-1.5 text-sm font-semibold"><SlidersHorizontal className="size-4" /> تعدیل موجودی</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="نوع">
          <Select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="adjust">انبارگردانی / تعدیل</option>
            <option value="opening">موجودی اولیه</option>
            <option value="damage">ضایعات / خرابی (کاهش)</option>
            <option value="supplier_return">برگشت به تامین‌کننده (کاهش)</option>
          </Select>
        </Field>
        {(kind === "adjust" || kind === "opening") && (
          <Field label="روش"><Segmented value={mode} onChange={setMode} options={[{ value: "set", label: "شمارش جدید" }, { value: "delta", label: "افزایش/کاهش" }]} /></Field>
        )}
        <Field label={needNote ? "تعداد کاسته‌شده" : mode === "set" && (kind === "adjust" || kind === "opening") ? "موجودی شمارش‌شده" : "تعداد (منفی = کاهش)"} error={err.value || err.qty}>
          <Input type="number" value={value} onChange={(e) => setValue(e.target.value)} dir="ltr" className="text-left" />
        </Field>
        <Field label={needNote ? "دلیل (الزامی)" : "توضیح (اختیاری)"} error={err.note}><Textarea value={note} onChange={(e) => setNote(e.target.value)} className="min-h-11" /></Field>
      </div>
      {adj.error && !Object.keys(err).length && <p className="mt-2 text-sm text-danger">{(adj.error as Error).message}</p>}
      <Button className="mt-3" loading={adj.isPending} disabled={value === "" || (needNote && !note.trim())} onClick={() => adj.mutate()}>ثبت تعدیل</Button>

      <h3 className="mb-2 mt-6 text-sm font-semibold">مشخصات انبارداری</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="کد کالا / بارکد"><Input value={f.sku} onChange={(e) => setF({ ...f, sku: e.target.value })} dir="ltr" className="text-left" /></Field>
        <Field label="محل قفسه"><Input value={f.shelf} onChange={(e) => setF({ ...f, shelf: e.target.value })} placeholder="مثلا A-3" /></Field>
        <Field label="حد سفارش مجدد" hint="با رسیدن موجودی به این عدد، هشدار کمبود می‌گیرید"><Input type="number" value={f.min_stock} onChange={(e) => setF({ ...f, min_stock: e.target.value })} dir="ltr" className="text-left" /></Field>
        <Field label="قیمت تمام‌شده (دستی)" hint="معمولا خودکار از فاکتور خرید به‌روز می‌شود"><PriceInput value={f.cost_price} onChange={(v) => setF({ ...f, cost_price: v })} /></Field>
      </div>
      <Button className="mt-3" variant="secondary" loading={save.isPending} onClick={() => save.mutate()}>ذخیره مشخصات</Button>

      <h3 className="mb-2 mt-6 flex items-center gap-1.5 text-sm font-semibold"><History className="size-4" /> آخرین حرکت‌ها</h3>
      {moves.isLoading ? <Loading /> : !moves.data?.results.length ? <p className="text-sm text-muted">هنوز حرکتی ثبت نشده.</p> : (
        <div className="divide-y divide-line rounded-xl border border-line text-sm">
          {moves.data.results.map((m) => (
            <div key={m.id} className="flex items-center justify-between gap-2 px-3 py-2">
              <div className="min-w-0"><div>{m.kind_display} {m.ref && <span className="text-xs text-muted" dir="ltr">{m.ref}</span>}</div>
                <div className="truncate text-[11px] text-muted">{m.note} {m.by_name && `· ${m.by_name}`} · {dateTime(m.created_at)}</div></div>
              <div className="shrink-0 text-left tabular"><b className={m.qty > 0 ? "text-ok" : "text-danger"} dir="ltr">{m.qty > 0 ? "+" : ""}{num(m.qty)}</b><div className="text-[11px] text-muted">مانده {num(m.balance_after)}</div></div>
            </div>
          ))}
        </div>
      )}
    </Sheet>
  );
}
