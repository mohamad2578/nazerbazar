import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { Badge, Button, Card, DataTable, Empty, Field, Input, Loading, PageHeader, Select, Sheet, useToast } from "../../components/ui";
import { api, fieldErrors } from "../../lib/api";
import { useAuth, type Role } from "../../lib/auth";
import { ago, num } from "../../lib/format";

/** صفحه عمومی مدیریت موجودیت‌های ساختاری (استان، شهرستان، اتاق اصناف، اتحادیه، کاربران، کالاهای اساسی، دسته‌ها) */
type FieldDef = { key: string; label: string; type?: "text" | "number" | "select" | "checkbox" | "password"; options?: string; choices?: [string, string][]; showIf?: (f: any) => boolean };
type Entity = { title: string; url: string; paginated: boolean; columns: { key: string; label: string; render?: (r: any) => React.ReactNode }[]; fields: FieldDef[]; canDelete?: boolean; roles: Role[] };

const ROLE_CHOICES: [string, string][] = [["governorate", "استانداری"], ["samt", "اداره صمت"], ["chamber", "اتاق اصناف"], ["union", "اتحادیه"], ["admin", "مدیر کل"]];

const ENTITIES: Record<string, Entity> = {
  provinces: { title: "استان‌ها", url: "/provinces/", paginated: true, roles: [], columns: [{ key: "name", label: "نام" }, { key: "is_active", label: "فعال", render: (r) => (r.is_active ? "✓" : "—") }],
    fields: [{ key: "name", label: "نام استان" }, { key: "lat", label: "عرض جغرافیایی" }, { key: "lng", label: "طول جغرافیایی" }, { key: "is_active", label: "فعال", type: "checkbox" }] },
  counties: { title: "شهرستان‌ها", url: "/counties/", paginated: true, roles: ["governorate", "samt"], columns: [{ key: "name", label: "نام" }, { key: "province_name", label: "استان" }, { key: "population", label: "جمعیت", render: (r) => num(r.population) }],
    fields: [{ key: "province", label: "استان", type: "select", options: "/provinces/" }, { key: "name", label: "نام شهرستان" }, { key: "population", label: "جمعیت", type: "number" }, { key: "lat", label: "عرض جغرافیایی" }, { key: "lng", label: "طول جغرافیایی" }] },
  chambers: { title: "اتاق‌های اصناف", url: "/chambers/", paginated: true, roles: ["governorate", "samt"], columns: [{ key: "name", label: "عنوان" }, { key: "county_name", label: "شهرستان" }, { key: "unions_count", label: "اتحادیه", render: (r) => num(r.unions_count) }],
    fields: [{ key: "county", label: "شهرستان", type: "select", options: "/counties/" }, { key: "name", label: "عنوان" }, { key: "phone", label: "تلفن" }, { key: "address", label: "نشانی" }] },
  unions: { title: "اتحادیه‌ها", url: "/unions/", paginated: true, roles: ["governorate", "samt", "chamber"], columns: [{ key: "name", label: "عنوان" }, { key: "guild", label: "رسته" }, { key: "chamber_name", label: "اتاق اصناف" }, { key: "is_active", label: "وضعیت", render: (r) => <Badge tone={r.is_active ? "ok" : "neutral"}>{r.is_active ? "فعال" : "غیرفعال"}</Badge> }],
    fields: [{ key: "chamber", label: "اتاق اصناف", type: "select", options: "/chambers/" }, { key: "name", label: "عنوان اتحادیه" }, { key: "guild", label: "رسته صنفی" }, { key: "phone", label: "تلفن" }, { key: "address", label: "نشانی" }, { key: "is_active", label: "فعال", type: "checkbox" }] },
  users: { title: "کاربران سازمانی", url: "/users/", paginated: true, canDelete: true, roles: ["governorate", "samt", "chamber"],
    columns: [{ key: "mobile", label: "موبایل" }, { key: "name", label: "نام", render: (r) => `${r.first_name} ${r.last_name}` }, { key: "role_display", label: "نقش" }, { key: "scope_name", label: "حوزه" }, { key: "last_login", label: "آخرین ورود", render: (r) => ago(r.last_login) || "—" }, { key: "is_active", label: "فعال", render: (r) => (r.is_active ? "✓" : "—") }],
    fields: [
      { key: "mobile", label: "موبایل" }, { key: "first_name", label: "نام" }, { key: "last_name", label: "نام خانوادگی" },
      { key: "role", label: "نقش", type: "select", choices: ROLE_CHOICES },
      { key: "province", label: "استان", type: "select", options: "/provinces/", showIf: (f) => f.role === "governorate" || f.role === "samt" },
      { key: "chamber", label: "اتاق اصناف", type: "select", options: "/chambers/", showIf: (f) => f.role === "chamber" },
      { key: "union", label: "اتحادیه", type: "select", options: "/unions/", showIf: (f) => f.role === "union" },
      { key: "password", label: "رمز عبور (اختیاری؛ ورود با پیامک همیشه فعال است)", type: "password" },
      { key: "is_active", label: "فعال", type: "checkbox" },
    ] },
  commodities: { title: "کالاهای اساسی و سبد خانوار", url: "/commodities/", paginated: false, roles: [],
    columns: [{ key: "name", label: "کالا" }, { key: "group_display", label: "گروه" }, { key: "unit", label: "واحد" }, { key: "basket_monthly_qty", label: "مقدار ماهانه در سبد", render: (r) => num(r.basket_monthly_qty, 2) }, { key: "subsidized", label: "یارانه‌ای", render: (r) => (r.subsidized ? "✓" : "—") }],
    fields: [{ key: "name", label: "نام" }, { key: "group", label: "گروه", type: "select", choices: [["protein", "پروتئینی"], ["dairy", "لبنیات"], ["grain", "غلات و حبوبات"], ["oil_sugar", "روغن، قند و شکر"], ["produce", "صیفی و تره‌بار"], ["hygiene", "بهداشتی و شوینده"], ["feed", "نهاده دامی"], ["other", "سایر"]] },
      { key: "unit", label: "واحد" }, { key: "basket_monthly_qty", label: "مقدار ماهانه در سبد خانوار", type: "number" }, { key: "order", label: "ترتیب", type: "number" }, { key: "subsidized", label: "وارداتی/یارانه‌ای", type: "checkbox" }] },
  categories: { title: "دسته‌بندی‌ها", url: "/categories/", paginated: false, canDelete: true, roles: [], columns: [{ key: "name", label: "عنوان" }, { key: "order", label: "ترتیب" }],
    fields: [{ key: "name", label: "عنوان" }, { key: "order", label: "ترتیب", type: "number" }] },
};

