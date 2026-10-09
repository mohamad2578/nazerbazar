import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, LocateFixed } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useGeoTree } from "../../components/CountyPicker";
import { Button, Card, Field, Input, Loading, Select } from "../../components/ui";
import { api, fieldErrors } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { toEn } from "../../lib/format";

const LocationPicker = lazy(() => import("../../components/MapView").then((m) => ({ default: m.LocationPicker })));

type UnionT = { id: number; name: string; county: number; county_name: string };

export default function RegisterStore() {
  const { user, reload } = useAuth();
  const geo = useGeoTree();
  const [county, setCounty] = useState("");
  const [loc, setLoc] = useState<{ lat: number; lng: number } | null>(null);
  const [f, setF] = useState({ name: "", union: "", license_no: "", phone: "", address: "", working_hours: "", first_name: user?.first_name ?? "", last_name: user?.last_name ?? "", national_code: user?.national_code ?? "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  // «فاقد اتحادیه» برای فروشگاه‌های زنجیره‌ای، جهاد، حامی و مانند آن‌ها
  const NONE = "none";
  const [covered, setCovered] = useState<number[]>([]);
  const noUnion = f.union === NONE;
  const toggleCovered = (id: number) =>
    setCovered((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  const unions = useQuery({ queryKey: ["unions", county], queryFn: () => api.get<UnionT[]>("/public/geo/unions/", { county }), enabled: !!county });
  const m = useMutation({
    mutationFn: () => api.post("/my-store/", {
      ...f, union: noUnion || !f.union ? null : Number(f.union),
      covered_unions: noUnion ? covered : [],
      national_code: toEn(f.national_code), phone: toEn(f.phone), lat: loc?.lat, lng: loc?.lng,
    }),
    onSuccess: () => reload(),
  });
  const err = fieldErrors(m.error);
  if (user?.store && !m.isSuccess) return <Navigate to="/panel" replace />;
  if (m.isSuccess)
    return (
      <Card className="mx-auto max-w-md p-6 text-center">
        <CheckCircle2 className="mx-auto size-14 text-ok" />
        <h1 className="mt-3 text-lg font-bold">درخواست شما ثبت شد</h1>
        <p className="mt-1 text-sm text-muted">درخواست فعال‌سازی در کارتابل اتحادیه قرار گرفت. پس از تایید، از پنل فروشگاه قیمت کالاها را ثبت کنید.</p>
        <Link to="/panel" className="mt-4 inline-block text-brand underline">ورود به پنل فروشگاه</Link>
      </Card>
    );

  const locate = () =>
    navigator.geolocation?.getCurrentPosition((p) => setLoc({ lat: +p.coords.latitude.toFixed(6), lng: +p.coords.longitude.toFixed(6) }));

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <h1 className="text-lg font-bold">ثبت‌نام فروشگاه</h1>
        <p className="mt-1 text-sm text-muted">پس از تایید اتحادیه صنفی، فروشگاه شما در سامانه نمایش داده می‌شود.</p>
      </div>
      <Card className="space-y-4 p-4 sm:p-6">
        <h2 className="font-semibold">مشخصات مالک</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="نام" error={err.first_name}><Input value={f.first_name} onChange={set("first_name")} /></Field>
          <Field label="نام خانوادگی" error={err.last_name}><Input value={f.last_name} onChange={set("last_name")} /></Field>
          <Field label="کد ملی" error={err.national_code}><Input value={f.national_code} onChange={set("national_code")} inputMode="numeric" dir="ltr" maxLength={10} /></Field>
        </div>
        <h2 className="pt-2 font-semibold">مشخصات فروشگاه</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="نام فروشگاه" error={err.name}><Input value={f.name} onChange={set("name")} /></Field>
          <Field label="شماره پروانه کسب" error={err.license_no}><Input value={f.license_no} onChange={set("license_no")} dir="ltr" /></Field>
          <Field label="شهرستان">
            <Select value={county} onChange={(e) => { setCounty(e.target.value); setF({ ...f, union: "" }); }}>
              <option value="">— انتخاب —</option>
              {geo.data?.map((p) => (
                <optgroup key={p.id} label={p.name}>
                  {p.counties.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </optgroup>
              ))}
            </Select>
          </Field>
          <Field label="اتحادیه صنفی" error={err.union}>
            <Select value={f.union} onChange={set("union")} disabled={!county}>
              <option value="">{unions.data && !unions.data.length ? "اتحادیه‌ای ثبت نشده" : "— انتخاب —"}</option>
              {unions.data?.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              <option value={NONE}>فاقد اتحادیه (زنجیره‌ای، جهاد، حامی و …)</option>
            </Select>
          </Field>
          <Field label="تلفن فروشگاه" error={err.phone}><Input value={f.phone} onChange={set("phone")} inputMode="tel" dir="ltr" /></Field>
          <Field label="ساعات کاری"><Input value={f.working_hours} onChange={set("working_hours")} placeholder="مثلا ۸ تا ۲۲" /></Field>
          <Field label="نشانی" className="sm:col-span-2" error={err.address}><Input value={f.address} onChange={set("address")} /></Field>
        </div>
        {noUnion && (
          <div className="rounded-2xl border border-line bg-surface-2 p-4">
            <h3 className="text-sm font-semibold">کالاهای کدام اتحادیه‌ها را عرضه می‌کنید؟</h3>
            <p className="mt-1 text-xs text-muted">
              چون عضو اتحادیه نیستید، مشخص کنید روی کالاهای کدام اتحادیه‌ها می‌خواهید قیمت اعلام کنید.
              می‌توانید چند مورد را انتخاب کنید.
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {unions.data?.map((u) => (
                <label key={u.id} className="flex items-center gap-2 rounded-xl bg-surface p-2.5 text-sm">
                  <input type="checkbox" className="size-4" checked={covered.includes(u.id)} onChange={() => toggleCovered(u.id)} />
                  {u.name}
                </label>
              ))}
            </div>
            {err.covered_unions && <p className="mt-2 text-xs text-danger">{err.covered_unions}</p>}
          </div>
        )}
        <Field label="موقعیت روی نقشه" error={err.lat} hint="روی نقشه لمس کنید تا محل دقیق فروشگاه ثبت شود.">
          <div className="mb-2">
            <Button type="button" size="sm" variant="soft" icon={<LocateFixed className="size-4" />} onClick={locate}>موقعیت فعلی من</Button>
          </div>
          <Suspense fallback={<Loading />}>
            <LocationPicker value={loc} onChange={setLoc} />
          </Suspense>
        </Field>
        {m.error && !Object.keys(err).length && <p className="text-sm text-danger">{(m.error as Error).message}</p>}
        <Button size="lg" className="w-full" loading={m.isPending} disabled={!f.name || !f.union || (noUnion && !covered.length) || !f.address || !loc} onClick={() => m.mutate()}>
          ارسال درخواست فعال‌سازی
        </Button>
      </Card>
    </div>
  );
}
