import { useId, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";
import { GLOSSARY, type GlossaryKey } from "../../field/hazardIntelligence";

/** A concise plain-language explanation beside a scientific term. */
export function InfoTip({ term }: { term: GlossaryKey }) {
  const id = useId();
  const entry = GLOSSARY[term];
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const show = (button: HTMLButtonElement) => {
    const box = button.getBoundingClientRect();
    setPosition({ left: Math.max(12, Math.min(box.left - 120, window.innerWidth - 272)), top: Math.max(12, Math.min(box.bottom + 8, window.innerHeight - 180)) });
  };
  return (
    <span className="info-tip">
      <button
        type="button"
        className="info-tip-button"
        aria-label={`What is ${entry.term}?`}
        aria-describedby={id}
        data-testid={`tip-${term}`}
        onMouseEnter={(e) => show(e.currentTarget)}
        onMouseLeave={() => setPosition(null)}
        onFocus={(e) => show(e.currentTarget)}
        onBlur={() => setPosition(null)}
        onKeyDown={(e) => { if (e.key === "Escape") setPosition(null); }}
      >
        <Info size={12} aria-hidden />
      </button>
      {position && createPortal(<span role="tooltip" id={id} className="info-tip-body info-tip-floating" style={position}>
        <strong>{entry.term}</strong> {entry.text}
      </span>, document.body)}
    </span>
  );
}
