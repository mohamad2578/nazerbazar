import L from "leaflet";
import { useEffect } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet";

const TILES = (import.meta.env.VITE_MAP_TILES as string | undefined) || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
export const DEFAULT_CENTER: [number, number] = [34.7983, 48.5148];

function pin(color: string, label?: string) {
  return L.divIcon({
    className: "",
    iconSize: [34, 42],
    iconAnchor: [17, 40],
    popupAnchor: [0, -36],
    html: `<div style="position:relative;width:34px;height:42px">
      <svg width="34" height="42" viewBox="0 0 34 42"><path d="M17 41C17 41 32 26 32 16A15 15 0 0 0 2 16C2 26 17 41 17 41Z" fill="${color}" stroke="white" stroke-width="2"/></svg>
      <span style="position:absolute;top:7px;left:0;right:0;text-align:center;color:white;font:600 11px Vazirmatn">${label ?? ""}</span></div>`,
  });
}

export type MapPoint = { id: number | string; lat: number | string; lng: number | string; title: string; sub?: string; label?: string; highlight?: boolean; href?: string };

function FitBounds({ points }: { points: MapPoint[] }) {
  const map = useMap();
  useEffect(() => {
    const valid = points.filter((p) => p.lat && p.lng);
    if (valid.length === 1) map.setView([+valid[0].lat, +valid[0].lng], 15);
    else if (valid.length > 1) map.fitBounds(L.latLngBounds(valid.map((p) => [+p.lat, +p.lng] as [number, number])), { padding: [30, 30], maxZoom: 16 });
  }, [map, points]);
  return null;
}

export default function MapView({ points, height = 320, me }: { points: MapPoint[]; height?: number | string; me?: { lat: number; lng: number } | null }) {
  return (
    <MapContainer center={DEFAULT_CENTER} zoom={12} style={{ height }} scrollWheelZoom={false}>
      <TileLayer url={TILES} attribution={ATTR} />
      <FitBounds points={points} />
      {me && <Marker position={[me.lat, me.lng]} icon={pin("#2563eb", "من")} />}
      {points
        .filter((p) => p.lat && p.lng)
        .map((p) => (
          <Marker key={p.id} position={[+p.lat, +p.lng]} icon={pin(p.highlight ? "#d97706" : "#0f766e", p.label)}>
            <Popup>
              <div className="text-sm font-semibold">{p.title}</div>
              {p.sub && <div className="text-xs">{p.sub}</div>}
              {p.href && (
                <a href={p.href} className="mt-1 block text-xs">
                  مشاهده
                </a>
              )}
            </Popup>
          </Marker>
        ))}
    </MapContainer>
  );
}

/** انتخاب موقعیت با لمس روی نقشه (ثبت‌نام فروشگاه/گزارش تخلف) */
export function LocationPicker({ value, onChange, height = 260 }: { value: { lat: number; lng: number } | null; onChange: (v: { lat: number; lng: number }) => void; height?: number }) {
  function Clicker() {
    useMapEvents({ click: (e) => onChange({ lat: +e.latlng.lat.toFixed(6), lng: +e.latlng.lng.toFixed(6) }) });
    return null;
  }
  function Recenter() {
    const map = useMap();
    useEffect(() => {
      if (value) map.setView([value.lat, value.lng], Math.max(map.getZoom(), 15));
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value?.lat, value?.lng]);
    return null;
  }
  return (
    <MapContainer center={value ? [value.lat, value.lng] : DEFAULT_CENTER} zoom={value ? 16 : 13} style={{ height }}>
      <TileLayer url={TILES} attribution={ATTR} />
      <Clicker />
      <Recenter />
      {value && <Marker position={[value.lat, value.lng]} icon={pin("#0f766e")} />}
    </MapContainer>
  );
}
