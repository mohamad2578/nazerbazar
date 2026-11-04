import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Printer, Trash2, Truck, Wallet } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Field, Input, Loading, PageHeader, PriceInput, Segmented, Select, Sheet, Stat, Textarea, useToast } from "../../../components/ui";
import { api, fieldErrors, type Page } from "../../../lib/api";
import { moneyCompact, faNum, printPurchaseInvoice, todayIso, toIntRial, type PurchaseData } from "../../../lib/erp";
import { useAuth } from "../../../lib/auth";
import { date, num, toman } from "../../../lib/format";

type Supplier = { id: number; name: string; phone: string; address: string; note: string; is_active: boolean; purchased: number; paid: number; balance: number };
type Purchase = PurchaseData & { supplier: number; created_at: string };
type Product = { id: number; name: string; cost_price: number };

/** خرید از تامین‌کنندگان: ثبت فاکتور خرید (ورود به انبار و به‌روزرسانی قیمت تمام‌شده)، بدهی و پرداخت‌ها. */
export default function Purchases() {
  const [tab, setTab] = useState<"invoices" | "suppliers">("invoices");
  const [adding, setAdding] = useState(false);
  const sup = useQuery({ queryKey: ["erp-suppliers"], queryFn: () => api.get<Supplier[]>("/erp/suppliers/") });
  const totalDebt = (sup.data ?? []).reduce((s, x) => s + Math.max(0, x.balance), 0);
  return (
    <div className="space-y-4">
      <PageHeader
        title="خرید و تامین‌کنندگان"
        subtitle="با ثبت فاکتور خرید، موجودی انبار زیاد و قیمت تمام‌شده (میانگین موزون، با حمل و تخفیف) به‌روز می‌شود."
        actions={<Button size="sm" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>فاکتور خرید جدید</Button>}
      />
      <div className="grid grid-cols-2 gap-3">
        <Stat label="تامین‌کنندگان" value={num(sup.data?.length ?? 0)} icon={<Truck className="size-4" />} />
        <Stat label="مجموع بدهی" value={moneyCompact(totalDebt)} tone={totalDebt ? "warn" : "ok"} icon={<Wallet className="size-4" />} />
      </div>
      <Segmented value={tab} onChange={setTab} options={[{ value: "invoices", label: "فاکتورهای خرید" }, { value: "suppliers", label: "تامین‌کنندگان و بدهی" }]} />
      {tab === "invoices" ? <Invoices /> : <Suppliers />}
      {adding && <PurchaseForm suppliers={sup.data ?? []} onClose={() => setAdding(false)} />}
    </div>
  );
}

function Invoices() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["erp-purchases"], queryFn: () => api.get<Page<Purchase>>("/erp/purchases/", { page_size: 50 }) });
  const toast = useToast();
  if (q.isLoading) return <Loading />;
  const rows = q.data?.results ?? [];
  if (!rows.length) return <Card><Empty title="هنوز فاکتور خریدی ثبت نشده" icon={<Truck className="size-7" />} /></Card>;
  return (
    <div className="space-y-2">
      {rows.map((p) => (
        <Card key={p.id} className="p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="font-medium">{p.supplier_name} <span className="text-xs text-muted" dir="ltr">{p.number}</span></div>
              <div className="mt-0.5 text-xs text-muted">{date(p.date)} · {num(p.items.length)} قلم: {p.items.map((i) => i.product_name).slice(0, 3).join("، ")}{p.items.length > 3 && "…"}</div>
            </div>
            <div className="shrink-0 text-left">
              <b className="tabular">{toman(p.total)}</b>
              <div className="mt-0.5">{p.paid >= p.total ? <Badge tone="ok">تسویه</Badge> : <Badge tone="warn">مانده {toman(p.total - p.paid, false)}</Badge>}</div>
            </div>
          </div>
          <Button className="mt-2" size="sm" variant="secondary" icon={<Printer className="size-4" />}
            onClick={() => printPurchaseInvoice(p, user?.store?.name ?? "") || toast("اجازه باز شدن پنجره جدید را بدهید", "danger")}>چاپ فاکتور</Button>
        </Card>
      ))}
    </div>
  );
}

