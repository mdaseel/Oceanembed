import { useCallback, useEffect, useRef, useState } from "react";
import { getJson } from "../field/api";

/**
 * Phase 8A — Latest Inputs. TELEMETRY ONLY.
 *
 * This tab describes two *inputs*. It never renders a temperature field, never
 * runs the frozen L2, and never derives D26, TCHP or a hazard level. Cached
 * telemetry is always labelled as such and never shown as fresh.
 *
 * Historical Replay is a local capability and is unaffected by anything that
 * happens here, including a total network failure.
 */

interface Source {
  channel: string;
  product_key: string;
  product_id: string;
  dataset_id: string;
  doi: string | null;
  provider: string;
  source_tier: string;
  state: string;
  product_valid_time: string | null;
  local_retrieval_time: string | null;
  product_generated_time: string | null;
  data_age_hours: number | null;
  nio_coverage_fraction: number | null;
  nio_cells_valid: number | null;
  nio_cells_total: number | null;
  variables: string[];
  error: string | null;
  notes: string | null;
}
interface Telemetry {
  state: string;
  generated_utc?: string;
  sources: Source[];
  subsurface_reconstruction: string;
  telemetry_banner?: string;
  why_these_inputs: string;
  scope_note?: string;
  historical_note?: string;
  is_cached: boolean;
  has_snapshot?: boolean;
  cached_generated_utc?: string;
  cached_staleness_hours?: number;
  cache_label?: string;
  unavailable_label?: string;
  live_attempt_sources?: Source[];
  elapsed_seconds?: number;
}

// Jury-facing text describes connectivity and retrieval only. Phase 8A measures
// data age; it does not qualify whether that age is acceptable for inference,
// so nothing here may read as "current" or "fresh" in that sense. The internal
// state names are unchanged.
const STATE_TEXT: Record<string, string> = {
  ONLINE_CURRENT: "All requested sources reachable",
  ONLINE_PARTIAL: "PARTIAL SOURCE AVAILABILITY",
  OFFLINE_OR_SOURCE_UNAVAILABLE: "Offline or source unavailable",
  CACHED_TELEMETRY_NOT_CURRENT: "Showing last successful telemetry — NOT CURRENT",
};
const stateText = (t: Telemetry) =>
  t.state === "ONLINE_CURRENT" &&
  t.sources.length > 0 &&
  t.sources.every((s) => s.state === "OK")
    ? "Both requested sources retrieved"
    : (STATE_TEXT[t.state] ?? t.state);
const RETRIEVAL_TEXT: Record<string, string> = {
  ONLINE_CURRENT: "Successful",
  ONLINE_PARTIAL: "Partial",
  OFFLINE_OR_SOURCE_UNAVAILABLE: "Failed",
};
const SOURCE_TEXT: Record<string, string> = {
  OK: "Retrieved",
  CATALOGUE_ONLY: "Catalogue answered; region not requested",
  COVERAGE_UNAVAILABLE: "Catalogue answered; region not retrieved",
  AUTH_FAILED: "Provider rejected or missing credentials",
  UNREACHABLE: "No answer from provider",
};

