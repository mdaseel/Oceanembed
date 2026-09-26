import { useCallback, useEffect, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { signed, type MonitoringResult } from "../../field/hazardIntelligence";
import { AlongTrackSection } from "./AlongTrackSection";
import { PrintableBrief } from "./Briefs";
import { TrackThermalPanel } from "./TrackThermal";
import { getJson, type CycloneAnalysis, type CycloneState } from "./api";

const hours = (h?: number | null) =>
  h == null ? "—" : Math.abs(h) < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} days`;

/**
 * Latest / NRT cyclone context. The external track comes from GDACS with its own
 * provenance; the thermal numbers come from an OceanEmbed field. The two are
 * never merged, and an archived test event is never shown as live.
 */
export function CycloneWatch({
  onContext,
  onStatus,
  onSelectPoint,
  latestValidDate,
  latestLagHours,
  monitoring,
}: {
  onContext: (context: CycloneAnalysis | null) => void;
  onStatus?: (status: CycloneState | null) => void;
  onSelectPoint: (lat: number, lon: number) => void;
  latestValidDate: string | null;
  latestLagHours: number | null;
  monitoring: MonitoringResult | null;
}) {
  const [status, setStatus] = useState<CycloneState | null>(null);
  const [analysis, setAnalysis] = useState<CycloneAnalysis | null>(null);
  const [test, setTest] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const check = useCallback(() => {
    setBusy(true);
    setError("");
    getJson<CycloneState>("/api/cyclones/current")
      .then((s) => {
        setStatus(s);
        onStatus?.(s);
      })
      .catch((e) => {
        setError((e as Error).message);
        onStatus?.(null);
      })
      .finally(() => setBusy(false));
  }, [onStatus]);
  useEffect(check, [check]);

  const load = useCallback(
    (kind: "active" | "test", mode: "temperature" | "anomaly" = "temperature") => {
      setBusy(true);
      setError("");
      getJson<CycloneAnalysis>(
        kind === "test"
          ? `/api/cyclones/archived-test?mode=${mode}`
          : `/api/cyclones/current/thermal-analysis?mode=${mode}`,
      )
        .then((a) => {
          setAnalysis(a.analysis ? a : null);
          onContext(a.analysis ? a : null);
        })
        .catch((e) => setError((e as Error).message))
        .finally(() => setBusy(false));
    },
    [onContext],
  );

  const active = status?.state === "ACTIVE_NORTH_INDIAN_CYCLONE";
  useEffect(() => {
    if (active) {
      setTest(false);
      load("active");
    }
  }, [active, load]);

  const adv = analysis?.advisory;
  const isTest = analysis?.state === "HISTORICAL_TEST_EVENT";
  const title = active ? "CYCLONE THERMAL SUPPORT WATCH" : "OCEAN THERMAL WATCH";

  return (
    <section className="panel cyclone-watch" data-testid="cyclone-watch" data-state={status?.state ?? "CHECKING"}>
      <div className="panel-heading">
        <div>
          <span className="eyebrow">EXTERNAL CYCLONE CONTEXT · {status?.provider ?? "GDACS"}</span>
          <h2 data-testid="cyclone-watch-title">{title}</h2>
        </div>
        <div className="section-tools">
          <button type="button" className="btn" onClick={check} disabled={busy}>
            {busy ? "Checking…" : "Check source"}
          </button>
          {!active && (
            <button
              type="button"
              className="btn"
              data-testid="archived-test-toggle"
              onClick={() => {
                if (test) {
                  setTest(false);
                  setAnalysis(null);
                  onContext(null);
                } else {
                  setTest(true);
                  load("test");
                }
              }}
            >
              {test ? "Hide archived test event" : "Show archived test event (HISTORICAL / TEST)"}
            </button>
          )}
        </div>
      </div>
      {error && <p className="notice" data-testid="cyclone-error">{error}</p>}
      {status && (
        <p
          className={`notice ${status.state === "SOURCE_UNAVAILABLE" || status.cached ? "nrt-unavailable" : ""}`}
          data-testid="cyclone-status"
        >
          <ShieldAlert size={16} aria-hidden />
          <span>
            <strong>
              {status.state === "NO_ACTIVE_NORTH_INDIAN_CYCLONE"
                ? "NO ACTIVE NORTH INDIAN OCEAN CYCLONE"
                : status.state === "ACTIVE_NORTH_INDIAN_CYCLONE"
                  ? "ACTIVE NORTH INDIAN OCEAN CYCLONE"
                  : status.state === "SOURCE_UNAVAILABLE"
                    ? "CYCLONE ADVISORY SOURCE CURRENTLY UNAVAILABLE"
                    : "CACHED ADVISORY — NOT CURRENT"}
            </strong>{" "}
            {status.message} Checked {status.checked_at ?? "—"}
            {status.current_outside_north_indian?.length
              ? `. Current storms elsewhere: ${status.current_outside_north_indian.join(", ")}.`
              : "."}
          </span>
        </p>
      )}
      <p className="small muted" data-testid="imd-status">
        {status?.imd_status ??
          "IMD / RSMC New Delhi official track: not connected in this build."}
      </p>

      {analysis?.analysis && adv && (
        <div className="cyclone-analysis" data-testid="cyclone-analysis" data-test-event={isTest ? "true" : "false"}>
          {isTest && (
            <p className="notice test-banner" data-testid="test-event-banner">
              <strong>HISTORICAL / TEST EVENT</strong> — {analysis.note}
            </p>
          )}
          <dl className="nrt-header">
            <div>
              <span>EVENT</span>
              <strong>{adv.storm_name}</strong>
              <small>{adv.basin}</small>
            </div>
            <div>
              <span>ADVISORY ISSUED</span>
              <strong>{adv.advisory_issued_at.replace("T", " ").replace("Z", " UTC")}</strong>
              <small>{adv.provenance_label}</small>
            </div>
            <div>
              <span>OCEANEMBED VALID DATE</span>
              <strong data-testid="cyclone-field-date">{analysis.thermal_field?.valid_date}</strong>
              <small>{analysis.thermal_field?.source}</small>
            </div>
            <div>
              <span>ADVISORY − FIELD VALID TIME</span>
              <strong data-testid="cyclone-mismatch">{hours(analysis.thermal_field?.advisory_minus_valid_hours)}</strong>
              <small>
                reconstruction lag {hours(analysis.thermal_field?.reconstruction_lag_hours ?? null)}
              </small>
            </div>
          </dl>
          <p className="small muted">
            {adv.observed_points.length} observed and {adv.forecast_points.length} forecast
            positions from {adv.provider}. Wind and pressure are not provided per position by this
            source and are not shown. {adv.attribution}
          </p>
          <TrackThermalPanel
            analysis={analysis.analysis}
            pathKind="external forecast track"
            labels={{ path: analysis.labels?.track ?? adv.provenance_label, thermal: analysis.labels?.thermal_state ?? "Thermal state: OceanEmbed" }}
            onSelectPoint={onSelectPoint}
            testid="cyclone-track"
          />
          <AlongTrackSection
            section={analysis.section}
            loading={busy}
            onMode={(m) => load(isTest ? "test" : "active", m)}
            labels={{ path: `Cyclone track: ${adv.provenance_label}`, thermal: "Subsurface field: OceanEmbed" }}
            testid="cyclone-section"
          />
          <PrintableBrief testid="cyclone-brief" title="CYCLONE OCEAN THERMAL BRIEF">
            <h2>
              {adv.storm_name}
              {isTest ? " — HISTORICAL / TEST EVENT" : ""}
            </h2>
            <dl className="brief-grid">
              <div><dt>External source</dt><dd>{adv.provenance_label}</dd></div>
              <div><dt>Advisory issued</dt><dd>{adv.advisory_issued_at}</dd></div>
              <div><dt>OceanEmbed valid date</dt><dd>{analysis.thermal_field?.valid_date}</dd></div>
              <div><dt>Reconstruction lag</dt><dd>{hours(analysis.thermal_field?.reconstruction_lag_hours ?? null)}</dd></div>
              <div><dt>Highest thermal support along track</dt><dd>{analysis.analysis.summary.highest_category ?? "—"}</dd></div>
              <div><dt>Peak TCHP</dt><dd>{analysis.analysis.summary.tchp.max ? `${analysis.analysis.summary.tchp.max.value.toFixed(1)} kJ/cm²` : "—"}</dd></div>
              <div><dt>Largest 100 m anomaly along track</dt><dd>{analysis.analysis.summary.anomaly["100"]?.max ? signed(analysis.analysis.summary.anomaly["100"].max!.value, 2, "°C") : "—"}</dd></div>
              <div><dt>Strongest thermal segment</dt><dd>{analysis.analysis.summary.strongest_segment ? `${analysis.analysis.summary.strongest_segment.category} · ${analysis.analysis.summary.strongest_segment.lat_range.map((v) => v.toFixed(1)).join("–")}°N / ${analysis.analysis.summary.strongest_segment.lon_range.map((v) => v.toFixed(1)).join("–")}°E` : "—"}</dd></div>
            </dl>
            <p>
              {analysis.analysis.summary.intersects.HIGH || analysis.analysis.summary.intersects.ELEVATED
                ? "Interpretation: the external track crosses a substantial subsurface warm-water reservoir. Monitoring recommendation: compare this segment with official intensity, wind-shear and track guidance."
                : "Interpretation: the external track does not intersect HIGH or ELEVATED thermal-support water in the sampled field."}
            </p>
            <p className="small">
              LIMITATION: OceanEmbed does not forecast cyclone track or intensity. The track is external
              context from {adv.provider}.
            </p>
          </PrintableBrief>
        </div>
      )}

      {!analysis && (
        <PrintableBrief testid="watch-brief" title="OCEAN THERMAL WATCH BRIEF">
          <dl className="brief-grid">
            <div><dt>External cyclone status</dt><dd>{status?.message ?? "Not checked"}</dd></div>
            <div><dt>OceanEmbed valid date</dt><dd>{latestValidDate ?? "—"}</dd></div>
            <div><dt>Reconstruction lag</dt><dd>{hours(latestLagHours)}</dd></div>
            <div>
              <dt>Thermal monitoring areas</dt>
              <dd>
                {monitoring?.areas.length
                  ? monitoring.areas
                      .map((a) => `${a.rank}. ${a.basin ?? `${a.lat.toFixed(2)}°N ${a.lon.toFixed(2)}°E`} ${a.tier} ${a.tchp.toFixed(1)} kJ/cm²`)
                      .join(" · ")
                  : "None under the frozen protocol"}
              </dd>
            </div>
          </dl>
          <p className="small">
            LIMITATION: OceanEmbed describes subsurface thermal conditions only; it does not
            detect, track or forecast cyclones.
          </p>
        </PrintableBrief>
      )}
    </section>
  );
}
