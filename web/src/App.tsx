import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
  Waves,
  Map,
  ShieldCheck,
  Download,
  Settings2,
  Menu,
  Search,
  RefreshCw,
  MapPin,
  ChevronRight,
  ArrowRight,
  Flame,
  Sigma,
  Crosshair,
  Layers3,
} from "lucide-react";
import { Button } from "./components/ui/button";
import { MapView } from "./components/MapView";
import { DiagnosticMap } from "./components/DiagnosticMap";
import { Profile } from "./components/Profile";
import { getJson, loadReplay } from "./field/api";
import {
  asLayer,
  format,
  isDiagnostic,
  resolve,
  type DiagnosticKind,
  type MapLayer,
  type Palette,
  type Selection,
} from "./field/contract";
import { type ScaleMode } from "./field/colors";
import { type ReplayData } from "./field/replayAdapter";
import { download, mapPng, profileCsv } from "./field/exports";
import OceanState from "./components/workspace/OceanState";
import { IntegrityDrawer } from "./components/workspace/IntegrityDrawer";
import type { Qualification } from "./components/LatestQualified";
import type { HazardLayer, MapPanelOptions } from "./components/hazard/types";
const DepthRenderer = lazy(() => import("./components/DepthRenderer"));
const Validation = lazy(() => import("./components/Validation"));
const HazardTab = lazy(() => import("./components/Hazard"));
const ModelScience = lazy(() => import("./components/workspace/ModelScience"));
const LatestInputsTab = lazy(() => import("./components/LatestInputs"));

/** Four workspaces. Everything else is a tool, one click away. */
const workspaces = [
  { id: "ocean", name: "Ocean State", icon: Map },
  { id: "events", name: "Events & Disasters", icon: Flame },
  { id: "science", name: "Model Science", icon: Sigma },
  { id: "scenario", name: "Scenario", icon: Crosshair },
];
const tools = [
  { id: "inputs", name: "Latest Inputs", icon: RefreshCw },
  { id: "validation", name: "Provenance & Validation", icon: ShieldCheck },
  { id: "exports", name: "Exports", icon: Download },
  { id: "settings", name: "Settings", icon: Settings2 },
];
/** Hash routes from earlier builds keep working: they open the equivalent workspace. */
const OCEAN_ALIASES = ["", "ocean", "replay", "depth"];

function readSettings() {
  try {
    return JSON.parse(localStorage.getItem("oceanembed-settings") || "{}");
  } catch {
    return {};
  }
}
const initialSettings = readSettings();
const defaultDate = /^\d{4}-\d{2}-\d{2}$/.test(initialSettings.date || "")
  ? initialSettings.date
  : "2021-06-15";

