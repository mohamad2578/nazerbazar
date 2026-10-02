import { useQuery } from "@tanstack/react-query";
import { Loading } from "../../components/ui";
import MapView from "../../components/MapView";
import { api } from "../../lib/api";
import { num } from "../../lib/format";
import { useCounty, useGeo } from "../../lib/prefs";

type S = { id: number; name: string; lat: string; lng: string; union_name: string; rating_avg: string; is_verified: boolean };

export default function MapPage() {
  const [county] = useCounty();
  const geo = useGeo();
  const q = useQuery({ queryKey: ["map", county?.id], queryFn: () => api.get<S[]>("/public/map/", { county: county?.id }) });
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">نقشه فروشگاه‌های مجاز</h1>
        {q.data && <span className="text-sm text-muted">{num(q.data.length)} فروشگاه</span>}
      </div>
      {q.isLoading ? (
        <Loading />
      ) : (
        <MapView
          height="calc(100dvh - 13rem)"
          me={geo.pos}
          points={(q.data ?? []).map((s) => ({ id: s.id, lat: s.lat, lng: s.lng, title: s.name, sub: s.union_name, href: `/s/${s.id}`, highlight: s.is_verified }))}
        />
      )}
      <p className="text-xs text-muted">نشانگرهای نارنجی: فروشگاه‌های دارای نشان اعتماد اتحادیه</p>
    </div>
  );
}
