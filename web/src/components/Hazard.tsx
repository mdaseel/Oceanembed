import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getJson, loadReplay } from "../field/api";
import { useBathymetry, type Bathymetry } from "../field/bathymetry";
import {
  diagnosticAt,
  format,
  offset,
  resolve,
  type FieldView,
  type Hazard,
  type Selection,
} from "../field/contract";
import type { ReplayData } from "../field/replayAdapter";
import {
  eventDates,
  formatDay,
  monitoringAreas,
  phaseFor,
  phaseShort,
  phaseTitle,
  type Basins,
  type EventInfo,
  type MonitoringArea,
  type SeriesRow,
} from "../field/hazardIntelligence";
import { pixelToLatLon } from "./MapView";
import type { Qualification } from "./LatestQualified";
import { AlongTrackSection } from "./hazard/AlongTrackSection";
import { BasinSummary } from "./hazard/BasinSummary";
import { EventBrief } from "./hazard/Briefs";
import { ColdWake } from "./hazard/ColdWake";
import { ColumnInsight } from "./hazard/ColumnInsight";
import { CompareCyclones } from "./hazard/CompareCyclones";
import { EventLibrary } from "./hazard/EventLibrary";
import { InterpretationCard } from "./hazard/InterpretationCard";
import { MapOverlay } from "./hazard/MapOverlay";
import { MonitoringAreas } from "./hazard/MonitoringAreas";
import { OceanChangePanel } from "./hazard/OceanChange";
import { PlaybackBar, SPEEDS, type Frame } from "./hazard/PlaybackBar";
import { ScenarioPanel, type PathPoint } from "./hazard/ScenarioPanel";
import { ThermalSupportMap } from "./hazard/ThermalSupportMap";
import { TrackThermalPanel } from "./hazard/TrackThermal";
import type { EventLibraryPayload, SectionPayload, TrackAnalysis } from "./hazard/api";
import type { HazardLayer, MapPanelOptions, RenderMapPanel, RenderProfile } from "./hazard/types";
import { useNrtStates } from "./hazard/useNrtStates";
import { CoastalContextView, ValidationContextView } from "./workspace/ContextSections";
import { Inspector, Section, SubTabs, Tray } from "./workspace/Layout";
import { RiStudy } from "./workspace/RiStudy";
import { StressTest } from "./workspace/StressTest";
import "./hazard/hazard.css";
import "./hazard/expansion.css";
import "./workspace/workspace.css";

/**
 * EVENTS & DISASTERS and SCENARIO.
 *
 * Historical events replay pre-registered cyclone windows through real per-date
 * replay_field reconstructions; Scenario samples a user-drawn path. Both use the
 * App's single map, 3D renderer and profile. Nothing here categorises,
 * thresholds, interpolates, persists, forecasts or produces a probability, and no
 * external track enters inference.
 */

type EventTab = "overview" | "evolution" | "trackanalysis" | "change" | "research";
type OverviewTab = "summary" | "brief" | "compare";
type TrackTab = "track" | "section" | "stress";
const EVENT_KEY = "oceanembed-hazard-event";
const DEFAULT_EVENT = "mocha-2023";
const seriesMemo = new Map<string, { rows: SeriesRow[]; corridorDeg: number | null }>();

const LAYERS: { id: HazardLayer; label: string; title: string }[] = [
  { id: "support", label: "Thermal support", title: "Ocean thermal support" },
  { id: "tchp", label: "TCHP", title: "Upper-ocean heat reservoir (TCHP)" },
  { id: "anomaly", label: "Anomaly", title: "Temperature anomaly" },
  { id: "temperature", label: "Temperature", title: "Reconstructed temperature" },
  { id: "d26", label: "D26", title: "26 °C isotherm depth" },
];
const EVENT_TABS: { id: EventTab; label: string }[] = [
  { id: "overview", label: "OVERVIEW" },
  { id: "evolution", label: "EVENT EVOLUTION" },
  { id: "trackanalysis", label: "TRACK ANALYSIS" },
  { id: "change", label: "OCEAN CHANGE" },
  { id: "research", label: "RESEARCH" },
];

export interface HazardProps {
  workspace: "events" | "scenario";
  historical: ReplayData | null;
  historicalDate: string;
  historicalLoading: boolean;
  historicalError: string;
  showHistorical: (data: ReplayData) => void;
  retryHistorical: () => void;
  requestHistorical: (date: string) => void;
  qualification: Qualification | null;
  coords: [number, number];
  onSelect: (lat: number, lon: number) => void;
  depth: number;
  onDepth: (k: number) => void;
  renderMapPanel: RenderMapPanel;
  renderProfile: RenderProfile;
}

const stored = (key: string, fallback: string) => {
  try {
    return sessionStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
};
const store = (key: string, value: string) => {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    /* per-tab convenience only */
  }
};

