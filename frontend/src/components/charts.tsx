"use client";

import { useId, useLayoutEffect, useMemo, useRef, useState } from "react";

export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

export type Series = { id: string; label: string; values: (number | null)[]; color?: string };

type LineChartProps = {
  title: string;
  subtitle?: string;
  series: Series[];
  xLabels: string[];
  yDomain?: [number, number];
  yFormat?: (v: number) => string;
  height?: number;
  dashed?: string[]; // series ids drawn dashed (secondary encoding, e.g. "ground truth")
};

/** Width of an element in CSS px, so charts draw at real size (text never scales down). */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0); // 0 until measured: never let content size the container
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Measure now (ResizeObserver only reports on rendered frames, which background tabs skip)
    setW(Math.max(160, Math.round(el.getBoundingClientRect().width)));
    const ro = new ResizeObserver(([e]) => setW(Math.max(160, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

/** Line chart: one y-axis, 2px lines, 8px markers, hairline grid, crosshair + tooltip,
 *  legend for >= 2 series plus direct end labels (<= 4 series). */
export function LineChart({
  title,
  subtitle,
  series,
  xLabels,
  yDomain,
  yFormat = (v) => v.toFixed(2),
  height = 200,
  dashed = [],
}: LineChartProps) {
  const [hover, setHover] = useState<number | null>(null);
  const [boxRef, W] = useWidth<HTMLDivElement>();
  const clipId = useId();
  const multi = series.length > 1;
  const PAD = { top: 12, right: multi ? 96 : 14, bottom: 26, left: 38 };
  const all = series.flatMap((s) => s.values.filter((v): v is number => v != null));
  const [y0, y1] = useMemo(() => {
    if (yDomain) return yDomain;
    if (!all.length) return [0, 1];
    const lo = Math.min(...all);
    const hi = Math.max(...all);
    const pad = (hi - lo || Math.abs(hi) || 1) * 0.15;
    return [Math.max(0, lo - pad), hi + pad];
  }, [yDomain, all]);

  const n = xLabels.length;
  const iw = W - PAD.left - PAD.right;
  const ih = height - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (n <= 1 ? iw / 2 : (i / (n - 1)) * iw);
  const y = (v: number) => PAD.top + ih - ((v - y0) / (y1 - y0 || 1)) * ih;
  const ticks = [0, 0.5, 1].map((t) => y0 + t * (y1 - y0));
  const maxXLabels = Math.max(2, Math.floor(iw / 36));

  const path = (vals: (number | null)[]) => {
    let d = "";
    let pen = false;
    vals.forEach((v, i) => {
      if (v == null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  };

  // End labels, nudged apart so they never collide.
  const ends = series
    .map((s, si) => {
      const last = [...s.values].reverse().findIndex((v) => v != null);
      if (last < 0) return null;
      const i = s.values.length - 1 - last;
      return { s, si, i, yy: y(s.values[i] as number) };
    })
    .filter((e): e is NonNullable<typeof e> => e != null)
    .sort((a, b) => a.yy - b.yy);
  for (let k = 1; k < ends.length; k++) {
    if (ends[k].yy - ends[k - 1].yy < 13) ends[k].yy = ends[k - 1].yy + 13;
  }

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * iw;
    setHover(Math.max(0, Math.min(n - 1, Math.round((px / iw) * (n - 1)))));
  };

  return (
    <figure className="min-w-0 rounded-2xl bg-[var(--card)] p-4">
      <figcaption className="mb-2">
        <div className="text-sm font-medium">{title}</div>
        {subtitle && <div className="text-xs text-[var(--muted)]">{subtitle}</div>}
      </figcaption>
      {multi && (
        <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--ink-2)]">
          {series.map((s, i) => (
            <li key={s.id} className="flex items-center gap-1.5">
              <svg width="18" height="8" aria-hidden>
                <line
                  x1="1" y1="4" x2="17" y2="4" strokeWidth="2" strokeLinecap="round"
                  stroke={s.color ?? SERIES[i]} strokeDasharray={dashed.includes(s.id) ? "3 3" : undefined}
                />
              </svg>
              {s.label}
            </li>
          ))}
        </ul>
      )}
      <div className="relative w-full min-w-0" ref={boxRef} style={{ height }}>
        {W > 0 && <svg width={W} height={height} className="block overflow-visible" role="img" aria-label={title}>
          <clipPath id={clipId}>
            <rect x={PAD.left - 6} y={0} width={iw + 12} height={height} />
          </clipPath>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={PAD.left + iw} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" strokeWidth="1" />
              <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize="11" fill="var(--viz-axis)">
                {yFormat(t)}
              </text>
            </g>
          ))}
          {xLabels.map((l, i) =>
            n <= maxXLabels || i % Math.ceil(n / maxXLabels) === 0 || i === n - 1 ? (
              <text key={i} x={x(i)} y={height - 8} textAnchor="middle" fontSize="11" fill="var(--viz-axis)">
                {l}
              </text>
            ) : null,
          )}
          {hover != null && (
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + ih} stroke="var(--viz-axis)" strokeWidth="1" />
          )}
          <g clipPath={`url(#${clipId})`}>
            {series.map((s, si) => (
              <g key={s.id}>
                <path
                  d={path(s.values)} fill="none" stroke={s.color ?? SERIES[si]} strokeWidth="2"
                  strokeLinejoin="round" strokeLinecap="round"
                  strokeDasharray={dashed.includes(s.id) ? "5 4" : undefined}
                />
                {s.values.map((v, i) =>
                  v == null ? null : (
                    <circle
                      key={i} cx={x(i)} cy={y(v)} r={hover === i ? 5 : 4}
                      fill={s.color ?? SERIES[si]} stroke="var(--card)" strokeWidth="2"
                    />
                  ),
                )}
              </g>
            ))}
          </g>
          {multi &&
            ends.map((e) => (
              <text key={e.s.id} x={x(e.i) + 10} y={e.yy} dy="0.32em" fontSize="11" fill="var(--ink-2)">
                {e.s.label.length > 14 ? e.s.label.slice(0, 13) + "…" : e.s.label}
              </text>
            ))}
          <rect
            x={PAD.left} y={PAD.top} width={iw} height={ih} fill="transparent"
            onPointerMove={onMove} onPointerLeave={() => setHover(null)}
          />
        </svg>}
        {hover != null && (
          <div
            className="pointer-events-none absolute top-0 z-10 rounded-lg bg-[var(--bg)] px-3 py-2 text-xs shadow-lg ring-1 ring-[var(--viz-grid)]"
            style={{
              left: `${(x(hover) / W) * 100}%`,
              transform: x(hover) > W * 0.6 ? "translateX(calc(-100% - 10px))" : "translateX(10px)",
            }}
          >
            <div className="mb-1 text-[var(--muted)]">{xLabels[hover]}</div>
            {series.map((s, si) => (
              <div key={s.id} className="flex items-center gap-2 whitespace-nowrap">
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.color ?? SERIES[si] }} />
                <span className="text-[var(--ink-2)]">{s.label}</span>
                <span className="ml-auto pl-3 font-medium tabular-nums text-[var(--fg)]">
                  {s.values[hover] == null ? "–" : yFormat(s.values[hover] as number)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </figure>
  );
}

export type Bar = { id: string; label: string; value: number; low?: number; high?: number; note?: string };

/** Horizontal 0..1 bars with an uncertainty whisker. Thin bars, rounded data end. */
export function MasteryBars({ title, subtitle, bars }: { title: string; subtitle?: string; bars: Bar[] }) {
  const [hover, setHover] = useState<string | null>(null);
  return (
    <figure className="min-w-0 rounded-2xl bg-[var(--card)] p-4">
      <figcaption className="mb-3">
        <div className="text-sm font-medium">{title}</div>
        {subtitle && <div className="text-xs text-[var(--muted)]">{subtitle}</div>}
      </figcaption>
      <ul className="flex flex-col gap-2.5">
        {bars.map((b) => (
          <li
            key={b.id}
            className="grid grid-cols-[minmax(0,11rem)_1fr_3.5rem] items-center gap-3 text-xs"
            onPointerEnter={() => setHover(b.id)}
            onPointerLeave={() => setHover(null)}
          >
            <span className="truncate text-[var(--ink-2)]" title={b.label}>
              {b.label}
            </span>
            <div className="relative h-3">
              <div className="absolute inset-y-[5px] left-0 right-0 rounded-full bg-[var(--viz-grid)]" />
              {b.low != null && b.high != null && (
                <div
                  className="absolute top-1/2 h-px -translate-y-1/2 bg-[var(--viz-axis)]"
                  style={{ left: `${b.low * 100}%`, width: `${(b.high - b.low) * 100}%` }}
                />
              )}
              <div
                className="absolute inset-y-[2px] left-0 rounded-r-[4px] bg-[var(--series-1)]"
                style={{ width: `max(${b.value * 100}%, 4px)` }}
              />
              {hover === b.id && (
                <div className="pointer-events-none absolute -top-9 left-0 z-10 whitespace-nowrap rounded-lg bg-[var(--bg)] px-2.5 py-1.5 shadow-lg ring-1 ring-[var(--viz-grid)]">
                  {(b.value * 100).toFixed(0)}%
                  {b.low != null && b.high != null && (
                    <span className="text-[var(--muted)]">
                      {" "}
                      (likely {(b.low * 100).toFixed(0)}–{(b.high * 100).toFixed(0)}%)
                    </span>
                  )}
                  {b.note && <span className="text-[var(--muted)]"> · {b.note}</span>}
                </div>
              )}
            </div>
            <span className="text-right tabular-nums text-[var(--fg)]">{(b.value * 100).toFixed(0)}%</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

export function StatTile({ label, value, delta, hint }: { label: string; value: string; delta?: string; hint?: string }) {
  return (
    <div className="rounded-2xl bg-[var(--card)] p-4">
      <div className="text-xs text-[var(--muted)]">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {delta && <div className="mt-0.5 text-xs text-[var(--ink-2)]">{delta}</div>}
      {hint && <div className="mt-0.5 text-xs text-[var(--muted)]">{hint}</div>}
    </div>
  );
}

/** Table view: the accessible twin of every chart. */
export function DataTable({ columns, rows }: { columns: string[]; rows: (string | number | null)[][] }) {
  return (
    <div className="overflow-x-auto rounded-2xl bg-[var(--card)] p-4">
      <table className="w-full text-left text-xs tabular-nums">
        <thead className="text-[var(--muted)]">
          <tr>
            {columns.map((c) => (
              <th key={c} className="pb-2 pr-4 font-normal">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-[var(--viz-grid)]">
              {r.map((c, j) => (
                <td key={j} className="py-1.5 pr-4">
                  {c ?? "–"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
