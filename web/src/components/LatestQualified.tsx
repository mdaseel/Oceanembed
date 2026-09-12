import { useCallback, useEffect, useRef, useState } from "react";
import { getJson } from "../field/api";
import {
  HAZARD_ORDER,
  format,
  hazardAt,
  type FieldView,
  type Selection,
} from "../field/contract";
import {
  adaptReplay,
  type ReplayData,
  type ReplayPayload,
} from "../field/replayAdapter";

/**
 * Phase 8B — latest qualified ocean state: status, provenance and refusals.
 *
 * This component never renders a field itself. It retrieves the authoritative
 * latest field, adapts it with the SAME adapter as Historical Replay, and hands
 * it to the app, which draws it with the SAME map, 3D renderer and profile.
 *
 * Every qualified claim here comes from the backend's frozen decision artifact
 * (`/api/latest/qualification`); none is written into this file.
 */

export interface Qualification {
  qualified: boolean;
  temperature_category: string;
  tab_name: string;
  banner: string;
  d26_category: string;
  tchp_category: string;
  latest_hazard_indicators: string;
  limitations: string[];
  policy: { name: string; persistence_envelope_days: number; policy_version: string };
  products?: Record<string, string>;
  stack_verdict?: string;
  hindcast?: { n_dates: number; window: string[] | null };
  protocol: string;
  protocol_commit?: string;
  qualified_unreachable_reason?: string;
  timeliness_note?: string;
  d26_tchp_explanation?: string;
  hazard_transfer_note?: string;
}
interface Source {
  product_key: string;
  channels: string[];
  product_id: string;
  dataset_id: string;
  state: string;
  newest_valid_time: string | null;
  product_valid_time: string | null;
  local_retrieval_time: string | null;
  age_hours: number | null;
  error: string | null;
}
interface WindowDay {
  date: string;
  status: "AVAILABLE" | "UNAVAILABLE";
  is_newest: boolean;
  /** An immutable field for this date is already on disk: opening it is instant. */
  cached?: boolean;
  /** "ready" | "pending" | "fetching" | "refused: …" | "error: …" */
  warm?: string;
  reason?: string;
  missing_channels?: string[];
}
interface AvailableDates {
  newest_qualified_date: string | null;
  days: WindowDay[];
  per_product_newest?: Record<string, string | null>;
  error?: string;
}
interface LatestPayload {
  state: string;
  label: string | null;
  effective_date?: string;
  selected_date?: string;
  newest_qualified_date?: string | null;
  is_newest?: boolean;
  served_from?: string;
  reason?: string;
  missing_channels?: string[];
  sources?: Source[];
  meta?: {
    retrieval_time_utc?: string;
    oldest_input_age_hours?: number;
    newest_input_age_hours?: number;
    reconstruction_lag_hours?: number;
    joint_mask_coverage?: number;
    persisted_inputs?: string;
    snapshot_generated_utc?: string;
    snapshot_staleness_hours?: number;
  };
  live_attempt?: { attempted: boolean; reasons?: string[]; sources?: Source[] } | null;
  field: ReplayPayload | null;
}