export default function App() {
  const initialHash = location.hash.slice(1);
  const [route, setRoute] = useState(initialHash || "ocean"),
    [menu, setMenu] = useState(false);
  const [date, setDate] = useState(defaultDate),
    [data, setData] = useState<ReplayData | null>(null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  const [record, setRecord] = useState<string[]>([]),
    [depth, setDepth] = useState(7),
    [display, setDisplay] = useState<HazardLayer>("temperature");
  // The latest workspace's name and every qualified claim come from the frozen
  // qualification artifact on the server, never from this file.
  const [qual, setQual] = useState<Qualification | null>(null),
    [qualLoaded, setQualLoaded] = useState(false);
  const [oceanSource, setOceanSource] = useState<"historical" | "latest">("historical");
  const [threeD, setThreeD] = useState(initialHash === "depth");
  const [lat, setLat] = useState(String(initialSettings.lat ?? 15.25)),
    [lon, setLon] = useState(String(initialSettings.lon ?? 87.75));
  const [coords, setCoords] = useState<[number, number]>([
    Number(initialSettings.lat ?? 15.25),
    Number(initialSettings.lon ?? 87.75),
  ]);
  const [palette, setPalette] = useState<Palette>(
    initialSettings.palette === "cividis"
      ? "cividis"
      : initialSettings.palette === "viridis"
        ? "viridis"
        : "thermal",
  );
  // Default "field": one colour scale over the whole reconstruction, so depths
  // and dates are comparable. "slice" restores the per-depth auto-stretch.
  const [scaleMode, setScaleMode] = useState<ScaleMode>(
    initialSettings.scaleMode === "slice" ? "slice" : "field",
  );
  const [query, setQuery] = useState("");
  const [exaggeration, setExaggeration] = useState(700),
    [clip, setClip] = useState<[number, number]>([0, 14]);
  // Exploded stack by default: at true spacing eleven of the fifteen levels fall
  // inside the top fifth of the axis and are unreadable. The renderer states in
  // the view that the spacing is then not to scale.
  const [explode, setExplode] = useState(1),
    [layerCount, setLayerCount] = useState(5);
  const [enable3d, setEnable3d] = useState(
    () => window.innerWidth >= 760 && !initialSettings.prefer2d,
  );
  const [exportError, setExportError] = useState(""),
    [exportBusy, setExportBusy] = useState(false),
    [saved, setSaved] = useState("");
  const pending = useRef<AbortController | null>(null);
  const request = useCallback(async (day: string, force = false) => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setDate(day);
    setLoading(true);
    setError("");
    setData(null);
    try {
      const result = await loadReplay(day, force, controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);
  // A real replayed day that a page already loaded (event playback) is shown
  // directly; the page is not blanked between frames.
  const showHistorical = useCallback((next: ReplayData) => {
    pending.current?.abort();
    setDate(next.field.effectiveDate);
    setData(next);
    setError("");
    setLoading(false);
  }, []);
  useEffect(() => {
    void request(defaultDate, true);
    getJson<{ date_range: string[] }>("/api/health")
      .then((r) => setRecord(r?.date_range ?? []))
      .catch(() => {});
    getJson<Qualification>("/api/latest/qualification")
      .then((q) => setQual(q && typeof q === "object" && "qualified" in q ? q : null))
      .catch(() => setQual(null))
      .finally(() => setQualLoaded(true));
    return () => pending.current?.abort();
  }, [request]);
  useEffect(() => {
    const change = () => {
      const h = location.hash.slice(1);
      setRoute(h || "ocean");
      if (h === "replay" || h === "depth") setOceanSource("historical");
      if (h === "depth") setThreeD(true);
      if (h === "replay") setThreeD(false);
      setMenu(false);
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  // #latest opens the latest source only where the latest state is qualified;
  // otherwise it is the Latest Inputs tool and Ocean State stays historical.
  useEffect(() => {
    if (route === "latest" && qualLoaded && qual?.qualified) setOceanSource("latest");
  }, [route, qualLoaded, qual]);
  const view = OCEAN_ALIASES.includes(route)
    ? "ocean"
    : route === "latest"
      ? !qualLoaded
        ? "pending"
        : qual?.qualified
          ? "ocean"
          : "inputs"
      : route === "hazard"
        ? "events"
        : route;
  const select = (a: number, b: number) => {
    setCoords([a, b]);
    setLat(String(a));
    setLon(String(b));
  };
  const navigate = (id: string) => {
    location.hash = id;
    setMenu(false);
  };
  const shiftDate = (days: number) => {
    const value = new Date(`${date}T12:00:00Z`);
    value.setUTCDate(value.getUTCDate() + days);
    void request(value.toISOString().slice(0, 10));
  };
  const changeDepth = (k: number) => {
    setDepth(k);
    if (k < clip[0] || k > clip[1])
      setClip([Math.min(k, clip[0]), Math.max(k, clip[1])]);
  };
  async function exportAction(action: () => Promise<void> | void) {
    setExportError("");
    setExportBusy(true);
    try {
      await action();
    } catch (e) {
      setExportError((e as Error).message);
    } finally {
      setExportBusy(false);
    }
  }
  // Quick-jump: accepts "lat, lon" inside the domain, or an ISO date. It only
  // moves the existing selection/date state - it performs no inference and has
  // no separate data path.
  const jumpTo = useCallback(
    (raw: string) => {
      const text = raw.trim();
      if (!text) return;
      const isoDate = text.match(/^(\d{4}-\d{2}-\d{2})$/);
      if (isoDate) {
        void request(isoDate[1]);
        setQuery("");
        return;
      }
      const pair = text.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
      if (!pair) return;
      const nextLat = Number(pair[1]);
      const nextLon = Number(pair[2]);
      if (!Number.isFinite(nextLat) || !Number.isFinite(nextLon)) return;
      setLat(String(nextLat));
      setLon(String(nextLon));
      setCoords([nextLat, nextLon]);
      setQuery("");
    },
    [request],
  );

  const renderProfile = (src: ReplayData, sel: Selection) => (
    <Profile field={src.field} selection={sel} depth={depth} />
  );
  // One map, one 3D renderer and one profile serve every source and workspace.
  // A workspace chooses the layer and may add an overlay; none draws a second map.
  const renderMapPanel = (src: ReplayData, sel: Selection, o: MapPanelOptions) => {
    const fv = src.field;
    const support = o.layer === "support";
    const diagnostic: DiagnosticKind | null =
      !support && isDiagnostic(o.layer as MapLayer) ? (o.layer as DiagnosticKind) : null;
    const drawLayer = support ? "temperature" : asLayer(o.layer as MapLayer);
    return (
      <section className="panel map-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">
              {o.eyebrow ?? (o.threeD ? "15-DEPTH RECONSTRUCTED THERMAL FIELD" : "SURFACE OBSERVATIONS → SUBSURFACE STRUCTURE")}
            </span>
            <h2>{o.title ?? (o.threeD ? "3D Depth View" : "North Indian Ocean")}</h2>
          </div>
          {o.headerExtra}
          <div className="view-switch">
            <Button size="sm" variant={!o.threeD ? "default" : "ghost"} onClick={() => o.setThreeD(false)}>
              2D map
            </Button>
            <Button size="sm" variant={o.threeD ? "default" : "ghost"} onClick={() => o.setThreeD(true)}>
              3D depth
            </Button>
          </div>
        </div>
        {o.threeD && (
          <>
            <div className="depth-controls">
              <label>
                Vertical exaggeration · {exaggeration}×
                <input
                  aria-label="Vertical exaggeration"
                  type="range"
                  min="100"
                  max="2200"
                  step="100"
                  value={exaggeration}
                  onChange={(e) => setExaggeration(+e.target.value)}
                />
              </label>
              <label>
                Clip from
                <select
                  aria-label="Clip from"
                  value={clip[0]}
                  onChange={(e) => {
                    const k = +e.target.value;
                    setClip([k, Math.max(k, clip[1])]);
                    if (depth < k) setDepth(k);
                  }}
                >
                  {fv.depths.map((d, k) => (
                    <option key={d} value={k}>
                      {d} m
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Clip to
                <select
                  aria-label="Clip to"
                  value={clip[1]}
                  onChange={(e) => {
                    const k = +e.target.value;
                    setClip([Math.min(k, clip[0]), k]);
                    if (depth > k) setDepth(k);
                  }}
                >
                  {fv.depths.map((d, k) => (
                    <option key={d} value={k}>
                      {d} m
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Layers
                <select aria-label="Layers" value={layerCount} onChange={(e) => setLayerCount(+e.target.value)}>
                  {[3, 4, 5, 6, 8].map((n) => (
                    <option key={n} value={n}>
                      {n} sheets
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Separation · {explode === 0 ? "true depth" : `${Math.round(explode * 100)}%`}
                <input
                  type="range"
                  aria-label="Layer separation"
                  min={0}
                  max={1}
                  step={0.05}
                  value={explode}
                  onChange={(e) => setExplode(+e.target.value)}
                />
              </label>
            </div>
            {!enable3d && (
              <div className="notice">
                Lighter 2D view is active for this device.{" "}
                <Button size="sm" variant="outline" onClick={() => setEnable3d(true)}>
                  Enable 3D
                </Button>
              </div>
            )}
          </>
        )}
        {o.threeD && (diagnostic || support) && (
          <p className="notice" data-testid="diagnostic-3d-note">
            {support
              ? "Thermal support is read from TCHP, a depth-integrated surface, so it has no 3D depth stack."
              : "D26 and TCHP are depth-integrated surfaces, so they have no 3D depth stack."}{" "}
            The volume below shows reconstructed temperature; switch to the map view to see the selected{" "}
            {support ? "category map" : "diagnostic"}.
          </p>
        )}
        <div
          className="map-stage"
          data-testid="map-stage"
          data-field-date={fv.effectiveDate}
          data-view={o.threeD && enable3d ? "3d" : "2d"}
        >
          {o.threeD && enable3d ? (
            <Suspense fallback={<p className="empty">Loading local 3D renderer…</p>}>
              <DepthRenderer
                field={fv}
                layer={drawLayer}
                depth={depth}
                palette={palette}
                selection={sel}
                onSelect={select}
                exaggeration={exaggeration}
                clip={clip}
                scaleMode={scaleMode}
                explode={explode}
                layerCount={layerCount}
              />
            </Suspense>
          ) : support && o.supportMap ? (
            o.supportMap
          ) : diagnostic ? (
            <DiagnosticMap field={fv} kind={diagnostic} selection={sel} onSelect={select} />
          ) : (
            <MapView
              field={fv}
              layer={drawLayer}
              depth={depth}
              palette={palette}
              selection={sel}
              onSelect={select}
              scaleMode={scaleMode}
            />
          )}
          {!(o.threeD && enable3d) && o.overlay}
        </div>
        <div className="scrubber">
          <label htmlFor="depth-scrub">
            DEPTH SCRUB <strong>{fv.depths[depth]} m</strong>
          </label>
          <input
            id="depth-scrub"
            aria-label="Depth scrub"
            title="Snaps to the 15 mandated levels. No inference or continuous-depth interpolation."
            type="range"
            min="0"
            max="14"
            step="1"
            value={depth}
            onChange={(e) => changeDepth(+e.target.value)}
          />
          <div className="depth-ticks">
            {fv.depths.map((d, k) => (
              <button
                key={d}
                className={k === depth ? "selected" : ""}
                onClick={() => changeDepth(k)}
                aria-label={`Select ${d} metres`}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
        <form
          className="coordinate-form"
          onSubmit={(e) => {
            e.preventDefault();
            select(Number(lat), Number(lon));
          }}
        >
          <MapPin size={17} />
          <label>
            Latitude °N
            <input aria-label="Latitude" type="number" step="any" value={lat} onChange={(e) => setLat(e.target.value)} required />
          </label>
          <label>
            Longitude °E
            <input aria-label="Longitude" type="number" step="any" value={lon} onChange={(e) => setLon(e.target.value)} required />
          </label>
          <Button type="submit" variant="outline" size="sm">
            Inspect column <ArrowRight size={14} />
          </Button>
        </form>
      </section>
    );
  };

  const f = data?.field;
  const selection = f ? resolve(f, ...coords) : null;
  const nameOf = (id: string) =>
    (id === "inputs" && qual && !qual.qualified && qual.tab_name) ||
    [...workspaces, ...tools].find((r) => r.id === id)?.name ||
    "Ocean State";
  const toolTitle: Record<string, string> = {
    inputs: "Near-real-time input telemetry.",
    validation: "Evidence behind the reconstruction.",
    exports: "Take the science with you.",
    settings: "Your local workspace.",
  };

  return (
    <div className={`app ${menu ? "menu-open" : ""}`}>
      <a
        className="skip-link"
        href="#main-content"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main-content")?.focus();
          document.getElementById("main-content")?.scrollIntoView();
        }}
      >
        Skip to content
      </a>
      <aside className="sidebar">
        <a href="#ocean" className="brand">
          <div className="brand-mark">
            <Waves size={28} />
          </div>
          <span>
            Ocean<span className="accent">Embed</span>
            <small>SATELLITE EMBEDDING ENGINE</small>
          </span>
        </a>
        <div className="nav-section-label">WORKSPACES</div>
        <nav aria-label="Main navigation">
          {workspaces.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              className={view === item.id ? "active" : ""}
              aria-current={view === item.id ? "page" : undefined}
            >
              <item.icon size={18} />
              <span>{item.name}</span>
              {view === item.id && <span className="nav-dot" />}
            </a>
          ))}
        </nav>
        <div className="nav-section-label tools">TOOLS</div>
        <nav aria-label="Tools" className="tools">
          {tools.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              className={view === item.id ? "active" : ""}
              aria-current={view === item.id ? "page" : undefined}
            >
              <item.icon size={15} />
              <span>{item.name}</span>
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-mark">
            <span className="status-dot" />
            FROZEN L2 · 2024 ARGO PROTECTED
          </div>
          <small>
            OceanEmbed · SIH26066
            <br />
            INCOIS / Ministry of Earth Sciences
          </small>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <Button
            className="menu-toggle"
            variant="ghost"
            size="icon"
            aria-label="Toggle navigation"
            aria-expanded={menu}
            onClick={() => setMenu(!menu)}
          >
            <Menu />
          </Button>
          <div className="breadcrumb">
            WORKSPACE <ChevronRight size={13} />
            <span>{nameOf(view)}</span>
          </div>
          <form
            className="topbar-search"
            role="search"
            onSubmit={(e) => {
              e.preventDefault();
              jumpTo(query);
            }}
          >
            <Search size={14} aria-hidden />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search coordinates (15.25, 87.75) or a date (2021-06-15)…"
              aria-label="Jump to a coordinate or a historical date"
            />
          </form>
          <IntegrityDrawer />
        </header>
        <main id="main-content" tabIndex={-1}>
          {toolTitle[view] && (
            <div className="page-title">
              <div>
                <span className="eyebrow">NORTH INDIAN OCEAN / TOOLS</span>
                <h1>{toolTitle[view]}</h1>
                <p className="muted">One frozen scientific core. Transparent inputs, outputs and provenance.</p>
              </div>
            </div>
          )}
          {view === "pending" ? (
            <p className="empty">Reading the latest-state qualification…</p>
          ) : view === "ocean" ? (
            <OceanState
              source={oceanSource}
              setSource={(s) => {
                setOceanSource(s);
                if (route !== "ocean") navigate("ocean");
              }}
              historical={data}
              historicalDate={date}
              historicalLoading={loading}
              historicalError={error}
              record={record}
              request={(day, force) => void request(day, force)}
              shiftDate={shiftDate}
              qualification={qual}
              coords={coords}
              onSelect={select}
              depth={depth}
              onDepth={changeDepth}
              display={display}
              setDisplay={setDisplay}
              threeD={threeD}
              setThreeD={setThreeD}
              renderMapPanel={renderMapPanel}
              renderProfile={renderProfile}
              onOpenEvents={() => navigate("events")}
            />
          ) : view === "events" || view === "scenario" ? (
            <Suspense fallback={<p className="empty">Loading {view === "events" ? "event intelligence" : "scenario analysis"}…</p>}>
              <HazardTab
                workspace={view}
                historical={data}
                historicalDate={date}
                historicalLoading={loading}
                historicalError={error}
                showHistorical={showHistorical}
                retryHistorical={() => void request(date, true)}
                requestHistorical={(day) => void request(day)}
                qualification={qual}
                coords={coords}
                onSelect={select}
                depth={depth}
                onDepth={changeDepth}
                renderMapPanel={renderMapPanel}
                renderProfile={renderProfile}
              />
            </Suspense>
          ) : view === "science" ? (
            <Suspense fallback={<p className="empty">Loading model science…</p>}>
              <ModelScience
                historical={data}
                historicalDate={date}
                qualification={qual}
                coords={coords}
                onSelect={select}
                depth={depth}
                renderMapPanel={renderMapPanel}
              />
            </Suspense>
          ) : view === "inputs" ? (
            // Deliberately independent of the replay data: Latest Inputs needs no
            // reconstruction, and a failure on either side never takes the other down.
            <Suspense fallback={<p className="empty">Loading latest inputs…</p>}>
              <LatestInputsTab />
            </Suspense>
          ) : view === "validation" ? (
            <Suspense fallback={<p className="empty">Loading validation page…</p>}>
              <Validation />
            </Suspense>
          ) : view === "settings" ? (
            <section className="panel settings">
              <h2>Display &amp; launch preferences</h2>
              <p className="muted">Saved in this browser. Scientific units remain °C and metres.</p>
              <label>
                Temperature colormap
                <select value={palette} onChange={(e) => setPalette(e.target.value as Palette)}>
                  <option value="thermal">Thermal · ocean-temperature default</option>
                  <option value="viridis">Viridis</option>
                  <option value="cividis">Cividis · color-vision accessible</option>
                </select>
              </label>
              <p className="small muted">Anomaly always uses a blue–white–red scale centered at zero.</p>
              <label>
                Color scale range
                <select value={scaleMode} onChange={(e) => setScaleMode(e.target.value as ScaleMode)}>
                  <option value="field">Whole reconstruction · all 15 depths (default)</option>
                  <option value="slice">Auto-stretch to the displayed depth only</option>
                </select>
              </label>
              <p className="small muted">
                Both ranges are computed from the values returned for the requested date — neither is a hardcoded temperature
                range. The default spans all 15 depths so a 0 m map and a 500 m map mean the same colours. Auto-stretching to one
                depth maximises contrast inside that layer but makes depths and dates <strong>not comparable</strong>: at 1000 m
                it renders ~6 °C water in the same colours as ~30 °C surface water.
              </p>
              <label>
                <input type="checkbox" checked={!enable3d} onChange={(e) => setEnable3d(!e.target.checked)} /> Prefer the
                lighter 2D view
              </label>
              <Button
                onClick={() => {
                  try {
                    localStorage.setItem(
                      "oceanembed-settings",
                      JSON.stringify({ palette, scaleMode, prefer2d: !enable3d, date, lat: coords[0], lon: coords[1] }),
                    );
                    setSaved(
                      `Saved launch date ${date} and requested location ${coords[0].toFixed(2)}°N, ${coords[1].toFixed(2)}°E.`,
                    );
                  } catch {
                    setSaved("Browser storage is unavailable. Settings apply to this session.");
                  }
                }}
              >
                Save current date, location &amp; display settings
              </Button>
              <p role="status">{saved}</p>
            </section>
          ) : view === "exports" ? (
            f && selection ? (
              <section className="panel">
                <span className="eyebrow">ACTUAL OUTPUTS / {f.effectiveDate}</span>
                <h2>Export the current reconstruction</h2>
                <p>Full precision values, explicit missing values, frozen model provenance and product-specific credits.</p>
                <div className="export-grid">
                  <article>
                    <Download />
                    <h3>Selected profile</h3>
                    <p>All 15 L2, L0 and anomaly values for the selected grid cell.</p>
                    <Button
                      disabled={selection.row < 0 || exportBusy}
                      onClick={() =>
                        void exportAction(() =>
                          download(
                            new Blob([profileCsv(f, selection)], { type: "text/csv;charset=utf-8" }),
                            `OceanEmbed-${f.effectiveDate}-profile.csv`,
                          ),
                        )
                      }
                    >
                      Download CSV
                    </Button>
                  </article>
                  <article>
                    <Map />
                    <h3>Current depth map</h3>
                    <p>
                      {f.depths[depth]} m · {asLayer((display === "support" ? "temperature" : display) as MapLayer)} · actual
                      color scale and attribution.
                    </p>
                    <Button
                      disabled={exportBusy}
                      onClick={() =>
                        void exportAction(() =>
                          mapPng({
                            field: f,
                            layer: asLayer((display === "support" ? "temperature" : display) as MapLayer),
                            depth,
                            palette,
                            selection,
                            scaleMode,
                          }),
                        )
                      }
                    >
                      Download PNG
                    </Button>
                  </article>
                  <article>
                    <Layers3 />
                    <h3>Complete field</h3>
                    <p>101 × 241 × 15, all three fields, support masks and provenance.</p>
                    <Button
                      disabled={exportBusy}
                      onClick={() =>
                        void exportAction(async () => {
                          const response = await fetch(`/api/export/field.nc?date=${f.effectiveDate}`);
                          if (!response.ok) throw Error("NetCDF export failed. Check local replay server.");
                          download(await response.blob(), `OceanEmbed-${f.effectiveDate}.nc`);
                        })
                      }
                    >
                      Download NetCDF
                    </Button>
                  </article>
                </div>
                {exportBusy && <p role="status">Preparing export…</p>}
                {exportError && <p role="alert">{exportError}</p>}
                <p className="muted small">
                  Selected request: {format(coords[0], 4)}°N, {format(coords[1], 4)}°E. Change location in Ocean State.
                </p>
                <p className="notice">
                  {f.provenance.nominal_zero_m_note}
                  <br />
                  {f.provenance.deep_skill_note}
                </p>
              </section>
            ) : (
              <p className="empty">{error || "Reconstructing the selected date…"}</p>
            )
          ) : (
            <section className="panel">
              <p>Page not found.</p>
              <Button onClick={() => navigate("ocean")}>Open Ocean State</Button>
            </section>
          )}
          <footer>
            OceanEmbed <span>Frozen scientific core · Historical and latest qualified states · 2024 Argo protected</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
