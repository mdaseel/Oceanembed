import { format, type Layer, type Palette } from "../field/contract";
import { gradient, type Range } from "../field/colors";
export function Colorbar({
  range,
  layer,
  palette,
  displayGradient,
}: {
  range: Range;
  layer: Layer;
  palette: Palette;
  displayGradient?: string;
}) {
  return (
    <div className="colorbar" aria-label="Color scale in degrees Celsius">
      <span>
        {layer === "anomaly"
          ? "Anomaly from climatology"
          : "Reconstructed temperature"}{" "}
        · °C
      </span>
      {range.count ? (
        <>
          <div
            className="scale"
            style={{ background: displayGradient ?? gradient(layer, palette) }}
          />
          <div className="scale-labels">
            <span>{format(range.min, 2)} °C</span>
            {layer === "anomaly" && <span>0</span>}
            <span>{format(range.max, 2)} °C</span>
          </div>
          <small>
            Displayed data: {format(range.actualMin, 2)} to{" "}
            {format(range.actualMax, 2)} °C
          </small>
        </>
      ) : (
        <p>No supported values at this depth / layer.</p>
      )}
    </div>
  );
}
