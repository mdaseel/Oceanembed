import { Pause, Play, RotateCcw, StepBack, StepForward } from "lucide-react";
import { phaseShort, shortDay } from "../../field/hazardIntelligence";

export interface Frame {
  date: string;
  available: boolean;
  /** Frozen segment label (historical) — display only. */
  phase?: string;
  reason?: string;
  marker?: string;
}
export const SPEEDS = [
  { label: "0.5×", ms: 2600 },
  { label: "1×", ms: 1500 },
  { label: "2×", ms: 750 },
];

/**
 * Play / pause / step over REAL dates only. Every chip is one calendar day;
 * a day without a qualified reconstruction stays visible, says why, and is
 * never requested.
 */
export function PlaybackBar({
  id,
  frames,
  current,
  playing,
  busy,
  speed,
  onSpeed,
  onPlay,
  onPause,
  onStep,
  onRestart,
  onSelect,
  onUnavailable,
  playLabel,
  stepNoun,
  disabledReason,
  skipped = [],
}: {
  id: string;
  frames: Frame[];
  current: string | null;
  playing: boolean;
  busy: boolean;
  speed: number;
  onSpeed: (ms: number) => void;
  onPlay: () => void;
  onPause: () => void;
  onStep: (direction: -1 | 1) => void;
  onRestart: () => void;
  onSelect: (date: string) => void;
  onUnavailable?: (date: string) => void;
  playLabel: string;
  stepNoun: string;
  disabledReason?: string;
  skipped?: string[];
}) {
  const none = !frames.some((f) => f.available);
  return (
    <div
      className="playback"
      data-testid={`${id}-playback`}
      data-playing={playing ? "true" : "false"}
      data-busy={busy ? "true" : "false"}
    >
      <div className="playback-controls">
        {playing ? (
          <button
            type="button"
            className="play-button"
            onClick={onPause}
            data-testid={`${id}-pause`}
          >
            <Pause size={16} aria-hidden /> PAUSE
          </button>
        ) : (
          <button
            type="button"
            className="play-button"
            onClick={onPlay}
            disabled={!!disabledReason || none}
            data-testid={`${id}-play`}
          >
            <Play size={16} aria-hidden /> {playLabel}
          </button>
        )}
        <button
          type="button"
          className="icon-button"
          aria-label={`Previous ${stepNoun}`}
          onClick={() => onStep(-1)}
          disabled={none}
        >
          <StepBack size={15} aria-hidden />
        </button>
        <button
          type="button"
          className="icon-button"
          aria-label={`Next ${stepNoun}`}
          onClick={() => onStep(1)}
          disabled={none}
        >
          <StepForward size={15} aria-hidden />
        </button>
        <button
          type="button"
          className="icon-button"
          aria-label="Restart"
          onClick={onRestart}
          disabled={none}
        >
          <RotateCcw size={15} aria-hidden />
        </button>
        <label className="speed">
          SPEED
          <select
            aria-label="Playback speed"
            value={speed}
            onChange={(e) => onSpeed(Number(e.target.value))}
          >
            {SPEEDS.map((s) => (
              <option key={s.ms} value={s.ms}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <span className="playback-status" role="status" data-testid={`${id}-status`}>
          {busy
            ? "Loading the next real reconstruction…"
            : playing
              ? "Playing independent daily reconstructions"
              : "Paused"}
        </span>
      </div>
      {disabledReason && (
        <p className="notice" data-testid={`${id}-disabled`}>
          {disabledReason}
        </p>
      )}
      <ol className="timeline" aria-label="Replay dates">
        {frames.map((f) => {
          const selected = f.date === current;
          const state = selected ? "SELECTED" : f.available ? "AVAILABLE" : "UNAVAILABLE";
          const phase = f.phase ? phaseShort(f.phase).toLowerCase() : "";
          return (
            <li key={f.date}>
              <button
                type="button"
                className={`timeline-chip state-${state.toLowerCase()}${
                  phase ? ` phase-${phase}` : ""
                }${skipped.includes(f.date) ? " skipped" : ""}`}
                data-testid={`${id}-day-${f.date}`}
                data-state={state}
                data-phase={f.phase ?? ""}
                aria-current={selected ? "date" : undefined}
                aria-disabled={f.available ? undefined : "true"}
                title={
                  f.available
                    ? `${f.date}${f.phase ? ` · ${f.phase}` : ""}`
                    : (f.reason ?? "Not qualified")
                }
                onClick={() => (f.available ? onSelect(f.date) : onUnavailable?.(f.date))}
              >
                <span className="chip-date">{shortDay(f.date)}</span>
                <span className="chip-mark" aria-hidden>
                  {f.available ? "✓" : "—"}
                </span>
                {f.marker && <span className="chip-marker">{f.marker}</span>}
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
