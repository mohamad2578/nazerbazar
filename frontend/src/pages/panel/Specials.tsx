import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgePercent, Info, Package, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import ImageUpload from "../../components/ImageUpload";
import { Badge, Button, Card, Empty, Field, Input, Loading, PageHeader, Select, Sheet, Textarea, useToast } from "../../components/ui";
import { api, fieldErrors, type Page } from "../../lib/api";
import { num, toman, toRial, toToman } from "../../lib/format";

type Special = {
  id: number; name: string; description: string; image: string | null; brand: string; unit: string; unit_display: string;
  price: number; old_price: number | null; discount_percent: number | null;
  is_active: boolean; is_available: boolean; status: string; status_display: string; review_note: string;
};

const UNITS = [["piece", "عدد"], ["kg", "کیلوگرم"], ["g", "گرم"], ["pack", "بسته"], ["l", "لیتر"], ["m", "متر"], ["service", "خدمت"]];
const TONE: Record<string, "warn" | "ok" | "danger"> = { pending: "warn", approved: "ok", rejected: "danger" };

/** «تخفیفات ویژه» در پنل فروشگاه: هر محصولی با قیمت اصلی و درصد تخفیف؛ پس از تایید صمت عمومی می‌شود. */
export default function Specials() {
  const [editing, setEditing] = useState<Special | "new" | null>(null);
  const q = useQuery({ queryKey: ["specials"], queryFn: () => api.get<Page<Special>>("/shop-products/", { is_special: true, page_size: 100 }) });
  const rows = q.data?.results ?? [];
  return (
    <div className="space-y-4">
      <PageHeader title="تخفیفات ویژه" subtitle="محصول خود را با قیمت اصلی و درصد تخفیف ثبت کنید."
        actions={<Button size="sm" icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>تخفیف جدید</Button>} />
      <Card className="flex items-start gap-2 border-brand/30 bg-brand-soft/60 p-3 text-xs leading-6 text-brand">
        <Info className="mt-0.5 size-4 shrink-0" />
        <span>هر تخفیف پس از تایید کارشناس اداره صمت در صفحه «تخفیفات فروشگاه‌ها» به مردم نمایش داده می‌شود. اگر قیمت یا تخفیف را تغییر دهید، دوباره به تایید نیاز دارد.</span>
      </Card>
      {q.isLoading ? <Loading /> : !rows.length ? (
        <Card><Empty title="هنوز تخفیفی ثبت نکرده‌اید" icon={<BadgePercent className="size-7" />} /></Card>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <Card key={r.id} className="flex items-center gap-3 p-3">
              {r.image ? <img src={r.image} alt="" className="size-14 shrink-0 rounded-xl object-contain bg-surface-2" />
                : <span className="grid size-14 shrink-0 place-items-center rounded-xl bg-surface-2 text-muted"><Package className="size-6" /></span>}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="truncate font-medium">{r.name}</span>
                  <Badge tone={TONE[r.status]}>{r.status_display}</Badge>
                  {!r.is_active && <Badge>پنهان</Badge>}
                </div>
                <div className="mt-0.5 text-xs text-muted">
                  <span className="line-through tabular">{toman(r.old_price)}</span>
                  {" ← "}<b className="tabular text-ok">{toman(r.price)}</b>
                  {r.discount_percent ? <> · {num(r.discount_percent)}٪ تخفیف</> : null}
                </div>
                {r.review_note && <div className="mt-0.5 text-xs text-danger">نتیجه بررسی: {r.review_note}</div>}
              </div>
              <button onClick={() => setEditing(r)} className="grid size-9 place-items-center rounded-lg hover:bg-surface-2" aria-label="ویرایش"><Pencil className="size-4" /></button>
            </Card>
          ))}
        </div>
      )}
      {editing && <SpecialForm item={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function SpecialForm({ item, onClose }: { item: Special | null; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState(() => ({
    name: item?.name ?? "", brand: item?.brand ?? "", description: item?.description ?? "", unit: item?.unit ?? "piece",
    original: item?.old_price ? String(toToman(item.old_price)) : "",
    percent: item?.discount_percent ? String(item.discount_percent) : "",
    is_available: item?.is_available ?? true, is_active: item?.is_active ?? true,
  }));
  const [image, setImage] = useState<File | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const original = f.original ? toRial(f.original) : 0;
  const pct = Math.min(90, Math.max(0, Number(f.percent) || 0));
  // قیمت نهایی به نزدیک‌ترین ۱۰۰ تومان گرد می‌شود
  const final = original && pct ? Math.round((original * (100 - pct)) / 100 / 1000) * 1000 : 0;

  const save = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.set("name", f.name);
      fd.set("brand", f.brand);
      fd.set("description", f.description);
      fd.set("unit", f.unit);
      fd.set("old_price", String(original));
      fd.set("price", String(final));
      fd.set("is_special", "true");
      fd.set("is_active", String(f.is_active));
      fd.set("is_available", String(f.is_available));
      if (image) fd.set("image", image);
      return item ? api.patch(`/shop-products/${item.id}/`, fd) : api.post("/shop-products/", fd);
    },
    onSuccess: () => {
      toast("ثبت شد؛ پس از تایید اداره صمت نمایش داده می‌شود");
      qc.invalidateQueries({ queryKey: ["specials"] });
      onClose();
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/shop-products/${item!.id}/`),
    onSuccess: () => { toast("حذف شد"); qc.invalidateQueries({ queryKey: ["specials"] }); onClose(); },
  });
  const err = fieldErrors(save.error);
  const ready = f.name.trim() && original > 0 && pct >= 1 && final > 0;

  return (
    <Sheet open onClose={onClose} title={item ? "ویرایش تخفیف" : "تخفیف ویژه جدید"}
      footer={
        <div className="flex w-full gap-2">
          <Button className="flex-1" loading={save.isPending} disabled={!ready} onClick={() => save.mutate()}>ثبت و ارسال برای تایید</Button>
          {item && <Button variant="danger" loading={remove.isPending} onClick={() => confirm("این تخفیف حذف شود؟") && remove.mutate()}><Trash2 className="size-4" /></Button>}
        </div>
      }>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="تصویر محصول" className="sm:col-span-2"><ImageUpload value={item?.image} onChange={setImage} aspect="4/3" /></Field>
        <Field label="نام محصول" error={err.name} className="sm:col-span-2"><Input value={f.name} onChange={set("name")} /></Field>
        <Field label="برند (اختیاری)"><Input value={f.brand} onChange={set("brand")} /></Field>
        <Field label="واحد">
          <Select value={f.unit} onChange={set("unit")}>{UNITS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>
        </Field>
        <Field label="قیمت اصلی (تومان)" error={err.old_price}><Input value={f.original} onChange={set("original")} inputMode="numeric" dir="ltr" /></Field>
        <Field label="درصد تخفیف" hint="بین ۱ تا ۹۰"><Input value={f.percent} onChange={set("percent")} inputMode="numeric" dir="ltr" /></Field>
        <div className="rounded-xl bg-surface-2 p-3 text-sm sm:col-span-2">
          قیمت با تخفیف: <b className="tabular text-ok">{final ? toman(final) : "—"}</b>
        </div>
        <Field label="توضیحات (اختیاری)" className="sm:col-span-2"><Textarea value={f.description} onChange={set("description")} className="min-h-16" /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4" checked={f.is_available} onChange={(e) => setF({ ...f, is_available: e.target.checked })} /> موجود است</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> نمایش داده شود</label>
      </div>
    </Sheet>
  );
}
