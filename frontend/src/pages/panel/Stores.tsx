import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Download, Phone, Search } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge, Button, Card, DataTable, Empty, Field, Input, Loading, PageHeader, Segmented, Sheet, STATUS_TONE, Textarea, useToast } from "../../components/ui";
import { api, download, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { date, num, telLink } from "../../lib/format";

type StoreT = {
  id: number; name: string; union_name: string; county_name: string; license_no: string; phone: string; address: string;
  status: string; status_display: string; status_reason: string; is_verified: boolean; rating_avg: string; owner_name: string;
  owner_mobile: string; offers_count: number; created_at: string; license_image: string | null; lat: string; lng: string;
};

export default function Stores() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<StoreT | null>(null);
  const q = useQuery({ queryKey: ["stores", status, search, page], queryFn: () => api.get<Page<StoreT>>("/stores/", { status, search, page }) });
  const canManage = user!.role === "union" || user!.role === "admin";
  return (
    <div className="space-y-4">
      <PageHeader
        title={canManage ? "کارتابل فروشگاه‌ها" : "فروشگاه‌ها"}
        subtitle={canManage ? "درخواست‌های فعال‌سازی را بررسی و فروشگاه‌های عضو را مدیریت کنید." : undefined}
        actions={<Button variant="secondary" size="sm" icon={<Download className="size-4" />} onClick={() => download("/analytics/export/stores/", "stores.xlsx")}>اکسل</Button>}
      />
      <div className="flex flex-col gap-2 sm:flex-row">
        <Segmented value={status} onChange={(v) => { setParams(v ? { status: v } : {}); setPage(1); }} options={[
          { value: "", label: "همه" }, { value: "pending", label: "در انتظار تایید" }, { value: "active", label: "فعال" },
          { value: "suspended", label: "تعلیق" }, { value: "rejected", label: "رد شده" },
        ]} />
        <div className="relative sm:mr-auto sm:w-64">
          <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="نام، موبایل، پروانه" className="pr-9" />
        </div>
      </div>
      <Card>
        {q.isLoading ? <Loading /> : !q.data?.results.length ? <Empty title="فروشگاهی یافت نشد" /> : (
          <DataTable
            rows={q.data.results}
            onRowClick={setSel}
            columns={[
              { key: "name", label: "فروشگاه", render: (s) => <span className="inline-flex items-center gap-1 font-medium">{s.name}{s.is_verified && <BadgeCheck className="size-4 text-brand" />}</span> },
              { key: "owner_name", label: "مالک", render: (s) => s.owner_name || s.owner_mobile },
              { key: "union_name", label: "اتحادیه" },
              { key: "status", label: "وضعیت", render: (s) => <Badge tone={STATUS_TONE[s.status]}>{s.status_display}</Badge> },
              { key: "offers_count", label: "قیمت‌ها", render: (s) => num(s.offers_count) },
              { key: "created_at", label: "ثبت", render: (s) => date(s.created_at), hideOnMobile: true },
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
      {sel && <StoreSheet store={sel} canManage={canManage} onClose={() => setSel(null)} />}
    </div>
  );
}

function StoreSheet({ store, canManage, onClose }: { store: StoreT; canManage: boolean; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const act = useMutation({
    mutationFn: ({ action, body }: { action: string; body?: object }) => api.post(`/stores/${store.id}/${action}/`, body),
    onSuccess: () => {
      toast("انجام شد");
      qc.invalidateQueries({ queryKey: ["stores"] });
      qc.invalidateQueries({ queryKey: ["pending-stores"] });
      onClose();
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <Sheet open onClose={onClose} title={store.name}>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <Info label="مالک" value={store.owner_name || "—"} />
        <Info label="موبایل" value={<a href={telLink(store.owner_mobile)} className="text-brand" dir="ltr">{store.owner_mobile}</a>} />
        <Info label="اتحادیه" value={store.union_name} />
        <Info label="پروانه کسب" value={store.license_no || "—"} />
        <Info label="تلفن" value={store.phone ? <a href={telLink(store.phone)} className="inline-flex items-center gap-1 text-brand"><Phone className="size-3" />{store.phone}</a> : "—"} />
        <Info label="وضعیت" value={<Badge tone={STATUS_TONE[store.status]}>{store.status_display}</Badge>} />
        <Info label="نشانی" value={store.address} wide />
        {store.status_reason && <Info label="دلیل" value={store.status_reason} wide />}
      </dl>
      {store.license_image && <a href={store.license_image} target="_blank" rel="noreferrer" className="mt-3 inline-block text-sm text-brand underline">مشاهده تصویر پروانه</a>}
      {canManage && (
        <div className="mt-5 space-y-3 border-t border-line pt-4">
          <Field label="دلیل (برای رد یا تعلیق الزامی است)">
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} className="min-h-16" />
          </Field>
          <div className="flex flex-wrap gap-2">
            {store.status !== "active" && <Button loading={act.isPending} onClick={() => act.mutate({ action: "approve" })}>تایید و فعال‌سازی</Button>}
            {store.status === "pending" && <Button variant="danger" disabled={!reason} onClick={() => act.mutate({ action: "reject", body: { reason } })}>رد درخواست</Button>}
            {store.status === "active" && <Button variant="danger" disabled={!reason} onClick={() => act.mutate({ action: "suspend", body: { reason } })}>تعلیق</Button>}
            {store.status === "active" && (
              <Button variant="soft" onClick={() => act.mutate({ action: "verify", body: { value: !store.is_verified } })}>
                {store.is_verified ? "حذف نشان اعتماد" : "اعطای نشان اعتماد"}
              </Button>
            )}
          </div>
        </div>
      )}
    </Sheet>
  );
}

export function Info({ label, value, wide }: { label: string; value: React.ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? "col-span-2" : ""}>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5">{value}</dd>
    </div>
  );
}