const hours = (h?: number | null) =>
  h == null ? "—" : h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} d`;

export default function LatestQualified({
  qualification,
  onData,
}: {
  qualification: Qualification;
  onData: (d: ReplayData | null) => void;
}) {
  const [payload, setPayload] = useState<LatestPayload | null>(null);
  const [window7, setWindow7] = useState<AvailableDates | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const live = useRef(true);

  const accept = useCallback(
    (p: LatestPayload) => {
      if (!live.current) return;
      try {
        onData(p.field ? adaptReplay(p.field) : null);
        setPayload(p);
      } catch (e) {
        setError(`Latest field rejected by the field contract: ${(e as Error).message}`);
      }
    },
    [onData],
  );

  /** One date, always through the same qualification + inference path. */
  const load = useCallback(
    (date?: string) => {
      setBusy(true);
      setError("");
      // A failure never blanks the tab: the previous state stays on screen.
      getJson<LatestPayload>(
        date ? `/api/latest/qualified?date=${encodeURIComponent(date)}` : "/api/latest/qualified",
      )
        .then(accept)
        .catch((e) => live.current && setError(String(e)))
        .finally(() => live.current && setBusy(false));
    },
    [accept],
  );

  const refresh = useCallback(() => {
    getJson<AvailableDates>("/api/latest/available-dates?refresh=true")
      .then((w) => live.current && setWindow7(w))
      .catch(() => {});
    load();
  }, [load]);

  useEffect(() => {
    live.current = true;
    // Ask the server to pre-produce every recent state, so switching dates is
    // instant. It returns at once; the work happens in the background and never
    // blocks this page or Historical Replay.
    getJson("/api/latest/prewarm").catch(() => {});
    getJson<AvailableDates>("/api/latest/available-dates")
      .then((w) => live.current && setWindow7(w))
      .catch(() => {});
    getJson<LatestPayload>("/api/latest/qualified/cached")
      .then((p) => {
        if (p.field) accept(p);
        else if (live.current) setPayload((cur) => cur ?? p);
      })
      .catch(() => {})
      .finally(() => live.current && load());
    return () => {
      live.current = false;
    };
  }, [accept, load]);

  // While the server is still preparing states, refresh the strip so each day
  // flips to "ready" as it lands.
  const preparing = (window7?.days ?? []).filter(
    (d) => d.status === "AVAILABLE" && d.warm !== "ready",
  ).length;
  useEffect(() => {
    if (!preparing) return;
    const timer = setTimeout(() => {
      getJson<AvailableDates>("/api/latest/available-dates")
        .then((w) => live.current && setWindow7(w))
        .catch(() => {});
    }, 8000);
    return () => clearTimeout(timer);
  }, [preparing, window7]);

  const state = payload?.state;
  const selectedDate = payload?.selected_date ?? payload?.effective_date;
  const sources = payload?.sources ?? [];
  const attempt = payload?.live_attempt;
  const m = payload?.meta ?? {};

  return (
    <>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">
              {qualification.tab_name.toUpperCase()} · COMPLETE SEVEN-CHANNEL STACK
            </span>
            <h2>Latest available qualified reconstruction</h2>
          </div>
          <button className="btn" onClick={refresh} disabled={busy}>
            {busy ? "Retrieving all seven inputs…" : "Retry / Refresh"}
          </button>
        </div>

        <p className="notice" data-testid="qualification-banner">
          <strong>{qualification.banner}</strong> — the frozen L2 driven by the
          complete near-real-time input stack ({qualification.policy.name}),
          qualified under the pre-registered Phase 8B protocol. Plain
          “QUALIFIED” is not reachable in this phase:{" "}
          {qualification.qualified_unreachable_reason}
        </p>

        {window7 && window7.days.length > 0 && (
          <div className="date-strip" data-testid="recent-states">
            <span className="eyebrow">RECENT QUALIFIED STATES</span>
            <div className="date-strip-row">
              {window7.days.map((d) => {
                const selected = d.date === selectedDate;
                return (
                  <button
                    key={d.date}
                    type="button"
                    className={`date-chip${selected ? " selected" : ""}${
                      d.status === "AVAILABLE" ? "" : " unavailable"
                    }${
                      d.status === "AVAILABLE" && d.warm !== "ready"
                        ? " preparing"
                        : ""
                    }`}
                    data-testid={`day-${d.date}`}
                    data-status={d.status}
                    data-warm={d.warm ?? "unknown"}
                    data-selected={selected ? "true" : "false"}
                    disabled={d.status !== "AVAILABLE" || busy}
                    title={
                      d.status !== "AVAILABLE"
                        ? d.reason
                        : d.warm === "ready"
                          ? `Qualified state for ${d.date} — ready`
                          : `Qualified state for ${d.date} — preparing (${d.warm})`
                    }
                    onClick={() => d.status === "AVAILABLE" && load(d.date)}
                  >
                    {d.date.slice(5)}
                    {d.is_newest && <span className="newest-dot" aria-hidden />}
                  </button>
                );
              })}
            </div>
            {preparing > 0 && (
              <p className="small muted" data-testid="warm-progress">
                Preparing {preparing} of{" "}
                {(window7.days ?? []).filter((d) => d.status === "AVAILABLE").length}{" "}
                recent states in the background — each is a full seven-channel
                qualification and frozen-L2 run, so they open instantly once ready.
              </p>
            )}
            <p className="small muted">
              Newest complete seven-channel state:{" "}
              <strong data-testid="newest-date">
                {window7.newest_qualified_date ?? "none"}
              </strong>
              . Unavailable days are shown, not hidden: each is missing at least
              one mandatory channel, and no day is filled from another.
            </p>
            {window7.days
              .filter((d) => d.status === "UNAVAILABLE")
              .slice(0, 3)
              .map((d) => (
                <p className="small muted" key={d.date} data-testid={`why-${d.date}`}>
                  {d.date} — {d.reason}
                </p>
              ))}
          </div>
        )}

        {payload?.state === "DATE_NOT_QUALIFIED" && (
          <p className="notice" data-testid="date-unavailable">
            <strong>{payload.label}</strong> — {payload.reason}. No inference was
            run for this date.
          </p>
        )}

        {payload?.effective_date && (
          <p className="notice" data-testid="timeliness-note">
            <strong>Operational timeliness not certified.</strong> Scientific
            input-stack qualification and operational timeliness are separate.
            This field is valid for <strong>{payload.effective_date}</strong> and
            was retrieved with a{" "}
            <strong>
              {m.reconstruction_lag_hours == null
                ? "—"
                : `${(m.reconstruction_lag_hours / 24).toFixed(1)}-day`}
            </strong>{" "}
            reconstruction lag. Operational timeliness has not been separately
            certified. This is not the ocean now.
          </p>
        )}

        {busy && (
          <p className="muted small" role="status" data-testid="latest-busy">
            Retrieving all seven inputs for their common valid date. Nothing is
            inferred until every channel is present and passes its checks.
          </p>
        )}
        {state === "LAST_SUCCESSFUL_QUALIFIED_SNAPSHOT_NOT_CURRENT" && (
          <p className="notice" data-testid="snapshot-label">
            <strong>{payload?.label}</strong> — produced{" "}
            {m.snapshot_generated_utc ?? "unknown"} UTC, {hours(m.snapshot_staleness_hours)}{" "}
            ago. It is shown because a new qualified reconstruction could not be
            produced; it is not presented as current.
          </p>
        )}
        {state === "LATEST_QUALIFIED_OCEAN_STATE_CURRENTLY_UNAVAILABLE" && (
          <p className="notice" data-testid="unavailable-label">
            <strong>{payload?.label}</strong> — no qualified reconstruction has
            been produced yet and the complete stack is not available now.
            Nothing is invented in its place.
          </p>
        )}
        {attempt?.attempted && attempt.reasons && attempt.reasons.length > 0 && (
          <div className="muted small" data-testid="live-attempt">
            Latest attempt refused — no inference was run:
            <ul>
              {attempt.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        )}
        {error && (
          <p className="panel error-state" data-testid="latest-error">
            {error}. The previous state is still shown, and Historical Replay is
            unaffected.
          </p>
        )}

        <div className="stats-grid">
          <div className="stat" data-testid="latest-state">
            <span>STATE</span>
            <strong>
              {state === "LATEST_QUALIFIED"
                ? "Newest qualified state"
                : state === "QUALIFIED_STATE_FOR_DATE"
                  ? "Qualified state for this date"
                  : state === "LAST_SUCCESSFUL_QUALIFIED_SNAPSHOT_NOT_CURRENT"
                    ? "Snapshot — not current"
                    : state === "DATE_NOT_QUALIFIED"
                      ? "No qualified state for this date"
                      : state
                        ? "Unavailable"
                        : "Checking…"}
            </strong>
            <span className="small muted">{state ?? ""}</span>
          </div>
          <div className="stat" data-testid="effective-date">
            <span>SELECTED OCEAN STATE · VALID</span>
            <strong>{payload?.effective_date ?? "—"}</strong>
            <span className="small muted">
              common valid date of all seven inputs
              {payload?.is_newest === false ? " · not the newest state" : ""}
            </span>
          </div>
          <div className="stat" data-testid="newest-qualified-state">
            <span>NEWEST QUALIFIED STATE</span>
            <strong>
              {payload?.newest_qualified_date ??
                window7?.newest_qualified_date ??
                "—"}
            </strong>
            <span className="small muted">
              newest date all seven channels can supply
            </span>
          </div>
          <div className="stat">
            <span>RECONSTRUCTION LAG</span>
            <strong>{hours(m.reconstruction_lag_hours)}</strong>
            <span className="small muted">retrieval time − effective date</span>
          </div>
          <div className="stat">
            <span>OLDEST / NEWEST INPUT AGE</span>
            <strong>
              {hours(m.oldest_input_age_hours)} / {hours(m.newest_input_age_hours)}
            </strong>
            <span className="small muted">
              persisted inputs: {m.persisted_inputs ? "none" : "—"}
            </span>
          </div>
          <div className="stat">
            <span>JOINT-MASK COVERAGE</span>
            <strong>
              {m.joint_mask_coverage == null
                ? "—"
                : `${(m.joint_mask_coverage * 100).toFixed(1)}%`}
            </strong>
            <span className="small muted">of the hindcast reference cells</span>
          </div>
        </div>

        <div className="notice" data-testid="d26-withheld">
          <p>
            <strong>D26 · {qualification.d26_category}</strong> (withheld) ·{" "}
            <strong>TCHP · {qualification.tchp_category}</strong> ·{" "}
            <strong>
              Ocean Hazard Indicators · {qualification.latest_hazard_indicators}
            </strong>
          </p>
          <p className="small">{qualification.d26_tchp_explanation}</p>
          <p className="small" data-testid="hazard-transfer-note">
            {qualification.hazard_transfer_note}
          </p>
        </div>
        <p className="muted small">
          Historical Replay and historical Ocean Hazard Indicators are local
          capabilities and remain fully available regardless of this state.
        </p>
      </section>

      <section className="panel" data-testid="latest-sources">
        <span className="eyebrow">SOURCE BY SOURCE</span>
        <h2>Seven channels, one common valid date</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Channels</th>
                <th>Product</th>
                <th>Status</th>
                <th>Newest available</th>
                <th>Valid time used</th>
                <th>Retrieved at</th>
                <th>Age</th>
              </tr>
            </thead>
            <tbody>
              {sources.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted">
                    No qualified reconstruction yet.
                  </td>
                </tr>
              )}
              {sources.map((s) => (
                <tr key={s.product_key} data-state={s.state}>
                  <td>{s.channels.join(", ").toUpperCase()}</td>
                  <td title={s.dataset_id}>
                    {s.product_id}
                    <br />
                    <span className="small muted">{s.dataset_id}</span>
                  </td>
                  <td>{s.state}</td>
                  <td>{s.newest_valid_time ?? "—"}</td>
                  <td>{s.product_valid_time ?? "—"}</td>
                  <td>{s.local_retrieval_time ?? "—"}</td>
                  <td>{hours(s.age_hours)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          Every channel is used at the same valid date, as in training; no
          channel is carried forward from an older day. Product valid time and
          local retrieval time are stored and shown separately.
        </p>
      </section>

      <section className="panel" data-testid="limitations">
        <span className="eyebrow">QUALIFIED WITH LIMITATIONS — WHAT THAT MEANS</span>
        <h2>Limitations</h2>
        <ul>
          {qualification.limitations.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
        <p className="muted small">
          Protocol {qualification.protocol} (commit {qualification.protocol_commit})
          · hindcast {qualification.hindcast?.n_dates} dates
          {qualification.hindcast?.window
            ? ` (${qualification.hindcast.window.join(" → ")})`
            : ""}{" "}
          · stack verdict {qualification.stack_verdict}.
        </p>
      </section>
    </>
  );
}

/** Latest Ocean Thermal Support, read from the SAME authoritative field. */
export function LatestHazardPanel({
  field,
  selection,
  note,
}: {
  field: FieldView;
  selection: Selection;
  note?: string;
}) {
  const h = field.hazard;
  if (!h) return null;
  const here = hazardAt(field, selection);
  return (
    <section className="panel" data-testid="latest-hazard">
      <span className="eyebrow">OCEAN HAZARD INDICATORS · LATEST QUALIFIED MODE</span>
      <h2>{h.indicator}</h2>
      {note && (
        <p className="muted" data-testid="latest-hazard-transfer">
          {note}
        </p>
      )}
      <p>
        Selected cell:{" "}
        <strong data-testid="latest-hazard-level">
          {here ? here.label.replaceAll("_", " ") : "—"}
        </strong>
        {here && Number.isFinite(here.tchp) && (
          <> · TCHP {format(here.tchp, 1)} kJ/cm²</>
        )}
      </p>
      <div className="stats-grid">
        {[...HAZARD_ORDER, "NOT_CATEGORIZED"].map((c) => (
          <div className="stat" key={c}>
            <span>{c.replaceAll("_", " ")}</span>
            <strong>{(h.categoryCounts[c] ?? 0).toLocaleString()}</strong>
            <span className="small muted">cells</span>
          </div>
        ))}
      </div>
      {h.thresholds && (
        <p className="muted small">
          Frozen Phase 7D boundaries (not retuned): {h.thresholds.p50} /{" "}
          {h.thresholds.p75} / {h.thresholds.p90} kJ/cm².
        </p>
      )}
      <p className="notice">{h.nonPrediction}</p>
      <p className="muted small">
        {h.scopeNote} {h.uncertaintyNote}
      </p>
    </section>
  );
}
