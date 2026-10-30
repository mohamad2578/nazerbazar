import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, LocateFixed, MapPin, Plus, Star, Trash2 } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import { api, fieldErrors } from "../lib/api";
import { useGeo } from "../lib/prefs";
import { Button, cx, Field, Input, Loading, Textarea, useToast } from "./ui";

const LocationPicker = lazy(() => import("./MapView").then((m) => ({ default: m.LocationPicker })));

export type Address = { id: number; title: string; address: string; receiver_phone: string; lat: string | null; lng: string | null; is_default: boolean };

/** نشانی‌های ذخیره‌شده مشتری برای ارسال با پیک. با `selected/onSelect` حالت انتخاب (در سبد خرید) دارد، بدون آن حالت مدیریت. */
export default function AddressBook({ selected, onSelect }: { selected?: number | null; onSelect?: (a: Address | null) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["my-addresses"], queryFn: () => api.get<Address[]>("/my-addresses/") });
  const [adding, setAdding] = useState(false);
  const rows = q.data ?? [];

  // اگر هنوز نشانی انتخاب نشده، نشانی پیش‌فرض (یا اولین) انتخاب شود
  useEffect(() => {
    if (onSelect && !selected && rows.length) onSelect(rows.find((a) => a.is_default) ?? rows[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows.length]);

  const del = useMutation({
    mutationFn: (id: number) => api.del(`/my-addresses/${id}/`),
    onSuccess: (_, id) => { qc.invalidateQueries({ queryKey: ["my-addresses"] }); if (id === selected) onSelect?.(null); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const makeDefault = useMutation({
    mutationFn: (id: number) => api.patch(`/my-addresses/${id}/`, { is_default: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["my-addresses"] }),
  });

  if (q.isLoading) return <Loading />;
  return (
    <div className="space-y-2">
      {rows.map((a) => {
        const active = onSelect && a.id === selected;
        return (
          <div
            key={a.id}
            onClick={() => onSelect?.(a)}
            className={cx("flex items-start gap-2.5 rounded-xl border p-3 text-sm", onSelect && "cursor-pointer", active ? "border-brand bg-brand-soft" : "border-line")}
          >
            <span className={cx("mt-0.5 grid size-5 shrink-0 place-items-center rounded-full", active ? "bg-brand text-brand-ink" : "bg-surface-2 text-muted")}>
              {active ? <Check className="size-3.5" /> : <MapPin className="size-3.5" />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 font-medium">
                {a.title}
                {a.is_default && <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] text-muted">پیش‌فرض</span>}
                {a.lat && <span className="text-[10px] text-ok">موقعیت روی نقشه ✓</span>}
              </div>
              <div className="mt-0.5 leading-6 text-muted">{a.address}</div>
              {a.receiver_phone && <div className="text-xs text-muted" dir="ltr">{a.receiver_phone}</div>}
            </div>
            <div className="flex shrink-0 gap-1" onClick={(e) => e.stopPropagation()}>
              {!a.is_default && (
                <button type="button" onClick={() => makeDefault.mutate(a.id)} className="grid size-8 place-items-center rounded-lg hover:bg-surface-2" aria-label="پیش‌فرض">
                  <Star className="size-4" />
                </button>
              )}
              <button type="button" onClick={() => confirm("این نشانی حذف شود؟") && del.mutate(a.id)} className="grid size-8 place-items-center rounded-lg text-danger hover:bg-surface-2" aria-label="حذف">
                <Trash2 className="size-4" />
              </button>
            </div>
          </div>
        );
      })}
      {!rows.length && !adding && <p className="rounded-xl bg-surface-2 p-3 text-xs text-muted">هنوز نشانی‌ای ذخیره نکرده‌اید.</p>}
      {adding ? (
        <AddressForm onDone={(a) => { setAdding(false); if (a) { onSelect?.(a); } }} />
      ) : (
        <Button type="button" size="sm" variant="secondary" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
          نشانی جدید
        </Button>
      )}
    </div>
  );
}

function AddressForm({ onDone }: { onDone: (a?: Address) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const geo = useGeo();
  const [f, setF] = useState({ title: "", address: "", receiver_phone: "" });
  const [loc, setLoc] = useState<{ lat: number; lng: number } | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  // وقتی موقعیت دستگاه گرفته شد، روی نقشه گذاشته شود
  useEffect(() => { if (geo.pos && !loc) setLoc(geo.pos); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [geo.pos]);
  const m = useMutation({
    mutationFn: () => api.post<Address>("/my-addresses/", { ...f, lat: loc?.lat.toFixed(6), lng: loc?.lng.toFixed(6) }),
    onSuccess: (a) => { toast("نشانی ذخیره شد"); qc.invalidateQueries({ queryKey: ["my-addresses"] }); onDone(a); },
  });
  const err = fieldErrors(m.error);
  return (
    <div className="space-y-3 rounded-xl border border-line bg-surface-2 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="عنوان" error={err.title}><Input value={f.title} onChange={set("title")} placeholder="مثلا خانه" /></Field>
        <Field label="تلفن تحویل‌گیرنده (اختیاری)" error={err.receiver_phone}><Input value={f.receiver_phone} onChange={set("receiver_phone")} dir="ltr" inputMode="tel" className="text-left" /></Field>
        <Field label="نشانی کامل" error={err.address} className="sm:col-span-2"><Textarea value={f.address} onChange={set("address")} className="min-h-16" placeholder="شهر، خیابان، کوچه، پلاک، واحد" /></Field>
      </div>
      <Field label="موقعیت روی نقشه (برای پیدا کردن آدرس توسط پیک)" hint="روی نقطه دقیق بزنید یا از موقعیت فعلی استفاده کنید.">
        <Suspense fallback={<Loading />}>
          <LocationPicker value={loc} onChange={setLoc} height={180} />
        </Suspense>
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" variant="soft" icon={<LocateFixed className="size-4" />} loading={geo.asking} onClick={geo.ask}>موقعیت فعلی من</Button>
        <Button type="button" size="sm" loading={m.isPending} disabled={!f.title.trim() || !f.address.trim()} onClick={() => m.mutate()}>ذخیره نشانی</Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => onDone()}>انصراف</Button>
      </div>
      {m.error && !Object.keys(err).length && <p className="text-sm text-danger">{(m.error as Error).message}</p>}
    </div>
  );
}
