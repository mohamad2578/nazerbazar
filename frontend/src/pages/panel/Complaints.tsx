import { useQuery } from "@tanstack/react-query";
import { Download, Search } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, DataTable, Empty, Input, Loading, PageHeader, Segmented, STATUS_TONE } from "../../components/ui";
import { api, download, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { ago, toman } from "../../lib/format";

export default function Complaints() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [status, setStatus] = useState(user!.role === "store" ? "" : "new");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["complaints", status, search, page], queryFn: () => api.get<Page<any>>("/complaints/", { status, search, page }) });
  return (
    <div className="space-y-4">
      <PageHeader
        title={user!.role === "store" ? "شکایات ثبت‌شده از فروشگاه" : user!.role === "chamber" ? "شکایات (رونوشت اتاق اصناف)" : "کارتابل شکایات"}
        actions={user!.role !== "store" && <Button variant="secondary" size="sm" icon={<Download className="size-4" />} onClick={() => download("/analytics/export/complaints/", "complaints.xlsx")}>اکسل</Button>}
      />
      <div className="flex flex-col gap-2 sm:flex-row">
        <Segmented value={status} onChange={(v) => { setStatus(v); setPage(1); }} options={[
          { value: "new", label: "جدید" }, { value: "reviewing", label: "در حال بررسی" }, { value: "inspection", label: "بازرسی" },
          { value: "resolved", label: "رسیدگی‌شده" }, { value: "rejected", label: "رد شده" }, { value: "", label: "همه" },
        ]} />
        <div className="relative sm:mr-auto sm:w-64">
          <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="کد، فروشگاه، کالا" className="pr-9" />
        </div>
      </div>
      <Card>
        {q.isLoading ? <Loading /> : !q.data?.results.length ? <Empty title="شکایتی در این وضعیت نیست" /> : (
          <DataTable
            rows={q.data.results}
            onRowClick={(c) => nav(`/panel/complaints/${c.id}`)}
            columns={[
              { key: "store", label: "فروشگاه", render: (c) => <div><div className="font-medium">{c.store_name || c.shop_name}</div><div className="text-xs text-muted" dir="ltr">{c.tracking_code}</div></div> },
              { key: "kind_display", label: "نوع" },
              { key: "product_name", label: "کالا", render: (c) => c.product_name || "—" },
              { key: "paid", label: "پرداختی / مصوب", render: (c) => c.paid_price ? `${toman(c.paid_price, false)} / ${toman(c.official_price, false)}` : "—", hideOnMobile: true },
              { key: "status", label: "وضعیت", render: (c) => <Badge tone={STATUS_TONE[c.status]}>{c.status_display}</Badge> },
              { key: "created_at", label: "زمان", render: (c) => ago(c.created_at) },
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
    </div>
  );
}
