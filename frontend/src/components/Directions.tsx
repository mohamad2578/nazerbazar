import { Copy, ExternalLink, Navigation } from "lucide-react";
import { useState } from "react";
import { Sheet, useToast } from "./ui";

type Coords = { lat?: number | string | null; lng?: number | string | null };

/** لینک‌های مسیریابی. `geo:` فقط روی موبایل کار می‌کند، پس همیشه نسخه وب هم می‌دهیم. */
export const mapLinks = (lat: number | string, lng: number | string, name = "") => [
  { key: "neshan", label: "نشان", url: `https://neshan.org/maps/@${lat},${lng},17z` },
  { key: "balad", label: "بلد", url: `https://balad.ir/location?latitude=${lat}&longitude=${lng}&zoom=17` },
  { key: "google", label: "گوگل مپ", url: `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}` },
  {
    key: "osm",
    label: "OpenStreetMap",
    url: `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=17/${lat}/${lng}${name ? "" : ""}`,
  },
];

export function hasCoords(s: Coords) {
  return s.lat != null && s.lng != null && s.lat !== "" && s.lng !== "";
}

/** دکمه مسیریابی: انتخاب اپ نقشه (نشان/بلد/گوگل) یا کپی مختصات. */
export default function Directions({
  lat,
  lng,
  name,
  className,
  children,
}: Coords & { name?: string; className?: string; children?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const toast = useToast();
  const disabled = !hasCoords({ lat, lng });
  const links = disabled ? [] : mapLinks(lat!, lng!, name);

  return (
    <>
      <button
        type="button"
        onClick={() => (disabled ? toast("موقعیت این فروشگاه هنوز ثبت نشده است.", "danger") : setOpen(true))}
        className={className}
        aria-label="مسیریابی"
      >
        {children ?? (
          <>
            <Navigation className="size-4" /> مسیریابی
          </>
        )}
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title={name ? `مسیریابی به ${name}` : "مسیریابی"}>
        <p className="mb-3 text-sm text-muted">نقشه مورد نظرتان را انتخاب کنید:</p>
        <div className="space-y-2">
          {links.map((l) => (
            <a
              key={l.key}
              href={l.url}
              target="_blank"
              rel="noreferrer"
              onClick={() => setOpen(false)}
              className="flex h-12 items-center justify-between rounded-xl border border-line px-4 text-sm hover:border-brand/50"
            >
              {l.label}
              <ExternalLink className="size-4 text-muted" />
            </a>
          ))}
          <button
            type="button"
            onClick={() => {
              navigator.clipboard?.writeText(`${lat},${lng}`).then(() => toast("مختصات کپی شد"));
              setOpen(false);
            }}
            className="flex h-12 w-full items-center justify-between rounded-xl border border-line px-4 text-sm"
          >
            کپی مختصات
            <Copy className="size-4 text-muted" />
          </button>
        </div>
      </Sheet>
    </>
  );
}