function Suppliers() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["erp-suppliers"], queryFn: () => api.get<Supplier[]>("/erp/suppliers/") });
  const [editing, setEditing] = useState<Supplier | "new" | null>(null);
  const [paying, setPaying] = useState<Supplier | null>(null);
  const [ledger, setLedger] = useState<Supplier | null>(null);
  if (q.isLoading) return <Loading />;
  return (
    <div className="space-y-2">
      <Button size="sm" variant="secondary" icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>تامین‌کننده جدید</Button>
      {!q.data?.length ? <Card><Empty title="هنوز تامین‌کننده‌ای ثبت نشده" icon={<Truck className="size-7" />} /></Card> : q.data.map((s) => (
        <Card key={s.id} className="p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0"><div className="font-medium">{s.name}</div><div className="text-xs text-muted" dir="ltr" style={{ textAlign: "right" }}>{s.phone}</div></div>
            <div className="shrink-0 text-left"><div className="text-[11px] text-muted">مانده بدهی</div><b className={`tabular ${s.balance > 0 ? "text-warn" : "text-ok"}`}>{toman(s.balance)}</b></div>
          </div>
          <div className="mt-1 text-xs text-muted">خرید کل {toman(s.purchased, false)} · پرداخت‌شده {toman(s.paid, false)}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" disabled={s.balance <= 0} onClick={() => setPaying(s)}>پرداخت به تامین‌کننده</Button>
            <Button size="sm" variant="secondary" onClick={() => setLedger(s)}>صورت‌حساب</Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(s)}>ویرایش</Button>
          </div>
        </Card>
      ))}
      {editing && <SupplierForm supplier={editing === "new" ? null : editing} onClose={() => setEditing(null)} onDone={() => { setEditing(null); qc.invalidateQueries({ queryKey: ["erp-suppliers"] }); }} />}
      {paying && (
        <PaySheet supplier={paying} onClose={() => setPaying(null)} onDone={() => { setPaying(null); toast("پرداخت ثبت شد"); qc.invalidateQueries({ queryKey: ["erp-suppliers"] }); qc.invalidateQueries({ queryKey: ["erp-dash"] }); }} />
      )}
      {ledger && <LedgerSheet supplier={ledger} onClose={() => setLedger(null)} />}
    </div>
  );
}

function SupplierForm({ supplier, onClose, onDone }: { supplier: Supplier | null; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ name: supplier?.name ?? "", phone: supplier?.phone ?? "", address: supplier?.address ?? "", note: supplier?.note ?? "" });
  const m = useMutation({ mutationFn: () => (supplier ? api.patch(`/erp/suppliers/${supplier.id}/`, f) : api.post("/erp/suppliers/", f)), onSuccess: onDone });
  const err = fieldErrors(m.error);
  return (
    <Sheet open onClose={onClose} title={supplier ? "ویرایش تامین‌کننده" : "تامین‌کننده جدید"} footer={<Button className="w-full" loading={m.isPending} disabled={!f.name.trim()} onClick={() => m.mutate()}>ذخیره</Button>}>
      <div className="grid gap-4">
        <Field label="نام" error={err.name}><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="تلفن"><Input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} dir="ltr" className="text-left" /></Field>
        <Field label="نشانی"><Input value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></Field>
        <Field label="یادداشت"><Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
      </div>
    </Sheet>
  );
}