/** Steps through an event window one REAL replayed day at a time. */
function useEventPlayback(
  event: EventInfo | null,
  historical: ReplayData | null,
  show: (data: ReplayData) => void,
) {
  const dates = useMemo(
    () => (event ? eventDates(event.window_start, event.window_end) : []),
    [event],
  );
  const [playing, setPlaying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [speed, setSpeed] = useState(SPEEDS[1].ms);
  const token = useRef(0);
  const inflight = useRef(new Map<string, Promise<ReplayData>>());

  const fetchFrame = useCallback((date: string) => {
    let pending = inflight.current.get(date);
    if (!pending) {
      pending = loadReplay(date).finally(() => inflight.current.delete(date));
      inflight.current.set(date, pending);
    }
    return pending;
  }, []);

  const goTo = useCallback(
    async (date: string) => {
      const mine = ++token.current;
      setBusy(true);
      setError("");
      try {
        const data = await fetchFrame(date);
        if (mine !== token.current) return;
        if (data.field.effectiveDate !== date) throw Error("Replay returned a different date");
        show(data);
      } catch (e) {
        if (mine === token.current) {
          setError((e as Error).message);
          setPlaying(false);
        }
      } finally {
        if (mine === token.current) setBusy(false);
      }
    },
    [fetchFrame, show],
  );

  const current = historical?.field.effectiveDate ?? null;
  useEffect(() => {
    if (!playing || busy || !current || !dates.length) return;
    const i = dates.indexOf(current);
    if (i === dates.length - 1) {
      setPlaying(false);
      return;
    }
    const next = dates[i < 0 ? 0 : i + 1];
    fetchFrame(next).catch(() => {});
    const timer = setTimeout(() => void goTo(next), i < 0 ? 0 : speed);
    return () => clearTimeout(timer);
  }, [playing, busy, current, dates, speed, fetchFrame, goTo]);

  return {
    dates,
    playing,
    busy,
    error,
    speed,
    setSpeed,
    play: () => {
      if (!dates.length) return;
      if (current === dates[dates.length - 1]) void goTo(dates[0]);
      setPlaying(true);
    },
    pause: () => setPlaying(false),
    step: (direction: -1 | 1) => {
      if (!dates.length) return;
      setPlaying(false);
      const i = current ? dates.indexOf(current) : -1;
      const target =
        i < 0 ? dates[0] : dates[Math.max(0, Math.min(dates.length - 1, i + direction))];
      if (target !== current) void goTo(target);
    },
    restart: () => {
      if (dates.length) void goTo(dates[0]);
    },
    select: (date: string) => {
      setPlaying(false);
      void goTo(date);
    },
  };
}

function trackContext(event: EventInfo, date: string): string {
  const points = event.track?.points ?? [];
  if (!points.length) return "Best track unavailable — run scripts/poc/build_event_library.py";
  const travelled = points.filter((p) => p.time.slice(0, 10) <= date);
  if (!travelled.length)
    return `No best-track position on or before ${date}; the first IBTrACS fix is ${points[0].time} UTC.`;
  const last = travelled[travelled.length - 1];
  const ended = last === points[points.length - 1] && date > last.time.slice(0, 10);
  return `${ended ? "Last observed best-track position" : "Observed best-track position"} (IBTrACS): ${last.time} UTC, ${last.lat.toFixed(1)}°N ${last.lon.toFixed(1)}°E${
    last.imd_wind_kt != null ? ` · ${last.imd_wind_kt} kt (IMD)` : ""
  }.`;
}

function ToggleRow<T extends string>({
  options,
  active,
  onActive,
  label,
}: {
  options: { id: T; label: string }[];
  active: T;
  onActive: (id: T) => void;
  label: string;
}) {
  return (
    <div className="ws-toggle-row">
      <div className="segmented" role="group" aria-label={label}>
        {options.map((o) => (
          <button
            key={o.id}
            type="button"
            className={active === o.id ? "active" : ""}
            aria-pressed={active === o.id}
            data-testid={`tab-${o.id}`}
            onClick={() => onActive(o.id)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function HazardDashboard(props: HazardProps) {
  const {
    workspace,
    historical,
    qualification,
    coords,
    onSelect,
    depth,
    onDepth,
    renderMapPanel,
    renderProfile,
  } = props;
  const events = workspace === "events";
  const [library, setLibrary] = useState<EventLibraryPayload | null>(null);
  const [eventId, setEventId] = useState(() => stored(EVENT_KEY, DEFAULT_EVENT));
  const [event, setEvent] = useState<EventInfo | null>(null);
  const [pendingJump, setPendingJump] = useState(false);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [tab, setTab] = useState<EventTab>("overview");
  const [overviewTab, setOverviewTab] = useState<OverviewTab>("summary");
  const [trackTab, setTrackTab] = useState<TrackTab>("track");
  const [basins, setBasins] = useState<Basins | null>(null);
  const [layer, setLayer] = useState<HazardLayer>("support");
  const [threeD, setThreeD] = useState(false);
  const [series, setSeries] = useState(() => seriesMemo.get(eventId) ?? null);
  const [seriesBusy, setSeriesBusy] = useState(false);
  const [seriesError, setSeriesError] = useState("");
  const [trackAnalysis, setTrackAnalysis] = useState<TrackAnalysis | null>(null);
  const [section, setSection] = useState<SectionPayload | null>(null);
  const [sectionMode, setSectionMode] = useState<"temperature" | "anomaly">("temperature");
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [scenarioPoints, setScenarioPoints] = useState<PathPoint[]>([]);
  const [drawing, setDrawing] = useState(false);
  const [scenarioField, setScenarioField] = useState<"historical" | "latest">("historical");
  const [scenarioTray, setScenarioTray] = useState("path");
  const { data: bathymetry } = useBathymetry();

  useEffect(() => {
    let active = true;
    getJson<EventLibraryPayload>("/api/events")
      .then((l) => active && setLibrary(l?.events ? l : null))
      .catch(() => {});
    getJson<{ basins: Basins }>("/api/basins")
      .then((r) => active && setBasins(r?.basins ?? null))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!events) return;
    let active = true;
    getJson<EventInfo>(`/api/events/${encodeURIComponent(eventId)}`)
      .then((e) => active && setEvent(e?.segments ? e : null))
      .catch(() => {
        // an unknown stored id falls back to the pre-registered default event
        if (active && eventId !== DEFAULT_EVENT) setEventId(DEFAULT_EVENT);
      });
    setSeries(seriesMemo.get(eventId) ?? null);
    setSeriesError("");
    setTrackAnalysis(null);
    setSection(null);
    return () => {
      active = false;
    };
  }, [eventId, events]);

  const hist = useEventPlayback(events ? event : null, historical, props.showHistorical);
  const nrt = useNrtStates(!events && scenarioField === "latest" && !!qualification?.qualified);

  useEffect(() => {
    if (pendingJump && event?.event_id === eventId) {
      setPendingJump(false);
      hist.select(event.peak);
    }
  }, [pendingJump, event, eventId, hist]);

  const chooseEvent = (id: string) => {
    hist.pause();
    store(EVENT_KEY, id);
    setEventId(id);
    setPendingJump(true);
  };

  const eventIdRef = useRef(eventId);
  eventIdRef.current = eventId;
  const runSeries = useCallback(() => {
    const id = eventId;
    setSeriesBusy(true);
    setSeriesError("");
    getJson<{ series: SeriesRow[]; corridor_deg?: number }>(`/api/events/${encodeURIComponent(id)}/series`)
      .then((r) => {
        const value = { rows: r.series, corridorDeg: r.corridor_deg ?? null };
        seriesMemo.set(id, value);
        if (id === eventIdRef.current) setSeries(value);
      })
      .catch((e) => setSeriesError((e as Error).message))
      .finally(() => setSeriesBusy(false));
  }, [eventId]);
  const seriesStarted = useRef(new Set<string>());
  useEffect(() => {
    if (events && !seriesMemo.has(eventId) && !seriesStarted.current.has(eventId)) {
      seriesStarted.current.add(eventId);
      runSeries();
    }
  }, [events, eventId, runSeries]);

  // ------------------------------------------------------------ source
  const source = !events && scenarioField === "latest" ? nrt.data : historical;
  const f: FieldView | null = source?.field ?? null;
  const selection = f ? resolve(f, coords[0], coords[1]) : null;
  const withheld: string[] = f?.diagnostics?.withheld ?? [];
  const shownLayer: HazardLayer =
    (layer === "d26" || layer === "tchp") && withheld.includes(layer) ? "support" : layer;
  const monitoring = useMemo(() => (f?.hazard?.available ? monitoringAreas(f, basins) : null), [f, basins]);
  const activeArea =
    selection && monitoring
      ? (monitoring.areas.find((a) => a.row === selection.row && a.col === selection.col) ?? null)
      : null;
  const activeKey = activeArea ? `${activeArea.row},${activeArea.col}` : null;
  const chooseArea = (a: MonitoringArea) => onSelect(a.lat, a.lon);

  // ------------------------------------------------------------ historical event
  const date = historical?.field.effectiveDate ?? props.historicalDate;
  const inWindow = events && !!event && date >= event.window_start && date <= event.window_end;
  const phase = event && inWindow ? phaseFor(date, event.segments) : null;
  const eventFrames: Frame[] = useMemo(
    () =>
      event
        ? hist.dates.map((d) => ({
            date: d,
            available: true,
            phase: phaseFor(d, event.segments)?.label,
            marker: d === event.peak ? "PEAK" : d === event.landfall ? "LANDFALL" : undefined,
          }))
        : [],
    [event, hist.dates],
  );

  const wantsTrack = tab === "trackanalysis" && trackTab === "track";
  const wantsSection = tab === "trackanalysis" && trackTab === "section";
  useEffect(() => {
    if (!events || !event?.event_id || !inWindow || (!wantsTrack && !wantsSection)) return;
    let live = true;
    const id = encodeURIComponent(event.event_id);
    const timer = setTimeout(() => {
      setAnalysisBusy(true);
      setAnalysisError("");
      const request = wantsTrack
        ? getJson<TrackAnalysis>(`/api/events/${id}/track-analysis?date=${date}`).then((a) => live && setTrackAnalysis(a))
        : getJson<SectionPayload>(`/api/events/${id}/section?date=${date}&mode=${sectionMode}`).then(
            (s) => live && setSection(s),
          );
      request
        .catch((e) => live && setAnalysisError((e as Error).message))
        .finally(() => live && setAnalysisBusy(false));
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [events, event?.event_id, inWindow, wantsTrack, wantsSection, date, sectionMode]);

  // ------------------------------------------------------------ map
  const trackNote = !events
    ? "User-drawn scenario path — not an official forecast."
    : !event
      ? ""
      : !inWindow
        ? `Track not drawn: ${date} is outside the ${event.name} window.`
        : event.track
          ? `Observed best track: ${event.track.dataset} · ${event.track.agency}. Static context — never a model input or output.`
          : "Best track unavailable — run scripts/poc/build_event_library.py";

  const mapOptions: MapPanelOptions | null =
    f && selection
      ? {
          layer: shownLayer,
          threeD,
          setThreeD,
          eyebrow: threeD
            ? "EXPLODED DEPTH LAYERS · SHARED 3D RENDERER"
            : `OCEAN THERMAL FIELD · ${events ? "HISTORICAL EVENT REPLAY" : "SCENARIO ANALYSIS"}`,
          title: threeD
            ? `Exploded depth layers · ${f.effectiveDate}`
            : `${LAYERS.find((l) => l.id === shownLayer)?.title} · ${f.effectiveDate}`,
          headerExtra: (
            <div className="hazard-map-tools">
              <div className="segmented" role="group" aria-label="Hazard map layer">
                {LAYERS.filter((l) => !withheld.includes(l.id)).map((l) => (
                  <button
                    key={l.id}
                    type="button"
                    className={shownLayer === l.id ? "active" : ""}
                    aria-pressed={shownLayer === l.id}
                    data-testid={`layer-${l.id}`}
                    onClick={() => setLayer(l.id)}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
              {(threeD || shownLayer === "temperature" || shownLayer === "anomaly") && (
                <label className="inline-select">
                  DEPTH
                  <select aria-label="Hazard map depth" value={depth} onChange={(e) => onDepth(Number(e.target.value))}>
                    {f.depths.map((d, k) => (
                      <option key={d} value={k}>
                        {d} m
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          ),
          overlay: (
            <MapOverlay
              rows={f.lat.length}
              cols={f.lon.length}
              areas={monitoring?.areas ?? []}
              activeKey={activeKey}
              onArea={chooseArea}
              track={inWindow ? (event?.track ?? null) : null}
              trackDate={inWindow ? date : null}
              externalTrack={null}
              scenarioPath={!events ? scenarioPoints : []}
              drawing={!events && drawing}
              onDraw={(lat, lon) => setScenarioPoints((p) => [...p, { lat, lon }])}
              toLatLon={(x, y) => pixelToLatLon(x, y, f)}
            />
          ),
          supportMap: <ThermalSupportMap field={f} selection={selection} onSelect={onSelect} trackNote={trackNote} />,
        }
      : null;

  const interpretation =
    f && selection && f.hazard?.available && monitoring ? (
      <Section title="Thermal interpretation" defaultOpen testid="inspector-interpretation">
        <InterpretationCard
          field={f}
          selection={selection}
          mode="historical"
          basins={basins}
          topArea={monitoring.areas[0] ?? null}
          onArea={chooseArea}
        />
      </Section>
    ) : f ? (
      <Section title="Thermal interpretation" defaultOpen>
        <HazardUnavailable hazard={f.hazard} />
      </Section>
    ) : null;

  const coastal =
    f && selection && selection.row >= 0 ? (
      <Section title="Coastal context" defaultOpen={!!activeArea} testid="inspector-coastal">
        <CoastalContextView
          lat={f.lat[selection.row]}
          lon={f.lon[selection.col]}
          label={activeArea ? `Thermal monitoring area ${activeArea.rank} · ${activeArea.tier}` : "Selected location"}
        />
      </Section>
    ) : null;

  const waterColumn =
    f && selection && source ? (
      <Section title="Water column" testid="inspector-water-column">
        <div className="profile-stage" data-testid="profile-stage" data-field-date={f.effectiveDate}>
          {renderProfile(source, selection)}
        </div>
        <ColumnInsight field={f} selection={selection} depth={depth} onDepth={onDepth} bathymetry={bathymetry} basins={basins} onSelect={onSelect} />
      </Section>
    ) : null;

  const header = (
    <header className="ws-head">
      <div>
        <span className="eyebrow">
          {events ? "EVENTS & DISASTERS / HISTORICAL CYCLONE OCEAN RESPONSE" : "SCENARIO ANALYSIS — NOT A FORECAST"}
        </span>
        <h1>{events ? "Ocean Thermal Hazard Intelligence" : "Scenario analysis"}</h1>
        <p className="muted">
          {events
            ? "Subsurface thermal conditions before, during and after real cyclones. Satellites see the surface; OceanEmbed reconstructs what is below."
            : "Thermal conditions along a path you draw, on a historical or latest qualified field. Hypothetical geometry, never a forecast."}
        </p>
      </div>
      <div className="ws-head-side">
        <span
          className={`mode-badge ${events ? "badge-historical" : "badge-scenario"}`}
          data-testid="intel-mode-badge"
        >
          {events ? "HISTORICAL EVENT REPLAY" : "USER-DRAWN SCENARIO"}
        </span>
      </div>
    </header>
  );

  const body =
    f && selection && source && mapOptions ? (
      <>
        <div className="ws-grid">
          <div className="ws-main">
            {renderMapPanel(source, selection, mapOptions)}
            <div className="ws-map-context">
              {events && event?.track && (
                <p className="muted small" data-testid="track-attribution">
                  {event.track.citation} Peak {event.track.peak_imd_wind_kt} kt · {event.track.min_imd_pressure_hpa} hPa (
                  {event.track.agency}). Static context — never a model input or output.
                  {inWindow ? "" : " Drawn only on dates inside the event window."}
                </p>
              )}
              {events && event && inWindow && (
                <p className="small" data-testid="track-context">
                  {trackContext(event, date)}
                </p>
              )}
              {!events && (
                <p className="small muted" data-testid="scenario-map-note">
                  {drawing
                    ? "Drawing: click the map to add path points (the thermal-support map is shown while drawing)."
                    : "Path points are user-drawn geometry, not an official forecast."}
                </p>
              )}
            </div>
          </div>
          <Inspector
            eyebrow={events ? "INSPECTOR · EVENT DAY" : "INSPECTOR · SCENARIO"}
            title={selection.row >= 0 ? `${f.lat[selection.row].toFixed(2)}°N, ${f.lon[selection.col].toFixed(2)}°E` : "Outside the domain"}
          >
            {!events && (
              <Section title="Scenario path" defaultOpen testid="inspector-scenario">
                <p className="ws-note">
                  {scenarioPoints.length} point{scenarioPoints.length === 1 ? "" : "s"} on the{" "}
                  {scenarioField === "latest" ? "latest qualified" : `historical ${f.effectiveDate}`} field. Draw on the map or
                  type positions in the Path analysis tab, then run the analysis.
                </p>
                <p className="ws-note">
                  The path is hypothetical geometry. It is never named as a cyclone and never enters a reconstruction.
                </p>
              </Section>
            )}
            {interpretation}
            {f.hazard?.available && monitoring && (
              <Section title="Thermal monitoring areas" badge={`${monitoring.areas.length}`} defaultOpen={events} testid="inspector-areas">
                <MonitoringAreas
                  result={monitoring}
                  activeKey={activeKey}
                  onArea={chooseArea}
                  date={f.effectiveDate}
                  mode={events ? "historical" : "scenario"}
                  rmse={f.hazard.error.rmse}
                />
              </Section>
            )}
            {coastal}
            {waterColumn}
            {f.hazard?.available && (
              <Section title="Basin summary">
                <BasinSummary field={f} basins={basins} bathymetry={bathymetry} />
              </Section>
            )}
            <Section title="Validation context">
              <ValidationContextView depth={f.depths[depth]} lat={coords[0]} lon={coords[1]} compact />
            </Section>
          </Inspector>
        </div>

        {events && event && (
          <section className="panel analysis-tabs" data-testid="analysis-tabs" data-tab={tab}>
            <SubTabs tabs={EVENT_TABS} active={tab} onActive={setTab} label="Event analysis" />
            <div className="ws-tray-body">
              {tab === "overview" && (
                <div className="ws">
                  <ToggleRow
                    options={[
                      { id: "summary", label: "Event summary" },
                      { id: "brief", label: "Response brief" },
                      { id: "compare", label: "Compare cyclones" },
                    ]}
                    active={overviewTab}
                    onActive={setOverviewTab}
                    label="Overview"
                  />
                  {overviewTab === "summary" && <EventSummary event={event} onEvolution={() => setTab("evolution")} />}
                  {overviewTab === "brief" && event.event_id && <EventBrief eventId={event.event_id} />}
                  {overviewTab === "compare" && <CompareCyclones ids={compareIds} />}
                </div>
              )}
              {tab === "evolution" && (
                <ColdWake
                  event={event}
                  series={series?.rows ?? null}
                  corridorDeg={series?.corridorDeg ?? null}
                  busy={seriesBusy}
                  error={seriesError}
                  onRun={runSeries}
                  currentDate={inWindow ? date : null}
                />
              )}
              {tab === "trackanalysis" && (
                <div className="ws">
                  <ToggleRow
                    options={[
                      { id: "track", label: "Track × thermal state" },
                      { id: "section", label: "Along-track section" },
                      { id: "stress", label: "Stress test on latest ocean" },
                    ]}
                    active={trackTab}
                    onActive={setTrackTab}
                    label="Track analysis"
                  />
                  {(trackTab === "track" || trackTab === "section") && !inWindow && (
                    <p className="notice">Choose a date inside the {event.name} window to sample the observed track.</p>
                  )}
                  {analysisError && trackTab !== "stress" && <p className="notice">{analysisError}</p>}
                  {trackTab === "track" &&
                    inWindow &&
                    (trackAnalysis && trackAnalysis.date === date ? (
                      <TrackThermalPanel
                        analysis={trackAnalysis}
                        pathKind="observed best track"
                        labels={{
                          path: trackAnalysis.labels?.track ?? "Track: external historical observation",
                          thermal: trackAnalysis.labels?.thermal_state ?? "Thermal state: OceanEmbed",
                        }}
                        onSelectPoint={onSelect}
                        testid="event-track"
                      />
                    ) : (
                      <p className="muted" role="status">
                        Sampling the observed track on the {date} reconstruction…
                      </p>
                    ))}
                  {trackTab === "section" && inWindow && (
                    <AlongTrackSection
                      section={section && section.date === date && section.mode === sectionMode ? section : null}
                      loading={analysisBusy}
                      onMode={setSectionMode}
                      labels={{
                        path: "Track: external historical observation — IBTrACS best track",
                        thermal: "Subsurface field: OceanEmbed frozen-L2 reconstruction",
                      }}
                      testid="event-section"
                    />
                  )}
                  {trackTab === "stress" && event.event_id && <StressTest initialEvent={event.event_id} />}
                </div>
              )}
              {tab === "change" && event.event_id && <OceanChangePanel eventId={event.event_id} field={f} onSelect={onSelect} />}
              {tab === "research" && <RiStudy />}
            </div>
          </section>
        )}

        {!events && (
          <Tray
            tabs={[
              {
                id: "path",
                label: "Path analysis",
                keepMounted: true,
                render: () => (
                  <ScenarioPanel
                    points={scenarioPoints}
                    onAdd={(p) => setScenarioPoints((pts) => [...pts, p])}
                    onUndo={() => setScenarioPoints((pts) => pts.slice(0, -1))}
                    onClear={() => setScenarioPoints([])}
                    drawing={drawing}
                    onDrawing={(on) => {
                      setDrawing(on);
                      if (on) {
                        setThreeD(false);
                        setLayer("support");
                      }
                    }}
                    field={scenarioField}
                    onField={setScenarioField}
                    historicalDate={props.historicalDate}
                    latestDate={nrt.data?.field.effectiveDate ?? (qualification?.qualified ? "on request" : null)}
                    onSelectPoint={onSelect}
                  />
                ),
              },
              { id: "stress", label: "Historical-geometry stress test", render: () => <StressTest /> },
            ]}
            active={scenarioTray}
            onActive={setScenarioTray}
          />
        )}

        <details className="panel scope-evidence" data-testid="scope-evidence">
          <summary className="eyebrow">SCOPE, EVIDENCE AND PROVENANCE · WHAT OCEANEMBED DOES NOT PREDICT</summary>
          <ScientificStatus field={f} selection={selection} scenario={!events} event={event} bathymetry={bathymetry} />
        </details>
      </>
    ) : !events && scenarioField === "latest" ? (
      <p className="notice">
        {nrt.busy || !nrt.initialised
          ? "Retrieving the latest qualified reconstruction…"
          : "Latest OceanEmbed reconstruction unavailable. Historical Event Intelligence remains available."}
      </p>
    ) : props.historicalError ? (
      <section className="panel error-state" role="alert">
        <h2>Historical reconstruction unavailable</h2>
        <p>{props.historicalError}</p>
        <button className="btn" onClick={props.retryHistorical}>
          Retry local replay
        </button>
      </section>
    ) : (
      <div className="loading-state panel" role="status">
        <h2>Reconstructing {props.historicalDate}</h2>
        <p>Reading local surface inputs and the frozen L2 field. All 15 depths arrive together.</p>
        <div className="loading-line" />
      </div>
    );

  return (
    <div className="intel ws" data-mode={events ? "historical" : "scenario"} data-testid="hazard-dashboard">
      {header}
      {events && (
        <>
          {library && (
            <EventLibrary
              library={library}
              selected={eventId}
              onSelect={chooseEvent}
              compareIds={compareIds}
              onToggleCompare={(id) =>
                setCompareIds((ids) =>
                  ids.includes(id) ? ids.filter((x) => x !== id) : ids.length >= 4 ? ids : [...ids, id],
                )
              }
            />
          )}
          <section className="panel event-bar" data-testid="event-bar" data-event={eventId}>
            <div className="event-bar-head">
              <div>
                <span className="eyebrow">
                  {event ? `${event.name.toUpperCase()} · ${event.basin.toUpperCase()}` : "PRE-REGISTERED EVENT"}
                </span>
                <h2>Historical ocean response replay</h2>
                {event?.split && (
                  <span className={`split-pill split-${event.split}`} data-testid="event-split-pill">
                    {event.in_sample ? "IN-SAMPLE · training period" : `${event.split} period`}
                  </span>
                )}
                <details className="ws-notes">
                  <summary>About this replay</summary>
                  <p className="ws-note">{event?.claim_note}</p>
                  {event?.split_note && (
                    <p className={`ws-note ${event.in_sample ? "in-sample-note" : ""}`} data-testid="event-split-note">
                      {event.split_note}
                    </p>
                  )}
                  <p className="ws-note">
                    {event?.independence_note} Playback advances only after the next day's reconstruction has loaded; no
                    frame is interpolated.
                  </p>
                </details>
              </div>
              <div
                className={`phase-banner phase-${phase ? phaseShort(phase.label).toLowerCase() : "outside"}`}
                data-testid="phase-banner"
                data-phase={phase?.label ?? "OUTSIDE"}
                data-date={date}
                aria-live="polite"
              >
                <span className="phase-short">{phase ? phaseShort(phase.label) : "OUTSIDE EVENT WINDOW"}</span>
                <strong>{phase ? phaseTitle(phase.label) : "Not part of the event replay"}</strong>
                <span className="phase-date">{formatDay(date)}</span>
                {phase && (
                  <span className="phase-segment">
                    {event?.event_id === DEFAULT_EVENT ? "Pre-registered segment" : "Rule-derived segment"} · {phase.start} →{" "}
                    {phase.end}
                  </span>
                )}
              </div>
            </div>
            {event && !inWindow && (
              <p className="notice" data-testid="outside-event-window">
                <span>
                  Showing <strong>{date}</strong>, which is outside the {event.name} window ({event.window_start} to{" "}
                  {event.window_end}). The observed track is not drawn over an ocean state it never crossed.{" "}
                  <button className="btn" onClick={() => hist.select(event.window_start)}>
                    Start at pre-event ({event.window_start})
                  </button>{" "}
                  <button className="btn" onClick={() => hist.select(event.peak)}>
                    Show peak intensity ({event.peak})
                  </button>
                </span>
              </p>
            )}
            {event && (
              <PlaybackBar
                id="event"
                frames={eventFrames}
                current={inWindow ? date : null}
                playing={hist.playing}
                busy={hist.busy || props.historicalLoading}
                speed={hist.speed}
                onSpeed={hist.setSpeed}
                onPlay={hist.play}
                onPause={hist.pause}
                onStep={hist.step}
                onRestart={hist.restart}
                onSelect={hist.select}
                playLabel="PLAY EVENT EVOLUTION"
                stepNoun="day"
              />
            )}
            {hist.error && (
              <p className="panel error-state" role="alert">
                {hist.error}
              </p>
            )}
          </section>
        </>
      )}
      {!events && (
        <section className="panel controls ws-controls">
          <label className="inline-select">
            HISTORICAL FIELD DATE
            <input
              type="date"
              aria-label="Scenario historical date"
              value={props.historicalDate}
              onChange={(e) => {
                if (e.target.value) props.requestHistorical(e.target.value);
              }}
            />
          </label>
          <span className="scenario-badge" data-testid="scenario-header-badge">
            USER-DRAWN SCENARIO · NOT AN OFFICIAL FORECAST
          </span>
        </section>
      )}
      {body}
    </div>
  );
}

function EventSummary({ event, onEvolution }: { event: EventInfo; onEvolution: () => void }) {
  const meta = (event as EventInfo & {
    external_metadata?: { peak_imd_wind_kt: number | null; min_imd_pressure_hpa: number | null; first_landfall_fix_time?: string };
  }).external_metadata;
  return (
    <div className="fig-row" data-testid="event-summary">
      <div className="fig-card">
        <h3>{event.name}</h3>
        <dl className="ws-kv">
          <dt>Basin</dt>
          <dd>{event.basin}</dd>
          <dt>Replay window</dt>
          <dd>
            {event.window_start} → {event.window_end}
          </dd>
          <dt>Peak intensity day</dt>
          <dd>{event.peak}</dd>
          <dt>Landfall day</dt>
          <dd>{event.landfall}</dd>
          <dt>Data split</dt>
          <dd>{event.in_sample ? "In-sample (training period)" : (event.split ?? "—")}</dd>
        </dl>
      </div>
      <div className="fig-card">
        <h3>External intensity record (IBTrACS)</h3>
        <dl className="ws-kv">
          <dt>Peak IMD wind</dt>
          <dd>{meta?.peak_imd_wind_kt != null ? `${meta.peak_imd_wind_kt} kt` : "—"}</dd>
          <dt>Minimum IMD pressure</dt>
          <dd>{meta?.min_imd_pressure_hpa != null ? `${meta.min_imd_pressure_hpa} hPa` : "—"}</dd>
          <dt>Segments</dt>
          <dd>{event.segments.map((s) => s.label).join(" · ")}</dd>
        </dl>
        <p className="ws-note">
          External observations, shown beside the ocean reconstruction and never used by it.
        </p>
      </div>
      <div className="fig-card">
        <h3>Ocean response</h3>
        <p className="ws-note">
          Corridor TCHP, subsurface temperature and D26 before, during and after the storm are measured day by day in Event
          Evolution; change maps and the cold-wake footprint are in Ocean Change.
        </p>
        <button type="button" className="btn" onClick={onEvolution}>
          Open event evolution
        </button>
      </div>
    </div>
  );
}

function HazardUnavailable({ hazard }: { hazard: Hazard | undefined }) {
  // Two different causes that must not be confused: an older backend serving
  // no hazard block, or a current one that could not load its frozen thresholds.
  if (!hazard)
    return (
      <p className="notice" data-testid="hazard-stale-backend">
        This reconstruction arrived without a hazard block, which means the running server predates Phase 7D. The thresholds
        on disk are not the problem. Restart the local server so it picks up the current backend:{" "}
        <code>python scripts/poc/serve.py</code>.
      </p>
    );
  return (
    <p className="notice" data-testid="hazard-no-thresholds">
      The backend served a hazard block but could not load the frozen thresholds, so no category can be assigned. Nothing is
      shown rather than a guessed level. Run <code>scripts/diagnostics/build_hazard_thresholds.py</code>.
    </p>
  );
}

function ScientificStatus({
  field: f,
  selection,
  scenario,
  event,
  bathymetry,
}: {
  field: FieldView | null;
  selection: Selection | null;
  scenario: boolean;
  event: EventInfo | null;
  bathymetry: Bathymetry | null;
}) {
  if (!f || !selection) return null;
  const hazard = f.hazard;
  const t = hazard?.thresholds;
  const tchp = diagnosticAt(f, "tchp", selection);
  const d26 = diagnosticAt(f, "d26", selection);
  const k100 = f.depths.indexOf(100);
  const anomaly100 =
    selection.row >= 0 && k100 >= 0 ? f.anomaly[offset(f, selection.row, selection.col, k100)] : NaN;
  const d26Withheld = !!f.diagnostics?.withheld?.includes("d26");
  const waterDepth =
    bathymetry && selection.row >= 0 ? bathymetry.depths[selection.row * f.lon.length + selection.col] : undefined;
  return (
    <section className="panel intel-status" data-testid="scientific-status">
      <h2>Scope, evidence and provenance</h2>
      {hazard && (
        <p className="notice" data-testid="hazard-non-prediction">
          {hazard.nonPrediction}
        </p>
      )}
      <ul className="scope-list">
        <li>
          OceanEmbed provides subsurface thermal intelligence — reconstructed temperature, {d26Withheld ? "TCHP" : "D26, TCHP"}{" "}
          and the frozen thermal-support category — from surface satellite inputs through the frozen L2 model.
        </li>
        <li>
          It does not forecast cyclone genesis, track, landfall, category or intensity, and it produces no storm-surge, wave or
          tsunami product. No numeric cyclone probability is produced anywhere on this page. External systems remain
          responsible for cyclone detection, tracks and warnings.
        </li>
        {scenario ? (
          <li>Scenario paths are user-drawn geometry and are never presented as a forecast.</li>
        ) : (
          event && <li>{event.claim_note}</li>
        )}
        <li data-testid="official-track-scope">
          Official cyclone-track overlay: Not connected in this build for IMD / RSMC New Delhi, which publishes PDF bulletins.
          External geometry, when shown in Ocean State, comes from GDACS with its own source label. Historical tracks are static
          IBTrACS best tracks, shown as context only.
        </li>
      </ul>
      {hazard && t && (
        <details data-testid="why-this-level">
          <summary>Why this level? Frozen boundaries, reconstruction error and model</summary>
          <table>
            <tbody>
              <tr>
                <td>Categorising quantity</td>
                <td>TCHP = {tchp && Number.isFinite(tchp.value) ? `${format(tchp.value, 1)} kJ/cm²` : "unavailable"}</td>
              </tr>
              <tr>
                <td>Frozen boundaries</td>
                <td>
                  MODERATE ≥ {t.p50.toFixed(1)} · ELEVATED ≥ {t.p75.toFixed(1)} · HIGH ≥ {t.p90.toFixed(1)} kJ/cm²
                </td>
              </tr>
              <tr>
                <td>Boundary source</td>
                <td>
                  percentiles of OceanEmbed's own TCHP over {t.reference_period}, {t.n_dates} dates,{" "}
                  {t.n_samples.toLocaleString("en-US")} samples
                </td>
              </tr>
              <tr>
                <td>Supporting D26</td>
                <td>
                  {d26Withheld
                    ? "withheld in the latest mode"
                    : d26 && Number.isFinite(d26.value)
                      ? `${format(d26.value, 1)} m${
                          waterDepth !== undefined && Number.isFinite(waterDepth)
                            ? ` within ${waterDepth.toFixed(0)} m of local water`
                            : ""
                        }`
                      : "—"}
                </td>
              </tr>
              <tr>
                <td>Subsurface anomaly at 100 m</td>
                <td>{Number.isFinite(anomaly100) ? `${format(anomaly100, 2)} °C` : "—"}</td>
              </tr>
              <tr>
                <td>Reconstruction error</td>
                <td>
                  TCHP MAE {hazard.error.mae} · RMSE {hazard.error.rmse} · bias +{hazard.error.bias} kJ/cm² ({hazard.error.source})
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
        </details>
      )}
    </section>
  );
}
