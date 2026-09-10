import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  HAZARD_ORDER,
  diagnosticAt,
  format,
  hazardAt,
  offset,
  type FieldView,
  type Selection,
} from "../field/contract";
import { getJson } from "../field/api";
import { PROJECTION, pixelToLatLon } from "./MapView";
import { currentMapRelief, loadMapRelief } from "../field/mapAppearance";
import { useBathymetry } from "../field/bathymetry";
const Plot = lazy(() => import("./Plot"));

/**
 * Ocean Hazard Indicators — HISTORICAL only.
 *
 * Every number here comes from the backend's `replay_field` result and the
 * frozen Phase 7C diagnostics. Nothing is categorised, thresholded or
 * recomputed in this file, and no numeric cyclone probability exists anywhere
 * in it.
 */

const { W, H, left, top, width, height } = PROJECTION;

/** Categorical, ordered, and distinct from every scientific temperature ramp. */
const CATEGORY_RGB: Record<string, [number, number, number]> = {
  LOW: [38, 84, 124],
  MODERATE: [64, 145, 140],
  ELEVATED: [222, 158, 54],
  HIGH: [193, 61, 44],
  NOT_CATEGORIZED: [48, 52, 58],
};
const OUTSIDE: [number, number, number] = [10, 22, 30];

interface TrackPoint {
  time: string;
  lat: number;
  lon: number;
  imd_wind_kt: number | null;
  imd_pressure_hpa: number | null;
}
interface EventInfo {
  name: string;
  basin: string;
  window_start: string;
  window_end: string;
  peak: string;
  landfall: string;
  segments: { label: string; start: string; end: string }[];
  independence_note: string;
  claim_note: string;
  track_available: boolean;
  track: {
    citation: string;
    agency: string;
    provider: string;
    dataset: string;
    peak_imd_wind_kt: number | null;
    min_imd_pressure_hpa: number | null;
    points: TrackPoint[];
  } | null;
}
interface SeriesRow {
  date: string;
  n_cells: number;
  sst_nominal_0m_c: number | null;
  temp_100m_c: number | null;
  anomaly_100m_c: number | null;
  d26_m: number | null;
  tchp_kj_cm2: number | null;
}

