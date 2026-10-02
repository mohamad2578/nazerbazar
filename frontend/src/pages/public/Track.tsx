import { useMutation, useQuery } from "@tanstack/react-query";
import { PackageSearch, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge, Button, Card, Field, Input, Segmented, STATUS_TONE } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, toEn, toman } from "../../lib/format";

export type ComplaintT = {
  id: number; tracking_code: string; kind_display: string; status: string; status_display: string; store_name: string;
  shop_name: string; product_name: string; union_name: string; chamber_name: string; paid_price: number | null;
  official_price: number | null; announced_price: number | null; description: string; resolution: string; created_at: string;
  events: { id: number; status_display: string; note: string; actor_name: string; created_at: string }[];
};

export function ComplaintTimeline({ c }: { c: ComplaintT }) {
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs text-muted">کد رهگیری</div>
          <div className="font-bold tracking-wider" dir="ltr">{c.tracking_code}</div>
        </div>
        <Badge tone={STATUS_TONE[c.status]}>{c.status_display}</Badge>
      </div>
      <div className="mt-3 text-sm">
        {c.kind_display} — {c.store_name || c.shop_name} {c.product_name && `· ${c.product_name}`}
      </div>
      {(c.paid_price || c.official_price) && (
        <div className="mt-1 text-xs text-muted">
          پرداختی {toman(c.paid_price)} · نرخ مصوب {toman(c.official_price)}
        </div>
      )}
      <ol className="mt-4 space-y-3 border-r-2 border-line pr-4">
        {c.events.map((e) => (
          <li key={e.id} className="relative">
            <span className="absolute -right-[23px] top-1.5 size-3 rounded-full border-2 border-surface bg-brand" />
            <div className="text-sm font-medium">{e.status_display}</div>
            {e.note && <div className="text-sm text-muted">{e.note}</div>}
            <div className="text-[11px] text-muted">{dateTime(e.created_at)} {e.actor_name && `· ${e.actor_name}`}</div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export default function Track() {
  const [params] = useSearchParams();
  const { user } = useAuth();
  const [tab, setTab] = useState<"complaint" | "quota">(params.get("quota") ? "quota" : "complaint");
  const [code, setCode] = useState(params.get("code") ?? params.get("quota") ?? "");
  const [mobile, setMobile] = useState(user?.mobile ?? "");
  const lookup = useMutation({ mutationFn: () => api.get<ComplaintT>("/public/complaints/track/", { code: toEn(code).trim(), mobile: toEn(mobile) }) });
  const quota = useMutation({ mutationFn: () => api.get(`/public/quota/${encodeURIComponent(toEn(code).trim())}/`) });
  const mine = useQuery({ queryKey: ["my-complaints"], queryFn: () => api.get<ComplaintT[]>("/public/complaints/mine/"), enabled: !!user });

  useEffect(() => {
    if (params.get("quota")) quota.mutate();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-lg font-bold">پیگیری</h1>
      <Segmented value={tab} onChange={setTab} options={[{ value: "complaint", label: "گزارش تخلف" }, { value: "quota", label: "رهگیری کالای تنظیم بازار" }]} />
      <Card className="p-4 sm:p-5">
        <form
          className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            (tab === "complaint" ? lookup : quota).mutate();
          }}
        >
          <Field label={tab === "complaint" ? "کد رهگیری گزارش" : "کد رهگیری درج‌شده روی فاکتور/بسته"}>
            <Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} dir="ltr" className="text-left tracking-wider" required />
          </Field>
          {tab === "complaint" ? (
            <Field label="موبایل ثبت‌کننده">
              <Input value={mobile} onChange={(e) => setMobile(e.target.value)} inputMode="tel" dir="ltr" className="text-left" required />
            </Field>
          ) : <div />}
          <Button type="submit" icon={<Search className="size-4" />} loading={lookup.isPending || quota.isPending}>
            جستجو
          </Button>
        </form>
        {(tab === "complaint" ? lookup.error : quota.error) && <p className="mt-3 text-sm text-danger">موردی با این مشخصات پیدا نشد.</p>}
      </Card>
      {tab === "complaint" && lookup.data && <ComplaintTimeline c={lookup.data} />}
      {tab === "quota" && quota.data && (
        <Card className="p-4 sm:p-5">
          <div className="flex items-center gap-3">
            <PackageSearch className="size-8 text-brand" />
            <div>
              <div className="font-semibold">{quota.data.commodity} — {quota.data.allocation}</div>
              <div className="text-xs text-muted">تامین: {quota.data.supplier || "—"} · سقف قیمت مصرف‌کننده {toman(quota.data.consumer_price)} / {quota.data.unit}</div>
            </div>
          </div>
          <div className="mt-3 text-sm">مقصد: {quota.data.store_name} — {quota.data.store_address}</div>
          <ol className="mt-4 space-y-3 border-r-2 border-line pr-4">
            {quota.data.events.map((e: any, i: number) => (
              <li key={i} className="relative">
                <span className="absolute -right-[23px] top-1.5 size-3 rounded-full border-2 border-surface bg-brand" />
                <div className="text-sm font-medium">{e.status_display}</div>
                {e.note && <div className="text-sm text-muted">{e.note}</div>}
                <div className="text-[11px] text-muted">{dateTime(e.created_at)}</div>
              </li>
            ))}
          </ol>
        </Card>
      )}
      {tab === "complaint" && !!mine.data?.length && (
        <section className="space-y-3">
          <h2 className="font-semibold">گزارش‌های من</h2>
          {mine.data.map((c) => (
            <ComplaintTimeline key={c.id} c={c} />
          ))}
        </section>
      )}
    </div>
  );
}
