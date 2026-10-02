import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Save, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge, Button, Card, cx, Empty, ErrorBox, Input, Loading, PageHeader, PriceInput, Segmented, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { ago, hoursLeft, num, toman, toRial, toToman } from "../../lib/format";

type Item = {
  product: number; name: string; unit_display: string; category_name: string; official_price: number; min_allowed_price: number;
  max_discount_percent: number; offer_price: number | null; is_available: boolean | null; confirmed_at: string | null;
  is_stale: boolean; deadline: string | null; hidden: boolean;
};

export default function Prices() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["catalog"], queryFn: () => api.get<{ store: { status: string }; items: Item[] }>("/store/catalog/") });
  const [draft, setDraft] = useState<Record<number, { price: string; available: boolean }>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState<"all" | "stale" | "unpriced" | "priced">("all");
  const [search, setSearch] = useState("");

  const items = q.data?.items ?? [];
  const shown = useMemo(
    () => items.filter((i) => (filter === "stale" ? i.is_stale : filter === "unpriced" ? i.offer_price == null : filter === "priced" ? i.offer_price != null : true) && (!search || i.name.includes(search))),
    [items, filter, search],
  );
  const dirty = Object.keys(draft).length;

  const save = useMutation({
    mutationFn: (rows: { product: number; price: number; is_available: boolean }[]) => api.post<{ saved: number[]; errors: Record<string, string> }>("/store/offers/", rows),
    onSuccess: (r) => {
      setErrors(r.errors);
      setDraft((d) => Object.fromEntries(Object.entries(d).filter(([k]) => r.errors[k])));
      qc.invalidateQueries({ queryKey: ["catalog"] });
      if (r.saved.length) toast(`${num(r.saved.length)} قیمت ثبت شد`);
      if (Object.keys(r.errors).length) toast(`${num(Object.keys(r.errors).length)} مورد خطا دارد`, "danger");
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });

  const rowsFromDraft = () =>
    Object.entries(draft).map(([pid, v]) => ({ product: +pid, price: toRial(v.price || "0"), is_available: v.available }));

  const confirmAll = () => {
    // تایید قیمت‌های فعلی که هنوز در بازه مجاز جدید هستند
    const rows = items.filter((i) => i.is_stale && i.offer_price != null && i.offer_price >= i.min_allowed_price && i.offer_price <= i.official_price)
      .map((i) => ({ product: i.product, price: i.offer_price!, is_available: i.is_available ?? true }));
    if (!rows.length) return toast("قیمت فعلی هیچ کالایی در بازه مجاز جدید نیست؛ قیمت‌ها را اصلاح کنید.", "danger");
    save.mutate(rows);
  };

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  if (q.data!.store.status !== "active") return <Card><Empty title="فروشگاه شما هنوز فعال نشده است">پس از تایید اتحادیه امکان ثبت قیمت فراهم می‌شود.</Empty></Card>;
  const staleCount = items.filter((i) => i.is_stale).length;

  return (
    <div className="space-y-4">
      <PageHeader
        title="قیمت‌های من"
        subtitle="قیمت هر کالا باید بین نرخ مصوب اتحادیه و حداکثر ۲۰٪ کمتر از آن باشد."
        actions={staleCount > 0 && <Button variant="soft" onClick={confirmAll} loading={save.isPending}>تایید قیمت‌های معتبر</Button>}
      />
      {staleCount > 0 && (
        <Card className="flex items-start gap-2 border-danger/30 bg-danger-soft p-3 text-sm text-danger">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          نرخ مصوب {num(staleCount)} کالا تغییر کرده است. اگر ظرف ۲۴ ساعت قیمت را به‌روز یا تایید نکنید، آن کالا موقتا از فهرست عمومی فروشگاه شما حذف می‌شود.
        </Card>
      )}
      <div className="flex flex-col gap-2 sm:flex-row">
        <Segmented value={filter} onChange={setFilter} options={[
          { value: "all", label: `همه (${num(items.length)})` },
          { value: "stale", label: `نیازمند به‌روزرسانی (${num(staleCount)})` },
          { value: "unpriced", label: "بدون قیمت" },
          { value: "priced", label: "ثبت‌شده" },
        ]} />
        <div className="relative sm:mr-auto sm:w-64">
          <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="جستجو" className="pr-9" />
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {shown.map((i) => {
          const d = draft[i.product];
          const value = d?.price ?? (i.offer_price != null ? String(toToman(i.offer_price)) : "");
          const rial = value ? toRial(value) : null;
          const invalid = rial != null && (rial > i.official_price || rial < i.min_allowed_price);
          const h = hoursLeft(i.deadline);
          return (
            <Card key={i.product} className={cx("p-4", i.is_stale && "border-danger/40")}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-medium">{i.name}</div>
                  <div className="text-xs text-muted">هر {i.unit_display} · نرخ مصوب <b className="text-ink">{toman(i.official_price)}</b></div>
                </div>
                {i.is_stale ? (
                  <Badge tone="danger">{i.hidden ? "پنهان از فهرست" : `مهلت ${num(Math.max(0, Math.floor(h ?? 0)))} ساعت`}</Badge>
                ) : i.offer_price != null ? <Badge tone="ok">فعال</Badge> : <Badge>بدون قیمت</Badge>}
              </div>
              <div className="mt-3 flex items-center gap-2">
                <div className="flex-1">
                  <PriceInput
                    value={value}
                    onChange={(v) => setDraft({ ...draft, [i.product]: { price: v, available: d?.available ?? i.is_available ?? true } })}
                    className={invalid ? "border-danger" : ""}
                    aria-label={`قیمت ${i.name}`}
                  />
                </div>
                <label className="flex items-center gap-1.5 text-xs">
                  <input
                    type="checkbox"
                    className="size-4 accent-[var(--brand)]"
                    checked={d?.available ?? i.is_available ?? true}
                    onChange={(e) => setDraft({ ...draft, [i.product]: { price: value, available: e.target.checked } })}
                  />
                  موجود
                </label>
              </div>
              <div className="mt-1.5 flex justify-between text-[11px] text-muted">
                <span className={invalid ? "text-danger" : ""}>بازه مجاز: {toman(i.min_allowed_price, false)} تا {toman(i.official_price, false)} تومان</span>
                {i.confirmed_at && <span>{ago(i.confirmed_at)}</span>}
              </div>
              <div className="mt-1 flex gap-3 text-[11px]">
                <button className="text-brand" onClick={() => setDraft({ ...draft, [i.product]: { price: String(toToman(i.official_price)), available: true } })}>= نرخ مصوب</button>
                <button className="text-brand" onClick={() => setDraft({ ...draft, [i.product]: { price: String(toToman(i.min_allowed_price)), available: true } })}>حداقل مجاز</button>
              </div>
              {errors[String(i.product)] && <p className="mt-1 text-xs text-danger">{errors[String(i.product)]}</p>}
            </Card>
          );
        })}
      </div>
      {!shown.length && <Card><Empty title="موردی نیست" /></Card>}
      {dirty > 0 && (
        <div className="fixed inset-x-0 bottom-16 z-[650] px-4 lg:bottom-4 lg:pr-68">
          <div className="mx-auto flex max-w-xl items-center justify-between gap-3 rounded-2xl bg-ink p-3 text-bg shadow-xl">
            <span className="text-sm">{num(dirty)} تغییر ذخیره‌نشده</span>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" className="text-bg" onClick={() => { setDraft({}); setErrors({}); }}>انصراف</Button>
              <Button size="sm" icon={<Save className="size-4" />} loading={save.isPending} onClick={() => save.mutate(rowsFromDraft())}>ذخیره</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
