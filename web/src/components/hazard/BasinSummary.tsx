import type { Bathymetry } from "../../field/bathymetry";
import type { FieldView } from "../../field/contract";
import { basinSummary, signed, type Basins } from "../../field/hazardIntelligence";

/** BASIN THERMAL SUMMARY over the existing Arabian Sea / Bay of Bengal boxes. */
export function BasinSummary({
  field,
  basins,
  bathymetry,
}: {
  field: FieldView;
  basins: Basins | null;
  bathymetry: Bathymetry | null;
}) {
  if (!basins) return null;
  const rows = basinSummary(field, basins, bathymetry);
  const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(0)} %`);
  return (
    <section className="panel basin-summary" data-testid="basin-summary" data-date={field.effectiveDate}>
      <span className="eyebrow">BASIN THERMAL SUMMARY · {field.effectiveDate}</span>
      <div className="table-scroll">
        <table className="level-table">
          <thead>
            <tr>
              <th>Basin</th>
              <th>Median TCHP</th>
              <th>Max TCHP</th>
              <th>HIGH</th>
              <th>ELEVATED</th>
              <th>Max 50 m anom.</th>
              <th>Max 100 m anom.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} data-basin={r.key}>
                <td>{r.name}</td>
                <td>{r.medianTchp === null ? "—" : r.medianTchp.toFixed(1)}</td>
                <td>{r.maxTchp === null ? "—" : r.maxTchp.toFixed(1)}</td>
                <td>{pct(r.highFraction)}</td>
                <td>{pct(r.elevatedFraction)}</td>
                <td>{signed(r.maxAnomaly50, 2)}</td>
                <td>{signed(r.maxAnomaly100, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">
        TCHP in kJ/cm² over cells with a supported value; category fractions are shares of the
        cells the backend categorised; anomalies in °C only where the local water column reaches
        that depth. Missing surface input and shallow bathymetry are excluded separately.
      </p>
    </section>
  );
}
