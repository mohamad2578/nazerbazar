import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useEffect } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ErrorBox, Loading } from "../../components/ui";
import { api } from "../../lib/api";
import FeaturedStorefront from "./FeaturedStorefront";

/** صفحه «بسته‌های پیشنهادی و کالاهای طرح ویژه» فروشگاه ویژه؛ از دکمه «مشاهده کالا و خرید» باز می‌شود. */
export default function FeaturedShop() {
  const { id } = useParams();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [id]);
  const q = useQuery({ queryKey: ["store", id], queryFn: () => api.get<{ id: number; name: string; is_featured?: boolean }>(`/public/stores/${id}/`) });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const s = q.data!;
  if (!s.is_featured) return <Navigate to={`/s/${s.id}`} replace />;
  return (
    <div className="space-y-4">
      <Link to={`/s/${s.id}`} className="inline-flex items-center gap-1 text-sm text-muted">
        <ArrowRight className="size-4" /> {s.name}
      </Link>
      <FeaturedStorefront storeId={s.id} storeName={s.name} />
    </div>
  );
}
