import { useMutation, useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useState } from "react";
import { Button, Card, Field, Input, Loading, PageHeader, useToast } from "../../components/ui";
import { api, fieldErrors } from "../../lib/api";
import { useAuth } from "../../lib/auth";

const LocationPicker = lazy(() => import("../../components/MapView").then((m) => ({ default: m.LocationPicker })));

export default function StoreProfile() {
  const { reload } = useAuth();
  const toast = useToast();
  const q = useQuery({ queryKey: ["my-store"], queryFn: () => api.get("/my-store/") });
  const [f, setF] = useState<any>(null);
  useEffect(() => { if (q.data) setF(q.data); }, [q.data]);
  const m = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      ["name", "license_no", "phone", "address", "working_hours", "lat", "lng"].forEach((k) => f[k] != null && fd.set(k, f[k]));
      if (f._photo) fd.set("photo", f._photo);
      if (f._license) fd.set("license_image", f._license);
      return api.patch("/my-store/", fd);
    },
    onSuccess: () => { toast("ذخیره شد"); reload(); },
  });
  const err = fieldErrors(m.error);
  if (!f) return <Loading />;
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <div className="space-y-4">
      <PageHeader title="مشخصات فروشگاه" subtitle={`اتحادیه: ${f.union_name} · وضعیت: ${f.status_display}`} />
      <Card className="space-y-4 p-4 sm:p-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="نام فروشگاه" error={err.name}><Input value={f.name} onChange={set("name")} /></Field>
          <Field label="شماره پروانه" error={err.license_no}><Input value={f.license_no} onChange={set("license_no")} dir="ltr" /></Field>
          <Field label="تلفن" error={err.phone}><Input value={f.phone} onChange={set("phone")} dir="ltr" /></Field>
          <Field label="ساعات کاری"><Input value={f.working_hours} onChange={set("working_hours")} /></Field>
          <Field label="نشانی" className="sm:col-span-2" error={err.address}><Input value={f.address} onChange={set("address")} /></Field>
          <Field label="تصویر فروشگاه"><input type="file" accept="image/*" onChange={(e) => setF({ ...f, _photo: e.target.files?.[0] })} className="text-sm" /></Field>
          <Field label="تصویر پروانه کسب"><input type="file" accept="image/*" onChange={(e) => setF({ ...f, _license: e.target.files?.[0] })} className="text-sm" /></Field>
        </div>
        <Field label="موقعیت روی نقشه">
          <Suspense fallback={<Loading />}>
            <LocationPicker value={f.lat ? { lat: +f.lat, lng: +f.lng } : null} onChange={(v) => setF({ ...f, lat: v.lat, lng: v.lng })} />
          </Suspense>
        </Field>
        <Button loading={m.isPending} onClick={() => m.mutate()}>ذخیره تغییرات</Button>
      </Card>
    </div>
  );
}