export default function Hazard({
  field: f,
  selection,
  onSelect,
  onDate,
}: {
  field: FieldView;
  selection: Selection;
  onSelect: (lat: number, lon: number) => void;
  onDate: (date: string) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [reliefReady, setReliefReady] = useState(!!currentMapRelief());
  const [event, setEvent] = useState<EventInfo | null>(null);
  const [series, setSeries] = useState<SeriesRow[] | null>(null);
  const [seriesError, setSeriesError] = useState("");
  const [seriesBusy, setSeriesBusy] = useState(false);
  const { data: bathymetry } = useBathymetry();

  useEffect(() => {
    let active = true;
    loadMapRelief().then(() => active && setReliefReady(true)).catch(() => {});
    getJson<EventInfo>("/api/event")
      .then((e) => active && setEvent(e))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const hazard = f.hazard;
  const here = hazardAt(f, selection);
  const d26 = diagnosticAt(f, "d26", selection);
  const tchp = diagnosticAt(f, "tchp", selection);
  const anomaly100 =
    selection.row >= 0
      ? f.anomaly[offset(f, selection.row, selection.col, f.depths.indexOf(100))]
      : NaN;
  const waterDepth =
    bathymetry && selection.row >= 0
      ? bathymetry.depths[selection.row * f.lon.length + selection.col]
      : undefined;

  useEffect(() => {
    if (!canvas.current || !hazard) return;
    const element = canvas.current;
    element.width = W;
    element.height = H;
    const c = element.getContext("2d")!;
    c.fillStyle = "#06080d";
    c.fillRect(0, 0, W, H);
    const rows = f.lat.length,
      cols = f.lon.length;
    const image = c.createImageData(width, height);
    for (let y = 0; y < height; y++)
      for (let x = 0; x < width; x++) {
        const r = rows - 1 - Math.min(rows - 1, Math.floor((y / height) * rows));
        const col = Math.min(cols - 1, Math.floor((x / width) * cols));
        const i = r * cols + col;
        const inside = !!(f.ocean[i] && f.inputValid[i]);
        const name = hazard.categoryLabels[hazard.category[i]] ?? "NOT_CATEGORIZED";
        const rgb = inside ? (CATEGORY_RGB[name] ?? OUTSIDE) : OUTSIDE;
        const o = (y * width + x) * 4;
        image.data[o] = rgb[0];
        image.data[o + 1] = rgb[1];
        image.data[o + 2] = rgb[2];
        image.data[o + 3] = 255;
      }
    c.putImageData(image, left, top);
    const relief = currentMapRelief();
    if (relief) c.drawImage(relief, left, top, width, height);

    const cw = width / cols,
      ch = height / rows;
    const project = (lat: number, lon: number): [number, number] => [
      left + ((lon - 45) / 0.25 + 0.5) * cw,
      top + ((30 - lat) / 0.25 + 0.5) * ch,
    ];
    // The track is only drawn over the ocean state it actually crossed. Laying
    // a 2023 storm over a 2021 field would imply a relationship that does not
    // exist, so outside the event window it is omitted entirely.
    const withinWindow =
      !!event &&
      f.effectiveDate >= event.window_start &&
      f.effectiveDate <= event.window_end;
    const points = withinWindow ? (event?.track?.points ?? []) : [];
    if (points.length) {
      c.strokeStyle = "#ffffff";
      c.lineWidth = 3;
      c.setLineDash([7, 5]);
      c.beginPath();
      points.forEach((p, i) => {
        const [x, y] = project(p.lat, p.lon);
        i === 0 ? c.moveTo(x, y) : c.lineTo(x, y);
      });
      c.stroke();
      c.setLineDash([]);
      for (const p of points) {
        if (p.imd_wind_kt == null) continue;
        const [x, y] = project(p.lat, p.lon);
        c.fillStyle = "#ffffff";
        c.beginPath();
        c.arc(x, y, Math.max(2, Math.min(7, p.imd_wind_kt / 22)), 0, Math.PI * 2);
        c.fill();
      }
    }
    if (selection.row >= 0) {
      const [x, y] = project(f.lat[selection.row], f.lon[selection.col]);
      c.strokeStyle = "#ffffff";
      c.lineWidth = 3;
      c.beginPath();
      c.arc(x, y, 9, 0, Math.PI * 2);
      c.stroke();
    }
    c.font = "600 19px system-ui";
    c.fillStyle = "#ced9e7";
    c.fillText(
      `${f.effectiveDate}  /  Ocean Thermal Support for Cyclone Intensification`,
      left,
      28,
    );
    // Legend, drawn on the map so it travels with a screenshot. The categories
    // are labelled THERMAL SUPPORT so HIGH cannot be read as "high cyclone
    // risk" — it means high reconstructed upper-ocean heat, nothing more.
    c.font = "600 13px system-ui";
    c.fillStyle = "#8fa6bd";
    c.fillText("THERMAL SUPPORT (ocean heat available, not cyclone risk)", left, 668);
    c.font = "14px system-ui";
    let x0 = left;
    for (const name of [...HAZARD_ORDER, "NOT_CATEGORIZED"]) {
      const rgb = CATEGORY_RGB[name];
      c.fillStyle = `rgb(${rgb.join(",")})`;
      c.fillRect(x0, 680, 22, 12);
      c.fillStyle = "#d5dfed";
      const count = hazard.categoryCounts[name] ?? 0;
      const text = `${name.replace("_", " ")} (${count.toLocaleString()})`;
      c.fillText(text, x0 + 28, 691);
      x0 += 32 + c.measureText(text).width + 24;
    }
    c.font = "12px system-ui";
    c.fillStyle = "#94a8c1";
    c.fillText(
      points.length
        ? `Observed best track: ${event?.track?.dataset} · ${event?.track?.agency}. Static context — never a model input or output.`
        : withinWindow
          ? "Best track unavailable — run scripts/poc/build_event_track.py"
          : `Track not drawn: ${f.effectiveDate} is outside the ${event?.name ?? "event"} window.`,
      left,
      716,
    );
    c.fillText(f.credits, left, 736);
  }, [f, hazard, selection, event, reliefReady]);

  // Two different causes, and they must not be confused: the server may not be
  // serving a hazard block at all (an older backend still running), or it may
  // be serving one that could not load its frozen thresholds. Naming the wrong
  // one sends the reader to fix something that is not broken.
  if (!hazard)
    return (
      <section className="panel">
        <span className="eyebrow">OCEAN HAZARD INDICATORS</span>
        <h2>Indicator not served by this backend</h2>
        <p className="notice" data-testid="hazard-stale-backend">
          This reconstruction arrived without a hazard block, which means the
          running server predates Phase 7D. The thresholds on disk are not the
          problem. Restart the local server so it picks up the current backend:{" "}
          <code>python scripts/poc/serve.py</code>.
        </p>
      </section>
    );
  if (!hazard.available)
    return (
      <section className="panel">
        <span className="eyebrow">OCEAN HAZARD INDICATORS</span>
        <h2>Indicator unavailable</h2>
        <p className="notice" data-testid="hazard-no-thresholds">
          The backend served a hazard block but could not load the frozen
          thresholds, so no category can be assigned. Nothing is shown rather
          than a guessed level. Run{" "}
          <code>scripts/diagnostics/build_hazard_thresholds.py</code>.
        </p>
      </section>
    );

  const t = hazard.thresholds!;
  const level = here?.label ?? "NOT_CATEGORIZED";
  const inEventWindow =
    !!event &&
    f.effectiveDate >= event.window_start &&
    f.effectiveDate <= event.window_end;
  const reason =
    tchp && !Number.isFinite(tchp.value)
      ? tchp.status === "SURFACE_BELOW_26"
        ? "the whole column is below 26 °C"
        : "the diagnostic is unavailable here"
      : tchp && tchp.physical !== "SUPPORTED"
        ? "there is no water column to support it"
        : "";

  return (
    <>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">OCEAN HAZARD INDICATORS · HISTORICAL</span>
            <h2>{hazard.indicator}</h2>
          </div>
          <span className="chip">{f.effectiveDate}</span>
        </div>
        <p className="notice" data-testid="hazard-non-prediction">
          {hazard.nonPrediction}
        </p>
        <div className="stats-grid">
          <div className="stat" data-testid="hazard-level">
            <span>OCEAN THERMAL SUPPORT · SELECTED CELL</span>
            <strong>
              {level === "NOT_CATEGORIZED"
                ? "NOT CATEGORIZED"
                : `${level} THERMAL SUPPORT`}
            </strong>
            {reason && <span className="small muted">{reason}</span>}
          </div>
          <div className="stat">
            <span>UPPER-OCEAN HEAT RESERVOIR · TCHP</span>
            <strong>
              {tchp && Number.isFinite(tchp.value) && tchp.physical === "SUPPORTED"
                ? `${format(tchp.value, 1)} kJ/cm²`
                : "Unavailable"}
            </strong>
          </div>
          <div className="stat">
            <span>D26 · 26 °C ISOTHERM DEPTH</span>
            <strong>
              {d26 && Number.isFinite(d26.value) && d26.physical === "SUPPORTED"
                ? `${format(d26.value, 1)} m`
                : "Unavailable"}
            </strong>
          </div>
          <div className="stat">
            <span>SUBSURFACE THERMAL ANOMALY · 100 m</span>
            <strong>
              {Number.isFinite(anomaly100) ? `${format(anomaly100, 2)} °C` : "Unavailable"}
            </strong>
          </div>
        </div>
      </section>

      <section className="panel" data-testid="why-this-level">
        <span className="eyebrow">EXPLAINABILITY</span>
        <h2>Why this level?</h2>
        <table>
          <tbody>
            <tr>
              <td>Categorising quantity</td>
              <td>
                TCHP ={" "}
                {tchp && Number.isFinite(tchp.value)
                  ? `${format(tchp.value, 1)} kJ/cm²`
                  : "unavailable"}
              </td>
            </tr>
            <tr>
              <td>Frozen boundaries</td>
              <td>
                MODERATE ≥ {t.p50.toFixed(1)} · ELEVATED ≥ {t.p75.toFixed(1)} ·
                HIGH ≥ {t.p90.toFixed(1)} kJ/cm²
              </td>
            </tr>
            <tr>
              <td>Boundary source</td>
              <td>
                percentiles of OceanEmbed's own TCHP over {t.reference_period},{" "}
                {t.n_dates} dates, {t.n_samples.toLocaleString()} samples
              </td>
            </tr>
            <tr>
              <td>Supporting D26</td>
              <td>
                {d26 && Number.isFinite(d26.value) ? `${format(d26.value, 1)} m` : "—"}
                {waterDepth !== undefined && Number.isFinite(waterDepth)
                  ? ` within ${waterDepth.toFixed(0)} m of local water`
                  : ""}
              </td>
            </tr>
            <tr>
              <td>Subsurface anomaly at 100 m</td>
              <td>{Number.isFinite(anomaly100) ? `${format(anomaly100, 2)} °C` : "—"}</td>
            </tr>
            <tr>
              <td>Reconstruction error</td>
              <td>
                TCHP MAE {hazard.error.mae} · RMSE {hazard.error.rmse} · bias +
                {hazard.error.bias} kJ/cm² ({hazard.error.source})
              </td>
            </tr>
            <tr>
              <td>Model</td>
              <td>
                <code>{f.provenance.l2_state_dict_sha256.slice(0, 16)}…</code>
              </td>
            </tr>
          </tbody>
        </table>
        <p className="muted small">{hazard.uncertaintyNote}</p>
        <p className="muted small">{hazard.scopeNote}</p>
        <p className="muted small">
          Protocol: <code>{hazard.protocol}</code>
        </p>
      </section>

      <section className="panel map-panel">
        <span className="eyebrow">
          {event ? `${event.name} · ${event.basin}` : "EVENT"}
        </span>
        <h2>Thermal support and the observed track</h2>
        {event && <p className="muted small">{event.claim_note}</p>}
        {event && !inEventWindow && (
          <p className="notice" data-testid="outside-event-window">
            Showing <strong>{f.effectiveDate}</strong>, which is outside the{" "}
            {event.name} window ({event.window_start} to {event.window_end}).
            The observed track is not drawn over an ocean state it never
            crossed.{" "}
            <button className="btn" onClick={() => onDate(event.peak)}>
              Show peak intensity ({event.peak})
            </button>
          </p>
        )}
        <canvas
          ref={canvas}
          className="map-canvas"
          data-testid="hazard-map"
          role="img"
          aria-label="Ocean thermal support categories with the observed cyclone track."
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const hit = pixelToLatLon(
              ((e.clientX - rect.left) / rect.width) * W,
              ((e.clientY - rect.top) / rect.height) * H,
              f,
            );
            if (hit) onSelect(hit[0], hit[1]);
          }}
        />
        {event?.track && (
          <p className="muted small" data-testid="track-attribution">
            {event.track.citation} Peak {event.track.peak_imd_wind_kt} kt ·{" "}
            {event.track.min_imd_pressure_hpa} hPa ({event.track.agency}).
            {inEventWindow
              ? ""
              : " Drawn only on dates inside the event window."}
          </p>
        )}
      </section>

      <section className="panel" data-testid="cold-wake">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">COLD WAKE &amp; THERMAL RECOVERY</span>
            <h2>{event ? `${event.name} window` : "Event window"}</h2>
          </div>
          <button
            className="btn"
            disabled={seriesBusy}
            onClick={() => {
              setSeriesBusy(true);
              setSeriesError("");
              getJson<{ series: SeriesRow[] }>("/api/event/series")
                .then((r) => setSeries(r.series))
                .catch((e) => setSeriesError(String(e)))
                .finally(() => setSeriesBusy(false));
            }}
          >
            {seriesBusy ? "Replaying each day…" : "Run the event window"}
          </button>
        </div>
        {event && <p className="muted small">{event.independence_note}</p>}
        {seriesError && <p className="panel error-state">{seriesError}</p>}
        {!series && !seriesBusy && !seriesError && (
          <p className="empty">
            Each day of the window is an independent frozen-L2 reconstruction.
            Run it to see the cold wake and recovery.
          </p>
        )}
        {series && (
          <Suspense fallback={<p className="empty">Loading chart…</p>}>
            <Plot
              // Three quantities, three units, three panels sharing one date
              // axis. They must never share a y-axis: metres and kJ/cm2 happen
              // to overlap numerically here (66-71 vs 67-89), so a shared axis
              // would look plausible while being meaningless.
              data={[
                {
                  x: series.map((r) => r.date),
                  y: series.map((r) => r.sst_nominal_0m_c),
                  name: "Nominal 0 m",
                  type: "scatter",
                  mode: "lines+markers",
                  line: { color: "#f0913a", width: 2 },
                  hovertemplate: "%{y:.2f} °C · %{x}<extra></extra>",
                },
                {
                  x: series.map((r) => r.date),
                  y: series.map((r) => r.d26_m),
                  name: "D26",
                  type: "scatter",
                  mode: "lines+markers",
                  yaxis: "y2",
                  line: { color: "#9db4c8", width: 2 },
                  hovertemplate: "%{y:.1f} m · %{x}<extra></extra>",
                },
                {
                  x: series.map((r) => r.date),
                  y: series.map((r) => r.tchp_kj_cm2),
                  name: "TCHP",
                  type: "scatter",
                  mode: "lines+markers",
                  yaxis: "y3",
                  line: { color: "#67e8f9", width: 2 },
                  hovertemplate: "%{y:.1f} kJ/cm² · %{x}<extra></extra>",
                },
              ]}
              layout={{
                autosize: true,
                height: 560,
                paper_bgcolor: "transparent",
                plot_bgcolor: "transparent",
                font: { color: "#aebfd5", family: "system-ui", size: 11 },
                margin: { l: 68, r: 24, t: 24, b: 56 },
                showlegend: false,
                xaxis: { gridcolor: "#253147", anchor: "y3" },
                yaxis: {
                  title: { text: "Nominal 0 m (°C)" },
                  domain: [0.70, 1.0],
                  gridcolor: "#253147",
                },
                yaxis2: {
                  title: { text: "D26 (m)" },
                  domain: [0.35, 0.65],
                  gridcolor: "#253147",
                },
                yaxis3: {
                  title: { text: "TCHP (kJ/cm²)" },
                  domain: [0.0, 0.30],
                  gridcolor: "#253147",
                },
                // Peak-intensity marker spans all three panels.
                shapes: event
                  ? [
                      {
                        type: "line",
                        x0: event.peak,
                        x1: event.peak,
                        yref: "paper",
                        y0: 0,
                        y1: 1,
                        line: { color: "#c13d2c", dash: "dash" },
                      },
                    ]
                  : [],
                annotations: event
                  ? [
                      {
                        x: event.peak,
                        yref: "paper",
                        y: 1.045,
                        text: `peak ${event.peak}`,
                        showarrow: false,
                        font: { color: "#c98277", size: 10 },
                      },
                    ]
                  : [],
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: "100%" }}
              useResizeHandler
            />
          </Suspense>
        )}
        <p className="muted small">
          Averaged over cells within 1.5° of the observed track. Each date is a
          separate reconstruction differenced afterwards — never a modelled
          evolution, and never a forecast. A single warm anomaly is not called a
          marine heatwave: no duration/percentile definition is implemented.
        </p>
      </section>
    </>
  );
}
