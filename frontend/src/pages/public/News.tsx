import { useQuery } from "@tanstack/react-query";
import { Newspaper } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { Card, Empty, Loading, PageHeader } from "../../components/ui";
import { api } from "../../lib/api";
import { date } from "../../lib/format";

export type NewsT = { id: number; title: string; body: string; image: string | null; published_at: string; created_by_name: string };

/** فهرست اخبار و اطلاعیه‌های منتشرشده. */
export default function News() {
  const q = useQuery({ queryKey: ["news"], queryFn: () => api.get<NewsT[]>("/public/news/") });
  const items = q.data ?? [];
  return (
    <div className="space-y-5">
      <PageHeader title="اخبار" />
      {q.isLoading ? <Loading /> : !items.length ? (
        <Card><Empty title="هنوز خبری منتشر نشده است" icon={<Newspaper className="size-7" />} /></Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {items.map((n) => (
            <Link key={n.id} to={`/news/${n.id}`} className="block">
              <Card className="h-full overflow-hidden transition hover:shadow-lg">
                {n.image ? (
                  <img src={n.image} alt="" loading="lazy" className="aspect-[16/9] w-full object-cover" />
                ) : (
                  <div className="grid aspect-[16/9] place-items-center bg-surface-2 text-muted"><Newspaper className="size-8" /></div>
                )}
                <div className="p-4">
                  <div className="text-[11px] text-muted">{date(n.published_at)}</div>
                  <h2 className="mt-1 font-semibold leading-7">{n.title}</h2>
                  <p className="mt-1 line-clamp-2 text-sm text-muted">{n.body}</p>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

/** نمایش کامل یک خبر. */
export function NewsDetail() {
  const { id = "" } = useParams();
  const q = useQuery({ queryKey: ["news", id], queryFn: () => api.get<NewsT>(`/public/news/${id}/`), enabled: !!id });
  if (q.isLoading) return <Loading />;
  if (!q.data) return <Card><Empty title="خبر یافت نشد" /></Card>;
  const n = q.data;
  return (
    <article className="mx-auto max-w-2xl space-y-4">
      <Link to="/news" className="text-sm text-brand">← همه اخبار</Link>
      {n.image && <img src={n.image} alt="" className="w-full rounded-2xl object-cover" />}
      <h1 className="text-xl font-bold leading-8 sm:text-2xl">{n.title}</h1>
      <div className="text-xs text-muted">{date(n.published_at)}{n.created_by_name && ` · ${n.created_by_name}`}</div>
      <div className="whitespace-pre-line leading-8">{n.body}</div>
    </article>
  );
}
