import { lazy, Suspense } from "react";
import {
  addDays,
  eventChanges,
  eventDates,
  fixed,
  oceanStory,
  phaseFor,
  phaseShort,
  signed,
  storyKeyFor,
  type EventInfo,
  type SeriesKey,
  type SeriesRow,
} from "../../field/hazardIntelligence";
import { InfoTip } from "./InfoTip";

const Plot = lazy(() => import("../Plot"));

const ROWS: { key: SeriesKey; label: string; unit: string; digits: number }[] = [
  { key: "sst_nominal_0m_c", label: "Nominal 0 m temperature", unit: "°C", digits: 2 },
  { key: "anomaly_100m_c", label: "100 m anomaly", unit: "°C", digits: 2 },
  { key: "d26_m", label: "D26", unit: "m", digits: 1 },
  { key: "tchp_kj_cm2", label: "TCHP", unit: "kJ/cm²", digits: 1 },
];

/** BEFORE → EVENT → COLD WAKE → RECOVERY, "What happened to the ocean?" and the chart. */
export function ColdWake({
  event,
  series,
  corridorDeg,
  busy,
  error,
  onRun,
  currentDate,
}: {
  event: EventInfo;
  series: SeriesRow[] | null;
  corridorDeg: number | null;
  busy: boolean;
  error: string;
  onRun: () => void;
  currentDate: string | null;
}) {
  const changes = series ? eventChanges(series, event.segments) : null;
  const story = changes ? oceanStory(changes) : [];
  const currentPhase = currentDate ? phaseFor(currentDate, event.segments) : null;
  const activeKey = storyKeyFor(currentPhase?.label);
  const pre = changes?.pre?.means.tchp_kj_cm2 ?? null;
  const min = changes?.wakeMin.tchp ?? null;
  const corridor = corridorDeg ?? 1.5;
  const midpoint = (start: string, end: string) => {
    const n = eventDates(start, end).length;
    const half = (n - 1) / 2;
    return Number.isInteger(half)
      ? addDays(start, half)
      : `${addDays(start, Math.floor(half))} 12:00`;
  };

  return (
    <>
      <section className="panel event-outcome" data-testid="event-comparison">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">BEFORE → EVENT → COLD WAKE → RECOVERY</span>
            <h2>
              What the replay measured along the track corridor <InfoTip term="corridor" />
            </h2>
          </div>
        </div>
        {!series && busy && (
          <p className="muted" role="status">
            Replaying each day of the window…
          </p>
        )}
        {!series && !busy && (
          <p className="empty">
            Run the event window below to compare the phases with real replayed values.
          </p>
        )}
        {changes && (
          <>
            <div className="table-scroll">
              <table className="compare-table">
                <thead>
                  <tr>
                    <th>Corridor mean</th>
                    {changes.segments.map((s) => (
                      <th
                        key={s.segment.label}
                        data-phase={s.segment.label}
                        className={currentPhase?.label === s.segment.label ? "current" : ""}
                      >
                        {phaseShort(s.segment.label)}
                        <small>
                          {s.segment.start.slice(5)} → {s.segment.end.slice(5)}
                        </small>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ROWS.map((r) => (
                    <tr key={r.key}>
                      <td>
                        {r.label} ({r.unit})
                      </td>
                      {changes.segments.map((s) => (
                        <td
                          key={s.segment.label}
                          className={currentPhase?.label === s.segment.label ? "current" : ""}
                        >
                          {fixed(s.means[r.key], r.digits)}
                        </td>
                      ))}
                    </tr>
                  ))}
                  <tr>
                    <td>ELEVATED + HIGH share of categorised cells</td>
                    {changes.segments.map((s) => (
                      <td
                        key={s.segment.label}
                        className={currentPhase?.label === s.segment.label ? "current" : ""}
                      >
                        {s.supportShare === null ? "—" : `${Math.round(s.supportShare * 100)} %`}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>

            <div
              className="reservoir"
              data-testid="event-changes"
              data-tchp-pre={pre ?? ""}
              data-tchp-min={min?.value ?? ""}
              data-tchp-change={changes.tchpChange ?? ""}
              data-tchp-pct={changes.tchpChangePct ?? ""}
            >
              <div className="reservoir-main">
                <span className="eyebrow">
                  UPPER-OCEAN THERMAL RESERVOIR <InfoTip term="tchp" />
                </span>
                <dl>
                  <div>
                    <dt>Pre-event mean</dt>
                    <dd data-testid="tchp-pre">{fixed(pre, 1)} kJ/cm²</dd>
                  </div>
                  <div>
                    <dt>Cold-wake minimum{min ? ` (${min.date})` : ""}</dt>
                    <dd data-testid="tchp-min">{fixed(min?.value, 1)} kJ/cm²</dd>
                  </div>
                  <div className="change">
                    <dt>Change</dt>
                    <dd data-testid="tchp-change">
                      {signed(changes.tchpChange, 1, "kJ/cm²")}
                      {changes.tchpChangePct !== null && (
                        <span className="pct">
                          {changes.tchpChangePct < 0 ? "↓" : "↑"}{" "}
                          {Math.abs(changes.tchpChangePct).toFixed(0)} %
                        </span>
                      )}
                    </dd>
                  </div>
                </dl>
                <p className="small">
                  {changes.tchpChange !== null && changes.tchpChange < 0
                    ? `Interpretation: at the wake minimum, ${Math.abs(changes.tchpChangePct ?? 0).toFixed(0)} % of the pre-event corridor reservoir had been depleted or mixed. This is a difference between reconstructions, not a measured energy transfer.`
                    : "Interpretation: corridor TCHP did not fall below its pre-event mean in the wake segment."}
                </p>
              </div>
              <dl className="change-list">
                <div>
                  <dt>Surface cooling · nominal 0 m (wake minimum − pre-event)</dt>
                  <dd data-testid="sst-change">{signed(changes.sstChange, 2, "°C")}</dd>
                </div>
                <div>
                  <dt>D26 change (wake minimum − pre-event)</dt>
                  <dd data-testid="d26-change">{signed(changes.d26Change, 1, "m")}</dd>
                </div>
                <div>
                  <dt>100 m anomaly (wake mean − pre-event)</dt>
                  <dd>{signed(changes.anomaly100Change, 2, "°C")}</dd>
                </div>
              </dl>
              <div className="recovery" data-testid="ocean-recovery">
                <span className="eyebrow">OCEAN RECOVERY · NUMBERS ONLY</span>
                {changes.final && changes.tchpFinalVsPre !== null ? (
                  <p>
                    By {changes.final.date}, TCHP{" "}
                    {changes.tchpFinalVsPre < 0
                      ? `remains ${Math.abs(changes.tchpFinalVsPre).toFixed(1)} kJ/cm² below`
                      : `is ${changes.tchpFinalVsPre.toFixed(1)} kJ/cm² above`}{" "}
                    the pre-event level
                    {changes.tchpFinalVsWakeMin !== null
                      ? changes.tchpFinalVsWakeMin >= 0
                        ? ` and has recovered ${changes.tchpFinalVsWakeMin.toFixed(1)} kJ/cm² from the cold-wake minimum`
                        : ` and is ${Math.abs(changes.tchpFinalVsWakeMin).toFixed(1)} kJ/cm² below the cold-wake minimum`
                      : ""}
                    .
                  </p>
                ) : (
                  <p>Not enough replayed values to state a recovery difference.</p>
                )}
                <p className="small muted">No recovery category is assigned.</p>
              </div>
            </div>
            <p className="small muted">
              Definitions: each phase value is the mean of that frozen segment's daily corridor
              means; the cold-wake minimum is the lowest daily corridor value in the Wake
              segment; recovery compares the last replayed day with both. Corridor: cells
              within {corridor}° of any observed track position.
            </p>
          </>
        )}
      </section>

      <section className="panel ocean-story" data-testid="ocean-story" data-active={activeKey ?? ""}>
        <span className="eyebrow">WHAT HAPPENED TO THE OCEAN?</span>
        <h2>{event.name}</h2>
        {story.length === 0 ? (
          <p className="empty">The explanation appears once the event window has been replayed.</p>
        ) : (
          <ol className="story-steps">
            {story.map((s) => (
              <li key={s.key} className={s.key === activeKey ? "active" : ""} data-key={s.key}>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
              </li>
            ))}
          </ol>
        )}
        <p className="small muted">
          "Consistent with" is deliberate: OceanEmbed reconstructs the thermal state along the
          track; it does not prove what caused a change.
        </p>
      </section>

      <section className="panel" data-testid="cold-wake">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">
              COLD WAKE &amp; THERMAL RECOVERY <InfoTip term="coldWake" />
            </span>
            <h2>{event.name} window</h2>
          </div>
          <button className="btn" disabled={busy} onClick={onRun}>
            {busy ? "Replaying each day…" : "Run the event window"}
          </button>
        </div>
        <p className="muted small">{event.independence_note}</p>
        {error && <p className="panel error-state">{error}</p>}
        {!series && !busy && !error && (
          <p className="empty">
            Each day of the window is an independent frozen-L2 reconstruction. Run it to see
            the cold wake and recovery.
          </p>
        )}
        {series && (
          <Suspense fallback={<p className="empty">Loading chart…</p>}>
            <Plot
              // Three quantities, three units, three panels sharing one date
              // axis. They never share a y-axis: metres and kJ/cm² overlap
              // numerically in this window, so a shared axis would mislead.
              data={[
                {
                  x: series.map((r) => r.date),
                  y: series.map((r) => r.sst_nominal_0m_c),
                  name: "Nominal 0 m",
                  type: "scatter",
                  mode: "lines+markers",
                  line: { color: "#f0913a", width: 2 },
                  hovertemplate: "%{y:.2f} °C · %{x}<extra></extra>",
                },
                {
                  x: series.map((r) => r.date),
                  y: series.map((r) => r.d26_m),
                  name: "D26",
                  type: "scatter",
                  mode: "lines+markers",
                  yaxis: "y2",
                  line: { color: "#9db4c8", width: 2 },
                  hovertemplate: "%{y:.1f} m · %{x}<extra></extra>",
                },
                {
                  x: series.map((r) => r.date),
                  y: series.map((r) => r.tchp_kj_cm2),
                  name: "TCHP",
                  type: "scatter",
                  mode: "lines+markers",
                  yaxis: "y3",
                  line: { color: "#67e8f9", width: 2 },
                  hovertemplate: "%{y:.1f} kJ/cm² · %{x}<extra></extra>",
                },
              ]}
              layout={{
                autosize: true,
                height: 560,
                paper_bgcolor: "transparent",
                plot_bgcolor: "transparent",
                font: { color: "#aebfd5", family: "system-ui", size: 11 },
                margin: { l: 68, r: 24, t: 34, b: 56 },
                showlegend: false,
                xaxis: { gridcolor: "#253147", anchor: "y3" },
                yaxis: {
                  title: { text: "Nominal 0 m (°C)" },
                  domain: [0.7, 1.0],
                  gridcolor: "#253147",
                },
                yaxis2: {
                  title: { text: "D26 (m)" },
                  domain: [0.35, 0.65],
                  gridcolor: "#253147",
                },
                yaxis3: {
                  title: { text: "TCHP (kJ/cm²)" },
                  domain: [0.0, 0.3],
                  gridcolor: "#253147",
                },
                shapes: [
                  ...event.segments.map((s, i) => ({
                    type: "rect" as const,
                    xref: "x" as const,
                    yref: "paper" as const,
                    x0: `${addDays(s.start, -1)} 12:00`,
                    x1: `${s.end} 12:00`,
                    y0: 0,
                    y1: 1,
                    fillcolor: i % 2 ? "rgba(103,232,249,0.035)" : "rgba(157,180,200,0.06)",
                    line: { width: 0 },
                    layer: "below" as const,
                  })),
                  {
                    type: "line" as const,
                    x0: event.peak,
                    x1: event.peak,
                    yref: "paper" as const,
                    y0: 0,
                    y1: 1,
                    line: { color: "#c13d2c", dash: "dash" as const },
                  },
                  ...(currentDate
                    ? [
                        {
                          type: "line" as const,
                          x0: currentDate,
                          x1: currentDate,
                          yref: "paper" as const,
                          y0: 0,
                          y1: 1,
                          line: { color: "#67e8f9", width: 2, dash: "dot" as const },
                        },
                      ]
                    : []),
                ],
                annotations: [
                  ...event.segments.map((s) => ({
                    x: midpoint(s.start, s.end),
                    yref: "paper" as const,
                    y: 1.05,
                    text: phaseShort(s.label),
                    showarrow: false,
                    font: { color: "#7f97b0", size: 9 },
                  })),
                  {
                    x: event.peak,
                    yref: "paper" as const,
                    y: 0.985,
                    xanchor: "left" as const,
                    text: ` peak ${event.peak}`,
                    showarrow: false,
                    font: { color: "#c98277", size: 10 },
                  },
                ],
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: "100%" }}
              useResizeHandler
            />
          </Suspense>
        )}
        <p className="muted small">
          Averaged over cells within {corridor}° of the observed track. Each date is a separate
          reconstruction differenced afterwards — never a modelled evolution, and never a
          forecast. A single warm anomaly is not called a marine heatwave: no
          duration/percentile definition is implemented.
        </p>
      </section>
    </>
  );
}
