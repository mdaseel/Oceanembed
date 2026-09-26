import { useEffect, useRef, useState } from "react";
import { coordText, signed } from "../../field/hazardIntelligence";
import { PROJECTION, pixelToLatLon } from "../MapView";
import type { FieldView } from "../../field/contract";
import { getJson, type ChangeStats, type DifferencePayload } from "./api";

const { W, H, left, top, width, height } = PROJECTION;
const DEPTHS = [0, 30, 50, 75, 100, 125, 150, 200, 300, 500];

function divergent(v: number, limit: number): [number, number, number] {
  const t = Math.max(-1, Math.min(1, v / (limit || 1)));
  // blue for cooling, light neutral near zero, red for warming
  if (t < 0) {
    const k = -t;
    return [Math.round(235 - 190 * k), Math.round(240 - 150 * k), Math.round(245 - 60 * k)];
  }
  return [Math.round(240 - 20 * t), Math.round(235 - 170 * t), Math.round(230 - 180 * t)];
}

/** A continuous change map in the shared projection. Blank means no value in either composite. */
function DifferenceCanvas({
  grid,
  field,
  unit,
  onSelect,
}: {
  grid: (number | null)[][];
  field: FieldView;
  unit: string;
  onSelect: (lat: number, lon: number) => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    canvas.width = W;
    canvas.height = H;
    const c = canvas.getContext("2d")!;
    c.fillStyle = "#06080d";
    c.fillRect(0, 0, W, H);
    const rows = grid.length,
      cols = grid[0]?.length ?? 0;
    let limit = 0;
    for (const row of grid) for (const v of row) if (v !== null) limit = Math.max(limit, Math.abs(v));
    const image = c.createImageData(width, height);
    if (image?.data && rows && cols) {
      for (let y = 0; y < height; y++)
        for (let x = 0; x < width; x++) {
          const r = rows - 1 - Math.min(rows - 1, Math.floor((y / height) * rows));
          const col = Math.min(cols - 1, Math.floor((x / width) * cols));
          const v = grid[r][col];
          const rgb: [number, number, number] = v === null ? [16, 22, 30] : divergent(v, limit);
          const o = (y * width + x) * 4;
          image.data[o] = rgb[0];
          image.data[o + 1] = rgb[1];
          image.data[o + 2] = rgb[2];
          image.data[o + 3] = 255;
        }
      c.putImageData(image, left, top);
    }
    c.font = "600 18px system-ui";
    c.fillStyle = "#ced9e7";
    c.fillText("Change between segment composites (later minus earlier)", left, 28);
    c.font = "13px system-ui";
    c.fillStyle = "#9fb3c8";
    c.fillText(
      `Blue = cooler, red = warmer · colour range ±${limit.toFixed(2)} ${unit} · dark = no value`,
      left,
      672,
    );
  }, [grid, unit]);
  return (
    <canvas
      ref={ref}
      className="map-canvas"
      data-testid="difference-map"
      role="img"
      aria-label="Change map between segment composites. Click to inspect a grid cell."
      onClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const hit = pixelToLatLon(
          ((e.clientX - rect.left) / rect.width) * W,
          ((e.clientY - rect.top) / rect.height) * H,
          field,
        );
        if (hit) onSelect(hit[0], hit[1]);
      }}
    />
  );
}

const stat = (s: ChangeStats | undefined, unit: string, digits: number) =>
  s && s.min ? `${signed(s.min.value, digits, unit)} at ${coordText(s.min.lat, s.min.lon)}` : "—";

