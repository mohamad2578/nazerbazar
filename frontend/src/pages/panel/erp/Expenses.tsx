import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Plus, Receipt, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Field, Input, Loading, PageHeader, PriceInput, Select, Sheet, Stat, useToast } from "../../../components/ui";
import { api, download, fieldErrors, type Page } from "../../../lib/api";
import { isoDaysAgo, todayIso, toIntRial } from "../../../lib/erp";
import { date, toman } from "../../../lib/format";

type Expense = { id: number; category: string; category_display: string; amount: number; date: string; note: string };
const CATS: [string, string][] = [["rent", "اجاره"], ["salary", "حقوق و دستمزد"], ["packaging", "بسته‌بندی"], ["transport", "حمل و نقل"], ["marketing", "تبلیغات"], ["utility", "قبوض و انرژی"], ["other", "سایر"]];

/** هزینه‌های جاری فروشگاه؛ در محاسبه سود خالص گزارش‌ها کسر می‌شود. */
export default function Expenses() {
  const qc = useQueryClient();
  const toast = useToast();
  const [from, setFrom] = useState(isoDaysAgo(29));
  const [to, setTo] = useState(todayIso());
  const [cat, setCat] = useState("");
  const [adding, setAdding] = useState(false);
  const q = useQuery({ queryKey: ["erp-expenses", from, to, cat], queryFn: () => api.get<Page<Expense> & { total: number }>("/erp/expenses/", { from, to, category: cat, page_size: 100 }) });
  const del = useMutation({
    mutationFn: (id: number) => api.del(`/erp/expenses/${id}/`),
    onSuccess: () => { toast("حذف شد"); qc.invalidateQueries({ queryKey: ["erp-expenses"] }); qc.invalidateQueries({ queryKey: ["erp-dash"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <div className="space-y-4">
      <PageHeader title="هزینه‌ها" subtitle="اجاره، حقوق، بسته‌بندی و سایر هزینه‌های جاری؛ از سود ناخالص کسر می‌شود."
        actions={<>
          <Button size="sm" variant="secondary" icon={<Download className="size-4" />} onClick={() => download(`/erp/export/expenses/?from=${from}&to=${to}`, "expenses.csv")}>اکسل</Button>
          <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>هزینه جدید</Button>
        </>} />
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="از تاریخ"><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} dir="ltr" /></Field>
        <Field label="تا تاریخ"><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} dir="ltr" /></Field>
        <Field label="دسته"><Select value={cat} onChange={(e) => setCat(e.target.value)}><option value="">همه</option>{CATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
        <Stat label="جمع هزینه‌ها" value={toman(q.data?.total ?? 0)} icon={<Receipt className="size-4" />} />
      </div>
      {q.isLoading ? <Loading /> : !q.data?.results.length ? <Card><Empty title="هزینه‌ای در این بازه ثبت نشده" icon={<Receipt className="size-7" />} /></Card> : (
        <Card className="divide-y divide-line">
          {q.data.results.map((e) => (
            <div key={e.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
              <div className="min-w-0"><div className="flex items-center gap-2"><Badge>{e.category_display}</Badge><span className="truncate">{e.note || "—"}</span></div><div className="mt-0.5 text-xs text-muted">{date(e.date)}</div></div>
              <div className="flex shrink-0 items-center gap-3"><b className="tabular">{toman(e.amount)}</b>
                <button onClick={() => confirm("این هزینه حذف شود؟") && del.mutate(e.id)} className="text-muted hover:text-danger" aria-label="حذف"><Trash2 className="size-4" /></button></div>
            </div>
          ))}
        </Card>
      )}
      {adding && <ExpenseForm onClose={() => setAdding(false)} onDone={() => { setAdding(false); qc.invalidateQueries({ queryKey: ["erp-expenses"] }); qc.invalidateQueries({ queryKey: ["erp-dash"] }); }} />}
    </div>
  );
}

function ExpenseForm({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ category: "other", amount: "", date: todayIso(), note: "" });
  const m = useMutation({ mutationFn: () => api.post("/erp/expenses/", { ...f, amount: toIntRial(f.amount) }), onSuccess: () => { toast("هزینه ثبت شد"); onDone(); } });
  const err = fieldErrors(m.error);
  return (
    <Sheet open onClose={onClose} title="ثبت هزینه" footer={<Button className="w-full" loading={m.isPending} disabled={!f.amount} onClick={() => m.mutate()}>ثبت</Button>}>
      <div className="grid gap-4">
        <Field label="دسته"><Select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{CATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
        <Field label="مبلغ" error={err.amount}><PriceInput value={f.amount} onChange={(v) => setF({ ...f, amount: v })} /></Field>
        <Field label="تاریخ" error={err.date}><Input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} dir="ltr" /></Field>
        <Field label="شرح"><Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="مثلا اجاره انبار آبان" /></Field>
      </div>
    </Sheet>
  );
}
