import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Clock, MapPin, Navigation, Phone, ShieldAlert, Star } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Badge, Button, Card, cx, ErrorBox, Loading, Sheet, Textarea, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { ago, directionsLink, num, telLink, toman } from "../../lib/format";

const MapView = lazy(() => import("../../components/MapView"));

type StoreDetailT = {
  id: number; name: string; address: string; phone: string; lat: string | null; lng: string | null; working_hours: string;
  is_verified: boolean; rating_avg: string; rating_count: number; union_name: string; county_name: string; photo: string | null;
  offers: { product: number; name: string; unit_display: string; price: number; official_price: number; discount_percent: number; pending_update: boolean }[];
  reviews: { id: number; rating: number; comment: string; user_name: string; created_at: string }[];
};

export default function StoreDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const [reviewOpen, setReviewOpen] = useState(false);
  const q = useQuery({ queryKey: ["store", id], queryFn: () => api.get<StoreDetailT>(`/public/stores/${id}/`) });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const s = q.data!;
  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        {s.lat && s.lng && (
          <Suspense fallback={<div className="h-40 bg-surface-2" />}>
            <MapView height={170} points={[{ id: s.id, lat: s.lat, lng: s.lng, title: s.name }]} />
          </Suspense>
        )}
        <div className="p-4 sm:p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h1 className="flex items-center gap-1.5 text-lg font-bold">
                {s.name} {s.is_verified && <BadgeCheck className="size-5 text-brand" />}
              </h1>
              <p className="mt-0.5 text-sm text-muted">عضو {s.union_name} · {s.county_name}</p>
            </div>
            {s.rating_count > 0 && (
              <div className="text-center">
                <div className="inline-flex items-center gap-1 text-lg font-bold">
                  <Star className="size-5 fill-accent text-accent" /> {num(s.rating_avg, 1)}
                </div>
                <div className="text-[11px] text-muted">{num(s.rating_count)} نظر</div>
              </div>
            )}
          </div>
          <div className="mt-3 space-y-1.5 text-sm text-muted">
            <p className="flex items-start gap-1.5"><MapPin className="mt-0.5 size-4 shrink-0" /> {s.address}</p>
            {s.working_hours && <p className="flex items-center gap-1.5"><Clock className="size-4" /> {s.working_hours}</p>}
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2">
            <a href={telLink(s.phone)} className={cx("inline-flex h-11 items-center justify-center gap-1.5 rounded-xl bg-brand text-sm text-brand-ink", !s.phone && "pointer-events-none opacity-40")}>
              <Phone className="size-4" /> تماس
            </a>
            <a href={directionsLink(s.lat, s.lng)} className="inline-flex h-11 items-center justify-center gap-1.5 rounded-xl bg-surface-2 text-sm">
              <Navigation className="size-4" /> مسیریابی
            </a>
            <Link to={`/report?store=${s.id}`} className="inline-flex h-11 items-center justify-center gap-1.5 rounded-xl bg-danger-soft text-sm text-danger">
              <ShieldAlert className="size-4" /> گزارش
            </Link>
          </div>
        </div>
      </Card>

      <section>
        <h2 className="mb-3 font-semibold">قیمت کالاها در این فروشگاه</h2>
        <Card className="divide-y divide-line">
          {s.offers.map((o) => (
            <Link key={o.product} to={`/p/${o.product}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-surface-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{o.name}</div>
                <div className="text-xs text-muted">نرخ مصوب {toman(o.official_price)} · هر {o.unit_display}</div>
              </div>
              <div className="shrink-0 text-left">
                <div className="font-semibold tabular">{toman(o.price)}</div>
                {o.pending_update ? <Badge tone="warn">در انتظار به‌روزرسانی</Badge> : o.discount_percent > 0 && <Badge tone="ok">{num(o.discount_percent, 1)}٪ ارزان‌تر</Badge>}
              </div>
            </Link>
          ))}
          {!s.offers.length && <p className="p-6 text-center text-sm text-muted">قیمتی ثبت نشده است.</p>}
        </Card>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">نظرات خریداران</h2>
          <Button size="sm" variant="soft" onClick={() => (user ? setReviewOpen(true) : nav(`/login?next=/s/${s.id}`))}>
            ثبت نظر
          </Button>
        </div>
        <div className="space-y-2">
          {s.reviews.map((r) => (
            <Card key={r.id} className="p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{r.user_name}</span>
                <Stars value={r.rating} />
              </div>
              {r.comment && <p className="mt-1.5 text-sm text-muted">{r.comment}</p>}
              <div className="mt-1 text-[11px] text-muted">{ago(r.created_at)}</div>
            </Card>
          ))}
          {!s.reviews.length && <p className="text-sm text-muted">هنوز نظری ثبت نشده است.</p>}
        </div>
      </section>
      <ReviewSheet open={reviewOpen} onClose={() => setReviewOpen(false)} storeId={s.id} />
    </div>
  );
}

function Stars({ value, onChange }: { value: number; onChange?: (v: number) => void }) {
  return (
    <span className="inline-flex gap-0.5" dir="ltr">
      {[1, 2, 3, 4, 5].map((i) => (
        <button key={i} type="button" disabled={!onChange} onClick={() => onChange?.(i)} aria-label={`${i} ستاره`}>
          <Star className={cx(onChange ? "size-8" : "size-4", i <= value ? "fill-accent text-accent" : "text-line")} />
        </button>
      ))}
    </span>
  );
}

function ReviewSheet({ open, onClose, storeId }: { open: boolean; onClose: () => void; storeId: number }) {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const m = useMutation({
    mutationFn: () => api.post(`/public/stores/${storeId}/reviews/`, { rating, comment }),
    onSuccess: () => {
      toast("نظر شما ثبت شد. سپاسگزاریم.");
      qc.invalidateQueries({ queryKey: ["store", String(storeId)] });
      onClose();
    },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="امتیاز شما به این فروشگاه"
      footer={<Button className="w-full" disabled={!rating} loading={m.isPending} onClick={() => m.mutate()}>ثبت نظر</Button>}
    >
      <div className="flex justify-center py-2">
        <Stars value={rating} onChange={setRating} />
      </div>
      <Textarea placeholder="تجربه خرید خود را بنویسید (اختیاری)" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
    </Sheet>
  );
}
