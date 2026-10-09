import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Download, KeyRound, Pencil, Phone, Plus, Search } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge, Button, Card, DataTable, Empty, Field, Input, Loading, PageHeader, Segmented, Select, Sheet, STATUS_TONE, Textarea, useToast } from "../../components/ui";
import { fieldErrors } from "../../lib/api";
import { api, download, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { date, num, telLink } from "../../lib/format";

const LocationPicker = lazy(() => import("../../components/MapView").then((m) => ({ default: m.LocationPicker })));

type StoreT = {
  id: number; name: string; union_name: string; county_name: string; license_no: string; phone: string; address: string;
  status: string; status_display: string; status_reason: string; is_verified: boolean; rating_avg: string; owner_name: string;
  owner_mobile: string; offers_count: number; created_at: string; license_image: string | null; lat: string; lng: string;
  union?: number | null; covered_unions?: number[]; covered_union_names?: string[]; working_hours?: string;
};

/** نقش‌هایی که اجازه تعریف و مدیریت فروشگاه دارند. */
const MANAGER_ROLES = ["union", "chamber", "samt", "governorate", "admin"];

export default function Stores() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<StoreT | null>(null);
  const q = useQuery({ queryKey: ["stores", status, search, page], queryFn: () => api.get<Page<StoreT>>("/stores/", { status, search, page }) });
  const [creating, setCreating] = useState(false);
  const canManage = MANAGER_ROLES.includes(user!.role);
  return (
    <div className="space-y-4">
      <PageHeader
        title={canManage ? "کارتابل فروشگاه‌ها" : "فروشگاه‌ها"}
        subtitle={canManage ? "درخواست‌های فعال‌سازی را بررسی و فروشگاه‌های عضو را مدیریت کنید." : undefined}
        actions={
          <span className="flex gap-2">
            <Button variant="secondary" size="sm" icon={<Download className="size-4" />} onClick={() => download("/analytics/export/stores/", "stores.xlsx")}>اکسل</Button>
            {canManage && <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>فروشگاه جدید</Button>}
          </span>
        }
      />
      <div className="flex flex-col gap-2 sm:flex-row">
        <Segmented value={status} onChange={(v) => { setParams(v ? { status: v } : {}); setPage(1); }} options={[
          { value: "", label: "همه" }, { value: "pending", label: "در انتظار تایید" }, { value: "active", label: "فعال" },
          { value: "suspended", label: "تعلیق" }, { value: "rejected", label: "رد شده" },
        ]} />
        <div className="relative sm:mr-auto sm:w-64">
          <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="نام، موبایل، پروانه" className="pr-9" />
        </div>
      </div>
      <Card>
        {q.isLoading ? <Loading /> : !q.data?.results.length ? <Empty title="فروشگاهی یافت نشد" /> : (
          <DataTable
            rows={q.data.results}
            onRowClick={setSel}
            columns={[
              { key: "name", label: "فروشگاه", render: (s) => <span className="inline-flex items-center gap-1 font-medium">{s.name}{s.is_verified && <BadgeCheck className="size-4 text-brand" />}</span> },
              { key: "owner_name", label: "مالک", render: (s) => s.owner_name || s.owner_mobile },
              { key: "union_name", label: "اتحادیه" },
              { key: "status", label: "وضعیت", render: (s) => <Badge tone={STATUS_TONE[s.status]}>{s.status_display}</Badge> },
              { key: "offers_count", label: "قیمت‌ها", render: (s) => num(s.offers_count) },
              { key: "created_at", label: "ثبت", render: (s) => date(s.created_at), hideOnMobile: true },
            ]}
          />
        )}
      </Card>
      {q.data && q.data.count > 20 && (
        <div className="flex justify-center gap-2">
          <Button size="sm" variant="secondary" disabled={!q.data.previous} onClick={() => setPage(page - 1)}>قبلی</Button>
          <Button size="sm" variant="secondary" disabled={!q.data.next} onClick={() => setPage(page + 1)}>بعدی</Button>
        </div>
      )}
      {sel && <StoreSheet store={sel} canManage={canManage} onClose={() => setSel(null)} />}
      {creating && <StoreForm onClose={() => setCreating(false)} />}
    </div>
  );
}

