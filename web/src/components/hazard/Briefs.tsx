import { useEffect, useState, type ReactNode } from "react";
import { coordText, signed } from "../../field/hazardIntelligence";
import { getJson, type EventBriefPayload } from "./api";

/** The dashboard map currently on screen, captured for a printed brief. */
function mapSnapshot(): string | null {
  const canvas = document.querySelector<HTMLCanvasElement>(
    '[data-testid="hazard-map"], [data-testid="diagnostic-map"], [data-testid="field-map"]',
  );
  try {
    return canvas ? canvas.toDataURL("image/png") : null;
  } catch {
    return null;
  }
}

/** Print only the brief: every other element is hidden by the print stylesheet. */
export function PrintableBrief({
  testid,
  title,
  children,
}: {
  testid: string;
  title: string;
  children: ReactNode;
}) {
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);
  useEffect(() => {
    if (!printing) return;
    document.body.classList.add("printing-brief");
    const done = () => {
      document.body.classList.remove("printing-brief");
      setPrinting(false);
    };
    window.addEventListener("afterprint", done, { once: true });
    const t = setTimeout(() => window.print(), 50);
    return () => {
      clearTimeout(t);
      window.removeEventListener("afterprint", done);
    };
  }, [printing]);
  return (
    <article className={`brief${printing ? " print-target" : ""}`} data-testid={testid}>
      <div className="panel-heading compact">
        <span className="eyebrow">{title}</span>
        <div className="section-tools no-print">
          <button type="button" className="btn" onClick={() => setSnapshot(mapSnapshot())}>
            Attach current map
          </button>
          <button
            type="button"
            className="btn"
            data-testid={`${testid}-print`}
            onClick={() => {
              setSnapshot((s) => s ?? mapSnapshot());
              setPrinting(true);
            }}
          >
            Print / save brief
          </button>
        </div>
      </div>
      {children}
      {snapshot && (
        <figure className="brief-map">
          <img src={snapshot} alt="Thermal map at the time the brief was prepared" />
          <figcaption className="small muted">Map as displayed when the brief was prepared.</figcaption>
        </figure>
      )}
    </article>
  );
}

/** CYCLONE OCEAN RESPONSE BRIEF for one historical event, assembled by the backend. */
export function EventBrief({ eventId }: { eventId: string }) {
  const [brief, setBrief] = useState<EventBriefPayload | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    setBrief(null);
    setError("");
    getJson<EventBriefPayload>(`/api/events/${eventId}/brief`)
      .then((b) => live && setBrief(b))
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, [eventId]);
  if (error) return <p className="notice">{error}</p>;
  if (!brief) return <p className="muted" role="status">Assembling the brief…</p>;
  const m = brief.metrics;
  const region = brief.strongest_affected_thermal_region;
  return (
    <PrintableBrief testid="event-brief" title={brief.title}>
      <h2>{brief.event}</h2>
      <dl className="brief-grid">
        <div><dt>Basin</dt><dd>{brief.basin}</dd></div>
        <div><dt>Replay window</dt><dd>{brief.event_dates.join(" → ")}</dd></div>
        <div><dt>Peak / landfall</dt><dd>{brief.peak} / {brief.landfall}</dd></div>
        <div><dt>Track source</dt><dd>{brief.track_source}</dd></div>
        <div><dt>Pre-event TCHP</dt><dd>{m.pre_event_tchp == null ? "—" : `${m.pre_event_tchp.toFixed(1)} kJ/cm²`}</dd></div>
        <div><dt>Wake minimum</dt><dd>{m.wake_min_tchp ? `${m.wake_min_tchp.value.toFixed(1)} kJ/cm² (${m.wake_min_tchp.date})` : "—"}</dd></div>
        <div><dt>TCHP change</dt><dd>{signed(m.tchp_change, 1, "kJ/cm²")}{m.tchp_change_pct == null ? "" : ` (${signed(m.tchp_change_pct, 0)} %)`}</dd></div>
        <div><dt>D26 change</dt><dd>{signed(m.d26_change_m, 1, "m")}</dd></div>
        <div><dt>Strongest 0 m cooling</dt><dd>{brief.strongest_subsurface_cooling_c["0"] ? `${signed(brief.strongest_subsurface_cooling_c["0"]!.value, 2, "°C")} at ${coordText(brief.strongest_subsurface_cooling_c["0"]!.lat, brief.strongest_subsurface_cooling_c["0"]!.lon)}` : "—"}</dd></div>
        <div><dt>Strongest 100 m cooling</dt><dd>{brief.strongest_subsurface_cooling_c["100"] ? `${signed(brief.strongest_subsurface_cooling_c["100"]!.value, 2, "°C")} at ${coordText(brief.strongest_subsurface_cooling_c["100"]!.lat, brief.strongest_subsurface_cooling_c["100"]!.lon)}` : "—"}</dd></div>
        <div><dt>Strongest affected thermal region</dt><dd>{region ? `${signed(region.value, 1, "kJ/cm²")} ΔTCHP at ${region.basin ? `${region.basin}, ` : ""}${coordText(region.lat, region.lon)}` : "—"}</dd></div>
        <div><dt>End of window</dt><dd>{m.final ? `${m.final.date}: ${signed(m.final_vs_pre_tchp, 1, "kJ/cm²")} vs pre-event` : "—"}</dd></div>
      </dl>
      <h3>INTERPRETATION</h3>
      <ul>{brief.interpretation.map((s) => <li key={s}>{s}</li>)}</ul>
      <h3>LIMITATIONS</h3>
      <ul>{brief.limitations.map((s) => <li key={s}>{s}</li>)}</ul>
      <h3>PROVENANCE</h3>
      <p className="small">
        {String(brief.provenance.model)} · L2 {String(brief.provenance.l2_state_dict_sha256).slice(0, 16)}… ·
        encoder {String(brief.provenance.l2_encoder_sha256).slice(0, 16)}… · split{" "}
        {String(brief.provenance.split)} · phases: {String(brief.provenance.phase_rule)}
      </p>
      <p className="small muted">{brief.non_prediction}</p>
    </PrintableBrief>
  );
}
