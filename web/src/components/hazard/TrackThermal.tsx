import { lazy, Suspense, useState } from "react";
import { coordText, signed } from "../../field/hazardIntelligence";
import type { TrackAnalysis, TrackSample } from "./api";
import { InfoTip } from "./InfoTip";

const Plot = lazy(() => import("../Plot"));

const CATEGORY_COLOR: Record<string, string> = {
  LOW: "rgb(38,84,124)",
  MODERATE: "rgb(64,145,140)",
  ELEVATED: "rgb(222,158,54)",
  HIGH: "rgb(193,61,44)",
};
type Metric = "tchp" | "50" | "75" | "100";
const METRICS: { id: Metric; label: string; unit: string }[] = [
  { id: "tchp", label: "TCHP", unit: "kJ/cm²" },
  { id: "50", label: "50 m anomaly", unit: "°C" },
  { id: "75", label: "75 m anomaly", unit: "°C" },
  { id: "100", label: "100 m anomaly", unit: "°C" },
];
const value = (s: TrackSample, m: Metric) => (m === "tchp" ? s.tchp : s.levels[m]?.anomaly ?? null);
const km = (v: number) => `~${Math.round(v).toLocaleString("en-US")} km`;

/**
 * TRACK x OCEAN THERMAL STATE, THERMAL INTERSECTION and THERMAL CONDITIONS
 * ALONG PATH. The path is external (or user-drawn); every number is sampled
 * from an existing OceanEmbed field by the backend.
 */
