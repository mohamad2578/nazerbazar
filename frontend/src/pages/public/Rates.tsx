import { useQuery } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, Empty, Loading, PageHeader } from "../../components/ui";
import { api, type Page } from "../../lib/api";
import { toman } from "../../lib/format";

type RateRow = { id: number; name: string; union_name: string; unit_display: string; official_price: number; min_allowed_price: number };

/** نرخ‌نامه اتحادیه‌ها: نرخ مصوب همه کالاها، گروه‌بندی‌شده بر اساس اتحادیه. */
export default function Rates() {
  const q = useQuery({
    queryKey: ["rates"],
    queryFn: () => api.get<Page<RateRow>>("/public/products/", { page_size: 200, ordering: "name" }),
    staleTime: 300_000,
  });
  const rows = q.data?.results ?? [];
  const groups = rows.reduce<Record<string, RateRow[]>>((acc, r) => {
    (acc[r.union_name] ??= []).push(r);
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      <PageHeader title="نرخ‌نامه اتحادیه‌ها" subtitle="نرخ مصوب هر کالای اساسی به تفکیک اتحادیه" />
      {q.isLoading ? <Loading /> : !rows.length ? (
        <Card><Empty title="هنوز نرخی ثبت نشده است" /></Card>
      ) : (
        Object.entries(groups).map(([union, items]) => (
          <section key={union}>
            <h2 className="mb-2 font-semibold">{union}</h2>
            <Card className="divide-y divide-line">
              {items.map((r) => (
                <Link key={r.id} to={`/p/${r.id}`} className="flex items-center justify-between gap-3 p-3.5 transition hover:bg-surface-2">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{r.name}</div>
                    <div className="text-[11px] text-muted">هر {r.unit_display}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <div className="text-left">
                      <div className="font-bold tabular">{toman(r.official_price)}</div>
                      <div className="text-[11px] text-muted">حداقل مجاز {toman(r.min_allowed_price, false)}</div>
                    </div>
                    <ChevronLeft className="size-4 text-muted" />
                  </div>
                </Link>
              ))}
            </Card>
          </section>
        ))
      )}
    </div>
  );
}
