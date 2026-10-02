import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Paperclip } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, Button, Card, ErrorBox, Field, Loading, Select, STATUS_TONE, Textarea, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, telLink, toman } from "../../lib/format";
import { Info } from "./Stores";

export default function ComplaintDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["complaint", id], queryFn: () => api.get(`/complaints/${id}/`) });
  const [status, setStatus] = useState("");
  const [note, setNote] = useState("");
  const [violation, setViolation] = useState<"" | "yes" | "no">("");
  const [suspend, setSuspend] = useState(false);
  const [internal, setInternal] = useState(false);
  const m = useMutation({
    mutationFn: () => api.post(`/complaints/${id}/transition/`, {
      status: status || q.data.status, note, violation_confirmed: violation === "" ? null : violation === "yes",
      suspend_store: suspend, is_public: !internal, override: user!.role === "chamber",
    }),
    onSuccess: () => { toast("ثبت شد"); setNote(""); qc.invalidateQueries({ queryKey: ["complaint", id] }); qc.invalidateQueries({ queryKey: ["complaints"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const c = q.data;
  const canAct = ["union", "chamber", "admin"].includes(user!.role);
  return (
    <div className="space-y-4">
      <Link to="/panel/complaints" className="inline-flex items-center gap-1 text-sm text-muted"><ArrowRight className="size-4" /> شکایات</Link>
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <Card className="p-5">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-lg font-bold">{c.kind_display}</h1>
              <div className="text-sm text-muted" dir="ltr">{c.tracking_code}</div>
            </div>
            <Badge tone={STATUS_TONE[c.status]}>{c.status_display}</Badge>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <Info label="فروشگاه" value={c.store_name || `${c.shop_name} (خارج از سامانه)`} />
            <Info label="تلفن فروشگاه" value={c.store_phone ? <a href={telLink(c.store_phone)} className="text-brand">{c.store_phone}</a> : "—"} />
            <Info label="نشانی" value={c.store_address || c.shop_address || "—"} wide />
            <Info label="کالا" value={c.product_name || "—"} />
            <Info label="اتحادیه / رونوشت" value={`${c.union_name || "—"} / ${c.chamber_name}`} />
            <Info label="قیمت پرداختی" value={<b className="text-danger">{toman(c.paid_price)}</b>} />
            <Info label="نرخ مصوب لحظه ثبت" value={toman(c.official_price)} />
            <Info label="قیمت اعلامی فروشگاه" value={toman(c.announced_price)} />
            {c.reporter_mobile && <Info label="گزارش‌دهنده" value={<span>{c.reporter_name} · <a href={telLink(c.reporter_mobile)} className="text-brand" dir="ltr">{c.reporter_mobile}</a></span>} />}
            <Info label="شرح" value={<p className="whitespace-pre-line">{c.description}</p>} wide />
          </dl>
          {c.attachment && <a href={c.attachment} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-sm text-brand"><Paperclip className="size-4" /> مستند پیوست</a>}
          {c.lat && <a href={`https://www.openstreetmap.org/?mlat=${c.lat}&mlon=${c.lng}#map=17/${c.lat}/${c.lng}`} target="_blank" rel="noreferrer" className="mr-4 mt-3 inline-block text-sm text-brand">موقعیت ثبت گزارش</a>}
        </Card>
        <div className="space-y-4">
          {canAct && (
            <Card className="space-y-3 p-5">
              <h2 className="font-semibold">اقدام</h2>
              <Field label="وضعیت جدید">
                <Select value={status} onChange={(e) => setStatus(e.target.value)}>
                  <option value="">— بدون تغییر (فقط یادداشت) —</option>
                  <option value="reviewing">در حال بررسی</option>
                  <option value="inspection">ارجاع به بازرسی</option>
                  <option value="resolved">رسیدگی شد</option>
                  <option value="rejected">رد شکایت</option>
                </Select>
              </Field>
              {(status === "resolved" || status === "rejected") && (
                <Field label="نتیجه بررسی تخلف">
                  <Select value={violation} onChange={(e) => setViolation(e.target.value as any)}>
                    <option value="">—</option>
                    <option value="yes">تخلف محرز شد</option>
                    <option value="no">تخلف محرز نشد</option>
                  </Select>
                </Field>
              )}
              <Field label="یادداشت / نتیجه رسیدگی"><Textarea value={note} onChange={(e) => setNote(e.target.value)} /></Field>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} className="size-4" /> یادداشت داخلی (برای شهروند نمایش داده نشود)</label>
              {violation === "yes" && c.store && (
                <label className="flex items-center gap-2 text-sm text-danger"><input type="checkbox" checked={suspend} onChange={(e) => setSuspend(e.target.checked)} className="size-4" /> تعلیق فروشگاه</label>
              )}
              <Button className="w-full" loading={m.isPending} disabled={!note && !status} onClick={() => m.mutate()}>ثبت</Button>
            </Card>
          )}
          <Card className="p-5">
            <h2 className="mb-3 font-semibold">سوابق</h2>
            <ol className="space-y-3 border-r-2 border-line pr-4">
              {c.events.map((e: any) => (
                <li key={e.id} className="relative">
                  <span className="absolute -right-[23px] top-1.5 size-3 rounded-full border-2 border-surface bg-brand" />
                  <div className="text-sm font-medium">{e.status_display} {!e.is_public && <Badge>داخلی</Badge>}</div>
                  {e.note && <div className="text-sm text-muted">{e.note}</div>}
                  <div className="text-[11px] text-muted">{dateTime(e.created_at)} · {e.actor_name}</div>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>
    </div>
  );
}
