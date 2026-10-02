import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { Card, cx, Empty, Loading, PageHeader } from "../../components/ui";
import { api, type Page } from "../../lib/api";
import { ago } from "../../lib/format";

export default function Notifications() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["notifications"], queryFn: () => api.get<Page<any>>("/notifications/", { page_size: 50 }) });
  const read = useMutation({ mutationFn: () => api.post("/notifications/read_all/"), onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications-count"] }) });
  useEffect(() => {
    if (q.data?.results.some((n) => !n.is_read)) read.mutate();
  }, [q.data]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="space-y-4">
      <PageHeader title="اعلان‌ها" />
      <Card className="divide-y divide-line">
        {q.isLoading ? <Loading /> : !q.data?.results.length ? <Empty title="اعلانی ندارید" /> : q.data.results.map((n) => (
          <Link key={n.id} to={n.link || "#"} className={cx("block px-4 py-3 hover:bg-surface-2", !n.is_read && "bg-brand-soft/50")}>
            <div className="text-sm font-medium">{n.title}</div>
            {n.body && <div className="mt-0.5 text-sm text-muted">{n.body}</div>}
            <div className="mt-1 text-[11px] text-muted">{ago(n.created_at)}</div>
          </Link>
        ))}
      </Card>
    </div>
  );
}
