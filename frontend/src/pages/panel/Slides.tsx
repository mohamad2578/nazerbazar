import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GripVertical, ImagePlus, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Field, Input, Loading, PageHeader, Sheet, useToast } from "../../components/ui";
import { api, fieldErrors } from "../../lib/api";

type SlideT = {
  id: number; title: string; subtitle: string; image: string; link_url: string; link_label: string; order: number; is_active: boolean;
};

/** مدیریت اسلایدهای بنر صفحه اصلی سایت عمومی (فقط مدیر کل) */
export default function Slides() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["slides-panel"], queryFn: () => api.get<SlideT[]>("/slides/") });
  const [editing, setEditing] = useState<SlideT | "new" | null>(null);
  const del = useMutation({
    mutationFn: (id: number) => api.del(`/slides/${id}/`),
    onSuccess: () => { toast("حذف شد"); qc.invalidateQueries({ queryKey: ["slides-panel"] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const rows = q.data ?? [];
  return (
    <div className="space-y-4">
      <PageHeader title="اسلایدهای صفحه اصلی" subtitle="بنرهای تبلیغاتی/اطلاع‌رسانی که در بالای صفحه اصلی سایت به‌صورت اسلایدشو نمایش داده می‌شوند." actions={<Button size="sm" icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>اسلاید جدید</Button>} />
      {q.isLoading ? <Loading /> : !rows.length ? <Card><Empty title="اسلایدی ثبت نشده است" icon={<ImagePlus className="size-7" />} /></Card> : (
        <div className="grid gap-3 md:grid-cols-2">
          {rows.map((s) => (
            <Card key={s.id} className="overflow-hidden">
              <div className="relative aspect-[21/9] bg-surface-2">
                {s.image && <img src={s.image} alt="" className="size-full object-cover" />}
                <span className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-full bg-black/50 px-2 py-0.5 text-xs text-white"><GripVertical className="size-3" /> ترتیب {s.order}</span>
              </div>
              <div className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{s.title}</div>
                    <div className="mt-0.5 line-clamp-2 text-xs text-muted">{s.subtitle}</div>
                  </div>
                  <Badge tone={s.is_active ? "ok" : "neutral"}>{s.is_active ? "فعال" : "غیرفعال"}</Badge>
                </div>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" variant="secondary" icon={<Pencil className="size-4" />} onClick={() => setEditing(s)}>ویرایش</Button>
                  <Button size="sm" variant="danger" icon={<Trash2 className="size-4" />} onClick={() => confirm("این اسلاید حذف شود؟") && del.mutate(s.id)}>حذف</Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing && <SlideForm slide={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function SlideForm({ slide, onClose }: { slide: SlideT | null; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState({ title: slide?.title ?? "", subtitle: slide?.subtitle ?? "", link_url: slide?.link_url ?? "", link_label: slide?.link_label ?? "مشاهده", order: slide?.order ?? 0, is_active: slide?.is_active ?? true });
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState(slide?.image ?? "");
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const m = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.set("title", f.title);
      fd.set("subtitle", f.subtitle);
      fd.set("link_url", f.link_url);
      fd.set("link_label", f.link_label);
      fd.set("order", String(f.order));
      fd.set("is_active", String(f.is_active));
      if (file) fd.set("image", file);
      return slide ? api.patch(`/slides/${slide.id}/`, fd) : api.post("/slides/", fd);
    },
    onSuccess: () => { toast("ذخیره شد"); qc.invalidateQueries({ queryKey: ["slides-panel"] }); onClose(); },
  });
  const err = fieldErrors(m.error);
  return (
    <Sheet open onClose={onClose} title={slide ? "ویرایش اسلاید" : "اسلاید جدید"} footer={<Button className="w-full" loading={m.isPending} disabled={!f.title || (!slide && !file)} onClick={() => m.mutate()}>ذخیره</Button>}>
      <div className="space-y-4">
        <Field label="تصویر" error={err.image} hint="نسبت پیشنهادی تصویر: ۲۱ به ۹ (عریض)">
          <label className="flex aspect-[21/9] cursor-pointer items-center justify-center overflow-hidden rounded-xl border border-dashed border-line bg-surface-2">
            {preview ? <img src={preview} alt="" className="size-full object-cover" /> : <span className="flex flex-col items-center gap-1 text-sm text-muted"><ImagePlus className="size-6" /> انتخاب تصویر</span>}
            <input type="file" accept="image/*" className="hidden" onChange={(e) => {
              const fl = e.target.files?.[0];
              if (fl) { setFile(fl); setPreview(URL.createObjectURL(fl)); }
            }} />
          </label>
        </Field>
        <Field label="عنوان" error={err.title}><Input value={f.title} onChange={set("title")} /></Field>
        <Field label="زیرعنوان" error={err.subtitle}><Input value={f.subtitle} onChange={set("subtitle")} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="لینک مقصد" hint="مثلا /p/12 یا یک آدرس خارجی" error={err.link_url}><Input value={f.link_url} onChange={set("link_url")} dir="ltr" /></Field>
          <Field label="متن دکمه"><Input value={f.link_label} onChange={set("link_label")} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="ترتیب نمایش"><Input type="number" value={f.order} onChange={(e) => setF({ ...f, order: +e.target.value })} dir="ltr" /></Field>
          <label className="mt-7 flex items-center gap-2 text-sm"><input type="checkbox" className="size-4" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> فعال و نمایش در سایت</label>
        </div>
      </div>
      {m.error && !Object.keys(err).length && <p className="mt-3 text-sm text-danger">{(m.error as Error).message}</p>}
    </Sheet>
  );
}
