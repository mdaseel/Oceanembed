import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { getJson } from "../../field/api";
import { resolve, type Selection } from "../../field/contract";
import type { ReplayData } from "../../field/replayAdapter";
import type { RenderMapPanel } from "../hazard/types";
import { useNrtStates } from "../hazard/useNrtStates";
import type { Qualification } from "../LatestQualified";
import { ValidationContextView } from "./ContextSections";
import { Heatmap } from "./Heatmap";
import { Inspector, num, pct, regionLabel, Section, SubTabs } from "./Layout";
import type {
  AttributionResult,
  BasinPhysics,
  OcclusionResult,
  PhysicalQASummary,
  ColumnQA,
  RetrainedAblation,
} from "./scienceApi";
import "./workspace.css";

const Plot = lazy(() => import("../Plot"));

type Tab = "attribution" | "ablation" | "qa" | "validation";
const TABS: { id: Tab; label: string }[] = [
  { id: "attribution", label: "ATTRIBUTION" },
  { id: "ablation", label: "ABLATION" },
  { id: "qa", label: "PHYSICAL QA" },
  { id: "validation", label: "VALIDATION" },
];
const BANDS: { name: string; depths: number[] }[] = [
  { name: "0–50 m", depths: [0, 5, 10, 20, 30, 50] },
  { name: "75–150 m", depths: [75, 100, 125, 150] },
  { name: "200–300 m", depths: [200, 300] },
  { name: "500–1000 m", depths: [500, 700, 1000] },
];
const COLORS = ["#67e8f9", "#9fd08c", "#f3c77a", "#c49cf0", "#8fb7f2", "#f39b7a", "#e8e18f"];

function useFetch<T>(url: string | null, ok: (d: T) => boolean) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!url) return;
    let live = true;
    setBusy(true);
    setError("");
    getJson<T>(url)
      .then((d) => live && setData(d && ok(d) ? d : null))
      .catch((e) => live && setError((e as Error).message))
      .finally(() => live && setBusy(false));
    return () => {
      live = false;
    };
    // `ok` is a stable validator per call site
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);
  return { data, error, busy };
}

/** Dominant channel per depth band, from the gross attribution share. */
function bandSummary(a: AttributionResult) {
  return BANDS.map((b) => {
    const rows = b.depths.map((d) => a.depths_m.indexOf(d)).filter((k) => k >= 0);
    const mean = a.channels.map((_, c) => rows.reduce((s, k) => s + a.gross_share[k][c], 0) / rows.length);
    const order = mean.map((v, c) => [v, c] as const).sort((x, y) => y[0] - x[0]);
    return { band: b.name, first: order[0], second: order[1], mean };
  });
}

