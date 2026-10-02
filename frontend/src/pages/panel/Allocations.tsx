import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Field, Input, Loading, PageHeader, PriceInput, Select, Sheet, STATUS_TONE, Textarea, useToast } from "../../components/ui";
import { api, fieldErrors, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { date, num, pct, toman, toRial } from "../../lib/format";

export default function Allocations() {
  const { user } = useAuth();
  const canEdit = user!.role === "governorate" || user!.role === "admin";
  const q = useQuery({ queryKey: ["allocations"], queryFn: () => api.get<Page<any>>("/allocations/") });
  const [creating, setCreating] = useState(false);
  const [sharing, setSharing] = useState<any>(null);
  return (
    <div className="space-y-4">
      <PageHeader
        title="تخصیص و توزیع کالای تنظیم بازار"
        subtitle="تخصیص استانی ← سهم اتحادیه ← سهمیه فروشگاه، با رهگیری تحویل و سنجش کسری"
        actions={canEdit && <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>تخصیص جدید</Button>}
      />
      {q.isLoading ? <Loading /> : !q.data?.results.length ? <Card><Empty title="تخصیصی ثبت نشده است" /></Card> : (
        <div className="grid gap-3 lg:grid-cols-2">
          {q.data.results.map((a) => (
            <Card key={a.id} className="p-4">
              <div className="flex justify-between gap-2">
                <div>
                  <div className="font-semibold">{a.title}</div>
                  <div className="text-xs text-muted">{a.commodity_name} · {a.province_name} · از {date(a.starts_on)} · {a.supplier}</div>
                </div>
                <Badge tone={STATUS_TONE[a.status]}>{a.status_display}</Badge>
              </div>
              <div className="mt-3 grid grid-cols-4 gap-2 text-center text-xs">
                {[["کل", a.progress.total], ["سهم اتحادیه‌ها", a.progress.shared], ["تحویل", a.progress.received], ["فروش", a.progress.sold]].map(([l, v]) => (
                  <div key={l as string} className="rounded-xl bg-surface-2 py-2"><div className="text-muted">{l}</div><div className="mt-0.5 font-semibold tabular">{num(v as number)}</div></div>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap justify-between gap-2 text-xs text-muted">
                <span>قیمت تخصیص {toman(a.allocation_price)} · سقف مصرف‌کننده {toman(a.consumer_price)} ({pct(a.progress.price_gap_percent)})</span>
                {a.progress.gap > 0 && <span className="text-danger">کسری تحویل: {num(a.progress.gap)} {a.unit}</span>}
              </div>
              {!!a.shares.length && (
                <div className="mt-3 divide-y divide-line rounded-xl border border-line text-sm">
                  {a.shares.map((s: any) => (
                    <div key={s.id} className="flex justify-between px-3 py-2">
                      <span>{s.union_name}</span>
                      <span className="tabular text-muted">{num(s.assigned)} / {num(s.quantity)} {a.unit}</span>
                    </div>
                  ))}
                </div>
              )}
              {canEdit && a.status !== "closed" && (
                <div className="mt-3 flex gap-2">
                  <Button size="sm" variant="soft" onClick={() => setSharing(a)}>تعیین سهم اتحادیه</Button>
                  <StatusButton a={a} />
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
      {creating && <CreateSheet onClose={() => setCreating(false)} />}
      {sharing && <ShareSheet a={sharing} onClose={() => setSharing(null)} />}
    </div>
  );
}

function StatusButton({ a }: { a: any }) {
  const qc = useQueryClient();
  const next = a.status === "draft" ? ["active", "شروع توزیع"] : ["closed", "بستن تخصیص"];
  const m = useMutation({ mutationFn: () => api.patch(`/allocations/${a.id}/`, { status: next[0] }), onSuccess: () => qc.invalidateQueries({ queryKey: ["allocations"] }) });
  return <Button size="sm" variant="secondary" loading={m.isPending} onClick={() => m.mutate()}>{next[1]}</Button>;
}

function CreateSheet({ onClose }: { onClose: () => void }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const coms = useQuery({ queryKey: ["commodities"], queryFn: () => api.get<any[]>("/commodities/") });
  const provs = useQuery({ queryKey: ["provinces"], queryFn: () => api.get<Page<any>>("/provinces/"), enabled: user!.role === "admin" });
  const [f, setF] = useState({ title: "", commodity: "", province: "", supplier: "", total_quantity: "", unit: "کیلوگرم", allocation_price: "", consumer_price: "", starts_on: new Date().toISOString().slice(0, 10), note: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const m = useMutation({
    mutationFn: () => api.post("/allocations/", { ...f, province: f.province || undefined, allocation_price: toRial(f.allocation_price || 0), consumer_price: toRial(f.consumer_price || 0) }),
    onSuccess: () => { toast("تخصیص ثبت شد"); qc.invalidateQueries({ queryKey: ["allocations"] }); onClose(); },
  });
  const err = fieldErrors(m.error);
  return (
    <Sheet open onClose={onClose} title="تخصیص جدید" footer={<Button className="w-full" loading={m.isPending} onClick={() => m.mutate()}>ثبت</Button>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="عنوان" error={err.title} className="sm:col-span-2"><Input value={f.title} onChange={set("title")} placeholder="مثلا توزیع برنج تنظیم بازار آبان" /></Field>
        <Field label="کالا" error={err.commodity}><Select value={f.commodity} onChange={set("commodity")}><option value="">—</option>{coms.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        {user!.role === "admin" && <Field label="استان" error={err.province}><Select value={f.province} onChange={set("province")}><option value="">—</option>{provs.data?.results.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>}
        <Field label="تامین‌کننده/واردکننده"><Input value={f.supplier} onChange={set("supplier")} /></Field>
        <Field label="مقدار کل" error={err.total_quantity}><Input value={f.total_quantity} onChange={set("total_quantity")} dir="ltr" inputMode="decimal" /></Field>
        <Field label="واحد"><Input value={f.unit} onChange={set("unit")} /></Field>
        <Field label="قیمت تخصیص (هر واحد)" error={err.allocation_price}><PriceInput value={f.allocation_price} onChange={(v) => setF({ ...f, allocation_price: v })} /></Field>
        <Field label="سقف قیمت مصرف‌کننده" error={err.consumer_price}><PriceInput value={f.consumer_price} onChange={(v) => setF({ ...f, consumer_price: v })} /></Field>
        <Field label="تاریخ شروع (میلادی)" error={err.starts_on}><Input type="date" value={f.starts_on} onChange={set("starts_on")} dir="ltr" /></Field>
        <Field label="توضیحات" className="sm:col-span-2"><Textarea value={f.note} onChange={set("note")} className="min-h-16" /></Field>
      </div>
    </Sheet>
  );
}

function ShareSheet({ a, onClose }: { a: any; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const unions = useQuery({ queryKey: ["unions-all"], queryFn: () => api.get<Page<any>>("/unions/", { page_size: 200 }) });
  const [union, setUnion] = useState("");
  const [qty, setQty] = useState("");
  const m = useMutation({
    mutationFn: () => api.post(`/allocations/${a.id}/set_share/`, { union, quantity: qty }),
    onSuccess: () => { toast("سهم ثبت شد"); qc.invalidateQueries({ queryKey: ["allocations"] }); onClose(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <Sheet open onClose={onClose} title={`سهم اتحادیه‌ها — ${a.title}`} footer={<Button className="w-full" loading={m.isPending} disabled={!union || !qty} onClick={() => m.mutate()}>ثبت سهم</Button>}>
      <p className="mb-3 text-sm text-muted">تقسیم‌نشده: {num(a.progress.total - a.progress.shared)} {a.unit}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="اتحادیه"><Select value={union} onChange={(e) => setUnion(e.target.value)}><option value="">—</option>{unions.data?.results.map((u) => <option key={u.id} value={u.id}>{u.name} ({u.county_name})</option>)}</Select></Field>
        <Field label={`مقدار (${a.unit})`}><Input value={qty} onChange={(e) => setQty(e.target.value)} dir="ltr" inputMode="decimal" /></Field>
      </div>
    </Sheet>
  );
}
