import { useEffect, useState } from "react";
import { signed } from "../../field/hazardIntelligence";
import { getJson, type CompareEntry, type ComparePayload, type EventMetrics } from "./api";

type Row = { label: string; get: (e: CompareEntry) => string; definition?: keyof EventMetrics["definitions"] | string };
const f1 = (v: number | null | undefined, unit = "") =>
  v == null ? "—" : `${v.toFixed(1)}${unit ? ` ${unit}` : ""}`;

const ROWS: Row[] = [
  { label: "Pre-event TCHP", get: (e) => f1(e.metrics.pre_event_tchp, "kJ/cm²"), definition: "pre_event_tchp" },
  { label: "Event TCHP", get: (e) => f1(e.metrics.event_tchp, "kJ/cm²"), definition: "event_tchp" },
  {
    label: "Wake minimum TCHP",
    get: (e) =>
      e.metrics.wake_min_tchp ? `${f1(e.metrics.wake_min_tchp.value, "kJ/cm²")} (${e.metrics.wake_min_tchp.date})` : "—",
    definition: "wake_min_tchp",
  },
  { label: "TCHP change", get: (e) => signed(e.metrics.tchp_change, 1, "kJ/cm²"), definition: "tchp_change" },
  {
    label: "TCHP change (%)",
    get: (e) => (e.metrics.tchp_change_pct == null ? "—" : `${signed(e.metrics.tchp_change_pct, 0)} %`),
  },
  ...(["50", "75", "100"] as const).map((d) => ({
    label: `${d} m temperature change`,
    get: (e: CompareEntry) => signed(e.metrics.temperature_change_c[d], 2, "°C"),
    definition: "temperature_change_c",
  })),
  { label: "D26 change", get: (e) => signed(e.metrics.d26_change_m, 1, "m"), definition: "d26_change_m" },
  {
    label: "Max pre-event 100 m anomaly",
    get: (e) => signed(e.metrics.max_pre_event_anomaly_100m_c, 2, "°C"),
    definition: "max_pre_event_anomaly_100m_c",
  },
  {
    label: "Strongest 0 m cooling (map)",
    get: (e) => signed(e.pre_to_wake_footprint.temperature["0"]?.min?.value, 2, "°C"),
  },
  {
    label: "Strongest 100 m cooling (map)",
    get: (e) => signed(e.pre_to_wake_footprint.temperature["100"]?.min?.value, 2, "°C"),
  },
  {
    label: "End of window vs pre-event TCHP",
    get: (e) => signed(e.metrics.final_vs_pre_tchp, 1, "kJ/cm²"),
    definition: "final_vs_pre_tchp",
  },
];

/** COMPARE CYCLONES — reconstructed ocean response side by side, never ranked. */
export function CompareCyclones({ ids }: { ids: string[] }) {
  const [data, setData] = useState<ComparePayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = ids.join(",");
  useEffect(() => {
    if (ids.length < 2) {
      setData(null);
      return;
    }
    let live = true;
    setBusy(true);
    setError("");
    getJson<ComparePayload>(`/api/events/compare?ids=${encodeURIComponent(key)}`)
      .then((d) => live && setData(d))
      .catch((e) => live && setError((e as Error).message))
      .finally(() => live && setBusy(false));
    return () => {
      live = false;
    };
    // the key captures the id list
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (ids.length < 2)
    return (
      <p className="notice" data-testid="compare-empty">
        Tick “Compare” on two to four events in the library to compare their reconstructed ocean
        response.
      </p>
    );
  return (
    <div className="compare" data-testid="compare-cyclones" data-ids={key}>
      <span className="eyebrow">COMPARE CYCLONES · RECONSTRUCTED OCEAN RESPONSE</span>
      {busy && <p className="muted" role="status">Replaying each window (first time only)…</p>}
      {error && <p className="notice">{error}</p>}
      {data && (
        <>
          <div className="table-scroll">
            <table className="compare-table">
              <thead>
                <tr>
                  <th>Corridor quantity</th>
                  {data.events.map((e) => (
                    <th key={e.event_id} data-event={e.event_id}>
                      {e.name}
                      <small>
                        {e.basin} · {e.split === "train" ? "in-sample" : e.split}
                      </small>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.map((r) => (
                  <tr key={r.label}>
                    <td title={r.definition ? data.events[0]?.metrics.definitions[r.definition] : undefined}>
                      {r.label}
                    </td>
                    {data.events.map((e) => (
                      <td key={e.event_id} data-testid={`compare-${r.label.replace(/\W+/g, "-").toLowerCase()}-${e.event_id}`}>
                        {r.get(e)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <span className="eyebrow">EXTERNAL INTENSITY RECORD · SHOWN SEPARATELY</span>
          <div className="table-scroll">
            <table className="compare-table external">
              <tbody>
                <tr>
                  <td>IMD peak wind (3-min)</td>
                  {data.events.map((e) => (
                    <td key={e.event_id}>{f1(e.external_metadata.peak_imd_wind_kt, "kt")}</td>
                  ))}
                </tr>
                <tr>
                  <td>IMD minimum pressure</td>
                  {data.events.map((e) => (
                    <td key={e.event_id}>{f1(e.external_metadata.min_imd_pressure_hpa, "hPa")}</td>
                  ))}
                </tr>
                <tr>
                  <td>Track source</td>
                  {data.events.map((e) => (
                    <td key={e.event_id}>{e.track_source}</td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
          <p className="small muted" data-testid="compare-note">
            {data.note} Corridor: cells within {data.corridor_deg}° of each observed track.
          </p>
        </>
      )}
    </div>
  );
}
