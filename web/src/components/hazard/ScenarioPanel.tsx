import { useState } from "react";
import { AlongTrackSection } from "./AlongTrackSection";
import { TrackThermalPanel } from "./TrackThermal";
import { postJson, type ScenarioResult } from "./api";

export interface PathPoint {
  lat: number;
  lon: number;
}

/** SCENARIO ANALYSIS — NOT A FORECAST. A user path sampled on an existing field. */
export function ScenarioPanel({
  points,
  onAdd,
  onUndo,
  onClear,
  drawing,
  onDrawing,
  field,
  onField,
  historicalDate,
  latestDate,
  onSelectPoint,
}: {
  points: PathPoint[];
  onAdd: (p: PathPoint) => void;
  onUndo: () => void;
  onClear: () => void;
  drawing: boolean;
  onDrawing: (on: boolean) => void;
  field: "historical" | "latest";
  onField: (f: "historical" | "latest") => void;
  historicalDate: string;
  latestDate: string | null;
  onSelectPoint: (lat: number, lon: number) => void;
}) {
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");

  const run = (mode: "temperature" | "anomaly" = "temperature") => {
    setBusy(true);
    setError("");
    postJson<ScenarioResult>("/api/scenario/analysis", {
      field,
      date: field === "historical" ? historicalDate : undefined,
      points,
      mode,
    })
      .then(setResult)
      .catch((e) => setError((e as Error).message))
      .finally(() => setBusy(false));
  };

  return (
    <section className="panel scenario" data-testid="scenario-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">SCENARIO ANALYSIS — NOT A FORECAST</span>
          <h2>Thermal conditions along a user-drawn path</h2>
        </div>
        <span className="scenario-badge" data-testid="scenario-badge">
          USER-DRAWN SCENARIO · NOT AN OFFICIAL FORECAST
        </span>
      </div>
      <div className="scenario-tools">
        <div className="segmented" role="group" aria-label="Scenario field">
          <button type="button" className={field === "historical" ? "active" : ""} aria-pressed={field === "historical"} data-testid="scenario-field-historical" onClick={() => onField("historical")}>
            Historical field · {historicalDate}
          </button>
          <button type="button" className={field === "latest" ? "active" : ""} aria-pressed={field === "latest"} data-testid="scenario-field-latest" onClick={() => onField("latest")} disabled={!latestDate}>
            Latest qualified field{latestDate ? ` · ${latestDate}` : " · unavailable"}
          </button>
        </div>
        <button type="button" className={`btn${drawing ? " active" : ""}`} data-testid="scenario-draw" aria-pressed={drawing} onClick={() => onDrawing(!drawing)}>
          {drawing ? "Stop drawing" : "Draw on map"}
        </button>
        <button type="button" className="btn" onClick={onUndo} disabled={!points.length}>Undo</button>
        <button type="button" className="btn" onClick={() => { onClear(); setResult(null); }} disabled={!points.length}>Clear</button>
      </div>
      <form
        className="scenario-add"
        onSubmit={(e) => {
          e.preventDefault();
          const p = { lat: Number(lat), lon: Number(lon) };
          if (Number.isFinite(p.lat) && Number.isFinite(p.lon)) {
            onAdd(p);
            setLat("");
            setLon("");
          }
        }}
      >
        <label>Latitude °N<input aria-label="Scenario latitude" type="number" step="any" value={lat} onChange={(e) => setLat(e.target.value)} required /></label>
        <label>Longitude °E<input aria-label="Scenario longitude" type="number" step="any" value={lon} onChange={(e) => setLon(e.target.value)} required /></label>
        <button type="submit" className="btn">Add point</button>
        <span className="small muted" data-testid="scenario-points">
          {points.length} point{points.length === 1 ? "" : "s"}
          {points.length ? `: ${points.map((p) => `${p.lat.toFixed(2)}, ${p.lon.toFixed(2)}`).join(" → ")}` : ""}
        </span>
        <button type="button" className="play-button" data-testid="scenario-run" onClick={() => run()} disabled={points.length < 2 || busy}>
          {busy ? "Sampling…" : "Analyse path"}
        </button>
      </form>
      {error && <p className="notice">{error}</p>}
      {result && (
        <>
          <TrackThermalPanel
            analysis={result.analysis}
            pathKind="user-drawn path"
            labels={{ path: result.labels.path, thermal: `${result.labels.thermal_state} (${result.thermal_field.source})` }}
            onSelectPoint={onSelectPoint}
            testid="scenario-track"
          />
          <AlongTrackSection
            section={result.section}
            loading={busy}
            onMode={run}
            labels={{ path: result.labels.path, thermal: result.labels.thermal_state }}
            testid="scenario-section"
          />
        </>
      )}
      <p className="small muted">
        The path is hypothetical geometry. It is not an observed or forecast cyclone track, it is
        never named as a cyclone, and it does not enter any reconstruction.
      </p>
    </section>
  );
}
