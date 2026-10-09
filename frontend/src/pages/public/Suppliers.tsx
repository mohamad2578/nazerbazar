import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Truck } from "lucide-react";
import { useState } from "react";
import { Button, Card, Field, Input, PageHeader, Textarea } from "../../components/ui";
import { api, fieldErrors } from "../../lib/api";
import { toEn } from "../../lib/format";

/** فرم ثبت‌نام تامین‌کنندگان؛ برای همه بدون نیاز به ورود. */
export default function Suppliers() {
  const [f, setF] = useState({ first_name: "", last_name: "", mobile: "", product_type: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const m = useMutation({
    mutationFn: () => api.post("/public/suppliers/", { ...f, mobile: toEn(f.mobile) }),
  });
  const err = fieldErrors(m.error);

  if (m.isSuccess) {
    return (
      <Card className="mx-auto max-w-md p-6 text-center">
        <CheckCircle2 className="mx-auto size-14 text-ok" />
        <h1 className="mt-3 text-lg font-bold">درخواست شما ثبت شد</h1>
        <p className="mt-1 text-sm text-muted">کارشناسان اداره صمت با شماره شما تماس می‌گیرند.</p>
      </Card>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <PageHeader title="ثبت‌نام تامین‌کنندگان" subtitle="اگر کالای اساسی تامین می‌کنید، مشخصات خود را ثبت کنید." />
      <Card className="p-5">
        <div className="mb-4 flex items-start gap-3 text-sm text-muted">
          <Truck className="mt-0.5 size-5 shrink-0 text-brand" />
          <span>اطلاعات شما فقط برای اداره صمت و مسئولان تامین کالا نمایش داده می‌شود.</span>
        </div>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
          <Field label="نام" error={err.first_name}><Input value={f.first_name} onChange={set("first_name")} required /></Field>
          <Field label="نام خانوادگی" error={err.last_name}><Input value={f.last_name} onChange={set("last_name")} required /></Field>
          <Field label="شماره تماس" error={err.mobile}>
            <Input value={f.mobile} onChange={set("mobile")} dir="ltr" inputMode="tel" placeholder="۰۹۱۲۳۴۵۶۷۸۹" required />
          </Field>
          <div />
          <Field label="نوع کالایی که می‌توانید تامین کنید" error={err.product_type} className="sm:col-span-2">
            <Textarea value={f.product_type} onChange={set("product_type")} placeholder="مثلا: برنج پاکستانی، روغن، لبنیات" className="min-h-20" required />
          </Field>
          {m.error && !Object.keys(err).length && <p className="text-sm text-danger sm:col-span-2">{(m.error as Error).message}</p>}
          <Button type="submit" size="lg" className="w-full sm:col-span-2" loading={m.isPending}>ثبت درخواست</Button>
        </form>
      </Card>
    </div>
  );
}
