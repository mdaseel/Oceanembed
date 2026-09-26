import {
  diagnosticAt,
  format,
  hazardAt,
  offset,
  type FieldView,
  type Selection,
} from "../../field/contract";
import {
  NOT_A_PROBABILITY,
  bandText,
  basinOf,
  boundaryDistance,
  categoryMeaning,
  coordText,
  signed,
  type Basins,
  type MonitoringArea,
} from "../../field/hazardIntelligence";
import { InfoTip } from "./InfoTip";

/**
 * DISASTER-MANAGEMENT INTERPRETATION for the selected location. The category
 * is the backend's; every sentence is conditional and none is a forecast.
 */
export function InterpretationCard({
  field: f,
  selection,
  mode,
  basins,
  topArea,
  onArea,
}: {
  field: FieldView;
  selection: Selection;
  mode: "historical" | "nrt";
  basins: Basins | null;
  topArea: MonitoringArea | null;
  onArea: (area: MonitoringArea) => void;
}) {
  const here = hazardAt(f, selection);
  const label = here?.label ?? "NOT_CATEGORIZED";
  const meaning = categoryMeaning(label);
  const tchp = diagnosticAt(f, "tchp", selection);
  const d26 = diagnosticAt(f, "d26", selection);
  const tchpOk =
    !!tchp && Number.isFinite(tchp.value) && tchp.physical === "SUPPORTED";
  const d26Withheld = !!f.diagnostics?.withheld?.includes("d26");
  const d26Ok =
    !d26Withheld && !!d26 && Number.isFinite(d26.value) && d26.physical === "SUPPORTED";
  const k100 = f.depths.indexOf(100);
  const anomaly100 =
    selection.row >= 0 && k100 >= 0
      ? f.anomaly[offset(f, selection.row, selection.col, k100)]
      : NaN;
  const thresholds = f.hazard?.thresholds ?? null;
  const place =
    selection.row >= 0
      ? basinOf(f.lat[selection.row], f.lon[selection.col], basins)
      : null;
  const distance = tchpOk ? boundaryDistance(tchp.value, thresholds) : null;
  const rmse = f.hazard?.error.rmse;
  const reason =
    selection.row < 0
      ? "The selected location is outside the reconstruction domain."
      : tchp && !Number.isFinite(tchp.value)
        ? tchp.status === "SURFACE_BELOW_26"
          ? "The whole column is below 26 °C."
          : "TCHP is unavailable at this cell."
        : tchp && tchp.physical !== "SUPPORTED"
          ? "There is no water column to support TCHP here."
          : "";

  const evidence: string[] = [];
  if (tchpOk) evidence.push(`TCHP ${format(tchp.value, 1)} kJ/cm²`);
  if (Number.isFinite(anomaly100))
    evidence.push(
      `${anomaly100 > 0 ? "Positive" : anomaly100 < 0 ? "Negative" : "Zero"} 100 m temperature anomaly (${signed(anomaly100, 2, "°C")})`,
    );
  if (d26Ok)
    evidence.push(`Water warmer than 26 °C reaches ${format(d26.value, 1)} m (D26)`);
  if (d26Withheld) evidence.push("D26 withheld — operational qualification did not pass");

  return (
    <section
      className={`panel interp-card cat-${label.toLowerCase()}`}
      data-testid="interpretation"
      data-category={label}
    >
      <span className="eyebrow">
        {mode === "nrt"
          ? "CURRENT QUALIFIED THERMAL STATE"
          : "DISASTER-MANAGEMENT INTERPRETATION"}
      </span>
      <div className="interp-headline" data-testid="hazard-level">
        <span className="category-swatch" aria-hidden />
        <strong>{meaning.headline}</strong>
        <InfoTip term="thermalSupport" />
      </div>
      <p className="interp-place">
        {selection.row >= 0
          ? `${place ? `${place} · ` : ""}${coordText(f.lat[selection.row], f.lon[selection.col])}`
          : "Outside domain"}{" "}
        · valid {f.effectiveDate}
      </p>
      {reason && <p className="small muted">{reason}</p>}
      <dl className="metric-list">
        <div>
          <dt>
            TCHP <InfoTip term="tchp" />
          </dt>
          <dd data-testid="interp-tchp">
            {tchpOk ? `${format(tchp.value, 1)} kJ/cm²` : "Unavailable"}
          </dd>
        </div>
        <div>
          <dt>
            100 m anomaly <InfoTip term="anomaly" />
          </dt>
          <dd data-testid="interp-anomaly">
            {Number.isFinite(anomaly100) ? signed(anomaly100, 2, "°C") : "Unavailable"}
          </dd>
        </div>
        <div>
          <dt>
            D26 <InfoTip term="d26" />
          </dt>
          <dd data-testid="interp-d26" className={d26Withheld ? "withheld" : ""}>
            {d26Withheld ? "WITHHELD" : d26Ok ? `${format(d26.value, 1)} m` : "Unavailable"}
          </dd>
        </div>
      </dl>
      {thresholds && label !== "NOT_CATEGORIZED" && (
        <p className="band small">{bandText(label, thresholds)}</p>
      )}
      <div className="meaning">
        <h3>WHAT THIS MEANS</h3>
        <p>{meaning.meaning}</p>
      </div>
      <div className="meaning">
        <h3>WHY THIS MATTERS</h3>
        <p>{meaning.why}</p>
      </div>
      <div className="meaning">
        <h3>DISASTER RELEVANCE</h3>
        <p data-testid="interp-relevance">{meaning.relevance}</p>
      </div>
      <div className="meaning attention">
        <h3>ATTENTION</h3>
        <p>{meaning.attention}</p>
      </div>
      {evidence.length > 0 && (
        <div className="evidence">
          <h3>MAIN EVIDENCE</h3>
          <ul>
            {evidence.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
          {distance !== null && rmse !== undefined && (
            <p className="small muted">
              TCHP is {distance.toFixed(1)} kJ/cm² from the nearest frozen boundary; the
              cell-level TCHP RMSE is {rmse} kJ/cm²
              {distance < rmse
                ? ", so a neighbouring category cannot be excluded at a single cell."
                : "."}
            </p>
          )}
        </div>
      )}
      {mode === "nrt" && topArea && (
        <div className="main-area" data-testid="main-area">
          <h3>MAIN AREA TO MONITOR</h3>
          <button type="button" className="link-button" onClick={() => onArea(topArea)}>
            {topArea.basin ? `${topArea.basin} · ` : ""}
            {coordText(topArea.lat, topArea.lon)} · {topArea.tier} · TCHP{" "}
            {topArea.tchp.toFixed(1)} kJ/cm²
          </button>
        </div>
      )}
      <p className="not-probability" data-testid="not-probability">
        {NOT_A_PROBABILITY} This does not predict cyclone occurrence or intensity.
      </p>
    </section>
  );
}
