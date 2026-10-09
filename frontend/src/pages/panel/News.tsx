import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Newspaper, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Field, Input, Loading, PageHeader, Sheet, Textarea, useToast } from "../../components/ui";
import ImageUpload from "../../components/ImageUpload";
import { api, fieldErrors } from "../../lib/api";
import { date } from "../../lib/format";

type NewsRow = { id: number; title: string; body: string; image: string | null; is_published: boolean; published_at: string; created_by_name: string };

/** مدیریت اخبار در پنل: اداره صمت و مدیر کل. */
export default function NewsAdmin() {
  const [editing, setEditing] = useState<NewsRow | "new" | null>(null);
  const q = useQuery({ queryKey: ["news-admin"], queryFn: () => api.get<NewsRow[]>("/news/") });
  const rows = q.data ?? [];
  return (
    <div className="space-y-4">
      <PageHeader title="اخبار" subtitle="خبر جدید ثبت کنید؛ عنوان، عکس و متن خبر." actions={<Button size="sm" icon={<Plus className="size-4" />} onClick={() => setEditing("new")}>خبر جدید</Button>} />
      {q.isLoading ? <Loading /> : !rows.length ? (
        <Card><Empty title="هنوز خبری ثبت نشده است" icon={<Newspaper className="size-7" />} /></Card>
      ) : (
        <div className="space-y-2">
          {rows.map((n) => (
            <Card key={n.id} className="flex items-center gap-3 p-3">
              {n.image ? <img src={n.image} alt="" className="size-16 shrink-0 rounded-xl object-cover" /> : <span className="grid size-16 shrink-0 place-items-center rounded-xl bg-surface-2 text-muted"><Newspaper className="size-6" /></span>}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate font-medium">{n.title}</span>
                  {!n.is_published && <Badge>پیش‌نویس</Badge>}
                </div>
                <div className="mt-0.5 text-xs text-muted">{date(n.published_at)}{n.created_by_name && ` · ${n.created_by_name}`}</div>
              </div>
              <button onClick={() => setEditing(n)} className="grid size-9 place-items-center rounded-lg hover:bg-surface-2" aria-label="ویرایش"><Pencil className="size-4" /></button>
            </Card>
          ))}
        </div>
      )}
      {editing && <NewsForm item={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function NewsForm({ item, onClose }: { item: NewsRow | null; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [title, setTitle] = useState(item?.title ?? "");
  const [body, setBody] = useState(item?.body ?? "");
  const [published, setPublished] = useState(item?.is_published ?? true);
  const [image, setImage] = useState<File | null>(null);

  const save = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.set("title", title);
      fd.set("body", body);
      fd.set("is_published", String(published));
      if (image) fd.set("image", image);
      return item ? api.patch(`/news/${item.id}/`, fd) : api.post("/news/", fd);
    },
    onSuccess: () => {
      toast("خبر ذخیره شد");
      qc.invalidateQueries({ queryKey: ["news-admin"] });
      qc.invalidateQueries({ queryKey: ["news"] });
      onClose();
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/news/${item!.id}/`),
    onSuccess: () => {
      toast("خبر حذف شد");
      qc.invalidateQueries({ queryKey: ["news-admin"] });
      qc.invalidateQueries({ queryKey: ["news"] });
      onClose();
    },
  });
  const err = fieldErrors(save.error);

  return (
    <Sheet open onClose={onClose} title={item ? "ویرایش خبر" : "خبر جدید"}
      footer={
        <div className="flex w-full gap-2">
          <Button className="flex-1" loading={save.isPending} disabled={!title.trim() || !body.trim()} onClick={() => save.mutate()}>ذخیره</Button>
          {item && <Button variant="danger" loading={remove.isPending} onClick={() => confirm("خبر حذف شود؟") && remove.mutate()}><Trash2 className="size-4" /></Button>}
        </div>
      }>
      <div className="space-y-4">
        <Field label="عکس خبر" hint="عکس اختیاری است؛ بزرگ باشد هم فشرده می‌شود.">
          <ImageUpload value={item?.image} onChange={setImage} aspect="16/9" />
        </Field>
        <Field label="عنوان خبر" error={err.title}><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="متن خبر" error={err.body}><Textarea value={body} onChange={(e) => setBody(e.target.value)} className="min-h-40" /></Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4" checked={published} onChange={(e) => setPublished(e.target.checked)} /> منتشر شود
        </label>
      </div>
    </Sheet>
  );
}
