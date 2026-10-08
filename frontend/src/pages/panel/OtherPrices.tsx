import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Info, PackageSearch, Search, Store as StoreIcon } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Field, Input, Loading, PageHeader, Segmented, Textarea, useToast } from "../../components/ui";
import { api, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { ago, dateTime, num, toman } from "../../lib/format";

type OtherProduct = {
  id: number; name: string; brand: string; description: string; image: string | null;
  store: number; store_name: string; union_name: string; category_name: string;
  price: number; old_price: number | null; discount_percent: number | null;
  unit_display: string; is_active: boolean; is_available: boolean;
  status: string; status_display: string; reviewed_at: string | null; review_note: string;
  created_at: string;
};

const TONE: Record<string, "warn" | "ok" | "danger"> = { pending: "warn", approved: "ok", rejected: "danger" };

/** کارتابل «نرخ مصوب سایر کالاها» — کالاهای غیراساسی که فروشگاه خودش قیمت می‌گذارد
 *  و تا تایید کارشناس اداره صمت به مردم نمایش داده نمی‌شود. */
export default function OtherPrices() {
  const { user } = useAuth();
  const canReview = user!.role === "samt" || user!.role === "admin";
  const [status, setStatus] = useState("pending");
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<OtherProduct | null>(null);

  const q = useQuery({
    queryKey: ["other-prices", status, search],
    queryFn: () => api.get<Page<OtherProduct>>("/other-prices/", { status, search, page_size: 100 }),
    refetchInterval: status === "pending" ? 60_000 : false,
  });
  const rows = q.data?.results ?? [];

  return (
    <div className="space-y-4">
      <PageHeader
        title="نرخ مصوب سایر کالاها"
        subtitle="کالاهای غیراساسی فروشگاه‌ها؛ قیمت را فروشنده تعیین می‌کند و پس از تایید شما نمایش داده می‌شود."
      />

      <Card className="flex items-start gap-2 border-brand/30 bg-brand-soft/60 p-3 text-xs leading-6 text-brand">
        <Info className="mt-0.5 size-4 shrink-0" />
        <span>
          این کالاها نرخ مصوب اتحادیه ندارند و سقف یا کف قیمتی برایشان اعمال نمی‌شود. محصول تا
          زمانی که تایید نشود در صفحه عمومی فروشگاه دیده نمی‌شود، و هر بار که فروشنده نام یا
          قیمت را تغییر دهد دوباره به همین کارتابل برمی‌گردد.
        </span>
      </Card>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Segmented value={status} onChange={setStatus} options={[
          { value: "pending", label: "در انتظار تایید" },
          { value: "approved", label: "تاییدشده" },
          { value: "rejected", label: "رد شده" },
          { value: "", label: "همه" },
        ]} />
        <div className="relative sm:mr-auto sm:w-64">
          <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="نام کالا، برند، فروشگاه" className="pr-9" />
        </div>
      </div>

      {q.isLoading ? <Loading /> : !rows.length ? (
        <Card><Empty title={status === "pending" ? "کالایی در انتظار تایید نیست" : "موردی نیست"} icon={<PackageSearch className="size-7" />} /></Card>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <Card key={r.id} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex min-w-0 gap-3">
                  {r.image ? (
                    <img src={r.image} alt="" className="size-14 shrink-0 rounded-xl object-cover" />
                  ) : (
                    <span className="grid size-14 shrink-0 place-items-center rounded-xl bg-surface-2 text-muted"><PackageSearch className="size-6" /></span>
                  )}
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{r.name}</span>
                      <Badge tone={TONE[r.status]}>{r.status_display}</Badge>
                      {!r.is_active && <Badge>پنهان توسط فروشنده</Badge>}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                      <StoreIcon className="size-3.5" />{r.store_name}
                      {r.union_name && <span>· {r.union_name}</span>}
                      {r.category_name && <span>· {r.category_name}</span>}
                      <span>· ثبت {ago(r.created_at)}</span>
                    </div>
                    {r.brand && <div className="mt-1 text-xs text-muted">برند: {r.brand}</div>}
                    {r.description && <div className="mt-1 line-clamp-2 text-xs text-muted">{r.description}</div>}
                    {r.review_note && <div className="mt-1 text-xs text-danger">نتیجه بررسی: {r.review_note}</div>}
                  </div>
                </div>
                <div className="shrink-0 text-left">
                  {r.old_price ? <div className="text-xs text-muted line-through">{toman(r.old_price)}</div> : null}
                  <div className="text-lg font-bold tabular">{toman(r.price)}</div>
                  <div className="text-[11px] text-muted">هر {r.unit_display}</div>
                  {r.discount_percent ? <Badge tone="ok" className="mt-1">{num(r.discount_percent)}٪ تخفیف</Badge> : null}
                </div>
              </div>
              {canReview && r.status !== "approved" && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <ApproveButton product={r} />
                  {r.status !== "rejected" && <Button size="sm" variant="secondary" onClick={() => setOpen(r)}>رد کردن</Button>}
                </div>
              )}
              {canReview && r.status === "approved" && (
                <div className="mt-3"><Button size="sm" variant="secondary" onClick={() => setOpen(r)}>لغو تایید و رد</Button></div>
              )}
              {r.reviewed_at && <div className="mt-2 text-[11px] text-muted">بررسی‌شده در {dateTime(r.reviewed_at)}</div>}
            </Card>
          ))}
        </div>
      )}
      {open && <RejectSheet product={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function useReview(onDone?: () => void) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ id, approve, note }: { id: number; approve: boolean; note?: string }) =>
      api.post(`/other-prices/${id}/${approve ? "approve" : "reject"}/`, { note }),
    onSuccess: (_d, v) => {
      toast(v.approve ? "کالا تایید شد و در صفحه فروشگاه نمایش داده می‌شود" : "کالا رد شد");
      qc.invalidateQueries({ queryKey: ["other-prices"] });
      onDone?.();
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
}

function ApproveButton({ product }: { product: OtherProduct }) {
  const m = useReview();
  return (
    <Button size="sm" icon={<CheckCircle2 className="size-4" />} loading={m.isPending} onClick={() => m.mutate({ id: product.id, approve: true })}>
      تایید و نمایش عمومی
    </Button>
  );
}

function RejectSheet({ product, onClose }: { product: OtherProduct; onClose: () => void }) {
  const [note, setNote] = useState("");
  const m = useReview(onClose);
  return (
    <div className="fixed inset-0 z-[1000] flex items-end justify-center sm:items-center" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <Card className="relative w-full max-w-md rounded-t-3xl p-5 sm:rounded-3xl">
        <h2 className="font-semibold">رد «{product.name}»</h2>
        <p className="mt-1 text-sm text-muted">قیمت {toman(product.price)} از فروشگاه {product.store_name}</p>
        <Field label="دلیل رد (برای فروشنده ارسال می‌شود)" className="mt-4">
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} className="min-h-20" />
        </Field>
        <div className="mt-4 flex gap-2">
          <Button variant="danger" disabled={!note.trim()} loading={m.isPending} onClick={() => m.mutate({ id: product.id, approve: false, note })}>
            رد کالا
          </Button>
          <Button variant="secondary" onClick={onClose}>انصراف</Button>
        </div>
      </Card>
    </div>
  );
}
