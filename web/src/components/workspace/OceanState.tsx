import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Flame, LineChart, RefreshCw, Sigma, Thermometer, Waves } from "lucide-react";
import { getJson, loadReplay } from "../../field/api";
import { useBathymetry } from "../../field/bathymetry";
import {
  DIAGNOSTIC_UNIT,
  diagnosticAt,
  format,
  offset,
  resolve,
  type FieldView,
} from "../../field/contract";
import {
  monitoringAreas,
  trackAreaRelation,
  windowGaps,
  type Basins,
  type DayState,
  type MonitoringArea,
} from "../../field/hazardIntelligence";
import type { ReplayData } from "../../field/replayAdapter";
import type { Qualification } from "../LatestQualified";
import { pixelToLatLon } from "../MapView";
import { BasinSummary } from "../hazard/BasinSummary";
import { ColumnInsight } from "../hazard/ColumnInsight";
import { CycloneWatch } from "../hazard/CycloneWatch";
import { ExternalHazardContext } from "../hazard/ExternalHazardContext";
import { InterpretationCard } from "../hazard/InterpretationCard";
import { MapOverlay } from "../hazard/MapOverlay";
import { MonitoringAreas, type AreaRelation } from "../hazard/MonitoringAreas";
import { RecentChange } from "../hazard/NrtPanels";
import { PlaybackBar, SPEEDS, type Frame } from "../hazard/PlaybackBar";
import { ThermalSupportMap } from "../hazard/ThermalSupportMap";
import type { CycloneAnalysis, CycloneState } from "../hazard/api";
import type { HazardLayer, RenderMapPanel, RenderProfile } from "../hazard/types";
import { useNrtStates, type NrtWindow } from "../hazard/useNrtStates";
import { CoastalContextView, ValidationContextView } from "./ContextSections";
import { Inspector, Section, Tray, type TrayTab } from "./Layout";
import { ExtremeOverlay, ThermalExtremesPanel } from "./ThermalExtremes";
import "../hazard/hazard.css";
import "../hazard/expansion.css";
import "./workspace.css";

const MultiDate = lazy(() => import("../MultiDate"));

