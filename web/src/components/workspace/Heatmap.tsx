/**
 * A small labelled matrix, drawn as SVG. Colour encodes the value; the number is
 * printed in each cell when there is room, so the figure never relies on colour
 * alone.
 */

function sequential(t: number): string {
  const stops: [number, number, number][] = [
    [14, 24, 34],
    [22, 78, 99],
    [52, 160, 176],
    [170, 226, 226],
  ];
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const c = stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function divergent(v: number, limit: number): string {
  const t = Math.max(-1, Math.min(1, v / (limit || 1)));
  const k = Math.abs(t);
  const base = [22, 30, 40];
  const end = t < 0 ? [70, 130, 205] : [212, 96, 70];
  const c = base.map((b, i) => Math.round(b + (end[i] - b) * k));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

export function Heatmap({
  rowLabels,
  colLabels,
  values,
  mode,
  format,
  testid,
  rowTitle,
  colTitle,
  highlightRow,
}: {
  rowLabels: string[];
  colLabels: string[];
  values: (number | null)[][];
  mode: "sequential" | "divergent";
  format: (v: number) => string;
  testid?: string;
  rowTitle?: string;
  colTitle?: string;
  highlightRow?: number;
}) {
  const cellW = 58;
  const cellH = 22;
  const left = 62;
  const top = 34;
  const width = left + cellW * colLabels.length + 8;
  const height = top + cellH * rowLabels.length + 8;
  let lo = Infinity;
  let hi = -Infinity;
  let limit = 0;
  for (const row of values)
    for (const v of row)
      if (v != null && Number.isFinite(v)) {
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
        limit = Math.max(limit, Math.abs(v));
      }
  const color = (v: number | null) =>
    v == null || !Number.isFinite(v)
      ? "#10161e"
      : mode === "divergent"
        ? divergent(v, limit)
        : sequential(hi > lo ? (v - lo) / (hi - lo) : 0.5);
  return (
    <svg
      className="heatmap"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${rowTitle ?? "rows"} by ${colTitle ?? "columns"}`}
      data-testid={testid}
      data-rows={rowLabels.length}
      data-cols={colLabels.length}
    >
      {colTitle && (
        <text className="axis-title" x={left} y={11}>
          {colTitle}
        </text>
      )}
      {colLabels.map((c, j) => (
        <text key={c} x={left + j * cellW + cellW / 2} y={top - 7} textAnchor="middle">
          {c}
        </text>
      ))}
      {rowLabels.map((r, i) => (
        <g key={r}>
          <text x={left - 8} y={top + i * cellH + cellH / 2 + 4} textAnchor="end">
            {r}
          </text>
          {colLabels.map((c, j) => {
            const v = values[i]?.[j] ?? null;
            const dark = mode === "sequential" && v != null && hi > lo && (v - lo) / (hi - lo) > 0.62;
            return (
              <g key={c}>
                <rect
                  x={left + j * cellW + 1}
                  y={top + i * cellH + 1}
                  width={cellW - 2}
                  height={cellH - 2}
                  rx={3}
                  fill={color(v)}
                  stroke={highlightRow === i ? "#67e8f9" : "none"}
                  strokeWidth={highlightRow === i ? 1.5 : 0}
                >
                  <title>{`${r} · ${c}: ${v == null ? "no value" : format(v)}`}</title>
                </rect>
                <text
                  className="cell-text"
                  x={left + j * cellW + cellW / 2}
                  y={top + i * cellH + cellH / 2 + 4}
                  textAnchor="middle"
                  style={{ fill: dark ? "#07121a" : "#e6f0f8" }}
                >
                  {v == null ? "—" : format(v)}
                </text>
              </g>
            );
          })}
        </g>
      ))}
    </svg>
  );
}
