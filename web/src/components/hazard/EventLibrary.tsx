import { useState } from "react";
import type { EventLibraryPayload } from "./api";

const BASINS = ["ALL", "Bay of Bengal", "Arabian Sea"] as const;
const splitText = (split: string) =>
  split === "train"
    ? "IN-SAMPLE · training period"
    : split === "validation"
      ? "Validation period"
      : split === "test"
        ? "Out-of-sample · test period"
        : "Mixed split";

/** HISTORICAL CYCLONE INTELLIGENCE — the enabled events, never ranked by severity. */
export function EventLibrary({
  library,
  selected,
  onSelect,
  compareIds,
  onToggleCompare,
}: {
  library: EventLibraryPayload;
  selected: string;
  onSelect: (eventId: string) => void;
  compareIds: string[];
  onToggleCompare: (eventId: string) => void;
}) {
  const [basin, setBasin] = useState<(typeof BASINS)[number]>("ALL");
  const events = library.events.filter((e) => basin === "ALL" || e.basin.includes(basin));
  const excluded = library.candidates.filter((c) => !c.enabled);
  return (
    <section className="panel event-library" data-testid="event-library">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">HISTORICAL CYCLONE INTELLIGENCE</span>
          <h2>Cyclone event library</h2>
        </div>
        <div className="segmented" role="group" aria-label="Basin filter">
          {BASINS.map((b) => (
            <button
              key={b}
              type="button"
              className={basin === b ? "active" : ""}
              aria-pressed={basin === b}
              data-testid={`basin-filter-${b.toLowerCase().replaceAll(" ", "-")}`}
              onClick={() => setBasin(b)}
            >
              {b === "ALL" ? "All basins" : b}
            </button>
          ))}
        </div>
      </div>
      <ul className="event-cards">
        {events.map((e) => (
          <li key={e.event_id}>
            <button
              type="button"
              className={`event-card${selected === e.event_id ? " active" : ""}`}
              data-testid={`event-card-${e.event_id}`}
              aria-pressed={selected === e.event_id}
              onClick={() => onSelect(e.event_id)}
            >
              <span className="event-card-name">
                {e.short_name} <small>{e.season}</small>
              </span>
              <span className="event-card-basin">{e.basin}</span>
              <span className="small muted">
                Replay {e.window_start} → {e.window_end} · {e.replay_days} days
              </span>
              <span className={`split-pill split-${e.split}`}>{splitText(e.split)}</span>
            </button>
            <label className="compare-toggle">
              <input
                type="checkbox"
                checked={compareIds.includes(e.event_id)}
                disabled={!compareIds.includes(e.event_id) && compareIds.length >= 4}
                onChange={() => onToggleCompare(e.event_id)}
                aria-label={`Compare ${e.short_name} ${e.season}`}
              />
              Compare
            </label>
          </li>
        ))}
      </ul>
      <p className="small muted" data-testid="event-exclusions">
        {excluded.length
          ? `Not enabled: ${excluded
              .map((c) => `${c.name} ${c.season} — ${c.exclusion_reasons.join("; ")}`)
              .join(" · ")}`
          : `All ${library.candidates.length} candidates passed the data-availability checks.`}{" "}
        Windows follow a frozen external-chronology rule ({library.rule}); tracks are{" "}
        {library.source?.dataset}. No cyclone severity is assigned by OceanEmbed.
      </p>
    </section>
  );
}