const lagText = (h?: number | null) =>
  h == null ? "—" : h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} days`;
const stateText = (state?: string) =>
  state === "LATEST_QUALIFIED"
    ? "Newest qualified state"
    : state === "QUALIFIED_STATE_FOR_DATE"
      ? "Qualified state for this date"
      : state === "LAST_SUCCESSFUL_QUALIFIED_SNAPSHOT_NOT_CURRENT"
        ? "Snapshot — not current"
        : state === "DATE_NOT_QUALIFIED"
          ? "No qualified state for this date"
          : state
            ? "Unavailable"
            : "Checking…";

function readableReason(day: DayState, w: NrtWindow | null): string {
  if (day.status === "AVAILABLE") return "";
  const missing = day.missing_channels ?? [];
  if (!missing.length) return `Not qualified — ${day.reason ?? "availability not determined"}`;
  const names = missing.map((key) => {
    const source = w?.sources?.find((s) => s.product_key === key);
    return source ? `${source.channels.join("/")} (${source.product_id})` : key;
  });
  return `Not qualified · missing/incomplete source: ${names.join(", ")}`;
}

function Stat({ label, value, unit, icon: Icon, primary }: {
  label: string;
  value: string;
  unit: string;
  icon?: typeof Thermometer;
  primary?: boolean;
}) {
  return (
    <div className={`stat${primary ? " primary" : ""}`}>
      <span>
        {Icon ? <Icon size={12} strokeWidth={2} aria-hidden /> : null}
        {label}
      </span>
      <strong>
        {value}
        {value !== "Unavailable" && <small>{unit}</small>}
      </strong>
      <div className="stat-rule" />
    </div>
  );
}

interface LatestSource {
  product_key: string;
  channels: string[];
  product_id: string;
  dataset_id: string;
  state: string;
  product_valid_time: string | null;
  local_retrieval_time: string | null;
  age_hours: number | null;
}

export interface OceanStateProps {
  source: "historical" | "latest";
  setSource: (s: "historical" | "latest") => void;
  historical: ReplayData | null;
  historicalDate: string;
  historicalLoading: boolean;
  historicalError: string;
  record: string[];
  request: (day: string, force?: boolean) => void;
  shiftDate: (days: number) => void;
  qualification: Qualification | null;
  coords: [number, number];
  onSelect: (lat: number, lon: number) => void;
  depth: number;
  onDepth: (k: number) => void;
  display: HazardLayer;
  setDisplay: (l: HazardLayer) => void;
  threeD: boolean;
  setThreeD: (v: boolean) => void;
  renderMapPanel: RenderMapPanel;
  renderProfile: RenderProfile;
  onOpenEvents: () => void;
}

/**
 * OCEAN STATE. One map, one inspector, one analysis tray, for either a
 * historical replay date or a latest qualified state. Every value is the
 * frozen field's; nothing is interpolated, persisted or forecast.
 */
export default function OceanState(props: OceanStateProps) {
  const {
    source,
    setSource,
    historical,
    qualification: q,
    coords,
    onSelect,
    depth,
    onDepth,
    display,
    setDisplay,
    threeD,
    setThreeD,
    renderMapPanel,
    renderProfile,
  } = props;
  const latest = source === "latest";
  const nrt = useNrtStates(latest && !!q?.qualified);
  const { data: bathymetry } = useBathymetry();
  const [basins, setBasins] = useState<Basins | null>(null);
  const [tray, setTray] = useState("profile");
  const [cyclone, setCyclone] = useState<CycloneAnalysis | null>(null);
  const [cycloneStatus, setCycloneStatus] = useState<CycloneState | null>(null);
  const [testField, setTestField] = useState<ReplayData | null>(null);
  const [extremeGrid, setExtremeGrid] = useState<number[][] | null>(null);
  const [nrtPlaying, setNrtPlaying] = useState(false);
  const [nrtSpeed, setNrtSpeed] = useState(SPEEDS[1].ms);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [gapNotice, setGapNotice] = useState<{ date: string; reason: string } | null>(null);

  useEffect(() => {
    getJson<{ basins: Basins }>("/api/basins")
      .then((r) => setBasins(r?.basins ?? null))
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!latest) {
      setCyclone(null);
      setNrtPlaying(false);
    }
    if (latest) setExtremeGrid(null);
    setTray((t) => (latest && (t === "extremes" || t === "compare") ? "profile" : !latest && t === "cyclone" ? "profile" : t));
  }, [latest]);

  const isTest = latest && cyclone?.state === "HISTORICAL_TEST_EVENT";
  useEffect(() => {
    const date = isTest ? cyclone?.thermal_field?.valid_date : undefined;
    if (!date) {
      setTestField(null);
      return;
    }
    let live = true;
    loadReplay(date)
      .then((d) => live && setTestField(d))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [isTest, cyclone?.thermal_field?.valid_date]);

  // The archived test field replaces the map only once it has loaded; until then the
  // latest state stays on screen, so the page (and the cyclone panel) never unmounts.
  const showingTest = isTest && !!testField;
  const data = latest ? (showingTest ? testField : nrt.data) : historical;
  const f: FieldView | null = data?.field ?? null;
  const selection = f ? resolve(f, coords[0], coords[1]) : null;
  const withheld: string[] = f?.diagnostics?.withheld ?? [];
  const hazardReady = !!f?.hazard?.available;
  const shown: HazardLayer =
    (display === "d26" || display === "tchp") && withheld.includes(display)
      ? "temperature"
      : display === "support" && !hazardReady
        ? "temperature"
        : display;
  const monitoring = useMemo(() => (f && hazardReady ? monitoringAreas(f, basins) : null), [f, hazardReady, basins]);
  const activeArea =
    selection && monitoring
      ? (monitoring.areas.find((a) => a.row === selection.row && a.col === selection.col) ?? null)
      : null;
  const activeKey = activeArea ? `${activeArea.row},${activeArea.col}` : null;
  const chooseArea = (a: MonitoringArea) => onSelect(a.lat, a.lon);
  const samples = latest ? cyclone?.analysis?.samples : undefined;
  const relations = useMemo(() => {
    if (!f || !monitoring || !samples?.length) return undefined;
    const out: Record<string, AreaRelation> = {};
    for (const a of monitoring.areas) out[`${a.row},${a.col}`] = trackAreaRelation(a, samples, f);
    return out;
  }, [f, monitoring, samples]);
  const onGrid = useCallback((g: number[][] | null) => setExtremeGrid(g), []);
  const onStatus = useCallback((s: CycloneState | null) => setCycloneStatus(s), []);

  // ------------------------------------------------------------ latest playback
  const days: DayState[] = useMemo(
    () => [...(nrt.window7?.days ?? [])].sort((a, b) => a.date.localeCompare(b.date)),
    [nrt.window7],
  );
  const available = days.filter((d) => d.status === "AVAILABLE").map((d) => d.date);
  const current = nrt.data?.field.effectiveDate ?? null;
  const gaps = windowGaps(days).gaps;
  const frames: Frame[] = useMemo(
    () =>
      days.map((d) => ({
        date: d.date,
        available: d.status === "AVAILABLE",
        reason: readableReason(d, nrt.window7),
        marker: d.is_newest ? "NEWEST" : undefined,
      })),
    [days, nrt.window7],
  );
  const { loadDate } = nrt;
  useEffect(() => {
    if (!nrtPlaying || nrt.busy || !current) return;
    const i = days.findIndex((d) => d.date === current);
    let j = i + 1;
    const gap: string[] = [];
    while (j < days.length && days[j].status !== "AVAILABLE") gap.push(days[j++].date);
    if (i < 0 || j >= days.length) {
      setNrtPlaying(false);
      return;
    }
    const target = days[j].date;
    const timer = setTimeout(() => {
      setSkipped(gap);
      void loadDate(target);
    }, nrtSpeed);
    return () => clearTimeout(timer);
  }, [nrtPlaying, nrt.busy, current, days, nrtSpeed, loadDate]);
  const play = () => {
    if (available.length < 2) return;
    setGapNotice(null);
    if (!current || !available.includes(current) || current === available[available.length - 1]) {
      setSkipped([]);
      void loadDate(available[0]);
    }
    setNrtPlaying(true);
  };
  const step = (direction: -1 | 1) => {
    setNrtPlaying(false);
    setGapNotice(null);
    if (!available.length) return;
    let j = current ? days.findIndex((d) => d.date === current) : -1;
    if (j < 0) j = direction > 0 ? -1 : days.length;
    const gap: string[] = [];
    for (j += direction; j >= 0 && j < days.length; j += direction) {
      if (days[j].status === "AVAILABLE") break;
      gap.push(days[j].date);
    }
    if (j < 0 || j >= days.length) return;
    setSkipped(direction > 0 ? gap : []);
    void loadDate(days[j].date);
  };

  const payload = nrt.payload as (typeof nrt.payload & {
    sources?: LatestSource[];
    meta?: Record<string, number | string | undefined>;
    newest_qualified_date?: string | null;
  }) | null;
  const m = (payload?.meta ?? {}) as Record<string, number | string | undefined>;
  const lagHours = typeof m.reconstruction_lag_hours === "number" ? m.reconstruction_lag_hours : null;
  const latestUnavailable = latest && (!q?.qualified || (nrt.initialised && !nrt.data && !nrt.busy));
  const d26Withheld = withheld.includes("d26") || (!!q && q.d26_category !== "QUALIFIED");
  const adv = latest ? cyclone?.advisory : null;

  // ------------------------------------------------------------ location tiles
  const cell = f && selection && selection.row >= 0 ? offset(f, selection.row, selection.col, depth) : -1;
  const diag = (kind: "d26" | "tchp") => {
    if (!f?.diagnostics || !selection) return null;
    const d = diagnosticAt(f, kind, selection);
    return (
      <Stat
        key={kind}
        label={kind === "d26" ? "D26 · 26 °C ISOTHERM DEPTH" : "TCHP · HEAT POTENTIAL"}
        icon={kind === "d26" ? Waves : Flame}
        value={
          !d || !Number.isFinite(d.value)
            ? "No 26 °C crossing"
            : d.physical === "SUPPORTED"
              ? format(d.value, 1)
              : "Below local seafloor"
        }
        unit={
          !d || !Number.isFinite(d.value)
            ? d?.status === "SURFACE_BELOW_26"
              ? "column below 26 °C"
              : "not a value"
            : d.physical === "SUPPORTED"
              ? DIAGNOSTIC_UNIT[kind]
              : `raw ${format(d.value, 1)} ${DIAGNOSTIC_UNIT[kind]} — no water column`
        }
      />
    );
  };

  const sources: LatestSource[] = payload?.sources ?? [];
  const qualificationDetails = q && (
    <>
      <div className="notice" data-testid="d26-withheld">
        <p>
          <strong>D26 · {q.d26_category}</strong> (withheld) · <strong>TCHP · {q.tchp_category}</strong> ·{" "}
          <strong>Ocean Hazard Indicators · {q.latest_hazard_indicators}</strong>
        </p>
        <p className="small">{q.d26_tchp_explanation}</p>
        <p className="small" data-testid="hazard-transfer-note">
          {q.hazard_transfer_note}
        </p>
      </div>
      <div className="table-scroll" data-testid="latest-sources">
        <table className="science-table">
          <thead>
            <tr>
              <th>Channels</th>
              <th>Product</th>
              <th>Status</th>
              <th>Valid time used</th>
              <th>Retrieved at</th>
              <th>Age</th>
            </tr>
          </thead>
          <tbody>
            {sources.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  No qualified reconstruction yet.
                </td>
              </tr>
            )}
            {sources.map((s) => (
              <tr key={s.product_key} data-state={s.state}>
                <td>{s.channels.join(", ").toUpperCase()}</td>
                <td title={s.dataset_id}>{s.product_id}</td>
                <td>{s.state}</td>
                <td>{s.product_valid_time ?? "—"}</td>
                <td>{s.local_retrieval_time ?? "—"}</td>
                <td>{lagText(s.age_hours)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div data-testid="limitations">
        <span className="eyebrow">QUALIFIED WITH LIMITATIONS</span>
        <ul className="ws-note">
          {q.limitations?.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
        <p className="ws-note">
          Protocol {q.protocol} · hindcast {q.hindcast?.n_dates} dates · stack verdict {q.stack_verdict}. Every channel is
          used at the same valid date; no channel is carried forward.
        </p>
      </div>
    </>
  );

  const layerSelect = f && (
    <label className="layer-control">
      DISPLAY LAYER
      <select aria-label="Display layer" value={shown} onChange={(e) => setDisplay(e.target.value as HazardLayer)}>
        <option value="temperature">Reconstructed temperature</option>
        <option value="anomaly">Anomaly from climatology</option>
        {hazardReady && <option value="support">Ocean thermal support category</option>}
        {f.diagnostics && (
          <>
            {!withheld.includes("d26") && <option value="d26">D26 · 26 °C isotherm depth (m)</option>}
            {!withheld.includes("tchp") && <option value="tchp">TCHP · heat potential (kJ/cm²)</option>}
          </>
        )}
      </select>
    </label>
  );

  const controls = (
    <section className="panel controls ws-controls" data-testid="ocean-controls">
      <div className="segmented" role="group" aria-label="Ocean state source">
        <button type="button" className={!latest ? "active" : ""} aria-pressed={!latest} data-testid="source-historical" onClick={() => setSource("historical")}>
          Historical date
        </button>
        <button type="button" className={latest ? "active" : ""} aria-pressed={latest} data-testid="source-latest" onClick={() => setSource("latest")}>
          Latest qualified
        </button>
      </div>
      {!latest ? (
        <div className="date-control">
          <label htmlFor="historical-date">HISTORICAL DATE</label>
          <div className="action-row">
            <button className="btn-icon" type="button" aria-label="Previous day" disabled={props.historicalLoading || props.historicalDate === props.record[0]} onClick={() => props.shiftDate(-1)}>
              <ChevronLeft size={16} />
            </button>
            <input
              id="historical-date"
              type="date"
              min={props.record[0]}
              max={props.record[1]}
              value={props.historicalDate}
              onChange={(e) => {
                if (e.target.value) props.request(e.target.value);
              }}
            />
            <button className="btn-icon" type="button" aria-label="Next day" disabled={props.historicalLoading || props.historicalDate === props.record[1]} onClick={() => props.shiftDate(1)}>
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      ) : (
        q?.qualified &&
        nrt.data && (
          <PlaybackBar
            id="nrt"
            frames={frames}
            current={current}
            playing={nrtPlaying}
            busy={nrt.busy}
            speed={nrtSpeed}
            onSpeed={setNrtSpeed}
            onPlay={play}
            onPause={() => setNrtPlaying(false)}
            onStep={step}
            onRestart={() => {
              setNrtPlaying(false);
              setSkipped([]);
              setGapNotice(null);
              if (available.length) void loadDate(available[0]);
            }}
            onSelect={(d) => {
              setNrtPlaying(false);
              setSkipped([]);
              setGapNotice(null);
              void loadDate(d);
            }}
            onUnavailable={(d) => {
              setNrtPlaying(false);
              const day = days.find((x) => x.date === d);
              setGapNotice({ date: d, reason: day ? readableReason(day, nrt.window7) : "Not qualified" });
            }}
            playLabel="PLAY RECENT QUALIFIED EVOLUTION"
            stepNoun="qualified day"
            disabledReason={
              days.length && available.length <= 1
                ? "Recent evolution unavailable: only one qualified state is currently available."
                : undefined
            }
            skipped={skipped}
          />
        )
      )}
      <label>
        DEPTH
        <select aria-label="Depth" value={depth} onChange={(e) => onDepth(+e.target.value)} disabled={!f}>
          {(f?.depths || []).map((d, k) => (
            <option value={k} key={d}>
              {d} m{d === 0 ? " · nominal" : ""}
            </option>
          ))}
        </select>
      </label>
      {layerSelect}
      {!latest ? (
        <button type="button" className="btn run-button" disabled={props.historicalLoading || !props.historicalDate} onClick={() => props.request(props.historicalDate, true)}>
          <RefreshCw size={14} className={props.historicalLoading ? "spin" : ""} aria-hidden /> Run frozen L2
        </button>
      ) : (
        q?.qualified && (
          <button type="button" className="btn run-button" onClick={nrt.refresh} disabled={nrt.busy}>
            <RefreshCw size={14} className={nrt.busy ? "spin" : ""} aria-hidden /> {nrt.busy ? "Retrieving…" : "Refresh"}
          </button>
        )
      )}
    </section>
  );

  const header = (
    <header className="ws-head">
      <div>
        <span className="eyebrow">
          NORTH INDIAN OCEAN / OCEAN STATE / {latest ? (q?.tab_name ?? "LATEST").toUpperCase() : "HISTORICAL REPLAY"}
        </span>
        <h1>
          {latest
            ? "The latest available qualified reconstruction."
            : threeD
              ? "Explore the ocean in depth."
              : "The surface tells a deeper story."}
        </h1>
        <p className="muted">
          {latest
            ? `Valid ${f?.effectiveDate ?? "—"} · the common date of all seven near-real-time inputs, not the ocean now · 5–30°N, 45–105°E`
            : "Reconstructed subsurface temperature · 5–30°N, 45–105°E · 0.25° grid · 15 depths"}
        </p>
      </div>
      <div className="ws-head-side">
        <span className="mode-badge" data-testid="intel-mode-badge">
          {latest ? "LATEST QUALIFIED STATE" : "HISTORICAL REPLAY"}
        </span>
      </div>
    </header>
  );

  if (latest && latestUnavailable) {
    const notice = nrt.notice;
    const why = !q
      ? "The latest-state qualification could not be read from this server."
      : !q.qualified
        ? `The latest subsurface reconstruction is not qualified (${q.temperature_category}).`
        : notice?.label
          ? `${notice.label}.`
          : nrt.error
            ? `${nrt.error}.`
            : "No qualified reconstruction could be produced.";
    return (
      <div className="ws" data-testid="ocean-state" data-source={source}>
        {header}
        {controls}
        <section className="panel" data-testid="nrt-status">
          <div className="notice nrt-unavailable" data-testid="nrt-unavailable">
            <span>
              <strong>Latest reconstruction currently unavailable.</strong> Historical Event Intelligence remains available. {why}
              {notice?.live_attempt?.reasons?.length ? ` Latest attempt refused: ${notice.live_attempt.reasons.join("; ")}.` : ""} Nothing is inferred or shown in its place.
            </span>
          </div>
          {notice?.state === "LATEST_QUALIFIED_OCEAN_STATE_CURRENTLY_UNAVAILABLE" && (
            <p className="notice" data-testid="unavailable-label">
              <strong>{notice.label}</strong> — no qualified reconstruction has been produced yet and the complete stack is
              not available now. Nothing is invented in its place.
            </p>
          )}
          <div className="action-row">
            <button type="button" className="btn" onClick={props.onOpenEvents}>
              Open Historical Event Intelligence
            </button>
            {q?.qualified && (
              <button type="button" className="btn" onClick={nrt.refresh}>
                Retry
              </button>
            )}
          </div>
          {q?.qualified && qualificationDetails}
        </section>
      </div>
    );
  }

  const latestState = latest && q && nrt.data && (
    <Section title="Latest qualified state" defaultOpen testid="inspector-latest">
      <div className="nrt-header" data-testid="nrt-header">
        <div data-testid="effective-date">
          <span>VALID DATE</span>
          <strong data-testid="nrt-valid-date">{current}</strong>
          <small>
            common valid date of all seven inputs{payload?.is_newest === false ? " · not the newest state" : ""}
          </small>
        </div>
        <div data-testid="latest-state">
          <span>STATE</span>
          <strong data-testid="nrt-stack">{stateText(payload?.state)}</strong>
          <small>{payload?.state}</small>
        </div>
        <div data-testid="newest-qualified-state">
          <span>NEWEST QUALIFIED</span>
          <strong>{payload?.newest_qualified_date ?? nrt.window7?.newest_qualified_date ?? "—"}</strong>
        </div>
        <div>
          <span>RECONSTRUCTION LAG</span>
          <strong data-testid="nrt-lag">{lagText(lagHours)}</strong>
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
      </ul>
      <p className="ws-note" data-testid="timeliness-note">
        <span data-testid="nrt-timeliness">
          Latest available qualified reconstruction, valid for {current} with a{" "}
          {lagHours == null ? "—" : `${(lagHours / 24).toFixed(1)}-day`} reconstruction lag: the map describes that valid
          date, not the present moment. Operational timeliness has not been separately certified. This is not the ocean now.
        </span>
      </p>
      {payload?.state === "LAST_SUCCESSFUL_QUALIFIED_SNAPSHOT_NOT_CURRENT" && (
        <p className="notice" data-testid="snapshot-label">
          <span data-testid="nrt-snapshot">
            <strong>{payload.label}</strong> — produced {String(m.snapshot_generated_utc ?? "unknown")} UTC,{" "}
            {lagText(typeof m.snapshot_staleness_hours === "number" ? m.snapshot_staleness_hours : null)} ago. Shown because a
            newer qualified reconstruction could not be produced; NOT CURRENT.
          </span>
        </p>
      )}
      {payload?.live_attempt?.attempted && !!payload.live_attempt.reasons?.length && (
        <div className="ws-note" data-testid="live-attempt">
          Latest attempt refused — no inference was run:
          <ul>
            {payload.live_attempt.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      {nrt.notice?.state === "DATE_NOT_QUALIFIED" && (
        <p className="notice" data-testid="nrt-date-refused">
          <strong>{nrt.notice.label}</strong> — {nrt.notice.reason}. No inference was run for this date.
        </p>
      )}
      {nrt.error && (
        <p className="notice" data-testid="nrt-error">
          {nrt.error}. The previous qualified state is still shown.
        </p>
      )}
      {gaps.length > 0 && (
        <p className="notice" data-testid="nrt-noncontiguous">
          Recent qualified states are non-contiguous. Missing days were not interpolated.
        </p>
      )}
      {skipped.length > 0 && (
        <p className="notice" data-testid="nrt-skipped">
          Skipped {skipped.join(", ")}: not a qualified state. Playback moved to the next qualified day; no field was shown
          for the skipped date.
        </p>
      )}
      {gapNotice && (
        <p className="notice" data-testid="nrt-gap-notice">
          <strong>{gapNotice.date}</strong> — {gapNotice.reason}. No request was made and no field is shown for this date.
        </p>
      )}
    </Section>
  );

  const loading = !latest && props.historicalLoading;
  const error = !latest && props.historicalError;

  const trayTabs: TrayTab[] = f && selection && data
    ? [
        {
          id: "profile",
          label: "Vertical profile",
          keepMounted: true,
          render: () => (
            <div className="profile-stage" data-testid="profile-stage" data-field-date={f.effectiveDate}>
              {renderProfile(data, selection)}
            </div>
          ),
        },
        {
          id: "column",
          label: "Column structure",
          keepMounted: true,
          render: () => (
            <ColumnInsight field={f} selection={selection} depth={depth} onDepth={onDepth} bathymetry={bathymetry} basins={basins} onSelect={onSelect} />
          ),
        },
        ...(latest
          ? [
              {
                id: "cyclone",
                label: "Cyclone context",
                badge: cycloneStatus?.state === "ACTIVE_NORTH_INDIAN_CYCLONE" ? "ACTIVE" : isTest ? "TEST" : undefined,
                keepMounted: true,
                render: () => (
                  <div className="ws">
                    <CycloneWatch
                      onContext={setCyclone}
                      onStatus={onStatus}
                      onSelectPoint={onSelect}
                      latestValidDate={current}
                      latestLagHours={lagHours}
                      monitoring={monitoring}
                    />
                    <ExternalHazardContext />
                  </div>
                ),
              },
            ]
          : [
              {
                id: "extremes",
                label: "Thermal extremes",
                render: () => (
                  <ThermalExtremesPanel date={f.effectiveDate} lat={f.lat[Math.max(0, selection.row)]} lon={f.lon[Math.max(0, selection.col)]} onGrid={onGrid} available={!latest} />
                ),
              },
              {
                id: "compare",
                label: "Date comparison",
                render: () => (
                  <Suspense fallback={<p className="empty">Loading date comparison…</p>}>
                    <MultiDate date={props.historicalDate} coords={coords} depth={depth} />
                  </Suspense>
                ),
              },
            ]),
        {
          id: "provenance",
          label: "Provenance",
          render: () => (
            <div className="fig-row">
              <div className="fig-card">
                <h3>{f.provenance.model_name}</h3>
                <dl className="ws-kv">
                  <dt>Latent width</dt>
                  <dd>{f.provenance.latent_dim}</dd>
                  <dt>Receptive field</dt>
                  <dd>
                    {f.provenance.receptive_field} × {f.provenance.receptive_field}
                  </dd>
                  <dt>Parameters</dt>
                  <dd>{f.provenance.n_parameters.toLocaleString("en-US")}</dd>
                  <dt>Supported cells</dt>
                  <dd>{f.provenance.n_supported_cells.toLocaleString("en-US")}</dd>
                  <dt>Compute</dt>
                  <dd>{f.provenance.compute_seconds === null ? "Validated cache" : `${format(f.provenance.compute_seconds, 3)} s`}</dd>
                </dl>
                <p className="ws-note">Only surface inputs at inference. {f.credits}</p>
              </div>
              <div className="fig-card">
                <h3>Frozen hashes &amp; support semantics</h3>
                <p className="ws-note">L2 state dictionary SHA256: {f.provenance.l2_state_dict_sha256}</p>
                <p className="ws-note">Encoder SHA256: {f.provenance.l2_encoder_sha256}</p>
                <p className="ws-note">{f.provenance.climatology_defined_note}</p>
              </div>
            </div>
          ),
        },
      ]
    : [];

  return (
    <div className="ws" data-testid="ocean-state" data-source={source}>
      {header}
      {latest && q && (
        <p className="notice ws-banner" data-testid="qualification-banner">
          <strong>{q.banner}</strong> — the frozen L2 driven by the complete near-real-time input stack ({q.policy?.name}),
          qualified under the pre-registered Phase 8B protocol. Plain “QUALIFIED” is not reachable in this phase:{" "}
          {q.qualified_unreachable_reason}
        </p>
      )}
      {controls}
      {isTest && !showingTest && (
        <p className="muted small" role="status">
          Loading the historical reconstruction for the archived test event…
        </p>
      )}
      {showingTest && (
        <p className="notice map-test-banner" data-testid="map-test-banner">
          <strong>HISTORICAL / TEST EVENT</strong> — the map shows the OceanEmbed historical reconstruction for{" "}
          {cyclone?.thermal_field?.valid_date}, matching the archived advisory. It is not the latest qualified state.
        </p>
      )}
      {loading && (
        <div className="loading-state panel" role="status">
          <Waves className="spin" />
          <h2>Reconstructing {props.historicalDate}</h2>
          <p>Reading local surface inputs and the frozen L2 field. All 15 depths arrive together.</p>
          <div className="loading-line" />
        </div>
      )}
      {error && (
        <section className="panel error-state" role="alert">
          <h2>Historical reconstruction unavailable</h2>
          <p>{props.historicalError}</p>
          <button className="btn" onClick={() => props.request(props.historicalDate, true)}>
            Retry local replay
          </button>
        </section>
      )}
      {latest && !nrt.data && !isTest && (
        <p className="muted" role="status" data-testid="nrt-loading">
          Retrieving the latest qualified reconstruction. All seven inputs must share one valid date before anything is inferred.
        </p>
      )}
      {!loading && !error && f && selection && data && (
        <>
          <div className="ws-grid">
            <div className="ws-main">
              {renderMapPanel(data, selection, {
                layer: shown,
                threeD,
                setThreeD,
                eyebrow: threeD ? "15-DEPTH RECONSTRUCTED THERMAL FIELD" : latest ? "LATEST QUALIFIED STATE" : "SURFACE OBSERVATIONS → SUBSURFACE STRUCTURE",
                title: threeD ? "3D Depth View" : `North Indian Ocean · ${f.effectiveDate}`,
                overlay: (
                  <>
                    {!latest && extremeGrid && tray === "extremes" && <ExtremeOverlay grid={extremeGrid} />}
                    {hazardReady && (
                      <MapOverlay
                        rows={f.lat.length}
                        cols={f.lon.length}
                        areas={monitoring?.areas ?? []}
                        activeKey={activeKey}
                        onArea={chooseArea}
                        track={null}
                        trackDate={null}
                        externalTrack={adv && (!isTest || showingTest) ? { label: adv.provenance_label, test: showingTest, points: [...adv.observed_points, ...adv.forecast_points] } : null}
                        scenarioPath={[]}
                        drawing={false}
                        onDraw={() => {}}
                        toLatLon={(x, y) => pixelToLatLon(x, y, f)}
                      />
                    )}
                  </>
                ),
                supportMap: <ThermalSupportMap field={f} selection={selection} onSelect={onSelect} trackNote="" />,
              })}
              <div className="ws-map-context">
                <span className="chip" data-testid="inference-source">
                  {f.provenance.inference_source}
                </span>
                {latest ? (
                  <>
                    <p data-testid="official-track-status">
                      {adv
                        ? `External cyclone track: ${adv.provenance_label}. `
                        : "Official cyclone-track overlay: Not connected in this build. No live or forecast cyclone track is shown unless the connected source reports one. "}
                      IMD / RSMC New Delhi official track: not connected in this build.
                    </p>
                    <p>OceanEmbed describes ocean thermal conditions; it does not forecast cyclones. No numeric cyclone probability is produced.</p>
                  </>
                ) : (
                  <p>Frozen L2 · {f.provenance.n_supported_cells.toLocaleString("en-US")} supported cells on this date</p>
                )}
              </div>
            </div>
            <Inspector eyebrow="INSPECTOR · SELECTED LOCATION" title={selection.row >= 0 ? `${f.lat[selection.row].toFixed(2)}°N, ${f.lon[selection.col].toFixed(2)}°E` : "Outside the domain"}>
              <Section title="Selected location" defaultOpen testid="inspector-location">
                <div className="stats-grid">
                  <Stat primary label={`L2 TEMPERATURE / ${f.depths[depth]} M`} icon={Thermometer} value={cell >= 0 ? format(f.temperature[cell]) : "Unavailable"} unit="°C" />
                  <Stat label="L0 CLIMATOLOGY" icon={LineChart} value={cell >= 0 ? format(f.climatology[cell]) : "Unavailable"} unit="°C" />
                  <Stat label="ANOMALY FROM CLIMATOLOGY" icon={Sigma} value={cell >= 0 ? format(f.anomaly[cell]) : "Unavailable"} unit="°C" />
                  {!withheld.includes("tchp") && diag("tchp")}
                  {!withheld.includes("d26") && diag("d26")}
                </div>
                {/* Folded by default; unfolds by itself where it matters most (500 m and deeper). */}
                <details className="ws-notes" open={f.depths[depth] >= 500}>
                  <summary>About these values · nominal 0 m and deep-ocean skill</summary>
                  <p className="ws-note" data-testid="zero-note">
                    <strong>Nominal 0 m.</strong> {f.provenance.nominal_zero_m_note}
                  </p>
                  <p className={`ws-note ${f.depths[depth] >= 500 ? "deep-active" : ""}`} data-testid="deep-note">
                    <strong>Deep-ocean skill.</strong> {f.provenance.deep_skill_note}
                  </p>
                </details>
              </Section>
              {latestState}
              {hazardReady && monitoring && (
                <Section title="Thermal interpretation" defaultOpen testid="inspector-interpretation">
                  {/* The location tiles above already carry TCHP, anomaly and D26, so the card's own
                      metric strip and evidence list are folded away here rather than repeated. */}
                  <div className="ocean-interp">
                    <InterpretationCard field={f} selection={selection} mode={latest && !showingTest ? "nrt" : "historical"} basins={basins} topArea={monitoring.areas[0] ?? null} onArea={chooseArea} />
                  </div>
                  {latest && f.hazard && (
                    <div className="ws-note" data-testid="latest-hazard">
                      {f.hazard.nonPrediction}
                      {q?.hazard_transfer_note && (
                        <span data-testid="latest-hazard-transfer"> {q.hazard_transfer_note}</span>
                      )}
                    </div>
                  )}
                </Section>
              )}
              {hazardReady && monitoring && (
                <Section title="Thermal monitoring areas" badge={`${monitoring.areas.length}`} defaultOpen testid="inspector-areas">
                  <MonitoringAreas result={monitoring} activeKey={activeKey} onArea={chooseArea} date={f.effectiveDate} mode={latest && !showingTest ? "nrt" : "historical"} rmse={f.hazard!.error.rmse} relations={relations} />
                </Section>
              )}
              {latest && !showingTest && nrt.data && (
                <Section title="Recent change" defaultOpen testid="inspector-recent">
                  <RecentChange days={days} current={current} summaries={nrt.summaries} failed={nrt.failed} ensure={nrt.ensureSummaries} field={f} selection={selection} />
                </Section>
              )}
              {latest && (
                <Section title="External cyclone context" badge={cycloneStatus ? (cycloneStatus.state === "ACTIVE_NORTH_INDIAN_CYCLONE" ? "ACTIVE" : "NONE") : undefined}>
                  <p className="ws-note" data-testid="inspector-cyclone">
                    {cycloneStatus?.message ?? "Checking the connected external source…"} Track and thermal analysis are in the
                    Cyclone context tab below.
                  </p>
                </Section>
              )}
              {selection.row >= 0 && (
                <Section title="Coastal context" defaultOpen={!!activeArea} testid="inspector-coastal">
                  <CoastalContextView
                    lat={f.lat[selection.row]}
                    lon={f.lon[selection.col]}
                    label={activeArea ? `Thermal monitoring area ${activeArea.rank} · ${activeArea.tier}` : "Selected location"}
                  />
                </Section>
              )}
              <Section title="Validation context" testid="inspector-validation">
                <ValidationContextView depth={f.depths[depth]} lat={coords[0]} lon={coords[1]} compact />
              </Section>
              {hazardReady && (
                <Section title="Basin summary">
                  <BasinSummary field={f} basins={basins} bathymetry={bathymetry} />
                </Section>
              )}
              <Section title="Surface inputs" testid="inspector-inputs">
                {selection.row < 0 ? (
                  <p className="ws-note">No inputs outside the domain.</p>
                ) : (
                  <div className="inputs-grid">
                    {Object.entries(data.surface).map(([name, input]) => (
                      <div key={name} className="input-tile">
                        <span>{name.replaceAll("_", " ").toUpperCase()}</span>
                        <strong data-testid={`surface-${name}`}>
                          {format(input.values[selection.row * f.lon.length + selection.col])} <small>{input.units}</small>
                        </strong>
                        <p>{input.product}</p>
                      </div>
                    ))}
                  </div>
                )}
              </Section>
              {latest && q && <Section title="Qualification & sources">{qualificationDetails}</Section>}
            </Inspector>
          </div>
          <Tray tabs={trayTabs} active={tray} onActive={setTray} />
        </>
      )}
    </div>
  );
}