function PaySheet({ supplier, onClose, onDone }: { supplier: Supplier; onClose: () => void; onDone: () => void }) {
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("");
  const [note, setNote] = useState("");
  const m = useMutation({ mutationFn: () => api.post(`/erp/suppliers/${supplier.id}/pay/`, { amount: toIntRial(amount), date: todayIso(), method, note }), onSuccess: onDone });
  const err = fieldErrors(m.error);
  return (
    <Sheet open onClose={onClose} title={`پرداخت به ${supplier.name}`} footer={<Button className="w-full" loading={m.isPending} disabled={!amount} onClick={() => m.mutate()}>ثبت پرداخت</Button>}>
      <p className="mb-3 text-sm text-muted">مانده بدهی: <b className="text-warn">{toman(supplier.balance)}</b></p>
      <div className="grid gap-4">
        <Field label="مبلغ" error={err.amount}><PriceInput value={amount} onChange={setAmount} /></Field>
        <Field label="روش پرداخت"><Input value={method} onChange={(e) => setMethod(e.target.value)} placeholder="نقد، کارت به کارت، چک…" /></Field>
        <Field label="توضیح"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </div>
      <button className="mt-3 text-xs text-brand" onClick={() => setAmount(String(Math.round(supplier.balance / 10)))}>پرداخت کل مانده</button>
    </Sheet>
  );
}

function LedgerSheet({ supplier, onClose }: { supplier: Supplier; onClose: () => void }) {
  const q = useQuery({ queryKey: ["erp-ledger", supplier.id], queryFn: () => api.get<{ rows: { type: string; date: string; amount: number; label: string; balance: number }[]; balance: number }>(`/erp/suppliers/${supplier.id}/ledger/`) });
  return (
    <Sheet open onClose={onClose} title={`صورت‌حساب ${supplier.name}`} wide>
      {q.isLoading ? <Loading /> : (
        <div className="divide-y divide-line rounded-xl border border-line text-sm">
          {q.data!.rows.map((r, i) => (
            <div key={i} className="flex items-center justify-between gap-2 px-3 py-2.5">
              <div className="min-w-0"><div className="truncate">{r.label}</div><div className="text-[11px] text-muted">{date(r.date)}</div></div>
              <div className="shrink-0 text-left tabular"><b className={r.amount > 0 ? "text-warn" : "text-ok"}>{r.amount > 0 ? "+" : "−"}{toman(Math.abs(r.amount), false)}</b><div className="text-[11px] text-muted">مانده {toman(r.balance, false)}</div></div>
            </div>
          ))}
          {!q.data!.rows.length && <p className="p-4 text-center text-muted">گردشی ثبت نشده.</p>}
        </div>
      )}
    </Sheet>
  );
}

type Line = { product: string; qty: string; cost: string };

