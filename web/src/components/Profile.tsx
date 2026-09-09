import { lazy, Suspense } from "react";
import { useBathymetry, displayDepthValid } from "../field/bathymetry";
import {
  profile,
  format,
  type FieldView,
  type Selection,
} from "../field/contract";
const Plot = lazy(() => import("./Plot"));
export function Profile({
  field,
  selection,
  depth,
}: {
  field: FieldView;
  selection: Selection;
  depth: number;
}) {
  const rows = profile(field, selection);
  const {data:bathymetry,error:bathymetryError}=useBathymetry();
  const depthValid=(d:number)=>displayDepthValid(field,bathymetry,selection.row,selection.col,d);
  const localDepth=bathymetry?.depths[selection.row*field.lon.length+selection.col];
  return (
    <section className="panel profile-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">SELECTED WATER COLUMN</span>
          <h2>Vertical temperature profile</h2>
        </div>
        <span className="chip">15 depths</span>
      </div>
      {selection.row < 0 ? (
        <p className="empty">
          Location is outside the North Indian Ocean domain.
        </p>
      ) : (
        <>
          <p className="muted small">
            Requested {format(selection.requestedLat, 4)}°N,{" "}
            {format(selection.requestedLon, 4)}°E
            <br />
            Grid {format(field.lat[selection.row], 2)}°N,{" "}
            {format(field.lon[selection.col], 2)}°E ·{" "}
            {selection.status.replaceAll("_", " ")}
          </p>
          {selection.status !== "OK" && (
            <p className="notice">
              This cell has no supported L2 reconstruction. It has not been
              replaced by another location.
            </p>
          )}
          <Suspense fallback={<p className="empty">Loading profile chart…</p>}>
            <p className="muted small" data-testid="profile-bathymetry">
              {localDepth!==undefined && Number.isFinite(localDepth)
                ? `Local ETOPO water depth: ${localDepth.toFixed(1)} m. Below-seafloor points are hidden in the chart; the table retains raw model values.`
                : bathymetryError ? "Bathymetry unavailable: physical depth validity unknown; chart points hidden. Raw values remain in the table."
                : "Physical depth support is being verified; raw values remain in the table."}
            </p>
            <Plot
              data={[
                {
                  x: rows.map((r) =>
                    depthValid(r.depth) && Number.isFinite(r.temperature) ? r.temperature : null,
                  ),
                  y: rows.map((r) => r.depth),
                  name: "OceanEmbed L2",
                  type: "scatter",
                  mode: "lines+markers",
                  line: { color: "#67e8f9", width: 2 },
                  marker: { size: 5 },
                  connectgaps: false,
                  hovertemplate: "%{x:.3f} °C · %{y} m<extra>L2</extra>",
                },
                {
                  x: rows.map((r) =>
                    depthValid(r.depth) && Number.isFinite(r.climatology) ? r.climatology : null,
                  ),
                  y: rows.map((r) => r.depth),
                  name: "L0 climatology",
                  type: "scatter",
                  mode: "lines+markers",
                  line: { color: "#a6adc2", dash: "dot", width: 2 },
                  marker: { size: 4 },
                  connectgaps: false,
                  hovertemplate: "%{x:.3f} °C · %{y} m<extra>L0</extra>",
                },
              ]}
              layout={{
                autosize: true,
                height: 355,
                paper_bgcolor: "transparent",
                plot_bgcolor: "transparent",
                font: { color: "#aebfd5", family: "system-ui", size: 11 },
                margin: { l: 48, r: 14, t: 24, b: 66 },
                xaxis: {
                  title: { text: "Temperature (°C)" },
                  side: "top",
                  gridcolor: "#253147",
                  zeroline: false,
                },
                yaxis: {
                  title: { text: "Depth (m)" },
                  autorange: "reversed",
                  gridcolor: "#253147",
                  zeroline: false,
                },
                legend: { orientation: "h", x: 0, y: -0.12 },
                shapes: [
                  {
                    type: "line",
                    xref: "paper",
                    x0: 0,
                    x1: 1,
                    y0: field.depths[depth],
                    y1: field.depths[depth],
                    line: { color: "#67e8f966", dash: "dot" },
                  },
                ],
                uirevision: field.effectiveDate,
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: "100%" }}
              useResizeHandler
            />
          </Suspense>
          <details>
            <summary>Inspect all profile values</summary>
            <div className="table-scroll">
              <table data-testid="profile-table">
                <thead>
                  <tr>
                    <th>Depth m</th>
                    <th>L2 °C</th>
                    <th>L0 °C</th>
                    <th>Δ °C</th>
                    <th>Physical depth support</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.depth} data-depth={r.depth}>
                      <td>{r.depth}</td>
                      <td>{format(r.temperature)}</td>
                      <td>{format(r.climatology)}</td>
                      <td>{format(r.anomaly)}</td>
                      <td>{localDepth===undefined || !Number.isFinite(localDepth) ? "Unverified"
                        : selection.status!=="OK" ? "Unsupported ocean cell"
                        : r.depth>localDepth ? "Below seafloor — raw output only" : "Within local water depth"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
