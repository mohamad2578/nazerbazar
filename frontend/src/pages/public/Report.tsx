import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Copy, ImagePlus, LocateFixed, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useGeoTree } from "../../components/CountyPicker";
import { Button, Card, Field, Input, PriceInput, Segmented, Select, Textarea, useToast } from "../../components/ui";
import { api, fieldErrors } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { toman, toRial } from "../../lib/format";
import { useCounty, useGeo } from "../../lib/prefs";

const KINDS = [
  ["overprice", "گران‌فروشی (بیش از نرخ مصوب)"],
  ["not_honored", "عدم رعایت قیمت اعلام‌شده در سامانه"],
  ["unavailable", "عدم عرضه با وجود اعلام موجودی"],
  ["weight", "کم‌فروشی"],
  ["quality", "کیفیت نامناسب"],
  ["other", "سایر"],
];

type StoreLite = { id: number; name: string; union_name: string };
type StoreOffers = { id: number; name: string; address: string; offers: { product: number; name: string; price: number; official_price: number }[] };

export default function Report() {
  const [params] = useSearchParams();
  const { user } = useAuth();
  const toast = useToast();
  const [county] = useCounty();
  const geo = useGeo();
  const [mode, setMode] = useState<"member" | "outside">("member");
  const [storeId, setStoreId] = useState(params.get("store") ?? "");
  const [productId, setProductId] = useState(params.get("product") ?? "");
  const [storeQuery, setStoreQuery] = useState("");
  const [form, setForm] = useState({ kind: "overprice", paid_price: "", description: "", reporter_name: user?.first_name ? `${user.first_name} ${user.last_name}` : "", shop_name: "", shop_address: "", county: county?.id ? String(county.id) : "" });
  const [file, setFile] = useState<File | null>(null);
  const [useLocation, setUseLocation] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  const stores = useQuery({ queryKey: ["map-stores", county?.id], queryFn: () => api.get<StoreLite[]>("/public/map/", { county: county?.id }), enabled: mode === "member" && !storeId });
  const store = useQuery({ queryKey: ["store", storeId], queryFn: () => api.get<StoreOffers>(`/public/stores/${storeId}/`), enabled: !!storeId });
  const product = useQuery({ queryKey: ["product-lite", productId], queryFn: () => api.get(`/public/products/${productId}/`), enabled: !!productId && mode === "outside" });
  const chambers = useQuery({ queryKey: ["chambers"], queryFn: () => api.get<{ id: number; county: number; name: string }[]>("/public/geo/chambers/"), enabled: mode === "outside" });
  const geoTree = useGeoTree();
  const filteredStores = useMemo(() => (stores.data ?? []).filter((s) => !storeQuery || s.name.includes(storeQuery)).slice(0, 30), [stores.data, storeQuery]);
  const selectedOffer = store.data?.offers.find((o) => String(o.product) === productId);

  const m = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.set("kind", form.kind);
      fd.set("description", form.description);
      if (form.reporter_name) fd.set("reporter_name", form.reporter_name);
      if (form.paid_price) fd.set("paid_price", String(toRial(form.paid_price)));
      if (productId) fd.set("product", productId);
      if (mode === "member") fd.set("store", storeId);
      else {
        const ch = chambers.data?.find((c) => String(c.county) === form.county);
        if (ch) fd.set("chamber", String(ch.id));
        fd.set("shop_name", form.shop_name);
        fd.set("shop_address", form.shop_address);
      }
      if (useLocation && geo.pos) {
        fd.set("lat", String(geo.pos.lat));
        fd.set("lng", String(geo.pos.lng));
      }
      if (file) fd.set("attachment", file);
      return api.post<{ tracking_code: string }>("/public/complaints/", fd);
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const errors = fieldErrors(m.error);

  if (m.data) {
    return (
      <Card className="mx-auto max-w-md p-6 text-center">
        <CheckCircle2 className="mx-auto size-14 text-ok" />
        <h1 className="mt-3 text-lg font-bold">گزارش شما ثبت شد</h1>
        <p className="mt-1 text-sm text-muted">گزارش برای اتحادیه مربوط ارسال و رونوشت آن به اتاق اصناف ارجاع شد. نتیجه از طریق پیامک و همین سامانه اطلاع‌رسانی می‌شود.</p>
        <div className="mt-5 rounded-2xl bg-surface-2 p-4">
          <div className="text-xs text-muted">کد رهگیری</div>
          <div className="mt-1 text-2xl font-bold tracking-widest" dir="ltr">{m.data.tracking_code}</div>
          <button onClick={() => navigator.clipboard?.writeText(m.data!.tracking_code).then(() => toast("کپی شد"))} className="mt-2 inline-flex items-center gap-1 text-sm text-brand">
            <Copy className="size-4" /> کپی کد
          </button>
        </div>
        <Link to={`/track?code=${m.data.tracking_code}`} className="mt-4 inline-block text-sm text-brand underline">پیگیری گزارش</Link>
      </Card>
    );
  }

  const canSubmit = form.description.trim().length >= 5 && (mode === "member" ? !!storeId : !!form.shop_name && !!form.county);

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div className="flex items-center gap-3">
        <span className="grid size-11 place-items-center rounded-2xl bg-danger-soft text-danger"><ShieldAlert className="size-6" /></span>
        <div>
          <h1 className="text-lg font-bold">گزارش تخلف</h1>
          <p className="text-sm text-muted">گزارش شما به اتحادیه صنفی ارسال و رونوشت آن برای اتاق اصناف فرستاده می‌شود.</p>
        </div>
      </div>
      <Card className="space-y-4 p-4 sm:p-6">
        {!params.get("store") && (
          <Segmented value={mode} onChange={(v) => { setMode(v); setStoreId(""); }} options={[{ value: "member", label: "فروشگاه عضو سامانه" }, { value: "outside", label: "فروشنده دیگر" }]} />
        )}

        {mode === "member" ? (
          storeId ? (
            <div className="rounded-xl bg-surface-2 p-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs text-muted">فروشگاه</div>
                  <div className="font-medium">{store.data?.name ?? "…"}</div>
                  <div className="text-xs text-muted">{store.data?.address}</div>
                </div>
                {!params.get("store") && <button className="text-sm text-brand" onClick={() => setStoreId("")}>تغییر</button>}
              </div>
              {!!store.data?.offers.length && (
                <Field label="کالا" className="mt-3">
                  <Select value={productId} onChange={(e) => setProductId(e.target.value)}>
                    <option value="">— انتخاب کالا —</option>
                    {store.data.offers.map((o) => (
                      <option key={o.product} value={o.product}>{o.name}</option>
                    ))}
                  </Select>
                </Field>
              )}
              {selectedOffer && (
                <p className="mt-2 text-xs text-muted">
                  قیمت اعلامی این فروشگاه: <b className="text-ink">{toman(selectedOffer.price)}</b> · نرخ مصوب: <b className="text-ink">{toman(selectedOffer.official_price)}</b>
                </p>
              )}
            </div>
          ) : (
            <Field label="جستجوی فروشگاه" error={errors.store}>
              <Input value={storeQuery} onChange={(e) => setStoreQuery(e.target.value)} placeholder="نام فروشگاه…" />
              <div className="mt-2 max-h-56 divide-y divide-line overflow-y-auto rounded-xl border border-line">
                {filteredStores.map((s) => (
                  <button key={s.id} type="button" onClick={() => setStoreId(String(s.id))} className="block w-full px-3 py-2.5 text-right text-sm hover:bg-surface-2">
                    {s.name} <span className="text-xs text-muted">· {s.union_name}</span>
                  </button>
                ))}
                {!filteredStores.length && <p className="p-3 text-sm text-muted">فروشگاهی یافت نشد؛ گزینه «فروشنده دیگر» را انتخاب کنید.</p>}
              </div>
            </Field>
          )
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="نام فروشگاه/فروشنده" error={errors.shop_name}>
              <Input value={form.shop_name} onChange={set("shop_name")} required />
            </Field>
            <Field label="شهرستان" error={errors.chamber}>
              <Select value={form.county} onChange={set("county")}>
                <option value="">— انتخاب —</option>
                {geoTree.data?.flatMap((p) => p.counties).filter((c) => chambers.data?.some((ch) => ch.county === c.id)).map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </Select>
            </Field>
            <Field label="نشانی" className="sm:col-span-2">
              <Input value={form.shop_address} onChange={set("shop_address")} />
            </Field>
            {product.data && <p className="text-xs text-muted sm:col-span-2">کالا: {product.data.name} — نرخ مصوب {toman(product.data.official_price)}</p>}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="نوع تخلف">
            <Select value={form.kind} onChange={set("kind")}>
              {KINDS.map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </Select>
          </Field>
          <Field label="مبلغ پرداختی (اختیاری)" error={errors.paid_price}>
            <PriceInput value={form.paid_price} onChange={(v) => setForm({ ...form, paid_price: v })} />
          </Field>
        </div>
        <Field label="شرح" error={errors.description}>
          <Textarea value={form.description} onChange={set("description")} placeholder="چه اتفاقی افتاد؟ زمان خرید و جزئیات را بنویسید." required />
        </Field>
        <Field label="نام شما" hint="هویت شما برای فروشگاه نمایش داده نمی‌شود.">
          <Input value={form.reporter_name} onChange={set("reporter_name")} />
        </Field>
        <div className="flex flex-wrap gap-2">
          <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-xl border border-dashed border-line px-3 text-sm">
            <ImagePlus className="size-4" /> {file ? file.name.slice(0, 24) : "تصویر فاکتور/کالا"}
            <input type="file" accept="image/*,application/pdf" capture="environment" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button
            type="button"
            onClick={() => {
              if (!geo.pos) geo.ask();
              setUseLocation(!useLocation);
            }}
            className={`inline-flex h-10 items-center gap-2 rounded-xl border px-3 text-sm ${useLocation ? "border-brand bg-brand-soft text-brand" : "border-line"}`}
          >
            <LocateFixed className="size-4" /> {useLocation ? "موقعیت ضمیمه شد" : "ضمیمه موقعیت فعلی"}
          </button>
        </div>
        {errors.attachment && <p className="text-xs text-danger">{errors.attachment}</p>}
        <Button className="w-full" size="lg" variant="danger" disabled={!canSubmit} loading={m.isPending} onClick={() => m.mutate()}>
          ثبت گزارش
        </Button>
      </Card>
    </div>
  );
}