function PurchaseForm({ suppliers, onClose }: { suppliers: Supplier[]; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const products = useQuery({ queryKey: ["erp-inventory-all"], queryFn: () => api.get<{ results: Product[] }>("/erp/inventory/") });
  const [f, setF] = useState({ supplier: suppliers[0] ? String(suppliers[0].id) : "", date: todayIso(), number: "", note: "", discount: "", tax: "", shipping: "", paid: "" });
  const [lines, setLines] = useState<Line[]>([{ product: "", qty: "1", cost: "" }]);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const setLine = (i: number, patch: Partial<Line>) => setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const goods = lines.reduce((s, l) => s + Number(l.qty || 0) * toIntRial(l.cost), 0);
  const total = goods - toIntRial(f.discount) + toIntRial(f.tax) + toIntRial(f.shipping);
  const valid = f.supplier && lines.length && lines.every((l) => l.product && Number(l.qty) > 0 && toIntRial(l.cost) > 0);
  const m = useMutation({
    mutationFn: () => api.post("/erp/purchases/", {
      supplier: Number(f.supplier), date: f.date, number: f.number, note: f.note, discount: toIntRial(f.discount), tax: toIntRial(f.tax), shipping: toIntRial(f.shipping),
      paid: toIntRial(f.paid), items: lines.map((l) => ({ product: Number(l.product), qty: Number(l.qty), unit_cost: toIntRial(l.cost) })),
    }),
    onSuccess: () => {
      toast("فاکتور خرید ثبت و موجودی انبار به‌روز شد");
      for (const k of ["erp-purchases", "erp-suppliers", "erp-inventory", "erp-dash", "erp-inventory-all"]) qc.invalidateQueries({ queryKey: [k] });
      onClose();
    },
  });
  const err = fieldErrors(m.error);
  return (
    <Sheet open onClose={onClose} title="فاکتور خرید جدید" wide
      footer={<Button className="w-full" loading={m.isPending} disabled={!valid} onClick={() => m.mutate()}>ثبت فاکتور و ورود به انبار ({toman(total)})</Button>}>
      {!suppliers.length ? <p className="rounded-xl bg-warn-soft p-3 text-sm text-warn">ابتدا از تب «تامین‌کنندگان» یک تامین‌کننده ثبت کنید.</p> : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="تامین‌کننده" error={err.supplier}><Select value={f.supplier} onChange={set("supplier")}>{suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></Field>
            <Field label="تاریخ فاکتور"><Input type="date" value={f.date} onChange={set("date")} dir="ltr" /></Field>
            <Field label="شماره فاکتور تامین‌کننده"><Input value={f.number} onChange={set("number")} dir="ltr" className="text-left" /></Field>
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">اقلام</div>
            {lines.map((l, i) => (
              <div key={i} className="grid grid-cols-[1fr_5rem_auto] items-start gap-2 rounded-xl border border-line p-2.5 sm:grid-cols-[1fr_6rem_11rem_auto]">
                <Select value={l.product} onChange={(e) => setLine(i, { product: e.target.value })} className="col-span-3 sm:col-span-1">
                  <option value="">— انتخاب کالا —</option>
                  {products.data?.results.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </Select>
                <Input type="number" min={1} value={l.qty} onChange={(e) => setLine(i, { qty: e.target.value })} dir="ltr" className="text-left" placeholder="تعداد" />
                <PriceInput value={l.cost} onChange={(v) => setLine(i, { cost: v })} placeholder="قیمت خرید واحد" />
                <button type="button" disabled={lines.length === 1} onClick={() => setLines(lines.filter((_, j) => j !== i))} className="grid h-11 place-items-center text-muted hover:text-danger disabled:opacity-30" aria-label="حذف"><Trash2 className="size-4" /></button>
              </div>
            ))}
            {err.items && <p className="text-xs text-danger">{err.items}</p>}
            <Button type="button" size="sm" variant="secondary" icon={<Plus className="size-4" />} onClick={() => setLines([...lines, { product: "", qty: "1", cost: "" }])}>ردیف جدید</Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            <Field label="تخفیف"><PriceInput value={f.discount} onChange={(v) => setF({ ...f, discount: v })} /></Field>
            <Field label="مالیات"><PriceInput value={f.tax} onChange={(v) => setF({ ...f, tax: v })} /></Field>
            <Field label="هزینه حمل" hint="در قیمت تمام‌شده تسهیم می‌شود"><PriceInput value={f.shipping} onChange={(v) => setF({ ...f, shipping: v })} /></Field>
            <Field label="پرداخت‌شده هنگام ثبت" error={err.paid}><PriceInput value={f.paid} onChange={(v) => setF({ ...f, paid: v })} /></Field>
          </div>
          <Field label="توضیح"><Textarea value={f.note} onChange={set("note")} className="min-h-14" /></Field>
          <div className="rounded-xl bg-surface-2 p-3 text-sm">
            <div className="flex justify-between"><span>جمع کالاها</span><b className="tabular">{toman(goods)}</b></div>
            <div className="mt-1 flex justify-between"><span>جمع فاکتور</span><b className="tabular text-brand">{toman(total)}</b></div>
            <div className="mt-1 text-xs text-muted">{faNum(lines.length)} ردیف</div>
          </div>
          {m.error && !Object.keys(err).length && <p className="text-sm text-danger">{(m.error as Error).message}</p>}
        </div>
      )}
    </Sheet>
  );
}
