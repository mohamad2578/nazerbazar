import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Database, Download, FileUp, History, ShieldCheck, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Badge, Button, Card, Loading, PageHeader, useToast } from "../../components/ui";
import { api, download, fieldErrors } from "../../lib/api";
import { dateTime, num } from "../../lib/format";

type Info = { version: number | null; created_at: string | null; counts: Record<string, number>; media_files: number };

/** برچسب فارسی جدول‌ها برای نمایش در فهرست شمارش رکوردها */
const LABELS: Record<string, string> = {
  "accounts.user": "کاربران",
  "orgs.province": "استان‌ها",
  "orgs.county": "شهرستان‌ها",
  "orgs.chamber": "اتاق‌های اصناف",
  "orgs.union": "اتحادیه‌ها",
  "orgs.store": "فروشگاه‌ها",
  "market.category": "دسته‌بندی کالا",
  "market.product": "کالاهای اساسی",
  "market.officialprice": "تاریخچه نرخ مصوب",
  "market.storeoffer": "قیمت فروشگاه‌ها",
  "market.offerlog": "سوابق قیمت",
  "market.review": "نظرات",
  "market.dailysnapshot": "آمار روزانه",
  "shop.shopcategory": "دسته محصولات فروشگاهی",
  "shop.shopproduct": "محصولات فروشگاه اینترنتی",
  "shop.order": "سفارش‌ها",
  "shop.orderitem": "اقلام سفارش",
  "shop.orderevent": "سوابق سفارش",
  "complaints.complaint": "شکایات",
  "complaints.complaintevent": "سوابق شکایات",
  "observatory.commodity": "کالاهای اساسی (رصدخانه)",
  "observatory.commodityreport": "گزارش‌های تامین و قیمت",
  "observatory.alert": "هشدارها",
  "distribution.allocation": "تخصیص‌ها",
  "distribution.allocationshare": "سهم اتحادیه‌ها",
  "distribution.quota": "سهمیه فروشگاه‌ها",
  "distribution.quotaevent": "سوابق سهمیه",
  "cms.slide": "اسلایدهای صفحه اصلی",
};

const label = (k: string) => LABELS[k] ?? k;

