import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, FileText, Percent } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorBox, Field, Input, Loading, PageHeader, PriceInput, Select, useToast } from "../../../components/ui";
import { api, fieldErrors } from "../../../lib/api";
import { toIntRial } from "../../../lib/erp";
import { toToman } from "../../../lib/format";

type S = {
  vat_percent: number; delivery_fee: number; free_delivery_over: number | null; economic_code: string; national_id: string; postal_code: string;
  invoice_prefix: string; invoice_footer: string; gateway_provider: string; gateway_merchant: string; gateway_sandbox: boolean; gateway_active: boolean;
  own_gateway: boolean; store_name: string; next_invoice: string;
};

/** تنظیمات مالی فروشگاه ویژه: مالیات، هزینه ارسال، مشخصات فاکتور و درگاه پرداخت اختصاصی. */
export default function ErpSettings() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["erp-settings"], queryFn: () => api.get<S>("/erp/settings/") });
  const [f, setF] = useState<Record<string, string | boolean>>({});
  useEffect(() => {
    const s = q.data;
    if (!s) return;
    setF({
      vat_percent: String(s.vat_percent), delivery_fee: s.delivery_fee ? String(toToman(s.delivery_fee)) : "", free_over: s.free_delivery_over ? String(toToman(s.free_delivery_over)) : "",
      economic_code: s.economic_code, national_id: s.national_id, postal_code: s.postal_code, invoice_prefix: s.invoice_prefix, invoice_footer: s.invoice_footer,
      gateway_provider: s.gateway_provider, gateway_merchant: s.gateway_merchant, gateway_sandbox: s.gateway_sandbox, gateway_active: s.gateway_active,
    });
  }, [q.data]);
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const m = useMutation({
    mutationFn: () => api.patch<S>("/erp/settings/", {
      vat_percent: Number(f.vat_percent || 0), delivery_fee: toIntRial(String(f.delivery_fee || "0")),
      free_delivery_over: f.free_over ? toIntRial(String(f.free_over)) : null,
      economic_code: f.economic_code, national_id: f.national_id, postal_code: f.postal_code, invoice_prefix: f.invoice_prefix, invoice_footer: f.invoice_footer,
      gateway_provider: f.gateway_provider, gateway_merchant: String(f.gateway_merchant).trim(), gateway_sandbox: f.gateway_sandbox, gateway_active: f.gateway_active,
    }),
    onSuccess: () => { toast("تنظیمات ذخیره شد"); qc.invalidateQueries({ queryKey: ["erp-settings"] }); },
  });
  const err = fieldErrors(m.error);
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  return (
    <div className="space-y-4">
      <PageHeader title="تنظیمات مالی و فاکتور" subtitle={`فروشگاه: ${q.data!.store_name} — شماره فاکتور بعدی: ${q.data!.next_invoice}`}
        actions={<Button size="sm" loading={m.isPending} onClick={() => m.mutate()}>ذخیره همه تغییرها</Button>} />

      <Card className="space-y-4 p-4">
        <h2 className="flex items-center gap-2 font-semibold"><Percent className="size-5 text-brand" /> مالیات و هزینه ارسال</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="مالیات بر ارزش افزوده (٪)" hint="۰ = بدون مالیات (اقلام اساسی معمولا معاف است)" error={err.vat_percent}><Input type="number" min={0} max={30} value={String(f.vat_percent ?? "")} onChange={set("vat_percent")} dir="ltr" className="text-left" /></Field>
          <Field label="هزینه ارسال با پیک" hint="از مشتری دریافت و در فاکتور نمایش داده می‌شود"><PriceInput value={String(f.delivery_fee ?? "")} onChange={(v) => setF({ ...f, delivery_fee: v })} /></Field>
          <Field label="ارسال رایگان برای خرید بالاتر از" hint="خالی = همیشه هزینه ارسال"><PriceInput value={String(f.free_over ?? "")} onChange={(v) => setF({ ...f, free_over: v })} /></Field>
        </div>
      </Card>

      <Card className="space-y-4 p-4">
        <h2 className="flex items-center gap-2 font-semibold"><FileText className="size-5 text-brand" /> مشخصات فاکتور</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="کد اقتصادی"><Input value={String(f.economic_code ?? "")} onChange={set("economic_code")} dir="ltr" className="text-left" /></Field>
          <Field label="شناسه ملی / کد ملی"><Input value={String(f.national_id ?? "")} onChange={set("national_id")} dir="ltr" className="text-left" /></Field>
          <Field label="کد پستی"><Input value={String(f.postal_code ?? "")} onChange={set("postal_code")} dir="ltr" className="text-left" /></Field>
          <Field label="پیشوند شماره فاکتور" hint="مثلا NZ ← NZ000001"><Input value={String(f.invoice_prefix ?? "")} onChange={set("invoice_prefix")} dir="ltr" className="text-left" maxLength={8} /></Field>
          <Field label="متن پاورقی فاکتور" className="sm:col-span-2"><Input value={String(f.invoice_footer ?? "")} onChange={set("invoice_footer")} placeholder="مثلا: کالای فروخته‌شده تا ۷ روز قابل مرجوع است" /></Field>
        </div>
      </Card>

      <Card className="space-y-4 p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 font-semibold"><CreditCard className="size-5 text-brand" /> درگاه پرداخت اختصاصی</h2>
          {q.data!.own_gateway ? <Badge tone="ok">فعال</Badge> : <Badge>از درگاه سامانه استفاده می‌شود</Badge>}
        </div>
        <p className="text-xs leading-6 text-muted">
          با فعال‌کردن درگاه خودتان، پرداخت اینترنتی سفارش‌های همین فروشگاه <b>مستقیم به حساب شما</b> واریز می‌شود (نه حساب سامانه).
          کد پذیرنده را از پنل درگاه (زرین‌پال یا زیبال) بردارید. قبل از فعال‌سازی نهایی، یک سفارش آزمایشی با حالت آزمایشی انجام دهید.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="درگاه"><Select value={String(f.gateway_provider ?? "")} onChange={set("gateway_provider")}>
            <option value="">درگاه پیش‌فرض سامانه</option><option value="zarinpal">زرین‌پال</option><option value="zibal">زیبال</option></Select></Field>
          <Field label="کد پذیرنده (Merchant ID)" error={err.gateway_merchant} hint="زیبال: برای آزمایش کد «zibal»"><Input value={String(f.gateway_merchant ?? "")} onChange={set("gateway_merchant")} dir="ltr" className="text-left" /></Field>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4" checked={!!f.gateway_sandbox} onChange={(e) => setF({ ...f, gateway_sandbox: e.target.checked })} /> حالت آزمایشی (sandbox) — فقط برای زرین‌پال</label>
        <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" className="size-4" checked={!!f.gateway_active} onChange={(e) => setF({ ...f, gateway_active: e.target.checked })} /> درگاه اختصاصی فعال باشد</label>
      </Card>
      {m.error && !Object.keys(err).length && <p className="text-sm text-danger">{(m.error as Error).message}</p>}
      <Button className="w-full sm:w-auto" loading={m.isPending} onClick={() => m.mutate()}>ذخیره همه تغییرها</Button>
    </div>
  );
}
