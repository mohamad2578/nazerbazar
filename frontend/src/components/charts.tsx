import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { dateShort, num } from "../lib/format";

/** پالت دسته‌ای اعتبارسنجی‌شده (ترتیب ثابت، بدون چرخش) */
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];

const axis = { stroke: "var(--muted)", fontSize: 11, tickLine: false, axisLine: false } as const;
const tooltipStyle = {
  contentStyle: { background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 12, fontFamily: "Vazirmatn", fontSize: 12, direction: "rtl" as const },
  labelStyle: { color: "var(--muted)" },
  itemStyle: { color: "var(--ink)" },
};

export type SeriesDef = { key: string; label: string };

export function TrendChart({ data, series, height = 260, format = (v: number) => num(v) }: { data: any[]; series: SeriesDef[]; height?: number; format?: (v: number) => string }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
        <CartesianGrid stroke="var(--line)" vertical={false} />
        <XAxis dataKey="date" tickFormatter={(d) => dateShort(d)} {...axis} minTickGap={24} reversed />
        <YAxis tickFormatter={(v) => format(v)} {...axis} width={70} orientation="right" domain={["auto", "auto"]} />
        <Tooltip {...tooltipStyle} labelFormatter={(d) => dateShort(d)} formatter={(v: number, name) => [format(v), name]} cursor={{ stroke: "var(--muted)", strokeDasharray: "3 3" }} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline" />}
        {series.map((s, i) => (
          <Line isAnimationActive={false} key={s.key} dataKey={s.key} name={s.label} stroke={SERIES[i]} strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }} connectNulls />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function BarsChart({ data, x, series, height = 260, horizontal }: { data: any[]; x: string; series: SeriesDef[]; height?: number; horizontal?: boolean }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 8, left: 8, bottom: 0 }} barGap={2}>
        <CartesianGrid stroke="var(--line)" horizontal={!horizontal} vertical={!!horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" {...axis} tickFormatter={(v) => num(v)} reversed />
            <YAxis type="category" dataKey={x} {...axis} width={110} orientation="right" />
          </>
        ) : (
          <>
            <XAxis dataKey={x} {...axis} reversed interval={0} tick={{ fontSize: 10 }} />
            <YAxis {...axis} tickFormatter={(v) => num(v)} orientation="right" width={40} />
          </>
        )}
        <Tooltip {...tooltipStyle} formatter={(v: number, name) => [num(v), name]} cursor={{ fill: "var(--surface-2)" }} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {series.map((s, i) => (
          <Bar isAnimationActive={false} key={s.key} dataKey={s.key} name={s.label} fill={SERIES[i]} radius={horizontal ? [4, 0, 0, 4] : [4, 4, 0, 0]} maxBarSize={28} stroke="var(--surface)" strokeWidth={1} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