export function TrackThermalPanel({
  analysis,
  pathKind,
  labels,
  onSelectPoint,
  testid,
}: {
  analysis: TrackAnalysis;
  pathKind: "observed best track" | "external forecast track" | "user-drawn path";
  labels: { path: string; thermal: string };
  onSelectPoint: (lat: number, lon: number) => void;
  testid: string;
}) {
  const [metric, setMetric] = useState<Metric>("tchp");
  const s = analysis.summary;
  const seg = s.strongest_segment;
  const high = s.intersects.HIGH;
  const elevated = s.intersects.ELEVATED;
  const top = high ? "HIGH" : elevated ? "ELEVATED" : null;
  const topKm = top ? s.category_distance_km[top] : 0;
  const peak = s.tchp.max;
  const a100 = s.anomaly["100"]?.max;
  const unit = METRICS.find((m) => m.id === metric)!.unit;
  const inDomain = analysis.samples.filter((x) => x.in_domain);

  return (
    <div className="track-thermal" data-testid={testid} data-date={analysis.date}>
      <div className="provenance-pair" data-testid={`${testid}-labels`}>
        <span>{labels.path}</span>
        <span>{labels.thermal} · valid {analysis.date}</span>
      </div>

      <div
        className={`thermal-alert ${top ? `alert-${top.toLowerCase()}` : "alert-none"}`}
        data-testid={`${testid}-intersection`}
        data-intersects={top ?? "NONE"}
      >
        <span className="eyebrow">THERMAL INTERSECTION</span>
        {top ? (
          <>
            <strong>
              The {pathKind} intersects {top} OceanEmbed thermal-support water.
            </strong>
            <dl className="metric-list">
              <div>
                <dt>
                  Peak TCHP <InfoTip term="tchp" />
                </dt>
                <dd>{peak ? `${peak.value.toFixed(1)} kJ/cm²` : "Unavailable"}</dd>
              </div>
              <div>
                <dt>100 m anomaly at peak TCHP</dt>
                <dd data-testid={`${testid}-peak-anomaly`}>
                  {seg?.peak_anomaly_100m != null
                    ? signed(seg.peak_anomaly_100m, 2, "°C")
                    : a100
                      ? `${signed(a100.value, 2, "°C")} (largest along path)`
                      : "Unavailable"}
                </dd>
              </div>
              <div>
                <dt>{top}-support length</dt>
                <dd>{km(topKm)}</dd>
              </div>
            </dl>
            <p className="small">
              <strong>Why this matters:</strong> the {pathKind} crosses a substantial
              upper-ocean warm-water reservoir as reconstructed by OceanEmbed.{" "}
              <strong>Attention:</strong> compare with official cyclone intensity and
              atmospheric guidance. OceanEmbed does not predict cyclone intensity.
            </p>
          </>
        ) : (
          <strong>
            No HIGH or ELEVATED thermal-support water was intersected along the sampled{" "}
            {pathKind}.
          </strong>
        )}
      </div>

      <dl className="metric-list track-metrics" data-testid={`${testid}-summary`}>
        <div>
          <dt>Peak TCHP</dt>
          <dd>{peak ? `${peak.value.toFixed(1)} kJ/cm²` : "—"}</dd>
        </div>
        <div>
          <dt>Median TCHP</dt>
          <dd>{s.tchp.median === null ? "—" : `${s.tchp.median.toFixed(1)} kJ/cm²`}</dd>
        </div>
        <div>
          <dt>Highest support</dt>
          <dd>{s.highest_category ?? "—"}</dd>
        </div>
        <div>
          <dt>D26 median</dt>
          <dd className={s.d26.withheld ? "withheld" : ""}>
            {s.d26.withheld
              ? "WITHHELD"
              : s.d26.median == null
                ? "—"
                : `${s.d26.median.toFixed(1)} m`}
          </dd>
        </div>
        {(["50", "75", "100"] as const).map((d) => (
          <div key={d}>
            <dt>Max {d} m anomaly</dt>
            <dd>{s.anomaly[d]?.max ? signed(s.anomaly[d].max!.value, 2, "°C") : "—"}</dd>
          </div>
        ))}
        <div>
          <dt>HIGH / ELEVATED</dt>
          <dd>
            {km(s.category_distance_km.HIGH ?? 0)} / {km(s.category_distance_km.ELEVATED ?? 0)}
          </dd>
        </div>
      </dl>

      {seg && (
        <div className="strongest-segment" data-testid={`${testid}-strongest`}>
          <span className="eyebrow">STRONGEST THERMAL SEGMENT ALONG PATH</span>
          <p>
            <strong>
              {seg.lat_range[0].toFixed(2)}–{seg.lat_range[1].toFixed(2)}°N /{" "}
              {seg.lon_range[0].toFixed(2)}–{seg.lon_range[1].toFixed(2)}°E
            </strong>{" "}
            · {seg.category} · {Math.round(seg.start_km)}–{Math.round(seg.end_km)} km along the
            path
          </p>
          <p className="small">
            Peak TCHP {seg.peak_tchp === null ? "—" : `${seg.peak_tchp.toFixed(1)} kJ/cm²`} at{" "}
            {coordText(seg.peak_lat, seg.peak_lon)} · 100 m anomaly{" "}
            {seg.peak_anomaly_100m === null ? "—" : signed(seg.peak_anomaly_100m, 2, "°C")}{" "}
            <button
              type="button"
              className="link-button"
              onClick={() => onSelectPoint(seg.peak_lat, seg.peak_lon)}
            >
              Inspect this column
            </button>
          </p>
        </div>
      )}

      <div className="panel-heading compact">
        <span className="eyebrow">THERMAL CONDITIONS ALONG PATH</span>
        <div className="segmented" role="group" aria-label="Path metric">
          {METRICS.map((m) => (
            <button
              key={m.id}
              type="button"
              className={metric === m.id ? "active" : ""}
              aria-pressed={metric === m.id}
              data-testid={`${testid}-metric-${m.id}`}
              onClick={() => setMetric(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
      {inDomain.length === 0 ? (
        <p className="empty">The path does not cross the reconstruction domain.</p>
      ) : (
        <Suspense fallback={<p className="empty">Loading profile…</p>}>
          <Plot
            data={[
              {
                x: analysis.samples.map((x) => x.distance_km),
                y: analysis.samples.map((x) => value(x, metric)),
                type: "scatter",
                mode: "lines+markers",
                connectgaps: false,
                line: { color: "#8fb3cc", width: 1.5 },
                marker: {
                  size: 6,
                  color: analysis.samples.map((x) => CATEGORY_COLOR[x.category ?? ""] ?? "#48525f"),
                },
                hovertemplate: `%{x:.0f} km · %{y:.2f} ${unit}<extra></extra>`,
              },
            ]}
            layout={{
              autosize: true,
              height: 240,
              paper_bgcolor: "transparent",
              plot_bgcolor: "transparent",
              font: { color: "#aebfd5", family: "system-ui", size: 11 },
              margin: { l: 56, r: 16, t: 10, b: 40 },
              xaxis: { title: { text: "Distance along path (km)" }, gridcolor: "#253147" },
              yaxis: { title: { text: unit }, gridcolor: "#253147", zeroline: metric !== "tchp" },
              showlegend: false,
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: "100%" }}
            useResizeHandler
            onClick={(event) => {
              const i = event.points?.[0]?.pointIndex;
              const sample = typeof i === "number" ? analysis.samples[i] : undefined;
              if (sample?.grid_lat != null && sample.grid_lon != null)
                onSelectPoint(sample.grid_lat, sample.grid_lon);
            }}
          />
        </Suspense>
      )}
      <p className="small muted">
        Marker colours are the backend thermal-support categories. Click a point to move the
        map, 3D probe and profile to that grid cell.
      </p>
      <details className="rules">
        <summary>Sampling and distance rules</summary>
        <p className="small">{analysis.rules.sampling}</p>
        <p className="small">{analysis.rules.distance}</p>
        <p className="small">{analysis.rules.strongest_segment}</p>
      </details>
    </div>
  );
}