export default function Org() {
  const { entity = "" } = useParams();
  const { user } = useAuth();
  const e = ENTITIES[entity];
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<any>(null);
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["org", entity, search], queryFn: () => api.get(e.url, { search, page_size: 200 }), enabled: !!e });
  const del = useMutation({ mutationFn: (id: number) => api.del(`${e.url}${id}/`), onSuccess: () => { toast("حذف شد"); qc.invalidateQueries({ queryKey: ["org", entity] }); }, onError: (err: Error) => toast(err.message, "danger") });
  if (!e || (user!.role !== "admin" && !e.roles.includes(user!.role))) return <Navigate to="/panel" replace />;
  const rows: any[] = (e.paginated ? q.data?.results : q.data) ?? [];
  return (
    <div className="space-y-4">
      <PageHeader title={e.title} actions={<Button size="sm" icon={<Plus className="size-4" />} onClick={() => setEditing({})}>افزودن</Button>} />
      <div className="relative sm:w-72">
        <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
        <Input value={search} onChange={(ev) => setSearch(ev.target.value)} placeholder="جستجو" className="pr-9" />
      </div>
      <Card>
        {q.isLoading ? <Loading /> : !rows.length ? <Empty title="موردی ثبت نشده است" /> : (
          <DataTable rows={rows} onRowClick={setEditing} columns={[...e.columns, {
            key: "_a", label: "", render: (r: any) => (
              <span className="flex gap-2">
                <Pencil className="size-4 text-muted" />
                {e.canDelete && <button onClick={(ev) => { ev.stopPropagation(); if (confirm("حذف/غیرفعال شود؟")) del.mutate(r.id); }} aria-label="حذف"><Trash2 className="size-4 text-danger" /></button>}
              </span>
            ),
          }]} />
        )}
      </Card>
      {editing && <EntityForm entity={entity} e={e} row={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function EntityForm({ entity, e, row, onClose }: { entity: string; e: Entity; row: any; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState<any>(() => ({ is_active: true, ...row, password: "" }));
  const m = useMutation({
    mutationFn: () => {
      const body: any = {};
      e.fields.forEach((fd) => { if (!fd.showIf || fd.showIf(f)) body[fd.key] = f[fd.key] === "" ? null : f[fd.key]; });
      if (!body.password) delete body.password;
      return row.id ? api.patch(`${e.url}${row.id}/`, body) : api.post(e.url, body);
    },
    onSuccess: () => { toast("ذخیره شد"); qc.invalidateQueries({ queryKey: ["org", entity] }); onClose(); },
  });
  const err = fieldErrors(m.error);
  return (
    <Sheet open onClose={onClose} title={row.id ? `ویرایش ${e.title}` : `افزودن به ${e.title}`} footer={<Button className="w-full" loading={m.isPending} onClick={() => m.mutate()}>ذخیره</Button>}>
      <div className="grid gap-4 sm:grid-cols-2">
        {e.fields.filter((fd) => !fd.showIf || fd.showIf(f)).map((fd) =>
          fd.type === "checkbox" ? (
            <label key={fd.key} className="flex items-center gap-2 text-sm sm:col-span-2">
              <input type="checkbox" className="size-4" checked={!!f[fd.key]} onChange={(ev) => setF({ ...f, [fd.key]: ev.target.checked })} /> {fd.label}
            </label>
          ) : (
            <Field key={fd.key} label={fd.label} error={err[fd.key]}>
              {fd.type === "select" ? (
                fd.options ? <RemoteSelect url={fd.options} value={f[fd.key] ?? ""} onChange={(v) => setF({ ...f, [fd.key]: v })} /> : (
                  <Select value={f[fd.key] ?? ""} onChange={(ev) => setF({ ...f, [fd.key]: ev.target.value })}>
                    <option value="">—</option>
                    {fd.choices!.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </Select>
                )
              ) : (
                <Input type={fd.type === "password" ? "password" : "text"} inputMode={fd.type === "number" ? "decimal" : undefined} value={f[fd.key] ?? ""} onChange={(ev) => setF({ ...f, [fd.key]: ev.target.value })} dir={fd.type === "number" || fd.key === "mobile" ? "ltr" : undefined} />
              )}
            </Field>
          ),
        )}
      </div>
      {m.error && !Object.keys(err).length && <p className="mt-3 text-sm text-danger">{(m.error as Error).message}</p>}
    </Sheet>
  );
}

function RemoteSelect({ url, value, onChange }: { url: string; value: any; onChange: (v: string) => void }) {
  const q = useQuery({ queryKey: ["options", url], queryFn: () => api.get(url, { page_size: 500 }) });
  const rows: any[] = q.data?.results ?? q.data ?? [];
  return (
    <Select value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
      <option value="">—</option>
      {rows.map((r) => <option key={r.id} value={r.id}>{r.name}{r.county_name ? ` (${r.county_name})` : ""}</option>)}
    </Select>
  );
}
