import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, CheckCircle2, ClipboardCheck, Info, XCircle } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Field, Loading, PageHeader, Segmented, Textarea, useToast } from "../../components/ui";
import { api, type Page } from "../../lib/api";
import { ago, dateTime, num, toman } from "../../lib/format";

type PendingPrice = {
  id: number; product: number; product_name: string; unit_display: string; union_name: string; county_name: string;
  price: number; previous_price: number; current_price: number; max_discount_percent: number; note: string;
  status: string; status_display: string; set_by_name: string; created_at: string;
  review_note: string; reviewed_at: string | null;
};

const TONE: Record<string, "warn" | "ok" | "danger"> = { pending: "warn", approved: "ok", rejected: "danger" };

/** کارتابل تایید نرخ: نرخی که اتحادیه ثبت کرده تا تایید اتاق اصناف اعمال نمی‌شود. */
export default function PriceApprovals() {
  const [status, setStatus] = useState("pending");
  const [open, setOpen] = useState<PendingPrice | null>(null);
  const q = useQuery({
    queryKey: ["pending-prices", status],
    queryFn: () => api.get<Page<PendingPrice>>("/prices/pending/", { status, page_size: 100 }),
    refetchInterval: status === "pending" ? 60_000 : false,
  });
  const rows = q.data?.results ?? [];

  return (
    <div className="space-y-4">
      <PageHeader
        title="تایید نرخ‌های مصوب"
        subtitle="نرخی که اتحادیه ثبت می‌کند تا تایید شما روی سایت اعمال نمی‌شود."
      />
      <Card className="flex items-start gap-2 border-brand/30 bg-brand-soft/60 p-3 text-xs leading-6 text-brand">
        <Info className="mt-0.5 size-4 shrink-0" />
        <span>
          نرخی که اداره صمت یا خود شما ثبت کنید بدون نیاز به تایید، بی‌درنگ اعمال می‌شود.
          با تایید هر نرخ، قیمت همه فروشگاه‌های آن کالا هم‌تراز نرخ جدید می‌شود و فروشگاه‌ها
          ۲۴ ساعت فرصت دارند قیمت خود را تایید یا کم کنند.
        </span>
      </Card>

      <Segmented value={status} onChange={setStatus} options={[
        { value: "pending", label: `در انتظار تایید${rows.length && status === "pending" ? ` (${num(rows.length)})` : ""}` },
        { value: "approved", label: "تاییدشده" },
        { value: "rejected", label: "رد شده" },
      ]} />

      {q.isLoading ? <Loading /> : !rows.length ? (
        <Card><Empty title={status === "pending" ? "نرخی در انتظار تایید نیست" : "موردی نیست"} icon={<ClipboardCheck className="size-7" />} /></Card>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => {
            const base = r.previous_price || r.current_price;
            const change = base ? ((r.price - base) / base) * 100 : null;
            const up = change != null && change > 0;
            return (
              <Card key={r.id} className="p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{r.product_name}</span>
                      <Badge tone={TONE[r.status]}>{r.status_display}</Badge>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {r.union_name} · {r.county_name} · هر {r.unit_display} · ثبت {ago(r.created_at)}
                      {r.set_by_name && ` توسط ${r.set_by_name}`}
                    </div>
                    {r.note && <div className="mt-1 text-xs text-muted">توضیح اتحادیه: {r.note}</div>}
                    {r.review_note && <div className="mt-1 text-xs text-danger">نتیجه بررسی: {r.review_note}</div>}
                  </div>
                  <div className="shrink-0 text-left">
                    <div className="text-xs text-muted">نرخ فعلی {toman(base)}</div>
                    <div className="text-lg font-bold tabular">{toman(r.price)}</div>
                    {change != null && change !== 0 && (
                      <div className={`inline-flex items-center gap-0.5 text-xs ${up ? "text-danger" : "text-ok"}`}>
                        {up ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />}
                        {num(Math.abs(change), 1)}٪
                      </div>
                    )}
                  </div>
                </div>
                {r.status === "pending" && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <ReviewButton record={r} approve />
                    <Button size="sm" variant="secondary" onClick={() => setOpen(r)}>رد کردن</Button>
                  </div>
                )}
                {r.reviewed_at && <div className="mt-2 text-[11px] text-muted">بررسی‌شده در {dateTime(r.reviewed_at)}</div>}
              </Card>
            );
          })}
        </div>
      )}
      {open && <RejectSheet record={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function useReview(onDone?: () => void) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ id, approve, note }: { id: number; approve: boolean; note?: string }) =>
      api.post(`/prices/${id}/review/`, { approve, note }),
    onSuccess: (_d, v) => {
      toast(v.approve ? "نرخ تایید و اعمال شد" : "نرخ رد شد");
      qc.invalidateQueries({ queryKey: ["pending-prices"] });
      qc.invalidateQueries({ queryKey: ["products-panel"] });
      onDone?.();
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
}

function ReviewButton({ record, approve }: { record: PendingPrice; approve: boolean }) {
  const m = useReview();
  return (
    <Button
      size="sm"
      icon={approve ? <CheckCircle2 className="size-4" /> : <XCircle className="size-4" />}
      loading={m.isPending}
      onClick={() => m.mutate({ id: record.id, approve })}
    >
      {approve ? "تایید و اعمال نرخ" : "رد"}
    </Button>
  );
}

function RejectSheet({ record, onClose }: { record: PendingPrice; onClose: () => void }) {
  const [note, setNote] = useState("");
  const m = useReview(onClose);
  return (
    <div className="fixed inset-0 z-[1000] flex items-end justify-center sm:items-center" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <Card className="relative w-full max-w-md rounded-t-3xl p-5 sm:rounded-3xl">
        <h2 className="font-semibold">رد نرخ «{record.product_name}»</h2>
        <p className="mt-1 text-sm text-muted">نرخ پیشنهادی {toman(record.price)} از {record.union_name}</p>
        <Field label="دلیل رد (برای اتحادیه ارسال می‌شود)" className="mt-4">
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} className="min-h-20" />
        </Field>
        <div className="mt-4 flex gap-2">
          <Button variant="danger" disabled={!note.trim()} loading={m.isPending} onClick={() => m.mutate({ id: record.id, approve: false, note })}>
            رد نرخ
          </Button>
          <Button variant="secondary" onClick={onClose}>انصراف</Button>
        </div>
      </Card>
    </div>
  );
}