const age = (h: number | null) =>
  h == null ? "—" : h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} d`;

export default function LatestInputs() {
  const [data, setData] = useState<Telemetry | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [why, setWhy] = useState(false);
  const live = useRef(true);

  const refresh = useCallback(() => {
    setBusy(true);
    setError("");
    // A failure here must never leave the tab blank: the previous state stays
    // on screen and the error is shown beside it.
    getJson<Telemetry>("/api/latest")
      .then((t) => live.current && setData(t))
      .catch((e) => live.current && setError(String(e)))
      .finally(() => live.current && setBusy(false));
  }, []);

  useEffect(() => {
    live.current = true;
    // Render the cache instantly, then attempt a real fetch, as 8A.4 requires.
    getJson<Telemetry>("/api/latest/cached")
      .then((t) => live.current && setData((d) => d ?? t))
      .catch(() => {})
      .finally(() => live.current && refresh());
    return () => {
      live.current = false;
    };
  }, [refresh]);

  const sources = data?.sources ?? [];
  const attempted = data?.live_attempt_sources ?? [];

  return (
    <>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">LATEST INPUTS · OPERATIONAL STATUS</span>
            <h2>Near-real-time input telemetry</h2>
          </div>
          <button className="btn" onClick={refresh} disabled={busy}>
            {busy ? "Contacting providers…" : "Retry / Refresh"}
          </button>
        </div>

        <p className="notice" data-testid="not-certified">
          <strong>{data?.subsurface_reconstruction ?? "SUBSURFACE NRT RECONSTRUCTION NOT YET CERTIFIED"}</strong>
          <br />
          <strong data-testid="not-produced">LATEST SUBSURFACE FIELD: NOT PRODUCED</strong>
        </p>

        <div className="stats-grid">
          <div className="stat" data-testid="telemetry-state">
            <span>CONNECTIVITY STATE</span>
            <strong>{data ? stateText(data) : "Checking…"}</strong>
            <span className="small muted">{data?.state ?? ""}</span>
          </div>
          <div className="stat" data-testid="live-retrieval">
            <span>LIVE RETRIEVAL</span>
            <strong>
              {data?.is_cached
                ? "No — cached"
                : data
                  ? (RETRIEVAL_TEXT[data.state] ?? data.state)
                  : "—"}
            </strong>
            {data?.is_cached && data.cached_staleness_hours != null ? (
              <span className="small muted">
                cached {age(data.cached_staleness_hours)} ago
              </span>
            ) : (
              sources.some((s) => s.data_age_hours != null) && (
                <span className="small muted">
                  data age{" "}
                  {sources
                    .filter((s) => s.data_age_hours != null)
                    .map((s) => `${s.channel.toUpperCase()} ${age(s.data_age_hours)}`)
                    .join(" · ")}
                  {" "}— measured, not qualified for inference
                </span>
              )
            )}
          </div>
          <div className="stat">
            <span>LATEST SUBSURFACE FIELD</span>
            <strong>NOT PRODUCED</strong>
            <span className="small muted">telemetry only in Phase 8A</span>
          </div>
        </div>

        {data?.is_cached && data.cache_label && (
          <p className="notice" data-testid="cache-label">
            <strong>{data.cache_label}</strong> — retrieved{" "}
            {data.cached_generated_utc ?? "unknown"} UTC. This is not a fresh
            reading and is not presented as one.
          </p>
        )}
        {data?.unavailable_label && (
          <p className="notice" data-testid="unavailable-label">
            <strong>{data.unavailable_label}</strong> — no successful telemetry
            has been stored yet, so there is nothing to show. Nothing is invented
            in its place.
          </p>
        )}
        {error && (
          <p className="panel error-state" data-testid="telemetry-error">
            Live attempt failed: {error}. The previous state is still shown
            above, and Historical Replay is unaffected.
          </p>
        )}

        <p className="muted small" data-testid="historical-unaffected">
          {data?.historical_note ??
            "Historical Replay and historical Ocean Hazard Indicators are local capabilities and remain fully available regardless of this state."}
        </p>
      </section>

      <section className="panel" data-testid="source-table">
        <span className="eyebrow">SOURCE BY SOURCE</span>
        <h2>Two inputs, reported separately</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Channel</th>
                <th>Product</th>
                <th>Status</th>
                <th>Product valid time</th>
                <th>Retrieved at</th>
                <th>Data age</th>
                <th>NIO coverage</th>
                <th>Tier</th>
              </tr>
            </thead>
            <tbody>
              {sources.length === 0 && (
                <tr>
                  <td colSpan={8} className="muted">
                    No telemetry yet.
                  </td>
                </tr>
              )}
              {sources.map((s) => (
                <tr key={s.product_key} data-channel={s.channel} data-state={s.state}>
                  <td>{s.channel.toUpperCase()}</td>
                  <td title={s.dataset_id}>
                    {s.product_id}
                    {s.doi && (
                      <>
                        <br />
                        <span className="small muted">doi:{s.doi}</span>
                      </>
                    )}
                  </td>
                  <td>{SOURCE_TEXT[s.state] ?? s.state}</td>
                  <td>{s.product_valid_time ?? "—"}</td>
                  <td>{s.local_retrieval_time ?? "—"}</td>
                  <td>{age(s.data_age_hours)}</td>
                  <td>
                    {s.nio_coverage_fraction == null
                      ? "unknown"
                      : `${(s.nio_coverage_fraction * 100).toFixed(1)}% (${s.nio_cells_valid?.toLocaleString()}/${s.nio_cells_total?.toLocaleString()})`}
                  </td>
                  <td>{s.source_tier}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {sources.some((s) => s.error) && (
          <ul className="muted small">
            {sources
              .filter((s) => s.error)
              .map((s) => (
                <li key={s.product_key}>
                  {s.channel.toUpperCase()}: {s.error}
                </li>
              ))}
          </ul>
        )}
        {attempted.length > 0 && (
          <p className="muted small" data-testid="live-attempt">
            Live attempt during this refresh:{" "}
            {attempted
              .map((s) => `${s.channel.toUpperCase()} ${s.state}`)
              .join(" · ")}
            . The table above is the cached reading, not this attempt.
          </p>
        )}
        <p className="muted small" data-testid="coverage-note">
          NIO coverage is the fraction of finite cells in the retrieved
          native-grid North Indian Ocean rectangle (5–30°N, 45–105°E). Much of
          the non-finite area is associated with land, but this is{" "}
          <strong>not</strong> an inference-readiness or ocean-only coverage
          metric.
        </p>
        <p className="muted small">
          Product valid time and local retrieval time are stored and shown
          separately, and a provider-side generation time appears only when the
          provider actually states one. Nothing here is an invented acquisition
          time. Data age is measured and shown; whether that age is acceptable
          for inference has not been qualified.
        </p>
        <p className="muted small" data-testid="credential-note">
          OceanEmbed code does not directly inspect, store, print or log
          credential values; authentication is delegated to the configured
          Copernicus Marine client.
        </p>
      </section>

      <section className="panel">
        <span className="eyebrow">SCOPE</span>
        <h2>Why SST and SLA first?</h2>
        <button className="btn" onClick={() => setWhy((v) => !v)}>
          {why ? "Hide" : "Why these inputs?"}
        </button>
        {why && (
          <p className="muted small" data-testid="why-these-inputs">
            {data?.why_these_inputs}
          </p>
        )}
        <p className="muted small" data-testid="scope-note">
          {data?.scope_note ??
            "Phase 8A is input telemetry only. The frozen L2 is not run on these inputs, no latest subsurface field is produced, and no latest D26, TCHP or hazard indicator is derived from them."}
        </p>
        <p className="muted small">
          Ocean Hazard Indicators remain <strong>historical</strong>. No latest
          or NRT hazard indicator is produced, and none is certified.
        </p>
      </section>
    </>
  );
}
