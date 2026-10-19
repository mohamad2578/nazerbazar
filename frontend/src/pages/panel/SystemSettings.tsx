import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, ChartColumn, Save, Store, Tags } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Card, cx, Loading, PageHeader, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { dateTime } from "../../lib/format";
import { type SystemSettings as SettingsT, useSystemSettings } from "../../lib/settings";

/** تنظیمات سامانه (فقط مدیر کل). */
export default function SystemSettings() {
  const q = useSystemSettings();
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState<SettingsT | null>(null);
  useEffect(() => { if (q.data) setF(q.data); }, [q.data]);

  const save = useMutation({
    mutationFn: () => api.patch<SettingsT>("/settings/", {
      union_can_set_prices: f!.union_can_set_prices,
      snap_store_prices: f!.snap_store_prices,
      union_sections: f!.union_sections,
      samt_reports: f!.samt_reports,
    }),
    onSuccess: (d) => { qc.setQueryData(["system-settings"], d); toast("تنظیمات ذخیره شد"); },
    onError: (e: Error) => toast(e.message, "danger"),
  });

  if (!f) return <Loading />;
  const toggle = (field: "union_sections" | "samt_reports", key: string) =>
    setF({ ...f, [field]: f[field].includes(key) ? f[field].filter((k) => k !== key) : [...f[field], key] });

  return (
    <div className="space-y-4">
      <PageHeader title="تنظیمات سامانه" subtitle={f.updated_by ? `آخرین تغییر: ${f.updated_by} · ${dateTime(f.updated_at)}` : undefined}
        actions={<Button icon={<Save className="size-4" />} loading={save.isPending} onClick={() => save.mutate()}>ذخیره تنظیمات</Button>} />

      <Section icon={<Tags className="size-5" />} title="ثبت حداکثر قیمت توسط اتحادیه">
        <Choice checked={f.union_can_set_prices} onChange={() => setF({ ...f, union_can_set_prices: true })}
          title="مجاز است" desc="اتحادیه حداکثر قیمت کالاهای خود را ثبت یا تغییر می‌دهد؛ قیمت پس از تایید اتاق اصناف اعمال می‌شود." />
        <Choice checked={!f.union_can_set_prices} onChange={() => setF({ ...f, union_can_set_prices: false })}
          title="مجاز نیست" desc="فقط اداره صمت، اتاق اصناف، استانداری و مدیر کل حداکثر قیمت را تعیین می‌کنند." />
      </Section>

      <Section icon={<Store className="size-5" />} title="قیمت فروشگاه‌ها پس از تغییر حداکثر قیمت">
        <Choice checked={f.snap_store_prices} onChange={() => setF({ ...f, snap_store_prices: true })}
          title="قیمت همه فروشگاه‌ها برابر حداکثر قیمت جدید شود"
          desc="فروشگاه‌ها می‌توانند دوباره وارد پنل شوند و قیمت کمتری (تا سقف تخفیف مجاز) بدهند." />
        <Choice checked={!f.snap_store_prices} onChange={() => setF({ ...f, snap_store_prices: false })}
          title="آخرین قیمت هر فروشگاه حفظ شود"
          desc="فقط قیمتی که از بازه مجاز جدید بیرون بیفتد به نزدیک‌ترین حد مجاز (سقف یا کف) آورده می‌شود." />
      </Section>

      <Section icon={<Building2 className="size-5" />} title="بخش‌های در دسترس پنل اتحادیه"
        hint="بخش‌های خاموش از منوی اتحادیه حذف می‌شوند و سرور هم درخواست آن‌ها را رد می‌کند.">
        <Checks items={f.sections} selected={f.union_sections} onToggle={(k) => toggle("union_sections", k)} />
      </Section>

      <Section icon={<ChartColumn className="size-5" />} title="گزارش‌های قابل مشاهده برای اداره صمت"
        hint="گزارش‌های خاموش در داشبورد و منوی اداره صمت نمایش داده نمی‌شوند.">
        <Checks items={f.reports} selected={f.samt_reports} onToggle={(k) => toggle("samt_reports", k)} />
      </Section>

      <div className="flex justify-end">
        <Button icon={<Save className="size-4" />} loading={save.isPending} onClick={() => save.mutate()}>ذخیره تنظیمات</Button>
      </div>
    </div>
  );
}

function Section({ icon, title, hint, children }: { icon: React.ReactNode; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <Card className="p-4 sm:p-5">
      <div className="mb-3 flex items-center gap-2">
        <span className="grid size-9 place-items-center rounded-xl bg-brand-soft text-brand">{icon}</span>
        <div>
          <h2 className="font-semibold">{title}</h2>
          {hint && <p className="text-xs text-muted">{hint}</p>}
        </div>
      </div>
      <div className="space-y-2">{children}</div>
    </Card>
  );
}

function Choice({ checked, onChange, title, desc }: { checked: boolean; onChange: () => void; title: string; desc: string }) {
  return (
    <label className={cx("flex cursor-pointer items-start gap-3 rounded-xl border p-3", checked ? "border-brand bg-brand-soft/50" : "border-line")}>
      <input type="radio" className="mt-1 size-4" checked={checked} onChange={onChange} />
      <span>
        <span className="block text-sm font-medium">{title}</span>
        <span className="block text-xs leading-6 text-muted">{desc}</span>
      </span>
    </label>
  );
}

function Checks({ items, selected, onToggle }: { items: { key: string; label: string }[]; selected: string[]; onToggle: (k: string) => void }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {items.map((it) => (
        <label key={it.key} className={cx("flex cursor-pointer items-center gap-2 rounded-xl border p-3 text-sm", selected.includes(it.key) ? "border-brand bg-brand-soft/50" : "border-line")}>
          <input type="checkbox" className="size-4" checked={selected.includes(it.key)} onChange={() => onToggle(it.key)} />
          {it.label}
        </label>
      ))}
    </div>
  );
}
