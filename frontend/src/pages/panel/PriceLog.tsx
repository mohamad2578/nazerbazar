import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, History, Search } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Input, Loading, PageHeader, Select } from "../../components/ui";
import { api, type Page } from "../../lib/api";
import { dateTime, num, toman } from "../../lib/format";

type LogRow = {
  id: number; product: number; product_name: string; unit_display: string; union_name: string;
  price: number; previous_price: number; note: string; status: string; status_display: string;
  set_by_name: string; set_by_role: string; set_by_mobile: string; created_at: string;
  reviewed_by_name: string; reviewed_by_role: string; reviewed_at: string | null; review_note: string;
};

const TONE: Record<string, "warn" | "ok" | "danger"> = { pending: "warn", approved: "ok", rejected: "danger" };
const ROLES: [string, string][] = [["", "همه نقش‌ها"], ["samt", "اداره صمت"], ["chamber", "اتاق اصناف"], ["union", "اتحادیه"], ["governorate", "استانداری"], ["admin", "مدیر کل"]];

/** سابقه حداکثر قیمت‌ها: چه کسی، با چه نقشی، در چه تاریخ و ساعتی قیمت را ثبت یا تایید کرد. */
export default function PriceLog() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [role, setRole] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const q = useQuery({
    queryKey: ["price-log", search, status, role, from, to, page],
    queryFn: () => api.get<Page<LogRow>>("/prices/log/", { q: search, status, role, from: from || undefined, to: to || undefined, page }),
  });
  const rows = q.data?.results ?? [];
  const reset = () => setPage(1);

  return (
    <div className="space-y-4">
      <PageHeader title="سابقه حداکثر قیمت‌ها" subtitle="هر ثبت یا تغییر حداکثر قیمت: ثبت‌کننده، نقش، تاریخ و ساعت، و نتیجه بررسی" />

      <Card className="grid gap-2 p-3 sm:grid-cols-2 lg:grid-cols-5">
        <div className="relative lg:col-span-2">
          <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={search} onChange={(e) => { setSearch(e.target.value); reset(); }} placeholder="نام کالا" className="pr-9" />
        </div>
        <Select value={role} onChange={(e) => { setRole(e.target.value); reset(); }}>
          {ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </Select>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); reset(); }}>
          <option value="">همه وضعیت‌ها</option>
          <option value="approved">اعمال‌شده</option>
          <option value="pending">در انتظار تایید</option>
          <option value="rejected">رد شده</option>
        </Select>
        <div className="grid grid-cols-2 gap-2 sm:col-span-2 lg:col-span-1">
          <Input type="date" value={from} onChange={(e) => { setFrom(e.target.value); reset(); }} dir="ltr" aria-label="از تاریخ" />
          <Input type="date" value={to} onChange={(e) => { setTo(e.target.value); reset(); }} dir="ltr" aria-label="تا تاریخ" />
        </div>
      </Card>

      {q.isLoading ? <Loading /> : !rows.length ? (
        <Card><Empty title="موردی یافت نشد" icon={<History className="size-7" />} /></Card>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => {
            const change = r.previous_price ? ((r.price - r.previous_price) / r.previous_price) * 100 : null;
            return (
              <Card key={r.id} className="p-3 sm:p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium">{r.product_name}</span>
                      <Badge tone={TONE[r.status]}>{r.status_display}</Badge>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">{r.union_name} · هر {r.unit_display}</div>
                  </div>
                  <div className="text-left">
                    <div className="font-bold tabular">{toman(r.price)}</div>
                    {change != null && change !== 0 && (
                      <div className={`inline-flex items-center gap-0.5 text-xs ${change > 0 ? "text-danger" : "text-ok"}`}>
                        {change > 0 ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />}
                        {num(Math.abs(change), 1)}٪ از {toman(r.previous_price, false)}
                      </div>
                    )}
                  </div>
                </div>
                <div className="mt-2 grid gap-1 rounded-xl bg-surface-2 p-2.5 text-xs sm:grid-cols-2">
                  <div>
                    <span className="text-muted">ثبت: </span>
                    <b>{r.set_by_name || r.set_by_mobile || "—"}</b>
                    {r.set_by_role && <span className="text-muted"> ({r.set_by_role})</span>}
                    <span className="block text-muted tabular">{dateTime(r.created_at)}</span>
                  </div>
                  {r.reviewed_at && (
                    <div>
                      <span className="text-muted">{r.status === "rejected" ? "رد: " : "تایید: "}</span>
                      <b>{r.reviewed_by_name || "—"}</b>
                      {r.reviewed_by_role && <span className="text-muted"> ({r.reviewed_by_role})</span>}
                      <span className="block text-muted tabular">{dateTime(r.reviewed_at)}</span>
                    </div>
                  )}
                </div>
                {(r.note || r.review_note) && (
                  <div className="mt-1.5 text-xs text-muted">
                    {r.note && <>توضیح: {r.note}</>}{r.note && r.review_note && " · "}{r.review_note && <>نتیجه بررسی: {r.review_note}</>}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
      {q.data && q.data.count > rows.length && (
        <div className="flex justify-center gap-2">
          <Button size="sm" variant="secondary" disabled={!q.data.previous} onClick={() => setPage(page - 1)}>قبلی</Button>
          <Button size="sm" variant="secondary" disabled={!q.data.next} onClick={() => setPage(page + 1)}>بعدی</Button>
        </div>
      )}
    </div>
  );
}
