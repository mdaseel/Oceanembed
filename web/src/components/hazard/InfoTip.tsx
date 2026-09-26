import { useId } from "react";
import { Info } from "lucide-react";
import { GLOSSARY, type GlossaryKey } from "../../field/hazardIntelligence";

/** A concise plain-language explanation beside a scientific term. */
export function InfoTip({ term }: { term: GlossaryKey }) {
  const id = useId();
  const entry = GLOSSARY[term];
  return (
    <span className="info-tip">
      <button
        type="button"
        className="info-tip-button"
        aria-label={`What is ${entry.term}?`}
        aria-describedby={id}
        data-testid={`tip-${term}`}
      >
        <Info size={12} aria-hidden />
      </button>
      <span role="tooltip" id={id} className="info-tip-body">
        <strong>{entry.term}</strong> {entry.text}
      </span>
    </span>
  );
}
