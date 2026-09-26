import { useEffect, useState } from "react";
import { ShieldCheck, X } from "lucide-react";
import { getJson } from "../../field/api";
import type { Integrity } from "./scienceApi";

const tone = (state: string) =>
  ["VERIFIED", "COMPLETED", "PROTECTED", "PASS", "FROZEN", "WITHHELD"].includes(state)
    ? "ok"
    : state.includes("QUALIFIED")
      ? "warn"
      : "bad";

/** SCIENTIFIC INTEGRITY: computed checks, one click away from every workspace. */
export function IntegrityDrawer() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Integrity | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || data) return;
    getJson<Integrity>("/api/science/integrity")
      .then((d) => setData(d?.items ? d : null))
      .catch((e) => setError((e as Error).message));
  }, [open, data]);

  useEffect(() => {
    if (!open) return;
    const close = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  return (
    <>
      <button
        type="button"
        className="integrity-button"
        data-testid="integrity-open"
        onClick={() => setOpen(true)}
      >
        <ShieldCheck size={13} aria-hidden /> SCIENTIFIC INTEGRITY
      </button>
      {open && (
        <>
          <div className="ws-drawer-backdrop" onClick={() => setOpen(false)} />
          <aside className="ws-drawer" role="dialog" aria-label="Scientific integrity" data-testid="integrity-drawer">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">COMPUTED FROM THE REPOSITORY, NOT ASSERTED</span>
                <h2>Scientific integrity</h2>
              </div>
              <button type="button" className="integrity-button" onClick={() => setOpen(false)} aria-label="Close">
                <X size={13} aria-hidden />
              </button>
            </div>
            {error && <p className="notice">{error}</p>}
            {!data && !error && <p className="muted small">Checking frozen artefacts…</p>}
            {data && (
              <>
                <ul className="integrity-list">
                  {data.items.map((item) => (
                    <li key={item.label} data-state={item.state}>
                      <span className="label">{item.label}</span>
                      <span className={`ws-pill ${tone(item.state)}`}>{item.state}</span>
                      <small>
                        {item.value}
                        <br />
                        {item.how}
                      </small>
                    </li>
                  ))}
                </ul>
                <div>
                  <span className="eyebrow">RESEARCH → OPERATIONS</span>
                  <ol className="pipeline" data-testid="integrity-pipeline">
                    {data.pipeline.map((p) => (
                      <li key={p.stage}>
                        {p.stage}
                        <small>{p.detail}</small>
                      </li>
                    ))}
                  </ol>
                </div>
              </>
            )}
          </aside>
        </>
      )}
    </>
  );
}