function AttributionView({ data, depthIndex }: { data: AttributionResult; depthIndex: number }) {
  const [view, setView] = useState<"share" | "net">("share");
  const bands = bandSummary(data);
  const values = view === "share" ? data.gross_share : data.net_c;
  return (
    <div className="ws" data-testid="attribution-panel" data-date={data.date}>
      <div className="ws-toggle-row">
        <span className="eyebrow">
          DEPTH × CHANNEL ATTRIBUTION · {data.lat.toFixed(2)}°N {data.lon.toFixed(2)}°E · {data.field.valid_date}
        </span>
        <div className="segmented" role="group" aria-label="Attribution view">
          <button type="button" className={view === "share" ? "active" : ""} aria-pressed={view === "share"} onClick={() => setView("share")}>
            Share of sensitivity
          </button>
          <button type="button" className={view === "net" ? "active" : ""} aria-pressed={view === "net"} data-testid="attribution-view-net" onClick={() => setView("net")}>
            Signed net (°C)
          </button>
        </div>
      </div>
      <div className="fig-row">
        <div className="fig-card">
          <h3>{view === "share" ? "Relative gross attribution per depth" : "Signed attribution per depth, °C"}</h3>
          <Heatmap
            rowLabels={data.depths_m.map((d) => `${d} m`)}
            colLabels={data.channel_short}
            values={values}
            mode={view === "share" ? "sequential" : "divergent"}
            format={(v) => (view === "share" ? `${Math.round(v * 100)}` : v.toFixed(2))}
            testid="attribution-heatmap"
            rowTitle="Output depth"
            colTitle={view === "share" ? "SURFACE CHANNEL · % OF GROSS MAGNITUDE" : "SURFACE CHANNEL · °C"}
            highlightRow={depthIndex}
          />
        </div>
        <div className="fig-card" data-testid="attribution-bands">
          <h3>Where the frozen model is most sensitive</h3>
          <table className="science-table">
            <thead>
              <tr>
                <th>Depth band</th>
                <th>Largest</th>
                <th>Second</th>
              </tr>
            </thead>
            <tbody>
              {bands.map((b) => (
                <tr key={b.band}>
                  <td>{b.band}</td>
                  <td>
                    {data.channel_labels[b.first[1]]} · {Math.round(b.first[0] * 100)} %
                  </td>
                  <td>
                    {data.channel_labels[b.second[1]]} · {Math.round(b.second[0] * 100)} %
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="ws-note">
            Integrated Gradients, {String(data.method.steps)} steps, baseline: {String(data.method.baseline)}. Largest
            completeness residual {Math.max(...data.completeness_residual_c).toFixed(3)} °C.
          </p>
          <p className="ws-note" data-testid="attribution-wording">
            {data.wording}
          </p>
        </div>
      </div>
    </div>
  );
}

function OcclusionView({ data }: { data: OcclusionResult }) {
  const domain = data.channels.map((c) => data.domain[c].median_abs_delta_c);
  const rows = data.depths_m.map((_, k) => domain.map((col) => col[k]));
  return (
    <div className="ws" data-testid="occlusion-panel" data-date={data.date}>
      <span className="eyebrow">
        CHANNEL OCCLUSION · FROZEN MODEL · {data.lat.toFixed(2)}°N {data.lon.toFixed(2)}°E · {data.field.valid_date}
      </span>
      <div className="fig-row">
        <div className="fig-card">
          <h3>Change in reconstructed temperature at this column</h3>
          <Suspense fallback={<p className="muted small">Loading chart…</p>}>
            <Plot
              data={data.channels.map((c, i) => ({
                type: "scatter",
                mode: "lines+markers",
                name: data.channel_short[i],
                x: data.point[c].delta_c.map((v, k) => (data.point[c].depth_supported[k] ? v : null)),
                y: data.depths_m,
                line: { color: COLORS[i], width: 2 },
                marker: { size: 4 },
                connectgaps: false,
                hovertemplate: `${data.channel_labels[i]} removed: %{x:.3f} °C at %{y} m<extra></extra>`,
              }))}
              layout={{
                autosize: true,
                height: 330,
                paper_bgcolor: "transparent",
                plot_bgcolor: "transparent",
                font: { color: "#aebfd5", family: "system-ui", size: 11 },
                margin: { l: 48, r: 10, t: 10, b: 40 },
                xaxis: { title: { text: "Occluded − original (°C)" }, gridcolor: "#253147", zerolinecolor: "#4a5c70" },
                yaxis: { title: { text: "Depth (m)" }, autorange: "reversed", gridcolor: "#253147" },
                legend: { orientation: "h", y: -0.2 },
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: "100%" }}
              useResizeHandler
            />
          </Suspense>
        </div>
        <div className="fig-card">
          <h3>Domain median |ΔT| when one channel is removed</h3>
          <Heatmap
            rowLabels={data.depths_m.map((d) => `${d} m`)}
            colLabels={data.channel_short}
            values={rows}
            mode="sequential"
            format={(v) => v.toFixed(2)}
            testid="occlusion-domain"
            rowTitle="Depth"
            colTitle="OCCLUDED CHANNEL · °C"
          />
        </div>
      </div>
      <table className="science-table" data-testid="occlusion-tchp">
        <thead>
          <tr>
            <th>Occluded channel</th>
            <th>ΔT 50 m</th>
            <th>ΔT 100 m</th>
            <th>TCHP original</th>
            <th>TCHP occluded</th>
            <th>ΔTCHP</th>
          </tr>
        </thead>
        <tbody>
          {data.channels.map((c, i) => {
            const p = data.point[c];
            const at = (d: number) => p.delta_c[data.depths_m.indexOf(d)];
            return (
              <tr key={c}>
                <td>{data.channel_labels[i]}</td>
                <td>{num(at(50), 3, "°C")}</td>
                <td>{num(at(100), 3, "°C")}</td>
                <td>{num(p.tchp_original, 1)}</td>
                <td>{num(p.tchp_occluded, 1)}</td>
                <td>{num(p.delta_tchp, 1, "kJ/cm²")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="ws-note" data-testid="occlusion-wording">
        {data.wording} Neutral value: {String(data.method.neutral_value)}. Not a production field.
      </p>
    </div>
  );
}

function RetrainedView({ data }: { data: RetrainedAblation }) {
  const groups = Object.keys(data.groups);
  const values = data.depths_m.map((_, k) => groups.map((g) => data.groups[g].rmse_change_percent[k]));
  const sst = data.sst_only;
  const keyDepths = [50, 75, 100, 125, 150];
  return (
    <div className="fig-row">
      <div className="fig-card" data-testid="retrained-ablation">
        <h3>Retrained without a group · % RMSE change (validation 2021)</h3>
        <Heatmap
          rowLabels={data.depths_m.map((d) => `${d} m`)}
          colLabels={groups}
          values={values}
          mode="divergent"
          format={(v) => `${v > 0 ? "+" : ""}${v.toFixed(0)}`}
          rowTitle="Depth"
          colTitle="GROUP REMOVED · % RMSE CHANGE (+ = WORSE)"
        />
        <p className="ws-note">
          {data.experiment}. Run-to-run noise floor {data.noise_floor_percent.mean.toFixed(2)} % mean,{" "}
          {data.noise_floor_percent.max.toFixed(2)} % maximum: changes inside it are indistinguishable. {data.report}.
        </p>
      </div>
      <div className="fig-card" data-testid="sst-only" data-status={sst.status}>
        <h3>SST-only experimental baseline</h3>
        {sst.status !== "COMPLETED" || !sst.models || !sst.depths_m ? (
          <p className="ws-note">{sst.note ?? "Not run."} The production model is unaffected either way.</p>
        ) : (
          <>
            <table className="science-table">
              <thead>
                <tr>
                  <th>RMSE °C</th>
                  {keyDepths.map((d) => (
                    <th key={d}>{d} m</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(sst.models).map(([model, m]) => (
                  <tr key={model} className={model === "SST_ONLY" ? "highlight" : ""}>
                    <td>{model.replaceAll("_", " ")}</td>
                    {keyDepths.map((d) => (
                      <td key={d}>{num(m.rmse_c[sst.depths_m!.indexOf(d)], 3)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="ws-note">
              Same architecture, schedule and seed as the full-input control; only the six non-SST planes are set to the
              training mean. Validation 2021, identical population. {sst.protocol}.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function QAView({ summary, profile, basin }: { summary: PhysicalQASummary; profile: ColumnQA | null; basin: BasinPhysics | null }) {
  const [region, setRegion] = useState("nio");
  const [mode, setMode] = useState<"qa" | "basin">("qa");
  const rec = summary.reconstruction[region];
  const ref = summary.reference_glorys[region];
  const env = summary.gradient_envelope[region];
  const regions = Object.keys(summary.reconstruction);
  return (
    <div className="ws" data-testid="physical-qa">
      <div className="ws-toggle-row">
        <div className="segmented" role="group" aria-label="Physical QA view">
          <button type="button" className={mode === "qa" ? "active" : ""} aria-pressed={mode === "qa"} onClick={() => setMode("qa")}>
            Profile plausibility
          </button>
          <button type="button" className={mode === "basin" ? "active" : ""} aria-pressed={mode === "basin"} data-testid="basin-physics-toggle" onClick={() => setMode("basin")}>
            Bay of Bengal vs Arabian Sea
          </button>
        </div>
        {mode === "qa" && (
          <div className="segmented" role="group" aria-label="Region">
            {regions.map((r) => (
              <button key={r} type="button" className={region === r ? "active" : ""} aria-pressed={region === r} onClick={() => setRegion(r)}>
                {regionLabel(r)}
              </button>
            ))}
          </div>
        )}
      </div>
      {mode === "qa" ? (
        <div className="fig-row">
          <div className="fig-card" data-testid="physical-qa-summary">
            <h3>Inversion frequency by depth band · {regionLabel(region)}</h3>
            <table className="science-table">
              <thead>
                <tr>
                  <th>Band</th>
                  <th>OceanEmbed</th>
                  <th>GLORYS reference</th>
                  <th>Level pairs</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(rec.bands).map((b) => (
                  <tr key={b}>
                    <td>{b}</td>
                    <td>{pct(rec.bands[b].inversion_frequency, 2)}</td>
                    <td>{pct(ref.bands[b].inversion_frequency, 2)}</td>
                    <td>{rec.bands[b].pairs.toLocaleString("en-US")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="ws-note">
              Profiles with at least one inversion: {pct(rec.profiles_with_inversion)} (reference{" "}
              {pct(ref.profiles_with_inversion)}), {rec.profiles.toLocaleString("en-US")} profiles on {summary.dates.n}{" "}
              dates ({summary.dates.rule}).
            </p>
          </div>
          <div className="fig-card" data-testid="physical-qa-envelope">
            <h3>Strongest cooling gradient vs the reference envelope</h3>
            <dl className="ws-kv">
              <dt>Within reference [p1, p99]</dt>
              <dd>{pct(env.fraction_within_reference_envelope)}</dd>
              <dt>Steeper than reference p1</dt>
              <dd>
                {pct(env.fraction_steeper_than_reference_p1, 2)} (reference {pct(env.reference_fraction_steeper_than_p1, 0)})
              </dd>
              <dt>Envelope</dt>
              <dd>
                {env.reference_p1.toFixed(3)} to {env.reference_p99.toFixed(3)} °C/m
              </dd>
            </dl>
            <h3>Independent Argo profiles · {summary.argo.period}</h3>
            <dl className="ws-kv" data-testid="physical-qa-argo">
              <dt>Argo observed inversions</dt>
              <dd>{pct(summary.argo.argo_observed.inversion_frequency, 2)}</dd>
              <dt>Collocated OceanEmbed</dt>
              <dd>{pct(summary.argo.l2_collocated.inversion_frequency, 2)}</dd>
              <dt>Level pairs compared</dt>
              <dd>{summary.argo.argo_observed.pairs.toLocaleString("en-US")}</dd>
            </dl>
            <p className="ws-note">{summary.rule}. No single physics score is computed.</p>
          </div>
          {profile && (
            <div className="fig-card" data-testid="profile-qa">
              <h3>
                Selected column · {profile.lat.toFixed(2)}°N {profile.lon.toFixed(2)}°E · {profile.date}
              </h3>
              <dl className="ws-kv">
                <dt>Supported levels</dt>
                <dd>{profile.profile.n_supported_levels}</dd>
                <dt>Strongest vertical gradient</dt>
                <dd>
                  {num(profile.profile.strongest_gradient_c_per_m, 4, "°C/m")} at {num(profile.profile.strongest_gradient_depth_m, 1, "m")}
                </dd>
                <dt>Inversions</dt>
                <dd data-testid="profile-qa-inversions">{profile.profile.inversion_count}</dd>
                <dt>Largest inversion</dt>
                <dd>{num(profile.profile.max_inversion_c, 2, "°C")}</dd>
                <dt>Reference percentile</dt>
                <dd>{profile.context?.reference_percentile == null ? "—" : `${profile.context.reference_percentile.toFixed(0)}th`}</dd>
              </dl>
              <p className="ws-note">{profile.context?.note}</p>
            </div>
          )}
        </div>
      ) : basin ? (
        <BasinPhysicsView data={basin} />
      ) : (
        <p className="muted small">Basin comparison not computed.</p>
      )}
    </div>
  );
}

function BasinPhysicsView({ data }: { data: BasinPhysics }) {
  const basins = Object.keys(data.regions).filter((r) => r !== "nio");
  const dist = (d: { p5?: number; p50?: number; p95?: number; n: number }, digits = 1) =>
    d.n ? `${num(d.p50, digits)} [${num(d.p5, digits)}, ${num(d.p95, digits)}]` : "—";
  return (
    <div className="ws" data-testid="basin-physics">
      <div className="fig-row">
        <div className="fig-card">
          <h3>Mean temperature profile, QA dates</h3>
          <Suspense fallback={<p className="muted small">Loading chart…</p>}>
            <Plot
              data={basins.flatMap((b, i) => [
                { type: "scatter", mode: "lines", name: `${regionLabel(b)} · OceanEmbed`, x: data.regions[b].mean_profile_l2_c, y: data.depths_m, line: { color: COLORS[i * 2], width: 2 } },
                { type: "scatter", mode: "lines", name: `${regionLabel(b)} · GLORYS`, x: data.regions[b].mean_profile_glorys_c, y: data.depths_m, line: { color: COLORS[i * 2], width: 1.5, dash: "dot" } },
              ])}
              layout={{
                autosize: true,
                height: 300,
                paper_bgcolor: "transparent",
                plot_bgcolor: "transparent",
                font: { color: "#aebfd5", family: "system-ui", size: 11 },
                margin: { l: 48, r: 10, t: 10, b: 40 },
                xaxis: { title: { text: "Temperature (°C)" }, gridcolor: "#253147" },
                yaxis: { title: { text: "Depth (m)" }, autorange: "reversed", gridcolor: "#253147", range: [300, 0] },
                legend: { orientation: "h", y: -0.25 },
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: "100%" }}
              useResizeHandler
            />
          </Suspense>
        </div>
        <div className="fig-card">
          <h3>Distributions · median [5th, 95th percentile]</h3>
          <table className="science-table">
            <thead>
              <tr>
                <th>Quantity</th>
                {basins.map((b) => (
                  <th key={b}>{regionLabel(b)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>TCHP (kJ/cm²)</td>
                {basins.map((b) => (
                  <td key={b}>{dist(data.regions[b].tchp_l2)}</td>
                ))}
              </tr>
              <tr>
                <td>D26 (m)</td>
                {basins.map((b) => (
                  <td key={b}>{dist(data.regions[b].d26_l2)}</td>
                ))}
              </tr>
              <tr>
                <td>50 m anomaly (°C)</td>
                {basins.map((b) => (
                  <td key={b}>{dist(data.regions[b].anomaly_50m_l2, 2)}</td>
                ))}
              </tr>
              <tr>
                <td>100 m anomaly (°C)</td>
                {basins.map((b) => (
                  <td key={b}>{dist(data.regions[b].anomaly_100m_l2, 2)}</td>
                ))}
              </tr>
              <tr>
                <td>0–50 m inversion frequency</td>
                {basins.map((b) => (
                  <td key={b}>{pct(data.regions[b].inversion_frequency_l2["0-50 m"]?.inversion_frequency, 1)}</td>
                ))}
              </tr>
            </tbody>
          </table>
          <h3>Argo RMSE by basin (°C, L2 / L0)</h3>
          <table className="science-table">
            <tbody>
              {[50, 100, 150].map((d) => (
                <tr key={d}>
                  <td>{d} m</td>
                  {basins.map((b) => {
                    const rows = data.argo_skill[b] ?? [];
                    const l2 = rows.find((r) => r.depth_m === d && r.model === "L2");
                    const l0 = rows.find((r) => r.depth_m === d && r.model === "L0");
                    return (
                      <td key={b}>
                        {num(l2?.rmse_c, 2)} / {num(l0?.rmse_c, 2)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.attribution && (
          <div className="fig-card">
            <h3>Mean attribution share by basin (12 dates of 2021)</h3>
            {basins.map((b) =>
              data.attribution!.basins[b] ? (
                <div key={b}>
                  <p className="ws-note">
                    {regionLabel(b)} · {data.attribution!.basins[b].n_cells} cells
                  </p>
                  <Heatmap
                    rowLabels={data.attribution!.depths_m.map((d) => `${d} m`).filter((_, k) => [0, 5, 7, 9, 11].includes(k))}
                    colLabels={data.attribution!.channel_short}
                    values={data.attribution!.basins[b].mean_gross_share.filter((_, k) => [0, 5, 7, 9, 11].includes(k))}
                    mode="sequential"
                    format={(v) => `${Math.round(v * 100)}`}
                  />
                </div>
              ) : null,
            )}
          </div>
        )}
      </div>
      <p className="ws-note" data-testid="basin-caveat">
        {data.caveat}
      </p>
    </div>
  );
}

export default function ModelScience({
  historical,
  historicalDate,
  qualification,
  coords,
  onSelect,
  depth,
  renderMapPanel,
}: {
  historical: ReplayData | null;
  historicalDate: string;
  qualification: Qualification | null;
  coords: [number, number];
  onSelect: (lat: number, lon: number) => void;
  depth: number;
  renderMapPanel: RenderMapPanel;
}) {
  const [tab, setTab] = useState<Tab>("attribution");
  const [source, setSource] = useState<"historical" | "latest">("historical");
  const [threeD, setThreeD] = useState(false);
  const nrt = useNrtStates(source === "latest" && !!qualification?.qualified);
  const data = source === "latest" ? nrt.data : historical;
  const f = data?.field ?? null;
  const selection: Selection | null = f ? resolve(f, coords[0], coords[1]) : null;
  const date = f?.effectiveDate ?? historicalDate;
  const depthM = f?.depths[depth] ?? 100;
  const lat = selection && selection.row >= 0 ? f!.lat[selection.row] : coords[0];
  const lon = selection && selection.col >= 0 ? f!.lon[selection.col] : coords[1];
  const usable = !!selection && selection.status === "OK";
  const q = `lat=${lat}&lon=${lon}&date=${date}&source=${source}`;

  const attribution = useFetch<AttributionResult>(
    tab === "attribution" && usable ? `/api/science/attribution?${q}` : null,
    (d) => Array.isArray(d.gross_share),
  );
  const occlusion = useFetch<OcclusionResult>(
    tab === "ablation" && usable ? `/api/science/occlusion?${q}` : null,
    (d) => !!d.point,
  );
  const retrained = useFetch<RetrainedAblation>(tab === "ablation" ? "/api/science/retrained-ablation" : null, (d) => !!d.groups);
  const qa = useFetch<PhysicalQASummary>(tab === "qa" ? "/api/science/physical-qa" : null, (d) => !!d.reconstruction);
  const profile = useFetch<ColumnQA>(tab === "qa" && usable ? `/api/science/physical-qa/profile?${q}` : null, (d) => !!d.profile);
  const basin = useFetch<BasinPhysics>(tab === "qa" ? "/api/science/basin-physics" : null, (d) => !!d.regions);

  const dominant = useMemo(() => (attribution.data ? bandSummary(attribution.data) : null), [attribution.data]);

  const analysis =
    tab === "attribution" ? (
      attribution.data ? (
        <AttributionView data={attribution.data} depthIndex={depth} />
      ) : (
        <p className="muted small" role="status">
          {attribution.error || (usable ? "Computing Integrated Gradients for the selected column…" : "Select an ocean cell with valid surface input.")}
        </p>
      )
    ) : tab === "ablation" ? (
      <div className="ws">
        {occlusion.data ? (
          <OcclusionView data={occlusion.data} />
        ) : (
          <p className="muted small" role="status">
            {occlusion.error || (usable ? "Running the frozen model once per occluded channel…" : "Select an ocean cell with valid surface input.")}
          </p>
        )}
        {retrained.data && <RetrainedView data={retrained.data} />}
      </div>
    ) : tab === "qa" ? (
      qa.data ? (
        <QAView summary={qa.data} profile={profile.data} basin={basin.data} />
      ) : (
        <p className="muted small">{qa.error || "Reading the pre-registered QA summary…"}</p>
      )
    ) : (
      <div className="fig-row">
        <div className="fig-card">
          <h3>Validation context at {depthM} m</h3>
          <ValidationContextView depth={depthM} lat={lat} lon={lon} />
        </div>
        <div className="fig-card">
          <h3>What this validation is</h3>
          <p className="ws-note">
            Independent Argo profiles from 2022–2023 were collocated with OceanEmbed, the pointwise L1 baseline, L0 climatology
            and GLORYS. GLORYS assimilates in-situ profiles, so it is shown for context, not as an independent reference. The
            2024 Argo holdout is protected and has not been opened. Full tables and reports are in Provenance &amp; Validation.
          </p>
        </div>
      </div>
    );

  return (
    <div className="ws" data-testid="model-science" data-tab={tab}>
      <header className="ws-head">
        <div>
          <span className="eyebrow">MODEL SCIENCE · FROZEN L2 · SEVEN SURFACE CHANNELS</span>
          <h1>What the reconstruction uses, and how it behaves</h1>
          <p className="muted">
            Attribution, occlusion, physical plausibility and validation — experiments beside the production model, never inside it.
          </p>
        </div>
        <div className="ws-head-side">
          <div className="segmented" role="group" aria-label="Field source">
            <button type="button" className={source === "historical" ? "active" : ""} aria-pressed={source === "historical"} onClick={() => setSource("historical")}>
              Historical · {historicalDate}
            </button>
            <button type="button" className={source === "latest" ? "active" : ""} aria-pressed={source === "latest"} disabled={!qualification?.qualified} onClick={() => setSource("latest")}>
              Latest qualified
            </button>
          </div>
        </div>
      </header>
      <SubTabs tabs={TABS} active={tab} onActive={setTab} label="Model science" />
      <div className="ws-grid">
        <div className="ws-main">
          {f && selection ? (
            renderMapPanel(data!, selection, {
              layer: tab === "qa" ? "temperature" : "anomaly",
              threeD,
              setThreeD,
              eyebrow: "SELECT A WATER COLUMN TO ANALYSE",
              title: `Selected column · ${f.effectiveDate}`,
            })
          ) : (
            <p className="muted small">Loading the field…</p>
          )}
        </div>
        <Inspector eyebrow={`INSPECTOR · ${TABS.find((t) => t.id === tab)?.label}`} title={`${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E`}>
          {tab === "attribution" && (
            <Section title="Attribution summary" defaultOpen testid="inspector-attribution">
              {dominant ? (
                <ul className="ws-note">
                  {dominant.map((b) => (
                    <li key={b.band}>
                      {b.band}: most sensitive to <strong>{attribution.data!.channel_labels[b.first[1]]}</strong> (
                      {Math.round(b.first[0] * 100)} %)
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="ws-note">{usable ? "Computing…" : "No valid surface input at this cell."}</p>
              )}
              <p className="ws-note">Model sensitivity / attribution — not causation.</p>
            </Section>
          )}
          {tab === "ablation" && (
            <Section title="Occlusion at this column" defaultOpen>
              {occlusion.data ? (
                <dl className="ws-kv">
                  {occlusion.data.channels.map((c, i) => (
                    <div key={c} style={{ display: "contents" }}>
                      <dt>{occlusion.data!.channel_labels[i]}</dt>
                      <dd>ΔTCHP {num(occlusion.data!.point[c].delta_tchp, 1)}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="ws-note">{usable ? "Computing…" : "No valid surface input at this cell."}</p>
              )}
            </Section>
          )}
          {tab === "qa" && (
            <Section title="Physical QA at this column" defaultOpen>
              {profile.data ? (
                <dl className="ws-kv">
                  <dt>Inversions</dt>
                  <dd>{profile.data.profile.inversion_count}</dd>
                  <dt>Strongest gradient</dt>
                  <dd>{num(profile.data.profile.strongest_gradient_c_per_m, 4, "°C/m")}</dd>
                  <dt>Depth</dt>
                  <dd>{num(profile.data.profile.strongest_gradient_depth_m, 1, "m")}</dd>
                </dl>
              ) : (
                <p className="ws-note">{profile.error || "Select an ocean column."}</p>
              )}
            </Section>
          )}
          <Section title="Validation context" defaultOpen={tab === "validation"}>
            <ValidationContextView depth={depthM} lat={lat} lon={lon} compact testid="inspector-validation" />
          </Section>
        </Inspector>
      </div>
      <section className="panel ws-tray" data-testid="science-analysis">
        <div className="ws-tray-body">{analysis}</div>
      </section>
    </div>
  );
}
