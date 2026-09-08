import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  Waves,
  Map,
  Layers3,
  ShieldCheck,
  Download,
  Settings2,
  Menu,
  Search,
  Thermometer,
  LineChart,
  Sigma,
  Grid3x3,
  ArrowRight,
  RefreshCw,
  MapPin,
  ChevronLeft,
  ChevronRight,
  Info,
} from "lucide-react";
import { Button } from "./components/ui/button";
import { MapView } from "./components/MapView";
import { Profile } from "./components/Profile";
import { getJson, loadReplay } from "./field/api";
import {
  format,
  offset,
  resolve,
  type Layer,
  type Palette,
} from "./field/contract";
import { type ScaleMode } from "./field/colors";
import { type ReplayData } from "./field/replayAdapter";
import { download, mapPng, profileCsv } from "./field/exports";
const DepthRenderer = lazy(() => import("./components/DepthRenderer"));
const Validation = lazy(() => import("./components/Validation"));
const MultiDate = lazy(() => import("./components/MultiDate"));
const routes = [
  { id: "replay", name: "Historical Replay", icon: Map },
  { id: "depth", name: "3D Depth View", icon: Layers3 },
  { id: "validation", name: "Provenance & Validation", icon: ShieldCheck },
  { id: "exports", name: "Exports", icon: Download },
  { id: "settings", name: "Settings", icon: Settings2 },
];
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
  const [route, setRoute] = useState(location.hash.slice(1) || "replay"),
    [menu, setMenu] = useState(false);
  const [date, setDate] = useState(defaultDate),
    [data, setData] = useState<ReplayData | null>(null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  const [record, setRecord] = useState<string[]>([]),
    [depth, setDepth] = useState(7),
    [layer, setLayer] = useState<Layer>("temperature");
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
  // and dates are comparable. "slice" restores the old per-depth auto-stretch.
  const [scaleMode, setScaleMode] = useState<ScaleMode>(
    initialSettings.scaleMode === "slice" ? "slice" : "field",
  );
  const [query, setQuery] = useState("");
  const [exaggeration, setExaggeration] = useState(700),
    [clip, setClip] = useState<[number, number]>([0, 14]);
  // Exploded stack by default on the depth page: at true spacing eleven of the
  // fifteen levels fall inside the top fifth of the axis and are unreadable.
  // The renderer states in the view that the spacing is then not to scale, and
  // 0 restores the true-depth layout.
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
  useEffect(() => {
    void request(defaultDate, true);
    getJson<{ date_range: string[] }>("/api/health")
      .then((r) => setRecord(r.date_range))
      .catch(() => {});
    return () => pending.current?.abort();
  }, [request]);
  useEffect(() => {
    const change = () => {
      setRoute(location.hash.slice(1) || "replay");
      setMenu(false);
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  const f = data?.field,
    selection = f ? resolve(f, ...coords) : null;
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
  const current =
    f && selection && selection.row >= 0
      ? offset(f, selection.row, selection.col, depth)
      : -1;
  const changeDepth = (k: number) => {
    setDepth(k);
    if (k < clip[0] || k > clip[1])
      setClip([Math.min(k, clip[0]), Math.max(k, clip[1])]);
  };
  const scientificView = route === "replay" || route === "depth";
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
  }  // Quick-jump: accepts "lat, lon" inside the domain, or an ISO date. It only
  // moves the existing selection/date state - it performs no inference and has
  // no separate data path.
  const jumpTo = useCallback(
    (raw: string) => {
      const text = raw.trim();
      if (!text) return;
      const isoDate = text.match(/^(\d{4}-\d{2}-\d{2})$/);
      if (isoDate) {
        setDate(isoDate[1]);
        setQuery("");
        return;
      }
      const pair = text.match(
        /^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/,
      );
      if (!pair) return;
      const nextLat = Number(pair[1]);
      const nextLon = Number(pair[2]);
      if (!Number.isFinite(nextLat) || !Number.isFinite(nextLon)) return;
      setLat(String(nextLat));
      setLon(String(nextLon));
      setCoords([nextLat, nextLon]);
      setQuery("");
    },
    [setDate, setLat, setLon, setCoords],
  );

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
        <a href="#replay" className="brand">
          <div className="brand-mark">
            <Waves size={28} />
          </div>
          <span>
            Ocean<span className="accent">Embed</span>
            <small>SATELLITE EMBEDDING ENGINE</small>
          </span>
        </a>
        <div className="nav-section-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {routes.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              className={route === item.id ? "active" : ""}
              aria-current={route === item.id ? "page" : undefined}
            >
              <item.icon size={18} />
              <span>{item.name}</span>
              {route === item.id && <span className="nav-dot" />}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-mark">
            <span className="status-dot" />
            LOCAL HISTORICAL MODE
          </div>
          <p>
            Surface observations.
            <br />
            Depth-resolved understanding.
          </p>
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
            <span>
              {routes.find((r) => r.id === route)?.name || "Historical Replay"}
            </span>
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
          <div className="local-mark">
            <span className="status-dot" />
            OFFLINE READY <span className="topbar-divider">/</span> FROZEN L2
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <div className="page-title">
            <div>
              <span className="eyebrow">
                NORTH INDIAN OCEAN / HISTORICAL REPLAY
              </span>
              <h1>
                {route === "depth"
                  ? "Explore the ocean in depth."
                  : route === "validation"
                    ? "Evidence behind the reconstruction."
                    : route === "exports"
                      ? "Take the science with you."
                      : route === "settings"
                        ? "Your local workspace."
                        : "The surface tells a deeper story."}
              </h1>
              <p className="muted">
                {route === "replay" || route === "depth"
                  ? "Reconstructed Subsurface Temperature · 5–30°N, 45–105°E · 0.25° grid"
                  : "One frozen scientific core. Transparent inputs, outputs and provenance."}
              </p>
            </div>
            <span className="mode-badge">HISTORICAL REPLAY</span>
          </div>
          {(scientificView || route === "exports") && (
            <section className="controls panel">
              <div className="date-control">
                <label htmlFor="historical-date">HISTORICAL DATE</label>
                <div className="action-row">
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Previous day"
                    disabled={loading || !date || date === record[0]}
                    onClick={() => shiftDate(-1)}
                  >
                    <ChevronLeft size={16} />
                  </Button>
                  <input
                    id="historical-date"
                    type="date"
                    min={record[0]}
                    max={record[1]}
                    value={date}
                    onChange={(e) => {
                      if (e.target.value) void request(e.target.value);
                    }}
                  />
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Next day"
                    disabled={loading || !date || date === record[1]}
                    onClick={() => shiftDate(1)}
                  >
                    <ChevronRight size={16} />
                  </Button>
                </div>
              </div>
              <label>
                DEPTH
                <select
                  aria-label="Depth"
                  value={depth}
                  onChange={(e) => changeDepth(+e.target.value)}
                  disabled={!f}
                >
                  {(f?.depths || []).map((d, k) => (
                    <option value={k} key={d}>
                      {d} m{d === 0 ? " · nominal" : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label className="layer-control">
                DISPLAY LAYER
                <select
                  aria-label="Display layer"
                  value={layer}
                  onChange={(e) => setLayer(e.target.value as Layer)}
                >
                  <option value="temperature">Reconstructed temperature</option>
                  <option value="anomaly">Anomaly from climatology</option>
                </select>
              </label>
              <Button
                variant="outline"
                disabled={loading || !date}
                onClick={() => void request(date, true)}
              >
                <RefreshCw size={15} className={loading ? "spin" : ""} />
                Run frozen L2
              </Button>
            </section>
          )}
          {route === "validation" ? (
            <Suspense
              fallback={<p className="empty">Loading validation page…</p>}
            >
              <Validation />
            </Suspense>
          ) : route === "settings" ? (
            <section className="panel settings">
              <h2>Display &amp; launch preferences</h2>
              <p className="muted">
                Saved in this browser. Scientific units remain °C and metres.
              </p>
              <label>
                Temperature colormap
                <select
                  value={palette}
                  onChange={(e) => setPalette(e.target.value as Palette)}
                >
                  <option value="thermal">
                    Thermal · ocean-temperature default
                  </option>
                  <option value="viridis">Viridis</option>
                  <option value="cividis">
                    Cividis · color-vision accessible
                  </option>
                </select>
              </label>
              <p className="small muted">
                Anomaly always uses a blue–white–red scale centered at zero.
              </p>
              <label>
                Color scale range
                <select
                  value={scaleMode}
                  onChange={(e) => setScaleMode(e.target.value as ScaleMode)}
                >
                  <option value="field">
                    Whole reconstruction · all 15 depths (default)
                  </option>
                  <option value="slice">
                    Auto-stretch to the displayed depth only
                  </option>
                </select>
              </label>
              <p className="small muted">
                Both ranges are computed from the values returned for the
                requested date — neither is a hardcoded temperature range. The
                default spans all 15 depths so a 0 m map and a 500 m map mean the
                same colours. Auto-stretching to one depth maximises contrast
                inside that layer but makes depths and dates{" "}
                <strong>not comparable</strong>: at 1000 m it renders ~6 °C water
                in the same colours as ~30 °C surface water.
              </p>
              <label>
                <input
                  type="checkbox"
                  checked={!enable3d}
                  onChange={(e) => setEnable3d(!e.target.checked)}
                />{" "}
                Prefer the lighter 2D view
              </label>
              <Button
                onClick={() => {
                  try {
                    localStorage.setItem(
                      "oceanembed-settings",
                      JSON.stringify({
                        palette,
                        scaleMode,
                        prefer2d: !enable3d,
                        date,
                        lat: coords[0],
                        lon: coords[1],
                      }),
                    );
                    setSaved(
                      `Saved launch date ${date} and requested location ${coords[0].toFixed(2)}°N, ${coords[1].toFixed(2)}°E.`,
                    );
                  } catch {
                    setSaved(
                      "Browser storage is unavailable. Settings apply to this session.",
                    );
                  }
                }}
              >
                Save current date, location &amp; display settings
              </Button>
              <p role="status">{saved}</p>
              <p className="muted small">
                Local server: same origin · historical source paths and frozen
                model configuration are managed by the repository.
              </p>
            </section>
          ) : (
            <>
              {loading && (
                <div className="loading-state panel" role="status">
                  <Waves className="spin" />
                  <h2>Reconstructing {date}</h2>
                  <p>
                    Reading local surface inputs and the frozen L2 field. All 15
                    depths arrive together.
                  </p>
                  <div className="loading-line" />
                </div>
              )}
              {error && (
                <section className="panel error-state" role="alert">
                  <h2>Historical reconstruction unavailable</h2>
                  <p>{error}</p>
                  <Button onClick={() => void request(date, true)}>
                    Retry local replay
                  </Button>
                </section>
              )}
              {!loading && !error && f && data && selection && (
                <>
                  {scientificView ? (
                    <>
                      <div className="stats-grid">
                        <Stat
                          label={`L2 TEMPERATURE / ${f.depths[depth]} M`}
                          icon={Thermometer}
                          value={
                            current >= 0
                              ? format(f.temperature[current])
                              : "Unavailable"
                          }
                          unit="°C"
                        />
                        <Stat
                          label="L0 CLIMATOLOGY"
                          icon={LineChart}
                          value={
                            current >= 0
                              ? format(f.climatology[current])
                              : "Unavailable"
                          }
                          unit="°C"
                        />
                        <Stat
                          label="ANOMALY FROM CLIMATOLOGY"
                          icon={Sigma}
                          value={
                            current >= 0
                              ? format(f.anomaly[current])
                              : "Unavailable"
                          }
                          unit="°C"
                        />
                        <Stat
                          label="DATE-SPECIFIC INPUT SUPPORT"
                          icon={Grid3x3}
                          value={f.provenance.n_supported_cells.toLocaleString()}
                          unit="cells"
                        />
                      </div>
                      <div className="explorer-grid">
                        <div className="map-column">
                          <section className="panel map-panel">
                            <div className="panel-heading">
                              <div>
                                <span className="eyebrow">
                                  {route === "depth"
                                    ? "15-DEPTH RECONSTRUCTED THERMAL FIELD"
                                    : "SURFACE OBSERVATIONS → SUBSURFACE STRUCTURE"}
                                </span>
                                <h2>
                                  {route === "depth"
                                    ? "3D Depth View"
                                    : "North Indian Ocean"}
                                </h2>
                              </div>
                              <div className="view-switch">
                                <Button
                                  size="sm"
                                  variant={
                                    route === "replay" ? "default" : "ghost"
                                  }
                                  onClick={() => navigate("replay")}
                                >
                                  2D map
                                </Button>
                                <Button
                                  size="sm"
                                  variant={
                                    route === "depth" ? "default" : "ghost"
                                  }
                                  onClick={() => navigate("depth")}
                                >
                                  3D depth
                                </Button>
                              </div>
                            </div>
                            {route === "depth" && (
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
                                      onChange={(e) =>
                                        setExaggeration(+e.target.value)
                                      }
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
                                      {f.depths.map((d, k) => (
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
                                      {f.depths.map((d, k) => (
                                        <option key={d} value={k}>
                                          {d} m
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  <label>
                                    Layers
                                    <select
                                      aria-label="Layers"
                                      value={layerCount}
                                      onChange={(e) =>
                                        setLayerCount(+e.target.value)
                                      }
                                    >
                                      {[3, 4, 5, 6, 8].map((n) => (
                                        <option key={n} value={n}>
                                          {n} sheets
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  <label>
                                    Separation ·{" "}
                                    {explode === 0
                                      ? "true depth"
                                      : `${Math.round(explode * 100)}%`}
                                    <input
                                      type="range"
                                      aria-label="Layer separation"
                                      min={0}
                                      max={1}
                                      step={0.05}
                                      value={explode}
                                      onChange={(e) =>
                                        setExplode(+e.target.value)
                                      }
                                    />
                                  </label>
                                </div>
                                {!enable3d && (
                                  <div className="notice">
                                    Lighter 2D view is active for this device.{" "}
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      onClick={() => setEnable3d(true)}
                                    >
                                      Enable 3D
                                    </Button>
                                  </div>
                                )}
                              </>
                            )}
                            {route === "depth" && enable3d ? (
                              <Suspense
                                fallback={
                                  <p className="empty">
                                    Loading local 3D renderer…
                                  </p>
                                }
                              >
                                <DepthRenderer
                                  field={f}
                                  layer={layer}
                                  depth={depth}
                                  palette={palette}
                                  selection={selection}
                                  onSelect={select}
                                  exaggeration={exaggeration}
                                  clip={clip}
                                  scaleMode={scaleMode}
                                  explode={explode}
                                  layerCount={layerCount}
                                />
                              </Suspense>
                            ) : (
                              <MapView
                                field={f}
                                layer={layer}
                                depth={depth}
                                palette={palette}
                                selection={selection}
                                onSelect={select}
                                scaleMode={scaleMode}
                              />
                            )}
                            <div className="scrubber">
                              <label htmlFor="depth-scrub">
                                DEPTH SCRUB <strong>{f.depths[depth]} m</strong>
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
                                {f.depths.map((d, k) => (
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
                                <input
                                  aria-label="Latitude"
                                  type="number"
                                  step="any"
                                  value={lat}
                                  onChange={(e) => setLat(e.target.value)}
                                  required
                                />
                              </label>
                              <label>
                                Longitude °E
                                <input
                                  aria-label="Longitude"
                                  type="number"
                                  step="any"
                                  value={lon}
                                  onChange={(e) => setLon(e.target.value)}
                                  required
                                />
                              </label>
                              <Button type="submit" variant="outline" size="sm">
                                Inspect column <ArrowRight size={14} />
                              </Button>
                            </form>
                          </section>
                          <section className="panel">
                            <div className="panel-heading">
                              <div>
                                <span className="eyebrow">
                                  OBSERVED PREDICTORS / SELECTED GRID CELL
                                </span>
                                <h2>Seven surface inputs</h2>
                              </div>
                            </div>
                            {selection.row < 0 ? (
                              <p className="empty">
                                No inputs outside the domain.
                              </p>
                            ) : (
                              <div className="inputs-grid">
                                {Object.entries(data.surface).map(
                                  ([name, input]) => (
                                    <div key={name} className="input-tile">
                                      <span>
                                        {name
                                          .replaceAll("_", " ")
                                          .toUpperCase()}
                                      </span>
                                      <strong data-testid={`surface-${name}`}>
                                        {format(
                                          input.values[
                                            selection.row * f.lon.length +
                                              selection.col
                                          ],
                                        )}{" "}
                                        <small>{input.units}</small>
                                      </strong>
                                      <p>{input.product}</p>
                                    </div>
                                  ),
                                )}
                              </div>
                            )}
                          </section>
                        </div>
                        <Profile
                          field={f}
                          selection={selection}
                          depth={depth}
                        />
                      </div>
                      <div className="disclosures">
                        <p className="notice" data-testid="zero-note">
                          <Info size={17} />
                          <span>
                            <strong>Nominal 0 m.</strong>{" "}
                            {f.provenance.nominal_zero_m_note}
                          </span>
                        </p>
                        <p
                          className={`notice ${f.depths[depth] >= 500 ? "deep-active" : ""}`}
                          data-testid="deep-note"
                        >
                          <Info size={17} />
                          <span>
                            <strong>Deep-ocean skill.</strong>{" "}
                            {f.provenance.deep_skill_note}
                          </span>
                        </p>
                      </div>
                      <section className="panel provenance">
                        <div className="panel-heading">
                          <div>
                            <span className="eyebrow">TRACEABLE BY DESIGN</span>
                            <h2>{f.provenance.model_name}</h2>
                          </div>
                          <span className="chip" data-testid="inference-source">
                            {f.provenance.inference_source}
                          </span>
                        </div>
                        <div className="provenance-summary">
                          <span>
                            Latent width{" "}
                            <strong>{f.provenance.latent_dim}</strong>
                          </span>
                          <span>
                            Receptive field{" "}
                            <strong>
                              {f.provenance.receptive_field} ×{" "}
                              {f.provenance.receptive_field}
                            </strong>
                          </span>
                          <span>
                            Parameters{" "}
                            <strong>
                              {f.provenance.n_parameters.toLocaleString()}
                            </strong>
                          </span>
                          <span>
                            Compute{" "}
                            <strong>
                              {f.provenance.compute_seconds === null
                                ? "Validated cache"
                                : `${format(f.provenance.compute_seconds, 3)} s`}
                            </strong>
                          </span>
                        </div>
                        <details>
                          <summary>
                            Inspect frozen hashes &amp; support semantics
                          </summary>
                          <dl>
                            <dt>L2 state dictionary SHA256</dt>
                            <dd>{f.provenance.l2_state_dict_sha256}</dd>
                            <dt>Encoder SHA256</dt>
                            <dd>{f.provenance.l2_encoder_sha256}</dd>
                          </dl>
                          <p>{f.provenance.climatology_defined_note}</p>
                        </details>
                        <p className="muted small">
                          Only surface inputs at inference. {f.credits}
                        </p>
                      </section>
                      <Suspense
                        fallback={
                          <p className="empty">Loading date comparison…</p>
                        }
                      >
                        <MultiDate date={date} coords={coords} depth={depth} />
                      </Suspense>
                    </>
                  ) : route === "exports" ? (
                    <section className="panel">
                      <span className="eyebrow">
                        ACTUAL OUTPUTS / {f.effectiveDate}
                      </span>
                      <h2>Export the current reconstruction</h2>
                      <p>
                        Full precision values, explicit missing values, frozen
                        model provenance and product-specific credits.
                      </p>
                      <div className="export-grid">
                        <article>
                          <Download />
                          <h3>Selected profile</h3>
                          <p>
                            All 15 L2, L0 and anomaly values for the selected
                            grid cell.
                          </p>
                          <Button
                            disabled={selection.row < 0 || exportBusy}
                            onClick={() =>
                              void exportAction(() =>
                                download(
                                  new Blob([profileCsv(f, selection)], {
                                    type: "text/csv;charset=utf-8",
                                  }),
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
                            {f.depths[depth]} m · {layer} · actual color scale
                            and attribution.
                          </p>
                          <Button
                            disabled={exportBusy}
                            onClick={() =>
                              void exportAction(() =>
                                mapPng({
                                  field: f,
                                  layer,
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
                          <p>
                            101 × 241 × 15, all three fields, support masks and
                            provenance.
                          </p>
                          <Button
                            disabled={exportBusy}
                            onClick={() =>
                              void exportAction(async () => {
                                const response = await fetch(
                                  `/api/export/field.nc?date=${f.effectiveDate}`,
                                );
                                if (!response.ok)
                                  throw Error(
                                    "NetCDF export failed. Check local replay server.",
                                  );
                                download(
                                  await response.blob(),
                                  `OceanEmbed-${f.effectiveDate}.nc`,
                                );
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
                        Selected request: {format(coords[0], 4)}°N,{" "}
                        {format(coords[1], 4)}°E. Change location in Historical
                        Replay.
                      </p>
                      <p className="notice">
                        {f.provenance.nominal_zero_m_note}
                        <br />
                        {f.provenance.deep_skill_note}
                      </p>
                    </section>
                  ) : (
                    <section className="panel">
                      <p>Page not found.</p>
                      <Button onClick={() => navigate("replay")}>
                        Open Historical Replay
                      </Button>
                    </section>
                  )}
                </>
              )}
            </>
          )}
          <footer>
            OceanEmbed{" "}
            <span>
              Historical reconstruction · Frozen scientific core · 2024 Argo
              protected
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
function Stat({
  label,
  value,
  unit,
  icon: Icon,
}: {
  label: string;
  value: string;
  unit: string;
  icon?: typeof Thermometer;
}) {
  return (
    <div className="stat">
      <span>
        {Icon ? <Icon size={13} strokeWidth={2} aria-hidden /> : null}
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
