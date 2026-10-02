import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles, Truck } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, DataTable, Empty, Field, Input, Loading, PageHeader, Sheet, STATUS_TONE, useToast } from "../../components/ui";
import { api, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, num, toman } from "../../lib/format";

export default function Quotas() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const isUnion = user!.role === "union" || user!.role === "admin";
  const shares = useQuery({ queryKey: ["shares"], queryFn: () => api.get<Page<any>>("/shares/"), enabled: isUnion });
  const quotas = useQuery({ queryKey: ["quotas"], queryFn: () => api.get<Page<any>>("/quotas/", { page_size: 100 }) });
  const [splitting, setSplitting] = useState<any>(null);
  const [acting, setActing] = useState<any>(null);
  const advance = useMutation({
    mutationFn: ({ id, ...body }: any) => api.post(`/quotas/${id}/advance/`, body),
    onSuccess: () => { toast("ثبت شد"); qc.invalidateQueries({ queryKey: ["quotas"] }); qc.invalidateQueries({ queryKey: ["shares"] }); setActing(null); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <div className="space-y-5">
      <PageHeader title={isUnion ? "سهمیه و توزیع" : "سهمیه‌های فروشگاه"} subtitle="رهگیری کالای تنظیم بازار از تخصیص تا تحویل و فروش" />
      {isUnion && (
        <section>
          <h2 className="mb-2 font-semibold">سهم اتحادیه از تخصیص‌ها</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {shares.data?.results.map((s) => (
              <Card key={s.id} className="p-4">
                <div className="flex justify-between gap-2">
                  <div>
                    <div className="font-medium">{s.commodity_name}</div>
                    <div className="text-xs text-muted">{s.allocation_title}</div>
                  </div>
                  <Badge tone={s.allocation_status === "active" ? "ok" : "neutral"}>{s.allocation_status === "active" ? "در حال توزیع" : s.allocation_status}</Badge>
                </div>
                <Progress total={s.quantity} a={s.assigned} b={s.received} unit={s.unit} />
                <div className="mt-2 text-xs text-muted">سقف قیمت مصرف‌کننده: {toman(s.consumer_price)} / {s.unit}</div>
                {s.allocation_status === "active" && s.assigned < s.quantity && (
                  <Button size="sm" className="mt-3" icon={<Truck className="size-4" />} onClick={() => setSplitting(s)}>تقسیم بین فروشگاه‌ها</Button>
                )}
              </Card>
            ))}
            {shares.data && !shares.data.results.length && <Card className="md:col-span-2"><Empty title="سهمی به اتحادیه تخصیص داده نشده است" /></Card>}
          </div>
        </section>
      )}
      <section>
        <h2 className="mb-2 font-semibold">سهمیه‌ها</h2>
        <Card>
          {quotas.isLoading ? <Loading /> : !quotas.data?.results.length ? <Empty title="سهمیه‌ای ثبت نشده است" /> : (
            <DataTable
              rows={quotas.data.results}
              onRowClick={setActing}
              columns={[
                { key: "commodity_name", label: "کالا", render: (q) => <div><div className="font-medium">{q.commodity_name}</div><div className="text-xs text-muted" dir="ltr">{q.tracking_code}</div></div> },
                { key: "store_name", label: "فروشگاه" },
                { key: "quantity", label: "سهمیه", render: (q) => `${num(q.quantity)} ${q.unit}` },
                { key: "received_quantity", label: "تحویل", render: (q) => (q.received_quantity != null ? num(q.received_quantity) : "—") },
                { key: "sold_quantity", label: "فروش", render: (q) => num(q.sold_quantity) },
                { key: "status", label: "وضعیت", render: (q) => <Badge tone={STATUS_TONE[q.status]}>{q.status_display}</Badge> },
              ]}
            />
          )}
        </Card>
      </section>
      {splitting && <SplitSheet share={splitting} onClose={() => setSplitting(null)} />}
      {acting && <QuotaSheet q={acting} role={user!.role} onClose={() => setActing(null)} onAct={(body) => advance.mutate({ id: acting.id, ...body })} busy={advance.isPending} />}
    </div>
  );
}

function Progress({ total, a, b, unit }: { total: number; a: number; b: number; unit: string }) {
  const w = (v: number) => `${Math.min(100, (v / (+total || 1)) * 100)}%`;
  return (
    <div className="mt-3">
      <div className="relative h-2 overflow-hidden rounded-full bg-surface-2">
        <div className="absolute inset-y-0 right-0 rounded-full bg-brand/35" style={{ width: w(a) }} />
        <div className="absolute inset-y-0 right-0 rounded-full bg-brand" style={{ width: w(b) }} />
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-muted">
        <span>تحویل {num(b)} · تقسیم {num(a)}</span>
        <span>از {num(total)} {unit}</span>
      </div>
    </div>
  );
}

function SplitSheet({ share, onClose }: { share: any; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const sug = useQuery({ queryKey: ["suggest", share.id], queryFn: () => api.get<{ store: number; store_name: string; quantity: number }[]>(`/shares/${share.id}/suggest/`) });
  const [vals, setVals] = useState<Record<number, string>>({});
  const [carrier, setCarrier] = useState("");
  const remaining = share.quantity - share.assigned;
  const total = Object.values(vals).reduce((s, v) => s + (+v || 0), 0);
  const m = useMutation({
    mutationFn: () => api.post(`/shares/${share.id}/assign/`, { items: Object.entries(vals).filter(([, v]) => +v > 0).map(([store, quantity]) => ({ store: +store, quantity: +quantity, carrier })) }),
    onSuccess: () => { toast("سهمیه‌ها تخصیص یافت"); qc.invalidateQueries({ queryKey: ["quotas"] }); qc.invalidateQueries({ queryKey: ["shares"] }); onClose(); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const applySuggestion = () => {
    const ratio = remaining / (share.quantity || 1);
    setVals(Object.fromEntries((sug.data ?? []).map((s) => [s.store, String(Math.floor(s.quantity * ratio))])));
  };
  return (
    <Sheet open onClose={onClose} title={`تقسیم ${share.commodity_name}`} footer={<Button className="w-full" loading={m.isPending} disabled={!total || total > remaining} onClick={() => m.mutate()}>تخصیص {num(total)} {share.unit}</Button>}>
      <div className="mb-3 flex items-center justify-between text-sm">
        <span>باقی‌مانده قابل تقسیم: <b>{num(remaining)} {share.unit}</b></span>
        <Button size="sm" variant="soft" icon={<Sparkles className="size-4" />} onClick={applySuggestion}>پیشنهاد هوشمند</Button>
      </div>
      <p className="mb-3 text-xs text-muted">پیشنهاد بر اساس فروشگاه‌های فعال و امتیاز مشتریان محاسبه می‌شود.</p>
      <div className="space-y-2">
        {sug.data?.map((s) => (
          <div key={s.store} className="flex items-center gap-3">
            <span className="flex-1 text-sm">{s.store_name}</span>
            <Input className="w-32 text-left" dir="ltr" inputMode="decimal" value={vals[s.store] ?? ""} onChange={(e) => setVals({ ...vals, [s.store]: e.target.value })} />
          </div>
        ))}
      </div>
      <Field label="حمل‌کننده/پخش" className="mt-4"><Input value={carrier} onChange={(e) => setCarrier(e.target.value)} /></Field>
      {total > remaining && <p className="mt-2 text-xs text-danger">مجموع از باقی‌مانده بیشتر است.</p>}
    </Sheet>
  );
}

function QuotaSheet({ q, role, onClose, onAct, busy }: { q: any; role: string; onClose: () => void; onAct: (b: object) => void; busy: boolean }) {
  const [received, setReceived] = useState(String(q.quantity));
  const [sold, setSold] = useState(String(q.sold_quantity));
  const isStore = role === "store" || role === "admin";
  const isUnion = role === "union" || role === "admin";
  return (
    <Sheet open onClose={onClose} title={`سهمیه ${q.tracking_code}`}>
      <div className="text-sm">{q.commodity_name} — {q.store_name}</div>
      <div className="mt-1 text-xs text-muted">سهمیه {num(q.quantity)} {q.unit} · سقف قیمت فروش {toman(q.consumer_price)}</div>
      <div className="mt-4 space-y-3">
        {isUnion && q.status === "assigned" && <Button className="w-full" loading={busy} onClick={() => onAct({ status: "dispatched" })}>ثبت ارسال محموله</Button>}
        {isUnion && ["assigned", "dispatched"].includes(q.status) && <Button variant="secondary" className="w-full" onClick={() => onAct({ status: "canceled", note: "لغو توسط اتحادیه" })}>لغو سهمیه</Button>}
        {isStore && q.status === "dispatched" && (
          <div className="flex items-end gap-2">
            <Field label="مقدار تحویل‌گرفته" className="flex-1"><Input value={received} onChange={(e) => setReceived(e.target.value)} dir="ltr" inputMode="decimal" /></Field>
            <Button loading={busy} onClick={() => onAct({ status: "received", received_quantity: +received })}>تایید تحویل</Button>
          </div>
        )}
        {isStore && q.status === "received" && (
          <>
            <div className="flex items-end gap-2">
              <Field label={`مقدار فروخته‌شده (از ${num(q.received_quantity)})`} className="flex-1"><Input value={sold} onChange={(e) => setSold(e.target.value)} dir="ltr" inputMode="decimal" /></Field>
              <Button loading={busy} onClick={() => onAct({ status: "received", sold_quantity: +sold })}>ثبت فروش</Button>
            </div>
            <Button variant="secondary" className="w-full" onClick={() => onAct({ status: "sold_out" })}>اتمام موجودی</Button>
          </>
        )}
      </div>
      <ol className="mt-5 space-y-3 border-r-2 border-line pr-4">
        {q.events.map((e: any, i: number) => (
          <li key={i} className="relative">
            <span className="absolute -right-[23px] top-1.5 size-3 rounded-full border-2 border-surface bg-brand" />
            <div className="text-sm font-medium">{e.status_display}</div>
            {e.note && <div className="text-sm text-muted">{e.note}</div>}
            <div className="text-[11px] text-muted">{dateTime(e.created_at)}</div>
          </li>
        ))}
      </ol>
    </Sheet>
  );
}
