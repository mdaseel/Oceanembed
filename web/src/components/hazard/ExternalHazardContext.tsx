const SOURCES = [
  "Cyclone advisory (IMD / RSMC New Delhi)",
  "Tsunami advisory (INCOIS)",
  "Storm-surge advisory",
  "High-wave advisory",
  "Swell-surge advisory",
];

/** EXTERNAL OCEAN HAZARD CONTEXT — only real authoritative feeds; none connected yet. */
export function ExternalHazardContext() {
  return (
    <details className="panel external-hazards" data-testid="external-hazard-context">
      <summary>
        <span className="eyebrow">EXTERNAL OCEAN HAZARD CONTEXT</span>
      </summary>
      <ul className="scope-list">
        {SOURCES.map((s) => (
          <li key={s}>
            {s}: <strong>NOT CONNECTED</strong>
          </li>
        ))}
      </ul>
      <p className="small muted">
        OceanEmbed does not calculate tsunami, storm-surge, wave or swell hazards. These rows show
        only whether an authoritative external feed is connected; none is in this build.
      </p>
    </details>
  );
}