function StoreSheet({ store, canManage, onClose }: { store: StoreT; canManage: boolean; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const [editing, setEditing] = useState(false);
  const [pwd, setPwd] = useState("");
  const [loc, setLoc] = useState<{ lat: number; lng: number } | null>(
    store.lat ? { lat: +store.lat, lng: +store.lng } : null,
  );
  const qc = useQueryClient();
  const toast = useToast();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["stores"] });
    qc.invalidateQueries({ queryKey: ["pending-stores"] });
  };
  const act = useMutation({
    mutationFn: ({ action, body }: { action: string; body?: object }) => api.post(`/stores/${store.id}/${action}/`, body),
    onSuccess: () => {
      toast("انجام شد");
      refresh();
      onClose();
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const saveLoc = useMutation({
    mutationFn: () => api.patch(`/stores/${store.id}/`, { lat: loc?.lat, lng: loc?.lng }),
    onSuccess: () => {
      toast("موقعیت فروشگاه ثبت شد");
      refresh();
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const setPassword = useMutation({
    mutationFn: () => api.post(`/stores/${store.id}/set_password/`, { password: pwd }),
    onSuccess: () => { toast("رمز عبور فروشگاه تغییر کرد"); setPwd(""); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  if (editing) return <StoreForm store={store} onClose={() => { setEditing(false); onClose(); }} />;
  return (
    <Sheet open onClose={onClose} title={store.name}>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <Info label="مالک" value={store.owner_name || "—"} />
        <Info label="موبایل" value={<a href={telLink(store.owner_mobile)} className="text-brand" dir="ltr">{store.owner_mobile}</a>} />
        <Info label="اتحادیه" value={store.union_name} />
        <Info label="پروانه کسب" value={store.license_no || "—"} />
        <Info label="تلفن" value={store.phone ? <a href={telLink(store.phone)} className="inline-flex items-center gap-1 text-brand"><Phone className="size-3" />{store.phone}</a> : "—"} />
        <Info label="وضعیت" value={<Badge tone={STATUS_TONE[store.status]}>{store.status_display}</Badge>} />
        <Info label="نشانی" value={store.address} wide />
        {store.status_reason && <Info label="دلیل" value={store.status_reason} wide />}
      </dl>
      {store.license_image && <a href={store.license_image} target="_blank" rel="noreferrer" className="mt-3 inline-block text-sm text-brand underline">مشاهده تصویر پروانه</a>}

      {canManage && (
        <div className="mt-5 border-t border-line pt-4">
          <Field
            label="موقعیت روی نقشه"
            hint={loc ? "برای جابه‌جایی، روی نقطه دلخواه نقشه بزنید." : "این فروشگاه هنوز موقعیت ندارد و روی نقشه سایت دیده نمی‌شود؛ روی نقشه بزنید."}
          >
            <Suspense fallback={<Loading />}>
              <LocationPicker value={loc} onChange={setLoc} height={220} />
            </Suspense>
          </Field>
          <Button size="sm" className="mt-2" variant="soft" loading={saveLoc.isPending} disabled={!loc} onClick={() => saveLoc.mutate()}>
            ذخیره موقعیت
          </Button>
        </div>
      )}

      {canManage && (
        <div className="mt-5 space-y-3 border-t border-line pt-4">
          <Button size="sm" variant="secondary" icon={<Pencil className="size-4" />} onClick={() => setEditing(true)}>
            ویرایش مشخصات فروشگاه و مالک
          </Button>
          <Field label="رمز عبور جدید مالک" hint="حداقل ۸ کاراکتر؛ پس از ثبت، فروشگاه با همین رمز و شماره موبایل خود وارد می‌شود.">
            <div className="flex gap-2">
              <Input type="text" dir="ltr" value={pwd} onChange={(e) => setPwd(e.target.value)} placeholder="رمز عبور" />
              <Button variant="soft" icon={<KeyRound className="size-4" />} loading={setPassword.isPending} disabled={pwd.length < 8} onClick={() => setPassword.mutate()}>
                ثبت رمز
              </Button>
            </div>
          </Field>
        </div>
      )}

      {canManage && (
        <div className="mt-5 space-y-3 border-t border-line pt-4">
          <Field label="دلیل (برای رد یا تعلیق الزامی است)">
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} className="min-h-16" />
          </Field>
          <div className="flex flex-wrap gap-2">
            {store.status !== "active" && <Button loading={act.isPending} onClick={() => act.mutate({ action: "approve" })}>تایید و فعال‌سازی</Button>}
            {store.status === "pending" && <Button variant="danger" disabled={!reason} onClick={() => act.mutate({ action: "reject", body: { reason } })}>رد درخواست</Button>}
            {store.status === "active" && <Button variant="danger" disabled={!reason} onClick={() => act.mutate({ action: "suspend", body: { reason } })}>تعلیق</Button>}
            {store.status === "active" && (
              <Button variant="soft" onClick={() => act.mutate({ action: "verify", body: { value: !store.is_verified } })}>
                {store.is_verified ? "حذف نشان اعتماد" : "اعطای نشان اعتماد"}
              </Button>
            )}
          </div>
        </div>
      )}
    </Sheet>
  );
}

export function Info({ label, value, wide }: { label: string; value: React.ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? "col-span-2" : ""}>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5">{value}</dd>
    </div>
  );
}

/** تعریف فروشگاه جدید یا ویرایش کامل مشخصات فروشگاه و حساب مالک آن. */
function StoreForm({ store, onClose }: { store?: StoreT; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState<Record<string, string>>(() => ({
    name: store?.name ?? "", license_no: store?.license_no ?? "",
    phone: store?.phone ?? "", address: store?.address ?? "", working_hours: store?.working_hours ?? "",
    owner_mobile: store?.owner_mobile ?? "", owner_first_name: "", owner_last_name: "", password: "",
  }));
  // «فاقد اتحادیه» برای فروشگاه‌های زنجیره‌ای، جهاد، حامی و مانند آن‌ها
  const NONE = "none";
  const [union, setUnion] = useState<string>(() =>
    store ? (store.union ? String(store.union) : store.covered_unions?.length ? NONE : "") : "");
  const [covered, setCovered] = useState<number[]>(() => store?.covered_unions ?? []);
  const toggleCovered = (id: number) =>
    setCovered((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  const unions = useQuery({ queryKey: ["options", "/unions/"], queryFn: () => api.get<Page<{ id: number; name: string; chamber_name: string }>>("/unions/", { page_size: 500 }) });
  const m = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { ...f };
      body.union = union === NONE || !union ? null : Number(union);
      body.covered_unions = union === NONE ? covered : [];
      if (!body.password) delete body.password;
      if (store) { delete body.owner_first_name; delete body.owner_last_name; }
      return store ? api.patch(`/stores/${store.id}/`, body) : api.post("/stores/", body);
    },
    onSuccess: () => {
      toast(store ? "مشخصات فروشگاه به‌روز شد" : "فروشگاه ثبت و فعال شد");
      qc.invalidateQueries({ queryKey: ["stores"] });
      qc.invalidateQueries({ queryKey: ["pending-stores"] });
      onClose();
    },
  });
  const err = fieldErrors(m.error);
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <Sheet open onClose={onClose} title={store ? "ویرایش فروشگاه" : "تعریف فروشگاه جدید"}
      footer={<Button className="w-full" loading={m.isPending} onClick={() => m.mutate()}>{store ? "ذخیره تغییرات" : "ثبت فروشگاه"}</Button>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="نام فروشگاه" error={err.name}><Input value={f.name} onChange={set("name")} /></Field>
        <Field label="اتحادیه" error={err.union}>
          <Select value={union} onChange={(e) => setUnion(e.target.value)}>
            <option value="">—</option>
            {(unions.data?.results ?? []).map((u) => <option key={u.id} value={u.id}>{u.name}{u.chamber_name ? ` (${u.chamber_name})` : ""}</option>)}
            <option value={NONE}>فاقد اتحادیه (زنجیره‌ای، جهاد، حامی و …)</option>
          </Select>
        </Field>
        <Field label="شماره پروانه کسب" error={err.license_no}><Input value={f.license_no} onChange={set("license_no")} dir="ltr" /></Field>
        <Field label="تلفن فروشگاه" error={err.phone}><Input value={f.phone} onChange={set("phone")} dir="ltr" /></Field>
        <Field label="نشانی" error={err.address} className="sm:col-span-2"><Textarea value={f.address} onChange={set("address")} className="min-h-16" /></Field>
        <Field label="ساعت کاری" error={err.working_hours} className="sm:col-span-2"><Input value={f.working_hours} onChange={set("working_hours")} placeholder="مثلا ۸ تا ۲۲" /></Field>
      </div>

      {union === NONE && (
        <div className="mt-4 rounded-2xl border border-line bg-surface-2 p-4">
          <h3 className="text-sm font-semibold">کالاهای کدام اتحادیه‌ها به این فروشگاه نمایش داده شود؟</h3>
          <p className="mt-1 text-xs text-muted">
            این فروشگاه عضو اتحادیه نیست، اما می‌تواند روی کالاهای اتحادیه‌های انتخابی قیمت پیشنهادی بدهد.
            فروشگاه‌های زنجیره‌ای معمولا کالاهای چند اتحادیه را پوشش می‌دهند.
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {(unions.data?.results ?? []).map((u) => (
              <label key={u.id} className="flex items-center gap-2 rounded-xl bg-surface p-2.5 text-sm">
                <input type="checkbox" className="size-4" checked={covered.includes(u.id)} onChange={() => toggleCovered(u.id)} />
                {u.name}
              </label>
            ))}
          </div>
          {err.covered_unions && <p className="mt-2 text-xs text-danger">{err.covered_unions}</p>}
        </div>
      )}

      <div className="mt-5 border-t border-line pt-4">
        <h3 className="mb-3 text-sm font-semibold">حساب کاربری مالک فروشگاه</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="موبایل مالک (نام کاربری ورود)" error={err.owner_mobile}><Input value={f.owner_mobile} onChange={set("owner_mobile")} dir="ltr" inputMode="numeric" /></Field>
          <Field label={store ? "رمز عبور جدید (خالی = بدون تغییر)" : "رمز عبور"} error={err.password}><Input value={f.password} onChange={set("password")} dir="ltr" /></Field>
          {!store && <Field label="نام مالک"><Input value={f.owner_first_name} onChange={set("owner_first_name")} /></Field>}
          {!store && <Field label="نام خانوادگی مالک"><Input value={f.owner_last_name} onChange={set("owner_last_name")} /></Field>}
        </div>
        {!store && <p className="mt-2 text-xs text-muted">فروشگاهی که از اینجا تعریف می‌کنید بدون نیاز به تایید مجدد، فعال ثبت می‌شود.</p>}
      </div>
      {m.error && !Object.keys(err).length && <p className="mt-3 text-sm text-danger">{(m.error as Error).message}</p>}
    </Sheet>
  );
}
