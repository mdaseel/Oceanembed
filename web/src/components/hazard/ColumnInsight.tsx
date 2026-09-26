import { useMemo, useState } from "react";
import type { Bathymetry } from "../../field/bathymetry";
import { diagnosticAt, type FieldView, type Selection } from "../../field/contract";
import {
  HEAT_PENETRATION_RULE,
  allLevels,
  basinOf,
  coordText,
  extremeAt,
  heatPenetration,
  keyLevels,
  levelAt,
  signed,
  type Basins,
} from "../../field/hazardIntelligence";
import { InfoTip } from "./InfoTip";

/** VERTICAL STRUCTURE, HEAT PENETRATION and SUBSURFACE THERMAL EXTREME MONITOR. */
export function ColumnInsight({
  field: f,
  selection,
  depth,
  onDepth,
  bathymetry,
  basins,
  onSelect,
}: {
  field: FieldView;
  selection: Selection;
  depth: number;
  onDepth: (k: number) => void;
  bathymetry: Bathymetry | null;
  basins: Basins | null;
  onSelect: (lat: number, lon: number) => void;
}) {
  const [layer, setLayer] = useState<"anomaly" | "temperature">("anomaly");
  const levels = keyLevels(f, selection, bathymetry);
  const byDepth = (d: number) => levels.find((l) => l.depth === d);
  const surface = byDepth(0),
    l100 = byDepth(100);
  const d26 = diagnosticAt(f, "d26", selection);
  const d26Withheld = !!f.diagnostics?.withheld?.includes("d26");
  const usable = levels.filter((l) => l.supported && Number.isFinite(l.anomaly));
  const warmer = usable.filter((l) => l.anomaly > 0).length;
  const penetration = heatPenetration(selection.row >= 0 ? allLevels(f, selection, bathymetry) : []);

  const statements: string[] = [];
  if (
    surface?.supported &&
    l100?.supported &&
    Number.isFinite(surface.temperature) &&
    Number.isFinite(l100.temperature)
  ) {
    const drop = surface.temperature - l100.temperature;
    statements.push(
      `Temperature ${drop >= 0 ? "falls" : "rises"} by ${Math.abs(drop).toFixed(2)} °C between nominal 0 m and 100 m.`,
    );
  }
  if (d26Withheld) statements.push("D26 is withheld in the latest mode, so no 26 °C depth is stated.");
  else if (d26 && Number.isFinite(d26.value) && d26.physical === "SUPPORTED")
    statements.push(`Water warmer than 26 °C extends to ${d26.value.toFixed(1)} m (D26).`);
  else if (d26?.status === "SURFACE_BELOW_26")
    statements.push("The column is cooler than 26 °C at every reconstructed depth.");
  if (usable.length)
    statements.push(`Warmer than climatology at ${warmer} of the ${usable.length} key depths shown.`);

  const here = levelAt(f, selection, depth, bathymetry);
  const depthM = f.depths[depth];
  const warmest = useMemo(() => extremeAt(f, depth, bathymetry, layer, true), [f, depth, bathymetry, layer]);
  const coolest = useMemo(() => extremeAt(f, depth, bathymetry, layer, false), [f, depth, bathymetry, layer]);
  const place = (p: { lat: number; lon: number }) => {
    const basin = basinOf(p.lat, p.lon, basins);
    return `${basin ? `${basin}, ` : ""}${coordText(p.lat, p.lon)}`;
  };
  const show = (v: number) => (layer === "anomaly" ? signed(v, 2, "°C") : `${v.toFixed(2)} °C`);

  return (
    <div className="column-insight">
      <section className="panel" data-testid="vertical-structure">
        <span className="eyebrow">VERTICAL STRUCTURE · SELECTED WATER COLUMN</span>
        <h2>How deep the warmth goes</h2>
        {selection.row < 0 ? (
          <p className="empty">Select a location inside the domain.</p>
        ) : (
          <>
            <table className="level-table">
              <thead>
                <tr>
                  <th>Depth</th>
                  <th>Temperature</th>
                  <th>
                    Anomaly <InfoTip term="anomaly" />
                  </th>
                </tr>
              </thead>
              <tbody>
                {levels.map((l) => (
                  <tr key={l.depth} data-depth={l.depth}>
                    <td>{l.depth === 0 ? "0 m · nominal" : `${l.depth} m`}</td>
                    <td>
                      {!l.supported
                        ? bathymetry
                          ? "Below local seafloor"
                          : "Depth support unverified"
                        : Number.isFinite(l.temperature)
                          ? `${l.temperature.toFixed(2)} °C`
                          : "Unavailable"}
                    </td>
                    <td>{l.supported && Number.isFinite(l.anomaly) ? signed(l.anomaly, 2, "°C") : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="structure-notes" data-testid="structure-notes">
              {statements.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
            <h3 className="sub">HEAT PENETRATION</h3>
            <ul className="structure-notes" data-testid="heat-penetration">
              {penetration.statements.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
            <p className="small muted">{HEAT_PENETRATION_RULE}</p>
          </>
        )}
      </section>

      <section className="panel" data-testid="subsurface-extreme" data-layer={layer}>
        <div className="panel-heading">
          <div>
            <span className="eyebrow">SUBSURFACE THERMAL EXTREME MONITOR</span>
            <h2>{depthM} m below the surface</h2>
          </div>
          <div className="section-tools">
            <div className="segmented" role="group" aria-label="Extreme quantity">
              <button type="button" className={layer === "anomaly" ? "active" : ""} aria-pressed={layer === "anomaly"} onClick={() => setLayer("anomaly")}>
                Anomaly
              </button>
              <button type="button" className={layer === "temperature" ? "active" : ""} aria-pressed={layer === "temperature"} data-testid="extreme-layer-temperature" onClick={() => setLayer("temperature")}>
                Temperature
              </button>
            </div>
            <label className="inline-select">
              DEPTH
              <select aria-label="Subsurface extreme depth" value={depth} onChange={(e) => onDepth(Number(e.target.value))}>
                {f.depths.map((d, k) => (
                  <option key={d} value={k}>
                    {d} m
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <dl className="metric-list">
          <div>
            <dt>Reconstructed</dt>
            <dd data-testid="extreme-temperature">
              {here?.supported && Number.isFinite(here.temperature) ? `${here.temperature.toFixed(2)} °C` : "Unavailable"}
            </dd>
          </div>
          <div>
            <dt>
              Climatology <InfoTip term="climatology" />
            </dt>
            <dd>{here?.supported && Number.isFinite(here.climatology) ? `${here.climatology.toFixed(2)} °C` : "Unavailable"}</dd>
          </div>
          <div>
            <dt>
              Anomaly <InfoTip term="anomaly" />
            </dt>
            <dd data-testid="extreme-anomaly">
              {here?.supported && Number.isFinite(here.anomaly) ? signed(here.anomaly, 2, "°C") : "Unavailable"}
            </dd>
          </div>
        </dl>
        <p data-testid="extreme-sentence">
          {!here || selection.row < 0
            ? "Select a location inside the domain."
            : !here.supported
              ? bathymetry
                ? `The local water column does not reach ${depthM} m here.`
                : "Physical depth support is still being verified."
              : Number.isFinite(here.anomaly)
                ? `${depthM} m is ${Math.abs(here.anomaly).toFixed(2)} °C ${here.anomaly >= 0 ? "warmer" : "cooler"} than climatological expectation at the selected location.`
                : "No climatology is defined here, so no anomaly is stated."}
        </p>
        <div className="extremes" data-testid="extreme-strongest">
          {bathymetry && warmest && coolest ? (
            <>
              <p className="small">
                {layer === "anomaly" ? "Strongest positive anomaly" : "Warmest"} at {depthM} m:{" "}
                <strong>{show(warmest.value)}</strong> at {place(warmest)}{" "}
                <button type="button" className="link-button" onClick={() => onSelect(warmest.lat, warmest.lon)}>
                  Inspect
                </button>
              </p>
              <p className="small" data-testid="extreme-coolest">
                {layer === "anomaly" ? "Strongest negative anomaly" : "Coolest"} at {depthM} m:{" "}
                <strong>{show(coolest.value)}</strong> at {place(coolest)}{" "}
                <button type="button" className="link-button" onClick={() => onSelect(coolest.lat, coolest.lon)}>
                  Inspect
                </button>
              </p>
              {layer === "anomaly" && (
                <p className="small muted">
                  {warmest.value > 0 ? "Unusually warm" : "Nowhere warmer than climatology"} /{" "}
                  {coolest.value < 0 ? "unusually cool" : "nowhere cooler than climatology"} relative to the
                  L0 climatology at this depth.
                </p>
              )}
            </>
          ) : (
            <p className="small muted">Domain extremes withheld until physical depth support is verified.</p>
          )}
        </div>
        <h3 className="sub">WHY THIS MATTERS</h3>
        <p className="small">
          Positive anomalies at depth indicate that unusual heat extends beneath the satellite-observed
          surface, which surface temperature alone would not reveal.
        </p>
        <p className="small muted">
          A single warm day is not called a marine heatwave: no duration or percentile definition is
          implemented.
        </p>
      </section>
    </div>
  );
}