/** پشتیبان‌گیری و بازیابی اطلاعات سامانه — فقط مدیر کل. */
export default function Backup() {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [info, setInfo] = useState<Info | null>(null);
  const [withMedia, setWithMedia] = useState(true);
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<{ restored: number; media_files: number; snapshot: string } | null>(null);

  const status = useQuery({ queryKey: ["backup-status"], queryFn: () => api.get<{ counts: Record<string, number> }>("/backup/status/") });

  const dl = useMutation({
    mutationFn: () => download("/backup/download/", `nazer724-backup-${new Date().toISOString().slice(0, 10)}.zip`),
    onSuccess: () => toast("فایل پشتیبان دانلود شد"),
    onError: (e: Error) => toast(e.message, "danger"),
  });

  const inspect = useMutation({
    mutationFn: (f: File) => {
      const fd = new FormData();
      fd.set("file", f);
      return api.post<Info>("/backup/inspect/", fd);
    },
    onSuccess: (d) => setInfo(d),
    onError: (e: Error) => {
      setInfo(null);
      toast(e.message, "danger");
    },
  });

  const restore = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.set("file", file!);
      fd.set("confirm", "true");
      fd.set("with_media", String(withMedia));
      return api.post<{ restored: number; media_files: number; snapshot: string }>("/backup/restore/", fd);
    },
    onSuccess: (d) => {
      setResult(d);
      setFile(null);
      setInfo(null);
      setConfirmed(false);
      status.refetch();
      toast("بازیابی با موفقیت انجام شد");
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const err = fieldErrors(restore.error);

  const pick = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setResult(null);
    setConfirmed(false);
    inspect.mutate(f);
  };

  const counts = status.data?.counts ?? {};
  const totalRecords = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-5">
      <PageHeader
        title="پشتیبان‌گیری و بازیابی"
        subtitle="تهیه نسخه پشتیبان کامل از اطلاعات سامانه و بازگرداندن آن در صورت نیاز."
      />

      {/* ── تهیه پشتیبان ── */}
      <Card className="p-5">
        <div className="flex items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-brand-soft text-brand"><Database className="size-6" /></span>
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold">تهیه نسخه پشتیبان</h2>
            <p className="mt-1 text-sm text-muted">
              یک فایل ZIP شامل تمام اطلاعات سامانه (کاربران، اتحادیه‌ها، فروشگاه‌ها، کالاها و نرخ‌ها، سفارش‌ها،
              شکایات و تصاویر آپلودشده) دریافت می‌کنید. آن را در جای امن نگه دارید.
            </p>
            <Button className="mt-3" icon={<Download className="size-4" />} loading={dl.isPending} onClick={() => dl.mutate()}>
              دانلود فایل پشتیبان
            </Button>
          </div>
        </div>

        {status.isLoading ? <Loading /> : (
          <div className="mt-5 border-t border-line pt-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-medium">اطلاعات فعلی سامانه</h3>
              <Badge tone="brand">{num(totalRecords)} رکورد</Badge>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
              {Object.entries(counts).filter(([, v]) => v > 0).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-2 border-b border-line/60 py-1">
                  <span className="truncate text-muted">{label(k)}</span>
                  <b className="tabular">{num(v)}</b>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* ── بازیابی ── */}
      <Card className="p-5">
        <div className="flex items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-warn-soft text-warn"><Upload className="size-6" /></span>
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold">بازیابی از فایل پشتیبان</h2>
            <p className="mt-1 text-sm text-muted">
              فایل پشتیبانی که قبلا دانلود کرده‌اید را انتخاب کنید. ابتدا محتوای آن را نشانتان می‌دهیم و
              بازیابی فقط با تایید شما انجام می‌شود.
            </p>
          </div>
        </div>

        <div className="mt-4">
          <input ref={fileRef} type="file" accept=".zip" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
          <Button variant="secondary" icon={<FileUp className="size-4" />} loading={inspect.isPending} onClick={() => fileRef.current?.click()}>
            {file ? file.name : "انتخاب فایل پشتیبان (ZIP)"}
          </Button>
          {err.file && <p className="mt-2 text-sm text-danger">{err.file}</p>}
        </div>

        {info && (
          <div className="mt-4 space-y-3 rounded-2xl border border-line bg-surface-2 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="inline-flex items-center gap-1.5"><History className="size-4 text-muted" /> ساخته‌شده در {dateTime(info.created_at)}</span>
              <Badge>{num(info.media_files)} فایل تصویر</Badge>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
              {Object.entries(info.counts).filter(([, v]) => v > 0).map(([k, v]) => {
                const current = counts[k] ?? 0;
                const diff = v - current;
                return (
                  <div key={k} className="flex justify-between gap-2 border-b border-line/60 py-1">
                    <span className="truncate text-muted">{label(k)}</span>
                    <span className="shrink-0 tabular">
                      <b>{num(v)}</b>
                      {diff !== 0 && <span className={diff > 0 ? "text-ok" : "text-danger"}> ({diff > 0 ? "+" : ""}{num(diff)})</span>}
                    </span>
                  </div>
                );
              })}
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="size-4" checked={withMedia} onChange={(e) => setWithMedia(e.target.checked)} />
              بازگرداندن تصاویر و فایل‌های پیوست
            </label>

            <div className="flex items-start gap-2 rounded-xl bg-warn-soft p-3 text-xs leading-6 text-warn">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <span>
                رکوردهای فعلی با همان شناسه، با اطلاعات این فایل بازنویسی می‌شوند. پیش از شروع، به‌صورت خودکار یک
                نسخه پشتیبان از وضعیت فعلی گرفته می‌شود تا در صورت اشتباه قابل برگشت باشد.
              </span>
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="size-4" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
              تایید می‌کنم که اطلاعات فعلی با محتوای این فایل جایگزین شود.
            </label>

            <Button variant="danger" disabled={!confirmed} loading={restore.isPending} onClick={() => restore.mutate()}>
              شروع بازیابی
            </Button>
          </div>
        )}

        {result && (
          <div className="mt-4 flex items-start gap-2 rounded-2xl border border-ok/30 bg-ok-soft p-4 text-sm text-ok">
            <ShieldCheck className="mt-0.5 size-5 shrink-0" />
            <div>
              <p className="font-medium">بازیابی کامل شد.</p>
              <p className="mt-1">{num(result.restored)} رکورد و {num(result.media_files)} فایل بازگردانده شد.</p>
              <p className="mt-1 text-xs">نسخه پشتیبان خودکار پیش از بازیابی: <span dir="ltr">{result.snapshot}</span></p>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
