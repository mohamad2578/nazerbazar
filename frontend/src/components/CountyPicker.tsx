import { useQuery } from "@tanstack/react-query";
import { Check, MapPin } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { useCounty } from "../lib/prefs";
import { cx, Input, Loading, Sheet } from "./ui";

type Geo = { id: number; name: string; counties: { id: number; name: string; lat?: string; lng?: string }[] }[];

export const useGeoTree = () => useQuery({ queryKey: ["geo"], queryFn: () => api.get<Geo>("/public/geo/"), staleTime: 3600_000 });

export default function CountyPicker({ compact }: { compact?: boolean }) {
  const [county, setCounty] = useCounty();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const { data, isLoading } = useGeoTree();
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={cx("inline-flex h-9 items-center gap-1.5 rounded-full border border-line bg-surface px-3 text-sm", compact && "max-w-36")}
      >
        <MapPin className="size-4 shrink-0 text-brand" />
        <span className="truncate">{county?.name ?? "همه شهرستان‌ها"}</span>
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title="انتخاب شهرستان">
        <Input placeholder="جستجوی شهرستان…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-3" />
        <button
          onClick={() => {
            setCounty(null);
            setOpen(false);
          }}
          className="flex w-full items-center justify-between rounded-xl px-3 py-3 text-right hover:bg-surface-2"
        >
          همه شهرستان‌ها {!county && <Check className="size-4 text-brand" />}
        </button>
        {isLoading && <Loading />}
        {data?.map((p) => {
          const counties = p.counties.filter((c) => !q || c.name.includes(q));
          if (!counties.length) return null;
          return (
            <div key={p.id} className="mt-2">
              <div className="px-3 py-1 text-xs font-medium text-muted">استان {p.name}</div>
              {counties.map((c) => (
                <button
                  key={c.id}
                  onClick={() => {
                    setCounty(c);
                    setOpen(false);
                  }}
                  className="flex w-full items-center justify-between rounded-xl px-3 py-3 text-right hover:bg-surface-2"
                >
                  {c.name}
                  {county?.id === c.id && <Check className="size-4 text-brand" />}
                </button>
              ))}
            </div>
          );
        })}
      </Sheet>
    </>
  );
}
