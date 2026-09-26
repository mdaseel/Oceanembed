import { useEffect, useMemo, type ReactNode } from "react";
import { RefreshCw, ShieldAlert } from "lucide-react";
import type { FieldView, Selection } from "../../field/contract";
import {
  addDays,
  contiguousRun,
  signed,
  supportCells,
  type DayState,
  type DaySummary,
} from "../../field/hazardIntelligence";
import type { Qualification } from "../LatestQualified";
import { InfoTip } from "./InfoTip";
import type { NrtPayload } from "./useNrtStates";

const lagText = (h?: number) =>
  h == null ? "—" : h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} days`;
const stackText = (state?: string) =>
  state === "LATEST_QUALIFIED"
    ? "Complete · newest state"
    : state === "QUALIFIED_STATE_FOR_DATE"
      ? "Complete · earlier state"
      : state === "LAST_SUCCESSFUL_QUALIFIED_SNAPSHOT_NOT_CURRENT"
        ? "Snapshot · NOT CURRENT"
        : (state ?? "—");

/** LATEST QUALIFIED OCEAN STATE: provenance, qualification and failure states. */
export function NrtStatus({
  qualification,
  payload,
  validDate,
  d26Withheld,
  hasData,
  initialised,
  busy,
  error,
  notice,
  windowError,
  skipped,
  gapNotice,
  noncontiguous,
  onRefresh,
  onHistorical,
  children,
}: {
  qualification: Qualification | null;
  payload: NrtPayload | null;
  validDate: string | null;
  d26Withheld: boolean;
  hasData: boolean;
  initialised: boolean;
  busy: boolean;
  error: string;
  notice: NrtPayload | null;
  windowError: string;
  skipped: string[];
  gapNotice: { date: string; reason: string } | null;
  noncontiguous: boolean;
  onRefresh: () => void;
  onHistorical: () => void;
  children: ReactNode;
}) {
  const qualified = !!qualification?.qualified;
  if (!qualified || (initialised && !hasData && !busy)) {
    const why = !qualification
      ? "The latest-state qualification could not be read from this server."
      : !qualification.qualified
        ? `The latest subsurface reconstruction is not qualified (${qualification.temperature_category}).`
        : notice?.label
          ? `${notice.label}.`
          : error
            ? `${error}.`
            : "No qualified reconstruction could be produced.";
    return (
      <section className="panel nrt-status" data-testid="nrt-status">
        <span className="eyebrow">LATEST QUALIFIED OCEAN STATE</span>
        <div className="notice nrt-unavailable" data-testid="nrt-unavailable">
          <ShieldAlert size={18} aria-hidden />
          <span>
            <strong>Latest reconstruction currently unavailable.</strong> Historical Event
            Intelligence remains available. {why}
            {notice?.live_attempt?.reasons?.length
              ? ` Latest attempt refused: ${notice.live_attempt.reasons.join("; ")}.`
              : ""}{" "}
            Nothing is inferred or shown in its place.
          </span>
        </div>
        <div className="action-row">
          <button type="button" className="btn" onClick={onHistorical}>
            Open Historical Event Intelligence
          </button>
          {qualified && (
            <button type="button" className="btn" onClick={onRefresh}>
              Retry
            </button>
          )}
        </div>
      </section>
    );
  }
  const m = payload?.meta ?? {};
  const state = payload?.state;
  const q = qualification!;
  return (
    <section className="panel nrt-status" data-testid="nrt-status">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">LATEST QUALIFIED OCEAN STATE</span>
          <h2>Latest available qualified reconstruction</h2>
        </div>
        <button type="button" className="btn" onClick={onRefresh} disabled={busy}>
          <RefreshCw size={14} className={busy ? "spin" : ""} aria-hidden />{" "}
          {busy ? "Retrieving…" : "Refresh"}
        </button>
      </div>
      {!hasData ? (
        <p className="muted" role="status" data-testid="nrt-loading">
          Retrieving the latest qualified reconstruction. All seven inputs must share one valid
          date before anything is inferred.
        </p>
      ) : (
        <>
          <div className="nrt-header" data-testid="nrt-header">
            <div>
              <span>VALID DATE</span>
              <strong data-testid="nrt-valid-date">{validDate}</strong>
              <small>common valid date of all seven inputs</small>
            </div>
            <div>
              <span>RETRIEVED</span>
              <strong>
                {m.retrieval_time_utc
                  ? `${m.retrieval_time_utc.replace("T", " ").slice(0, 16)} UTC`
                  : "—"}
              </strong>
              <small>local retrieval of the inputs</small>
            </div>
            <div>
              <span>
                RECONSTRUCTION LAG <InfoTip term="lag" />
              </span>
              <strong data-testid="nrt-lag">{lagText(m.reconstruction_lag_hours)}</strong>
              <small>retrieval time − valid date</small>
            </div>
            <div>
              <span>
                INPUT STACK <InfoTip term="qualified" />
              </span>
              <strong data-testid="nrt-stack">{stackText(state)}</strong>
              <small>seven channels, one valid date, no persistence</small>
            </div>
          </div>
          <ul className="qual-list" data-testid="nrt-qualification">
            <li>
              <span>15-depth temperature</span>
              <strong>{q.temperature_category}</strong>
            </li>
            <li>
              <span>TCHP</span>
              <strong data-testid="nrt-tchp-qual">{q.tchp_category}</strong>
            </li>
            {d26Withheld ? (
              <li className="withheld" data-testid="nrt-d26">
                <span>D26</span>
                <strong>WITHHELD</strong>
                <span>Operational qualification did not pass ({q.d26_category}).</span>
              </li>
            ) : (
              <li data-testid="nrt-d26">
                <span>D26</span>
                <strong>{q.d26_category}</strong>
              </li>
            )}
            <li>
              <span>Thermal-support indicator</span>
              <strong>{q.latest_hazard_indicators}</strong>
            </li>
          </ul>
        </>
      )}
      {state === "LAST_SUCCESSFUL_QUALIFIED_SNAPSHOT_NOT_CURRENT" && (
        <p className="notice" data-testid="nrt-snapshot">
          <strong>{payload?.label}</strong> — shown because a newer qualified reconstruction could
          not be produced; it is not presented as current.
        </p>
      )}
      {notice?.state === "DATE_NOT_QUALIFIED" && hasData && (
        <p className="notice" data-testid="nrt-date-refused">
          <strong>{notice.label}</strong> — {notice.reason}. No inference was run for this date;
          the previous qualified state stays on screen.
        </p>
      )}
      {error && hasData && (
        <p className="notice" data-testid="nrt-error">
          {error}. The previous qualified state is still shown.
        </p>
      )}
      <div className="nrt-evolution">
        <span className="eyebrow">RECENT QUALIFIED OCEAN EVOLUTION · SEVEN CALENDAR DAYS</span>
        {children}
        {noncontiguous && (
          <p className="notice" data-testid="nrt-noncontiguous">
            Recent qualified states are non-contiguous. Missing days were not interpolated.
          </p>
        )}
        {skipped.length > 0 && (
          <p className="notice" data-testid="nrt-skipped">
            Skipped {skipped.join(", ")}: not a qualified state. Playback moved to the next
            qualified day; no field was shown for the skipped date.
          </p>
        )}
        {gapNotice && (
          <p className="notice" data-testid="nrt-gap-notice">
            <strong>{gapNotice.date}</strong> — {gapNotice.reason}. No request was made and no
            field is shown for this date.
          </p>
        )}
        {windowError && (
          <p className="small muted">Recent-state discovery unavailable: {windowError}</p>
        )}
      </div>
      {hasData && (
        <p className="small muted" data-testid="nrt-timeliness">
          Latest available qualified reconstruction, valid for {validDate} with a{" "}
          {lagText(m.reconstruction_lag_hours)} reconstruction lag: the map describes that valid
          date, not the present moment. Operational timeliness has not been separately
          certified.
        </p>
      )}
    </section>
  );
}

/**
 * RECENT QUALIFIED OCEAN EVOLUTION. A change is only a subtraction between two
 * real, consecutive qualified states; with too few of them an explicit
 * fallback is shown instead of a trend.
 */
export function RecentChange({
  days,
  current,
  summaries,
  failed,
  ensure,
  field: f,
  selection,
}: {
  days: DayState[];
  current: string | null;
  summaries: Record<string, DaySummary>;
  failed: string[];
  ensure: (dates: string[]) => Promise<void>;
  field: FieldView;
  selection: Selection;
}) {
  const run = useMemo(() => contiguousRun(days, current), [days, current]);
  const runKey = run.join(",");
  useEffect(() => {
    if (run.length >= 2) void ensure(run);
    // run is derived from runKey; depending on the key avoids refetch loops
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runKey, ensure]);
  const available = days.filter((d) => d.status === "AVAILABLE").length;
  const i = selection.row >= 0 ? selection.row * f.lon.length + selection.col : -1;
  const missing = run.filter((d) => failed.includes(d));
  const loaded = run.length > 0 && run.every((d) => summaries[d]);

  let body: ReactNode;
  if (!current || days.length === 0) {
    body = (
      <p className="notice" data-testid="trend-fallback">
        RECENT TREND · Recent qualified states are not yet known.
      </p>
    );
  } else if (available <= 1) {
    body = (
      <p className="notice" data-testid="trend-fallback">
        RECENT TREND · Insufficient consecutive qualified days — only one qualified state is
        currently available.
      </p>
    );
  } else if (run.length < 2) {
    body = (
      <p className="notice" data-testid="trend-fallback">
        RECENT TREND · Insufficient consecutive qualified days: {addDays(current, -1)} is not a
        qualified state, so no change is computed across the gap. Missing days were not
        interpolated.
      </p>
    );
  } else if (missing.length) {
    body = (
      <p className="notice" data-testid="trend-fallback">
        RECENT TREND · {missing.join(", ")} could not be read, so no change is computed.
      </p>
    );
  } else if (!loaded) {
    body = (
      <p className="muted small" role="status" data-testid="trend-loading">
        Reading {run.length} consecutive qualified states…
      </p>
    );
  } else {
    const cur = summaries[current],
      prev = summaries[run[run.length - 2]],
      first = summaries[run[0]];
    const at = (s: DaySummary, key: "tchp" | "anomaly100") => (i >= 0 ? s[key][i] : NaN);
    const dT = at(cur, "tchp") - at(prev, "tchp");
    const dA = at(cur, "anomaly100") - at(prev, "anomaly100");
    const dRun = at(cur, "tchp") - at(first, "tchp");
    body = (
      <>
        <h3 className="sub">CHANGE SINCE PREVIOUS QUALIFIED DAY · {prev.date}</h3>
        <dl className="metric-list">
          <div>
            <dt>TCHP · here</dt>
            <dd data-testid="change-tchp">
              {Number.isFinite(dT) ? signed(dT, 1, "kJ/cm²") : "Unavailable here"}
            </dd>
          </div>
          <div>
            <dt>100 m anomaly · here</dt>
            <dd data-testid="change-anomaly">
              {Number.isFinite(dA) ? signed(dA, 2, "°C") : "Unavailable here"}
            </dd>
          </div>
          <div>
            <dt>HIGH + ELEVATED cells</dt>
            <dd data-testid="change-support-cells">
              {signed(supportCells(cur) - supportCells(prev), 0)}
            </dd>
          </div>
        </dl>
        {run.length >= 3 ? (
          <p data-testid="trend-line">
            Recent trend:{" "}
            <strong>{Number.isFinite(dRun) ? signed(dRun, 1, "kJ/cm²") : "unavailable here"}</strong>{" "}
            TCHP at the selected location across {run.length} consecutive qualified states (
            {first.date} → {cur.date}).
          </p>
        ) : (
          <p className="small muted" data-testid="trend-fallback">
            RECENT TREND · Only two consecutive qualified states are available; the change above
            is the whole record.
          </p>
        )}
      </>
    );
  }

  return (
    <section className="panel recent-change" data-testid="recent-change" data-run={run.length}>
      <span className="eyebrow">RECENT QUALIFIED OCEAN EVOLUTION</span>
      <h2>What changed between qualified days</h2>
      {body}
      <p className="small muted">
        Subtractions between independent daily reconstructions. No trend line is fitted, no day
        is filled from another, and nothing here is a forecast. Domain cell counts are the
        backend's category counts.
      </p>
    </section>
  );
}
