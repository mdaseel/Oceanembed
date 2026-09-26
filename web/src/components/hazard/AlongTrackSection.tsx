import { useEffect, useMemo, useRef, useState } from "react";
import type { SectionPayload } from "./api";

const W = 1200;
const H = 340;
const PAD = { left: 64, right: 96, top: 14, bottom: 42 };
const NO_VALUE = "#141b25";

/** Five-stop sequential ramp for temperature (cool blue to warm red). */
const RAMP: [number, number, number][] = [
  [37, 52, 148],
  [44, 127, 184],
  [127, 205, 187],
  [253, 174, 97],
  [215, 48, 39],
];
function sequential(t: number): string {
  const x = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(x));
  const f = x - i;
  const c = RAMP[i].map((v, k) => Math.round(v + (RAMP[i + 1][k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
/** Symmetric divergent scale for anomaly: blue cooler, red warmer, neutral at zero. */
function divergent(v: number, limit: number): string {
  const t = Math.max(-1, Math.min(1, v / (limit || 1)));
  const k = Math.abs(t);
  const c =
    t < 0
      ? [235 - 190 * k, 240 - 150 * k, 245 - 60 * k]
      : [240 - 20 * k, 235 - 170 * k, 230 - 180 * k];
  return `rgb(${c.map(Math.round).join(",")})`;
}

/** Edges halfway between neighbouring coordinates; the outer edges mirror the inner step. */
function edges(values: number[], floor?: number): number[] {
  if (!values.length) return [];
  if (values.length === 1) return [floor ?? values[0] - 1, values[0] + 1];
  const out = [floor ?? values[0] - (values[1] - values[0]) / 2];
  for (let i = 1; i < values.length; i++) out.push((values[i - 1] + values[i]) / 2);
  const n = values.length - 1;
  out.push(values[n] + (values[n] - values[n - 1]) / 2);
  return out;
}

/**
 * ALONG-TRACK VERTICAL SECTION: distance along a path x OceanEmbed's 15 depths.
 * Each sample and model depth is one block (no smoothing or interpolation);
 * blank blocks are below the local seafloor or have no surface input. Reused
 * for historical, external and user-drawn paths.
 */
export function AlongTrackSection({
  section,
  onMode,
  loading,
  labels,
  testid,
}: {
  section: SectionPayload | null;
  onMode: (mode: "temperature" | "anomaly") => void;
  loading: boolean;
  labels: { path: string; thermal: string };
  testid: string;
}) {
  const [full, setFull] = useState(false);
  const [hover, setHover] = useState<string>("");
  const ref = useRef<HTMLCanvasElement>(null);
  const mode = section?.mode ?? "temperature";
  const maxDepth = full ? 1000 : 200;

  const scale = useMemo(() => {
    if (!section) return null;
    let lo = Infinity,
      hi = -Infinity,
      limit = 0;
    section.depths_m.forEach((d, k) => {
      if (d > maxDepth) return;
      for (const v of section.values[k] ?? []) {
        if (v === null || !Number.isFinite(v)) continue;
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
        limit = Math.max(limit, Math.abs(v));
      }
    });
    return Number.isFinite(lo) ? { lo, hi, limit } : null;
  }, [section, maxDepth]);

  const geometry = useMemo(() => {
    if (!section) return null;
    const xEdges = edges(section.distance_km, section.distance_km.length ? Math.max(0, section.distance_km[0]) : 0);
    const yEdges = edges(section.depths_m, 0);
    const x0 = xEdges[0] ?? 0,
      x1 = xEdges[xEdges.length - 1] ?? 1;
    const plotW = W - PAD.left - PAD.right,
      plotH = H - PAD.top - PAD.bottom;
    const px = (km: number) => PAD.left + ((km - x0) / (x1 - x0 || 1)) * plotW;
    const py = (m: number) => PAD.top + (Math.min(m, maxDepth) / maxDepth) * plotH;
    return { xEdges, yEdges, x0, x1, px, py, plotW, plotH };
  }, [section, maxDepth]);

  const color = (v: number) =>
    !scale
      ? NO_VALUE
      : mode === "anomaly"
        ? divergent(v, scale.limit)
        : sequential((v - scale.lo) / (scale.hi - scale.lo || 1));

  let painted = 0;
  if (section)
    section.depths_m.forEach((d, k) => {
      if (d <= maxDepth) for (const v of section.values[k] ?? []) if (v !== null && Number.isFinite(v)) painted++;
    });

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !section || !geometry) return;
    canvas.width = W;
    canvas.height = H;
    const c = canvas.getContext("2d");
    if (!c) return;
    const { xEdges, yEdges, x0, x1, px, py, plotW, plotH } = geometry;
    c.fillStyle = "#0a0f16";
    c.fillRect(0, 0, W, H);
    c.fillStyle = NO_VALUE;
    c.fillRect(PAD.left, PAD.top, plotW, plotH);

    section.depths_m.forEach((d, k) => {
      if (yEdges[k] >= maxDepth) return;
      const top = py(yEdges[k]),
        bottom = py(yEdges[k + 1]);
      (section.values[k] ?? []).forEach((v, i) => {
        if (v === null || !Number.isFinite(v)) return;
        c.fillStyle = color(v);
        const left = px(xEdges[i]),
          right = px(xEdges[i + 1]);
        c.fillRect(left, top, Math.max(1, right - left + 0.5), Math.max(1, bottom - top + 0.5));
      });
    });

    // Local ETOPO seafloor, drawn only where it is inside the displayed range.
    c.strokeStyle = "#e3eaf2";
    c.lineWidth = 1.5;
    c.setLineDash([4, 4]);
    c.beginPath();
    let open = false;
    section.water_depth_m.forEach((w, i) => {
      if (w === null || w > maxDepth) {
        open = false;
        return;
      }
      const x = px(section.distance_km[i]),
        y = py(w);
      if (open) c.lineTo(x, y);
      else c.moveTo(x, y);
      open = true;
    });
    c.stroke();
    c.setLineDash([]);

    // Axes.
    c.strokeStyle = "#3a4a5e";
    c.lineWidth = 1;
    c.strokeRect(PAD.left, PAD.top, plotW, plotH);
    c.fillStyle = "#aebfd5";
    c.font = "11px system-ui";
    c.textAlign = "right";
    c.textBaseline = "middle";
    for (const d of section.depths_m.filter((d) => d <= maxDepth && (full ? [0, 100, 200, 300, 500, 700, 1000].includes(d) : true)))
      c.fillText(`${d}`, PAD.left - 6, py(d));
    c.textAlign = "center";
    c.textBaseline = "top";
    const step = Math.max(50, Math.ceil((x1 - x0) / 8 / 50) * 50);
    for (let km = Math.ceil(x0 / step) * step; km <= x1; km += step) c.fillText(`${km}`, px(km), H - PAD.bottom + 6);
    c.fillText("Distance along path (km)", PAD.left + plotW / 2, H - 16);
    c.save();
    c.translate(14, PAD.top + plotH / 2);
    c.rotate(-Math.PI / 2);
    c.fillText("Depth (m)", 0, -4);
    c.restore();

    // Colour legend with its numeric range.
    if (scale) {
      const lx = W - PAD.right + 22,
        lh = plotH;
      for (let y = 0; y < lh; y++) {
        const t = 1 - y / lh;
        c.fillStyle =
          mode === "anomaly" ? divergent((t * 2 - 1) * scale.limit, scale.limit) : sequential(t);
        c.fillRect(lx, PAD.top + y, 14, 1);
      }
      c.fillStyle = "#aebfd5";
      c.textAlign = "left";
      c.textBaseline = "middle";
      const hiText = mode === "anomaly" ? `+${scale.limit.toFixed(2)}` : scale.hi.toFixed(1);
      const loText = mode === "anomaly" ? `−${scale.limit.toFixed(2)}` : scale.lo.toFixed(1);
      c.fillText(hiText, lx + 18, PAD.top + 6);
      c.fillText(loText, lx + 18, PAD.top + lh - 6);
      c.fillText("°C", lx + 18, PAD.top + lh / 2);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section, geometry, scale, mode, maxDepth, full]);

  const inspect = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!section || !geometry) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    const y = ((e.clientY - rect.top) / rect.height) * H;
    const { xEdges, yEdges, px, py } = geometry;
    const i = xEdges.findIndex((_, j) => j < xEdges.length - 1 && x >= px(xEdges[j]) && x < px(xEdges[j + 1]));
    const k = yEdges.findIndex((_, j) => j < yEdges.length - 1 && y >= py(yEdges[j]) && y < py(yEdges[j + 1]));
    if (i < 0 || k < 0 || section.depths_m[k] > maxDepth) {
      setHover("");
      return;
    }
    const v = section.values[k]?.[i];
    const w = section.water_depth_m[i];
    setHover(
      `${section.distance_km[i].toFixed(0)} km · ${section.lat[i].toFixed(2)}°N ${section.lon[i].toFixed(2)}°E · ${section.depths_m[k]} m · ${
        v === null || v === undefined || !Number.isFinite(v)
          ? "no value (below seafloor or no input)"
          : `${mode === "anomaly" && v > 0 ? "+" : ""}${v.toFixed(2)} °C`
      }${w === null ? "" : ` · seafloor ${Math.round(w)} m`}`,
    );
  };

  return (
    <div className="along-section" data-testid={testid} data-mode={mode}>
      <div className="panel-heading compact">
        <span className="eyebrow">ALONG-TRACK VERTICAL SECTION</span>
        <div className="section-tools">
          <div className="segmented" role="group" aria-label="Section quantity">
            {(["temperature", "anomaly"] as const).map((m) => (
              <button
                key={m}
                type="button"
                className={mode === m ? "active" : ""}
                aria-pressed={mode === m}
                data-testid={`${testid}-mode-${m}`}
                onClick={() => onMode(m)}
                disabled={loading}
              >
                {m === "temperature" ? "Temperature" : "Anomaly"}
              </button>
            ))}
          </div>
          <div className="segmented" role="group" aria-label="Section depth range">
            <button type="button" className={!full ? "active" : ""} aria-pressed={!full} onClick={() => setFull(false)}>
              Upper 200 m
            </button>
            <button type="button" className={full ? "active" : ""} aria-pressed={full} onClick={() => setFull(true)}>
              0–1000 m
            </button>
          </div>
        </div>
      </div>
      <div className="provenance-pair">
        <span>{labels.path}</span>
        <span>
          {labels.thermal}
          {section ? ` · valid ${section.date}` : ""}
        </span>
      </div>
      {!section ? (
        <p className="empty">{loading ? "Sampling the section…" : "No section yet."}</p>
      ) : (
        <>
          <canvas
            ref={ref}
            className="section-canvas"
            data-testid={`${testid}-canvas`}
            data-painted-cells={painted}
            role="img"
            aria-label={`Vertical ${mode} section along the path, ${section.length_km.toFixed(0)} km, model depths to ${maxDepth} m`}
            onMouseMove={inspect}
            onMouseLeave={() => setHover("")}
          />
          <p className="small section-readout" data-testid={`${testid}-readout`} aria-live="polite">
            {hover || "Hover the section to read a sample. Dotted line: local ETOPO seafloor."}
          </p>
        </>
      )}
      <p className="small muted" data-testid={`${testid}-note`}>
        {section?.note ??
          "Values exist only at OceanEmbed's 15 depths; blank cells are below the seafloor or without input."}{" "}
        {section ? `Depths: ${section.depths_m.join(", ")} m.` : ""}
      </p>
    </div>
  );
}
