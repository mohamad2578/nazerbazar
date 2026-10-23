import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, MessageSquareText, XCircle } from "lucide-react";
import { useState } from "react";
import { Badge, Card, Empty, Input, Loading, PageHeader, Segmented } from "../../components/ui";
import { api } from "../../lib/api";
import { dateTime, num } from "../../lib/format";

type Row = { id: number; kind: string; mobile: string; text: string; ok: boolean; detail: string; created_at: string };
type Resp = { total: number; failed: number; results: Row[] };

const KINDS: Record<string, string> = { price_change: "تغییر حداکثر قیمت", otp: "کد ورود", other: "سایر" };

/** سابقه پیامک‌ها (فقط مدیر کل): چه پیامی به چه شماره‌ای رفت و سرویس‌دهنده چه پاسخی داد. */
export default function SmsLog() {
  const [ok, setOk] = useState("");
  const [q, setQ] = useState("");
  const query = useQuery({
    queryKey: ["sms-log", ok, q],
    queryFn: () => api.get<Resp>("/sms-log/", { ok: ok || undefined, q: q || undefined }),
    refetchInterval: 30_000,
  });
  const d = query.data;
  return (
    <div className="space-y-4">
      <PageHeader title="پیامک‌ها" subtitle={d ? `${num(d.total)} پیامک ثبت شده · ${num(d.failed)} ناموفق` : undefined} />
      <div className="flex flex-col gap-2 sm:flex-row">
        <Segmented value={ok} onChange={setOk} options={[{ value: "", label: "همه" }, { value: "true", label: "موفق" }, { value: "false", label: "ناموفق" }]} />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="جستجوی شماره موبایل" dir="ltr" className="sm:mr-auto sm:w-56" />
      </div>
      {query.isLoading ? <Loading /> : !d?.results.length ? (
        <Card><Empty title="پیامکی ثبت نشده است" icon={<MessageSquareText className="size-7" />} /></Card>
      ) : (
        <div className="space-y-2">
          {d.results.map((r) => (
            <Card key={r.id} className="p-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                {r.ok ? <CheckCircle2 className="size-4 text-ok" /> : <XCircle className="size-4 text-danger" />}
                <b dir="ltr" className="tabular">{r.mobile}</b>
                <Badge>{KINDS[r.kind] ?? r.kind}</Badge>
                <span className="mr-auto text-xs text-muted tabular">{dateTime(r.created_at)}</span>
              </div>
              <p className="mt-1.5 whitespace-pre-line text-xs leading-6 text-muted">{r.text}</p>
              {!r.ok && r.detail && <p className="mt-1 break-all rounded-lg bg-danger-soft p-2 text-[11px] text-danger" dir="ltr">{r.detail}</p>}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
