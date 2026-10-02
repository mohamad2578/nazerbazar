import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, cx, Empty, Loading, PageHeader, Segmented, STATUS_TONE } from "../../components/ui";
import { api, type Page } from "../../lib/api";
import { ago } from "../../lib/format";

export default function Alerts() {
  const qc = useQueryClient();
  const [resolved, setResolved] = useState("false");
  const q = useQuery({ queryKey: ["alerts", resolved], queryFn: () => api.get<Page<any>>("/alerts/", { is_resolved: resolved, page_size: 100 }) });
  const m = useMutation({ mutationFn: (id: number) => api.post(`/alerts/${id}/resolve/`), onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }) });
  return (
    <div className="space-y-4">
      <PageHeader title="هشدارهای رصد بازار" subtitle="جهش نرخ، افزایش قیمت بازار، کاهش عرضه، قیمت‌های به‌روزنشده و افزایش شکایات — روزانه به‌صورت خودکار" />
      <Segmented value={resolved} onChange={setResolved} options={[{ value: "false", label: "باز" }, { value: "true", label: "بررسی‌شده" }]} />
      {q.isLoading ? <Loading /> : !q.data?.results.length ? <Card><Empty title="هشداری نیست" /></Card> : (
        <div className="space-y-2">
          {q.data.results.map((a) => (
            <Card key={a.id} className="flex items-start gap-3 p-4">
              <AlertTriangle className={cx("mt-0.5 size-5 shrink-0", a.level === "critical" ? "text-danger" : a.level === "warning" ? "text-warn" : "text-brand")} />
              <div className="flex-1">
                <div className="font-medium">{a.title}</div>
                {a.message && <div className="mt-0.5 text-sm text-muted">{a.message}</div>}
                <div className="mt-1.5 flex flex-wrap gap-2 text-xs text-muted">
                  <Badge tone={STATUS_TONE[a.level]}>{a.level_display}</Badge>
                  <span>{a.kind_display}</span>{a.county_name && <span>· {a.county_name}</span>}<span>· {ago(a.created_at)}</span>
                </div>
              </div>
              {!a.is_resolved && <Button size="sm" variant="secondary" icon={<Check className="size-4" />} onClick={() => m.mutate(a.id)}>بررسی شد</Button>}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
