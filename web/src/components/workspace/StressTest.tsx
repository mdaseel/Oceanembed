import { useEffect, useState } from "react";
import { getJson } from "../../field/api";
import { AlongTrackSection } from "../hazard/AlongTrackSection";
import type { EventLibraryPayload } from "../hazard/api";
import type { StressTestPayload } from "./scienceApi";

const fmt = (v: number | null, unit: string) =>
  v == null ? "—" : `${v.toFixed(unit === "°C" ? 2 : unit === "km" ? 0 : 1)} ${unit}`;
const signedFmt = (v: number | null, unit: string) =>
  v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(unit === "°C" ? 2 : unit === "km" ? 0 : 1)} ${unit}`;

/**
 * HISTORICAL TRACK STRESS TEST. The observed geometry of a past cyclone, unmoved,
 * sampled on the historical and on the latest qualified field.
 */
export function StressTest({ initialEvent = "mocha-2023" }: { initialEvent?: string }) {
  const [library, setLibrary] = useState<EventLibraryPayload | null>(null);
  const [eventId, setEventId] = useState(initialEvent);
  const [data, setData] = useState<StressTestPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [which, setWhich] = useState<"historical" | "latest">("latest");

  useEffect(() => {
    getJson<EventLibraryPayload>("/api/events")
      .then((l) => setLibrary(l?.events ? l : null))
      .catch(() => {});
  }, []);
  useEffect(() => setEventId(initialEvent), [initialEvent]);
  useEffect(() => {
    let live = true;
    setBusy(true);
    setError("");
    getJson<StressTestPayload>(`/api/events/${encodeURIComponent(eventId)}/stress-test`)
      .then((d) => live && setData(d?.label ? d : null))
      .catch((e) => live && setError((e as Error).message))
      .finally(() => live && setBusy(false));
    return () => {
      live = false;
    };
  }, [eventId]);

  const section = which === "latest" && data?.latest ? data.latest.section : data?.historical.section;
  return (
    <div className="ws" data-testid="stress-test" data-event={eventId}>
      <div className="ws-toggle-row">
        <span className="eyebrow">HISTORICAL TRACK STRESS TEST</span>
        <label className="inline-select">
          GEOMETRY
          <select aria-label="Historical geometry" value={eventId} onChange={(e) => setEventId(e.target.value)}>
            {(library?.events ?? []).map((e) => (
              <option key={e.event_id} value={e.event_id}>
                {e.short_name} {e.season}
              </option>
            ))}
          </select>
        </label>
        {busy && <span className="muted small">Sampling both fields…</span>}
      </div>
      <p className="stress-label" data-testid="stress-label">
        {data?.label ?? "REPLAYED HISTORICAL GEOMETRY — NOT A FORECAST OR PREDICTION"}
      </p>
      {error && <p className="notice">{error}</p>}
      {data && (
        <>
          <p className="ws-note">
            {data.note} Question: what thermal environment would this exact {data.event} path encounter in the
            latest qualified ocean state, compared with {data.historical.date}?
          </p>
          {!data.latest && <p className="notice">{data.latest_state}</p>}
          <div className="fig-row">
            <div className="fig-card">
              <h3>
                {data.event} geometry · {data.historical.date} vs {data.latest?.date ?? "latest unavailable"}
              </h3>
              <table className="science-table" data-testid="stress-comparison">
                <thead>
                  <tr>
                    <th>Along the same path</th>
                    <th>Historical event field</th>
                    <th>Latest qualified field</th>
                    <th>Difference</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.comparison ?? []).map((row) => (
                    <tr key={row.metric} data-metric={row.metric}>
                      <td>{row.label}</td>
                      <td>{fmt(row.historical, row.unit)}</td>
                      <td>{fmt(row.latest, row.unit)}</td>
                      <td>{signedFmt(row.difference, row.unit)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="ws-note">
                Difference = latest − historical, along the unmoved observed geometry. Latest D26 is withheld; no
                intensity is inferred and no recurrence is implied.
              </p>
            </div>
            <div className="fig-card">
              <h3>Strongest thermal segment</h3>
              <dl className="ws-kv">
                <dt>Historical</dt>
                <dd>{data.historical.analysis.summary.strongest_segment?.category ?? "—"}</dd>
                <dt>Latest</dt>
                <dd>{data.latest?.analysis.summary.strongest_segment?.category ?? "—"}</dd>
              </dl>
              {data.coastal_approach?.status === "OK" && (
                <p className="ws-note" data-testid="stress-coastal">
                  Closest mapped coastline along this geometry: {data.coastal_approach.coastal_state},{" "}
                  {data.coastal_approach.country}, ~{data.coastal_approach.offshore_distance_km} km offshore.
                  Geographic context only.
                </p>
              )}
            </div>
          </div>
          <div className="ws-toggle-row">
            <div className="segmented" role="group" aria-label="Section field">
              <button type="button" className={which === "historical" ? "active" : ""} aria-pressed={which === "historical"} onClick={() => setWhich("historical")}>
                Historical field · {data.historical.date}
              </button>
              <button type="button" className={which === "latest" ? "active" : ""} aria-pressed={which === "latest"} disabled={!data.latest} onClick={() => setWhich("latest")}>
                Latest qualified field{data.latest ? ` · ${data.latest.date}` : ""}
              </button>
            </div>
          </div>
          {section && (
            <AlongTrackSection
              section={section}
              loading={busy}
              onMode={() => {}}
              labels={{ path: `${data.label} · ${data.geometry.source}`, thermal: `OceanEmbed ${which} field` }}
              testid="stress-section"
            />
          )}
        </>
      )}
    </div>
  );
}
