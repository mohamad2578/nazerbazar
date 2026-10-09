import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Truck } from "lucide-react";
import { Badge, Button, Card, DataTable, Empty, Loading, PageHeader, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { date, telLink } from "../../lib/format";

type SupplierRow = { id: number; first_name: string; last_name: string; mobile: string; product_type: string; is_reviewed: boolean; created_at: string };

/** فهرست تامین‌کنندگان ثبت‌شده از فرم عمومی؛ اداره صمت پس از تماس، علامت بررسی می‌زند. */
export default function SupplierList() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["suppliers"], queryFn: () => api.get<SupplierRow[]>("/suppliers/") });
  const mark = useMutation({
    mutationFn: (r: SupplierRow) => api.patch(`/suppliers/${r.id}/`, { is_reviewed: !r.is_reviewed }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["suppliers"] }),
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const rows = q.data ?? [];
  return (
    <div className="space-y-4">
      <PageHeader title="تامین‌کنندگان" subtitle="درخواست‌های ثبت‌شده از فرم عمومی سایت" />
      {q.isLoading ? <Loading /> : !rows.length ? (
        <Card><Empty title="هنوز درخواستی ثبت نشده است" icon={<Truck className="size-7" />} /></Card>
      ) : (
        <Card>
          <DataTable
            rows={rows}
            columns={[
              { key: "name", label: "نام", render: (r) => `${r.first_name} ${r.last_name}` },
              { key: "mobile", label: "تماس", render: (r) => <a href={telLink(r.mobile)} className="text-brand" dir="ltr">{r.mobile}</a> },
              { key: "product_type", label: "کالای قابل تامین" },
              { key: "created_at", label: "ثبت", render: (r) => date(r.created_at), hideOnMobile: true },
              {
                key: "is_reviewed", label: "وضعیت",
                render: (r) => (
                  <Button size="sm" variant={r.is_reviewed ? "soft" : "secondary"} icon={r.is_reviewed ? <CheckCircle2 className="size-4" /> : undefined} onClick={() => mark.mutate(r)}>
                    {r.is_reviewed ? <Badge tone="ok">بررسی شد</Badge> : "علامت بررسی"}
                  </Button>
                ),
              },
            ]}
          />
        </Card>
      )}
    </div>
  );
}