/** OCEAN CHANGE and COLD-WAKE FOOTPRINT between frozen segments. */
export function OceanChangePanel({
  eventId,
  field,
  onSelect,
}: {
  eventId: string;
  field: FieldView;
  onSelect: (lat: number, lon: number) => void;
}) {
  const [to, setTo] = useState<"Event" | "Wake" | "Recovery">("Wake");
  const [depth, setDepth] = useState(100);
  const [quantity, setQuantity] = useState<"temperature" | "tchp">("temperature");
  const [data, setData] = useState<DifferencePayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setBusy(true);
    setError("");
    getJson<DifferencePayload>(
      `/api/events/${eventId}/difference?from_segment=Pre-event&to_segment=${to}&depth=${depth}&tchp_grid=true`,
    )
      .then((d) => live && setData(d))
      .catch((e) => live && setError((e as Error).message))
      .finally(() => live && setBusy(false));
    return () => {
      live = false;
    };
  }, [eventId, to, depth]);

  const grid = quantity === "tchp" ? data?.tchp_grid : data?.grid?.values;
  const fp = data?.footprint;
  return (
    <div className="ocean-change" data-testid="ocean-change" data-to={to} data-depth={depth}>
      <div className="panel-heading compact">
        <span className="eyebrow">OCEAN CHANGE · PRE-EVENT → {to.toUpperCase()}</span>
        <div className="section-tools">
          <div className="segmented" role="group" aria-label="Comparison">
            {(["Event", "Wake", "Recovery"] as const).map((s) => (
              <button
                key={s}
                type="button"
                className={to === s ? "active" : ""}
                aria-pressed={to === s}
                data-testid={`change-to-${s.toLowerCase()}`}
                onClick={() => setTo(s)}
              >
                PRE → {s.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="segmented" role="group" aria-label="Change quantity">
            <button
              type="button"
              className={quantity === "temperature" ? "active" : ""}
              aria-pressed={quantity === "temperature"}
              onClick={() => setQuantity("temperature")}
            >
              ΔTemperature
            </button>
            <button
              type="button"
              className={quantity === "tchp" ? "active" : ""}
              aria-pressed={quantity === "tchp"}
              data-testid="change-quantity-tchp"
              onClick={() => setQuantity("tchp")}
            >
              ΔTCHP
            </button>
          </div>
          {quantity === "temperature" && (
            <label className="inline-select">
              DEPTH
              <select
                aria-label="Change depth"
                value={depth}
                onChange={(e) => setDepth(Number(e.target.value))}
              >
                {DEPTHS.map((d) => (
                  <option key={d} value={d}>
                    {d} m
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </div>
      {error && <p className="notice">{error}</p>}
      {busy && !data && <p className="muted" role="status">Compositing the frozen segments…</p>}
      {data && grid && (
        <DifferenceCanvas
          grid={grid}
          field={field}
          unit={quantity === "tchp" ? "kJ/cm²" : "°C"}
          onSelect={onSelect}
        />
      )}
      {data && (
        <p className="small muted">
          {data.label} Pre-event: {data.from_dates.join(", ")} · {data.to_segment}:{" "}
          {data.to_dates.join(", ")}. {data.rule}
        </p>
      )}
      {fp && (
        <div className="footprint" data-testid="cold-wake-footprint">
          <span className="eyebrow">COLD-WAKE FOOTPRINT · PRE-EVENT → {to.toUpperCase()}</span>
          <table className="level-table">
            <thead>
              <tr>
                <th>Quantity</th>
                <th>Strongest cooling</th>
                <th>Largest warming</th>
                <th>Median change</th>
              </tr>
            </thead>
            <tbody>
              {(["0", "50", "75", "100"] as const).map((d) => {
                const s = fp.temperature[d];
                return (
                  <tr key={d} data-depth={d}>
                    <td>{d === "0" ? "Nominal 0 m temperature" : `${d} m temperature`}</td>
                    <td>{stat(s, "°C", 2)}</td>
                    <td>{s?.max ? `${signed(s.max.value, 2, "°C")} at ${coordText(s.max.lat, s.max.lon)}` : "—"}</td>
                    <td>{s?.median == null ? "—" : signed(s.median, 2, "°C")}</td>
                  </tr>
                );
              })}
              <tr data-depth="tchp">
                <td>TCHP</td>
                <td>{stat(fp.tchp, "kJ/cm²", 1)}</td>
                <td>
                  {fp.tchp.max
                    ? `${signed(fp.tchp.max.value, 1, "kJ/cm²")} at ${coordText(fp.tchp.max.lat, fp.tchp.max.lon)}`
                    : "—"}
                </td>
                <td>{fp.tchp.median == null ? "—" : signed(fp.tchp.median, 1, "kJ/cm²")}</td>
              </tr>
            </tbody>
          </table>
          <p className="small">
            Where cooling appears, the reconstructed pattern may be consistent with
            cyclone-associated cooling or mixing. {data?.caution} No cold-wake severity score is
            assigned.
          </p>
        </div>
      )}
    </div>
  );
}
