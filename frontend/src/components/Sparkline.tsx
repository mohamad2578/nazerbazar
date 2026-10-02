/** نمودار خطی سبک بدون وابستگی (برای صفحات عمومی که باید سریع بارگذاری شوند) */
export default function Sparkline({ values, height = 56, className }: { values: number[]; height?: number; className?: string }) {
  if (values.length < 2) return null;
  const w = 300;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, height - 6 - ((v - min) / span) * (height - 12)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className={className} style={{ width: "100%", height }} aria-hidden>
      <path d={`${d} L${w},${height} L0,${height} Z`} fill="var(--brand)" opacity="0.08" />
      <path d={d} fill="none" stroke="var(--brand)" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="3.5" fill="var(--brand)" />
    </svg>
  );
}
