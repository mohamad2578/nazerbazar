import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardPaste, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Field, Input, Loading, PriceInput, Sheet, Textarea, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { toRial, toToman } from "../../lib/format";

type Row = { title: string; price: string };

/** از متن چسبانده‌شده (هر خط: شرح خدمت و در انتها تعرفه به ریال) ردیف می‌سازد؛ ۸۰۰/۰۰۰ و ۸۰۰,۰۰۰ هر دو پذیرفته است. */
function parsePasted(text: string): Row[] {
  const rows: Row[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim().replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)));
    const m = line.match(/^(?:\d+\s*[.\-)]?\s+)?(.*?)[\s\t]+(\d[\d/,٬،.]*)$/);
    if (!m || !m[1].trim()) continue;
    const rial = Number(m[2].replace(/[/,٬،.]/g, ""));
    if (rial > 0) rows.push({ title: m[1].trim(), price: String(toToman(rial)) });
  }
  return rows;
}

export default function TariffEditor({ product, canEdit, onClose }: { product: { id: number; name: string }; canEdit: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["tariffs", product.id], queryFn: () => api.get<{ title: string; price: number }[]>(`/products/${product.id}/tariffs/`) });
  const [rows, setRows] = useState<Row[] | null>(null);
  const [paste, setPaste] = useState("");
  const [showPaste, setShowPaste] = useState(false);
  useEffect(() => {
    if (q.data && rows === null) setRows(q.data.map((t) => ({ title: t.title, price: String(toToman(t.price)) })));
  }, [q.data, rows]);
  const m = useMutation({
    mutationFn: () => api.put(`/products/${product.id}/tariffs/`, { items: rows!.map((r) => ({ title: r.title.trim(), price: toRial(r.price) })) }),
    onSuccess: () => {
      toast("نرخ‌نامه ذخیره شد");
      qc.invalidateQueries({ queryKey: ["products-panel"] });
      qc.invalidateQueries({ queryKey: ["tariffs", product.id] });
      onClose();
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const set = (i: number, patch: Partial<Row>) => setRows(rows!.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const valid = !!rows?.length && rows.every((r) => r.title.trim() && toRial(r.price) > 0);
  const applyPaste = () => {
    const parsed = parsePasted(paste);
    if (!parsed.length) return toast("هیچ ردیف معتبری پیدا نشد؛ هر خط باید شرح خدمت و در انتها قیمت باشد.", "danger");
    setRows([...(rows ?? []), ...parsed]);
    setPaste("");
    setShowPaste(false);
    toast(`${parsed.length} ردیف اضافه شد`);
  };
  return (
    <Sheet open onClose={onClose} title={`نرخ‌نامه خدمات: ${product.name}`} wide footer={canEdit
      ? <Button className="w-full" loading={m.isPending} disabled={!valid} onClick={() => m.mutate()}>ذخیره نرخ‌نامه</Button>
      : undefined}>
      {q.isLoading || rows === null ? <Loading /> : (
        <div className="space-y-3">
          {canEdit && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" icon={<Plus className="size-4" />} onClick={() => setRows([...rows, { title: "", price: "" }])}>ردیف جدید</Button>
              <Button size="sm" variant="secondary" icon={<ClipboardPaste className="size-4" />} onClick={() => setShowPaste(!showPaste)}>چسباندن از اکسل/ورد</Button>
            </div>
          )}
          {showPaste && (
            <div className="space-y-2 rounded-xl bg-surface-2 p-3">
              <Field label="هر خط یک خدمت؛ شرح خدمت و در انتها تعرفه به ریال" hint="مثلا: تعویض روغن انواع سواری و وانت  800/000 (شماره ردیف ابتدای خط نادیده گرفته می‌شود)">
                <Textarea value={paste} onChange={(e) => setPaste(e.target.value)} className="min-h-32" />
              </Field>
              <Button size="sm" onClick={applyPaste} disabled={!paste.trim()}>افزودن به نرخ‌نامه</Button>
            </div>
          )}
          {!rows.length && <p className="py-6 text-center text-sm text-muted">هنوز ردیفی ثبت نشده است.</p>}
          <ol className="space-y-2">
            {rows.map((r, i) => (
              <li key={i} className="grid grid-cols-[2rem_1fr_auto] items-start gap-2 sm:grid-cols-[2rem_1fr_11rem_auto]">
                <span className="pt-3 text-center text-xs text-muted tabular">{i + 1}</span>
                <Input value={r.title} disabled={!canEdit} onChange={(e) => set(i, { title: e.target.value })} placeholder="شرح خدمت" />
                <div className="col-start-2 sm:col-start-auto">
                  <PriceInput value={r.price} disabled={!canEdit} onChange={(v) => set(i, { price: v })} />
                </div>
                {canEdit && (
                  <button type="button" onClick={() => setRows(rows.filter((_, j) => j !== i))} className="col-start-3 row-start-1 pt-3 text-muted hover:text-danger sm:col-start-auto sm:row-start-auto" aria-label="حذف ردیف">
                    <Trash2 className="size-4" />
                  </button>
                )}
              </li>
            ))}
          </ol>
          <p className="text-xs text-muted">قیمت‌ها به تومان نمایش و ثبت می‌شود؛ مبلغ‌های چسبانده‌شده (ریال) خودکار تبدیل می‌شوند.</p>
        </div>
      )}
    </Sheet>
  );
}
