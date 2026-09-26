import { useEffect, useRef, useState } from "react";
import { getJson } from "../../field/api";
import { PROJECTION } from "../MapView";
import { num, regionLabel } from "./Layout";
import type { ExtremePoint, ThermalExtremes } from "./scienceApi";

export const EXTREME_DEPTHS = [0, 50, 75, 100, 125, 150];
const { W, H, left, top, width, height } = PROJECTION;

/** Active thermal-extreme cells drawn over the shared map, in its projection. */
export function ExtremeOverlay({ grid }: { grid: number[][] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    canvas.width = W;
    canvas.height = H;
    const c = canvas.getContext("2d");
    if (!c || !grid.length) return;
    c.clearRect(0, 0, W, H);
    const rows = grid.length;
    const cols = grid[0].length;
    const cw = width / cols;
    const ch = height / rows;
    // magenta: outside both the temperature and the anomaly colour scales
    c.fillStyle = "rgba(236, 72, 190, 0.78)";
    for (let r = 0; r < rows; r++)
      for (let k = 0; k < cols; k++)
        if (grid[r][k]) c.fillRect(left + k * cw, top + (rows - 1 - r) * ch, cw + 0.5, ch + 0.5);
  }, [grid]);
  return <canvas ref={ref} className="grid-overlay" data-testid="extreme-overlay" aria-hidden />;
}

/** SUBSURFACE THERMAL EXTREMES for one historical date: computed, named honestly. */
export function ThermalExtremesPanel({
  date,
  lat,
  lon,
  onGrid,
  available,
}: {
  date: string;
  lat: number;
  lon: number;
  onGrid: (grid: number[][] | null) => void;
  available: boolean;
}) {
  const [depth, setDepth] = useState(100);
  const [data, setData] = useState<ThermalExtremes | null>(null);
  const [point, setPoint] = useState<ExtremePoint | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!available) {
      onGrid(null);
      return;
    }
    let live = true;
    setBusy(true);
    setError("");
    getJson<ThermalExtremes>(`/api/science/thermal-extremes?date=${date}&depth=${depth}`)
      .then((d) => {
        if (!live) return;
        setData(d?.name ? d : null);
        onGrid(d?.active ?? null);
      })
      .catch((e) => live && setError((e as Error).message))
      .finally(() => live && setBusy(false));
    return () => {
      live = false;
    };
  }, [date, depth, available, onGrid]);

  useEffect(() => () => onGrid(null), [onGrid]);

  useEffect(() => {
    if (!available || !data) return;
    let live = true;
    getJson<ExtremePoint>(`/api/science/thermal-extremes/point?date=${date}&lat=${lat}&lon=${lon}&depth=${depth}`)
      .then((p) => live && setPoint(p?.name ? p : null))
      .catch(() => live && setPoint(null));
    return () => {
      live = false;
    };
  }, [date, lat, lon, depth, available, data]);

  if (!available)
    return (
      <p className="notice" data-testid="thermal-extremes-unavailable">
        Subsurface thermal extremes are computed for historical dates only. The latest mode does not
        have enough consecutive qualified days for the 5-day persistence rule, so nothing is shown.
      </p>
    );

  return (
    <div className="ws" data-testid="thermal-extremes" data-depth={depth} data-date={date}>
      <div className="ws-toggle-row">
        <span className="eyebrow">SUBSURFACE THERMAL EXTREME · {date}</span>
        <label className="inline-select">
          DEPTH
          <select aria-label="Thermal extreme depth" value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
            {EXTREME_DEPTHS.map((d) => (
              <option key={d} value={d}>
                {d} m
              </option>
            ))}
          </select>
        </label>
        {busy && <span className="muted small">Evaluating the trailing 60-day window…</span>}
      </div>
      {error && <p className="notice">{error}</p>}
      {data && (
        <div className="fig-row">
          <div className="fig-card">
            <h3>Active extent · {data.depth_m} m</h3>
            <table className="science-table" data-testid="extreme-extent">
              <tbody>
                {Object.entries(data.extent_km2).map(([region, km2]) => (
                  <tr key={region}>
                    <td>{regionLabel(region)}</td>
                    <td>{Math.round(km2).toLocaleString("en-US")} km²</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="ws-note">
              {data.n_active_cells.toLocaleString("en-US")} active cells, shown in magenta on the map while this tab is open.{" "}
              {data.extent_note}.
            </p>
          </div>
          <div className="fig-card" data-testid="extreme-point">
            <h3>Selected location</h3>
            {point ? (
              point.supported ? (
                <dl className="ws-kv">
                  <dt>State</dt>
                  <dd>{point.active ? "ACTIVE" : "Not active"}</dd>
                  <dt>Duration so far</dt>
                  <dd>
                    {point.active ? `${point.duration_at_least ? "≥ " : ""}${point.duration_days} days` : "—"}
                  </dd>
                  <dt>Above threshold</dt>
                  <dd>{num(point.excess_over_threshold_c, 2, "°C")}</dd>
                  <dt>Baseline percentile</dt>
                  <dd>{point.percentile_in_baseline_window == null ? "—" : `${point.percentile_in_baseline_window.toFixed(0)}th`}</dd>
                </dl>
              ) : (
                <p className="ws-note">No physically supported reconstruction at this depth here.</p>
              )
            ) : (
              <p className="ws-note">Select a location on the map.</p>
            )}
          </div>
          <div className="fig-card">
            <h3>Definition</h3>
            <p className="ws-note" data-testid="extreme-rule">
              {data.rule}.
            </p>
            <p className="ws-note" data-testid="mhw-decision">
              {data.mhw_decision}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
