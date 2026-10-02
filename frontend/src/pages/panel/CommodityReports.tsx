import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { Button, Card, DataTable, Empty, Field, Input, Loading, PageHeader, PriceInput, Select, Sheet, useToast } from "../../components/ui";
import { api, fieldErrors, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { date, num, pct, toman, toRial, toToman } from "../../lib/format";

/** جدول‌های الف (نیاز/تامین) و ب (قیمت زنجیره) هر کالای اساسی — مطابق پیوست «توزیع ۱۴۰۵» */
const SUPPLY = [
  ["annual_need_kt", "نیاز سالانه (هزار تن)"], ["annual_production_kt", "تولید سالانه (هزار تن)"], ["imports_kt", "واردات (هزار تن)"],
  ["neighbor_price_usd", "قیمت در کشور همسایه (دلار/کیلو)"], ["per_capita_stat", "سرانه مصرف طبق آمار (کیلو)"],
];
const PRICES = [
  ["import_price", "قیمت واردات"], ["clearance_cost", "هزینه ترخیص و حمل"], ["producer_price", "قیمت تولیدکننده/سر مزرعه"],
  ["wholesale_price", "قیمت عمده/کشتارگاه"], ["consumer_price_county", "مصرف‌کننده — شهرستان"], ["consumer_price_center", "مصرف‌کننده — مرکز استان"],
  ["consumer_price_tehran", "مصرف‌کننده — تهران"], ["national_min", "ارزان‌ترین استان"], ["national_max", "گران‌ترین استان"], ["national_avg", "متوسط کشور"],
];

export default function CommodityReports() {
  const { user } = useAuth();
  const canEdit = user!.role === "governorate" || user!.role === "admin";
  const [editing, setEditing] = useState<any>(null);
  const q = useQuery({ queryKey: ["c-reports"], queryFn: () => api.get<Page<any>>("/commodity-reports/", { page_size: 200 }) });
  return (
    <div className="space-y-4">
      <PageHeader title="رصدخانه کالاهای اساسی" subtitle="نیاز، تولید، واردات، بهای تمام‌شده و قیمت در زنجیره از تولید تا مصرف"
        actions={canEdit && <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setEditing({})}>گزارش جدید</Button>} />
      <Card>
        {q.isLoading ? <Loading /> : !q.data?.results.length ? <Empty title="گزارشی ثبت نشده است" /> : (
          <DataTable rows={q.data.results} onRowClick={canEdit ? setEditing : undefined} columns={[
            { key: "commodity_name", label: "کالا" }, { key: "province_name", label: "محدوده" }, { key: "period", label: "دوره", render: (r) => date(r.period) },
            { key: "supply_gap_kt", label: "کسری تامین (هزار تن)", render: (r) => (r.supply_gap_kt != null ? num(r.supply_gap_kt, 1) : "—") },
            { key: "landed_cost", label: "بهای تمام‌شده واردات", render: (r) => toman(r.landed_cost) },
            { key: "national_avg", label: "متوسط کشور", render: (r) => toman(r.national_avg) },
            { key: "chain_markup_percent", label: "فاصله تولید تا مصرف", render: (r) => <span className="text-warn">{pct(r.chain_markup_percent)}</span> },
          ]} />
        )}
      </Card>
      {editing && <ReportForm row={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ReportForm({ row, onClose }: { row: any; onClose: () => void }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const coms = useQuery({ queryKey: ["commodities"], queryFn: () => api.get<any[]>("/commodities/") });
  const provs = useQuery({ queryKey: ["provinces"], queryFn: () => api.get<Page<any>>("/provinces/"), enabled: user!.role === "admin" });
  const [f, setF] = useState<any>(() => {
    const v: any = { period: new Date().toISOString().slice(0, 10), neighbor_country: "عراق", source: "", ...row };
    PRICES.forEach(([k]) => (v[k] = row[k] != null ? String(toToman(row[k])) : ""));
    return v;
  });
  const m = useMutation({
    mutationFn: () => {
      const body: any = { ...f };
      PRICES.forEach(([k]) => (body[k] = f[k] ? toRial(f[k]) : null));
      SUPPLY.forEach(([k]) => (body[k] = f[k] === "" || f[k] == null ? null : f[k]));
      if (!body.province) body.province = null;
      return row.id ? api.patch(`/commodity-reports/${row.id}/`, body) : api.post("/commodity-reports/", body);
    },
    onSuccess: () => { toast("ذخیره شد"); qc.invalidateQueries({ queryKey: ["c-reports"] }); onClose(); },
  });
  const err = fieldErrors(m.error);
  return (
    <Sheet open wide onClose={onClose} title="گزارش تامین و قیمت کالا" footer={<Button className="w-full" loading={m.isPending} onClick={() => m.mutate()}>ذخیره</Button>}>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="کالا" error={err.commodity}><Select value={f.commodity ?? ""} onChange={(e) => setF({ ...f, commodity: e.target.value })}><option value="">—</option>{coms.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        {user!.role === "admin" && <Field label="استان (خالی = ملی)"><Select value={f.province ?? ""} onChange={(e) => setF({ ...f, province: e.target.value })}><option value="">کل کشور</option>{provs.data?.results.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>}
        <Field label="تاریخ دوره" error={err.period || err.non_field_errors}><Input type="date" value={f.period} onChange={(e) => setF({ ...f, period: e.target.value })} dir="ltr" /></Field>
      </div>
      <h3 className="mb-2 mt-5 text-sm font-semibold">جدول الف — نیاز و تامین</h3>
      <div className="grid gap-3 sm:grid-cols-3">
        {SUPPLY.map(([k, l]) => <Field key={k} label={l} error={err[k]}><Input value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} dir="ltr" inputMode="decimal" /></Field>)}
      </div>
      <h3 className="mb-2 mt-5 text-sm font-semibold">جدول ب — قیمت در زنجیره (تومان/کیلو)</h3>
      <div className="grid gap-3 sm:grid-cols-3">
        {PRICES.map(([k, l]) => <Field key={k} label={l}><PriceInput value={f[k]} onChange={(v) => setF({ ...f, [k]: v })} /></Field>)}
      </div>
      <Field label="منبع" className="mt-4"><Input value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} /></Field>
    </Sheet>
  );
}
