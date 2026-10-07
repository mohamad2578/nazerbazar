import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, Download, FileSpreadsheet, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Badge, Button, Card, DataTable, Empty, Loading, PageHeader, useToast } from "../../components/ui";
import { api, download } from "../../lib/api";
import { num, toman } from "../../lib/format";

type Change = {
  row: number; product: number; product_name: string; union_name: string;
  current_price: number; new_price: number; max_discount_percent: number; note: string; unchanged: boolean;
};
type Result = { dry_run: boolean; total_rows: number; changes: Change[]; errors: { row: number; error: string }[]; skipped: number; applied: number };

/** بارگذاری گروهی نرخ مصوب از فایل اکسل — اداره صمت و استانداری. */
export default function PriceUpload() {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Result | null>(null);
  const [done, setDone] = useState<Result | null>(null);

  const tpl = useMutation({
    mutationFn: () => download("/prices/bulk-template/", `نرخ-مصوب-${new Date().toISOString().slice(0, 10)}.xlsx`),
    onSuccess: () => toast("فایل اکسل دانلود شد؛ ستون «نرخ جدید» را پر کنید."),
    onError: (e: Error) => toast(e.message, "danger"),
  });

  const send = useMutation({
    mutationFn: ({ f, dry }: { f: File; dry: boolean }) => {
      const fd = new FormData();
      fd.set("file", f);
      if (dry) fd.set("dry_run", "true");
      return api.post<Result>("/prices/bulk-upload/", fd);
    },
    onSuccess: (d, v) => {
      if (v.dry) setPreview(d);
      else {
        setDone(d);
        setPreview(null);
        setFile(null);
        toast(`${num(d.applied)} نرخ اعمال شد`);
      }
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });

  const pick = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setDone(null);
    send.mutate({ f, dry: true });
  };

  const effective = preview?.changes.filter((c) => !c.unchanged) ?? [];

  return (
    <div className="space-y-5">
      <PageHeader title="بارگذاری نرخ‌های مصوب" subtitle="نرخ کالاهای حوزه خود را گروهی با فایل اکسل ثبت کنید." />

      <Card className="p-5">
        <div className="flex items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-brand-soft text-brand"><FileSpreadsheet className="size-6" /></span>
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold">۱) دریافت فایل اکسل</h2>
            <p className="mt-1 text-sm text-muted">
              فایل شامل همه کالاهای حوزه شما به‌همراه نرخ فعلی است. فقط ستون «نرخ جدید (ریال)» را برای
              کالاهایی که می‌خواهید تغییر کند پر کنید؛ بقیه را خالی بگذارید.
            </p>
            <Button className="mt-3" variant="secondary" icon={<Download className="size-4" />} loading={tpl.isPending} onClick={() => tpl.mutate()}>
              دانلود فایل اکسل
            </Button>
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <div className="flex items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-warn-soft text-warn"><Upload className="size-6" /></span>
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold">۲) بارگذاری فایل تکمیل‌شده</h2>
            <p className="mt-1 text-sm text-muted">ابتدا پیش‌نمایش تغییرات را نشانتان می‌دهیم؛ اعمال فقط با تایید شما انجام می‌شود.</p>
            <input ref={fileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
            <Button className="mt-3" icon={<FileSpreadsheet className="size-4" />} loading={send.isPending && !!preview === false} onClick={() => fileRef.current?.click()}>
              {file ? file.name : "انتخاب فایل اکسل"}
            </Button>
          </div>
        </div>

        {send.isPending && !preview && <Loading label="در حال بررسی فایل…" />}

        {preview && (
          <div className="mt-5 border-t border-line pt-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge tone="brand">{num(effective.length)} نرخ برای تغییر</Badge>
              {preview.changes.length - effective.length > 0 && <Badge>{num(preview.changes.length - effective.length)} بدون تغییر</Badge>}
              {preview.skipped > 0 && <Badge>{num(preview.skipped)} ردیف خالی</Badge>}
              {preview.errors.length > 0 && <Badge tone="danger">{num(preview.errors.length)} خطا</Badge>}
            </div>

            {preview.errors.length > 0 && (
              <div className="mb-3 space-y-1 rounded-xl bg-danger-soft p-3 text-xs text-danger">
                {preview.errors.slice(0, 10).map((e, i) => (
                  <div key={i} className="flex items-start gap-1.5">
                    <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> ردیف {num(e.row)}: {e.error}
                  </div>
                ))}
              </div>
            )}

            {effective.length ? (
              <>
                <div className="overflow-hidden rounded-xl border border-line">
                  <DataTable<Change & { id: number }>
                    rows={effective.map((c) => ({ ...c, id: c.row }))}
                    columns={[
                      { key: "product_name", label: "کالا" },
                      { key: "union_name", label: "اتحادیه" },
                      { key: "current_price", label: "نرخ فعلی", render: (c) => toman(c.current_price) },
                      { key: "new_price", label: "نرخ جدید", render: (c) => <b className="tabular">{toman(c.new_price)}</b> },
                      {
                        key: "diff", label: "تغییر",
                        render: (c) => {
                          if (!c.current_price) return <Badge tone="brand">نرخ اولیه</Badge>;
                          const pct = ((c.new_price - c.current_price) / c.current_price) * 100;
                          const up = pct > 0;
                          return (
                            <span className={`inline-flex items-center gap-0.5 ${up ? "text-danger" : "text-ok"}`}>
                              {up ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />}{num(Math.abs(pct), 1)}٪
                            </span>
                          );
                        },
                      },
                    ]}
                  />
                </div>
                <Button
                  className="mt-4"
                  loading={send.isPending}
                  onClick={() => file && send.mutate({ f: file, dry: false })}
                >
                  اعمال {num(effective.length)} نرخ
                </Button>
                <p className="mt-2 text-xs text-muted">
                  با اعمال، قیمت فروشگاه‌ها هم‌تراز نرخ جدید می‌شود و به آن‌ها اعلان می‌رود.
                </p>
              </>
            ) : (
              <Empty title="تغییری برای اعمال پیدا نشد">ستون «نرخ جدید (ریال)» را در فایل پر کرده‌اید؟</Empty>
            )}
          </div>
        )}

        {done && (
          <div className="mt-4 flex items-start gap-2 rounded-2xl border border-ok/30 bg-ok-soft p-4 text-sm text-ok">
            <CheckCircle2 className="mt-0.5 size-5 shrink-0" />
            <div>
              <p className="font-medium">{num(done.applied)} نرخ مصوب با موفقیت اعمال شد.</p>
              <p className="mt-1 text-xs">قیمت فروشگاه‌های مربوط هم‌تراز شد و اعلان به‌روزرسانی برایشان ارسال گردید.</p>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
