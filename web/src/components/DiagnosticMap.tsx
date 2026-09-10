import { useEffect, useRef, useState } from "react";
import {
  DIAGNOSTIC_NAME,
  DIAGNOSTIC_UNIT,
  type DiagnosticKind,
  type FieldView,
  type Selection,
} from "../field/contract";
import {
  NO_CROSSING_RGB,
  UNSUPPORTED_RGB,
  diagnosticColor,
  diagnosticGradient,
  diagnosticRange,
  diagnosticRaster,
} from "../field/diagnostics";
import { PROJECTION, pixelToLatLon } from "./MapView";
import { currentMapRelief, loadMapRelief } from "../field/mapAppearance";

export interface DiagnosticMapProps {
  field: FieldView;
  kind: DiagnosticKind;
  selection: Selection;
  onSelect: (lat: number, lon: number) => void;
}
const { W, H, left, top, width, height } = PROJECTION;

export function drawDiagnostic(
  canvas: HTMLCanvasElement,
  { field: f, kind, selection }: Omit<DiagnosticMapProps, "onSelect">,
) {
  canvas.width = W;
  canvas.height = H;
  const c = canvas.getContext("2d")!;
  c.fillStyle = "#06080d";
  c.fillRect(0, 0, W, H);
  const range = diagnosticRange(f, kind);
  const { pixels, counts } = diagnosticRaster(f, kind, range, width, height);
  const image = c.createImageData(width, height);
  if (image?.data) {
    image.data.set(pixels);
    c.putImageData(image, left, top);
  }
  // Same ETOPO shaded land as the temperature map, drawn over the field so the
  // two layers read as one cartography rather than two different maps.
  const relief = currentMapRelief();
  if (relief) {
    c.imageSmoothingEnabled = true;
    c.imageSmoothingQuality = "high";
    c.drawImage(relief, left, top, width, height);
  }
  const cw = width / f.lon.length,
    ch = height / f.lat.length;
  c.strokeStyle = "#a2bad512";
  c.lineWidth = 1;
  c.font = "17px system-ui";
  for (let lon = 45; lon <= 105; lon += 10) {
    const x = left + ((lon - 45) / 0.25 + 0.5) * cw;
    c.beginPath();
    c.moveTo(x, top);
    c.lineTo(x, top + height);
    c.stroke();
    c.fillStyle = "#a3b4cb";
    c.fillText(`${lon}°E`, x - 20, top + height + 30);
  }
  for (let lat = 5; lat <= 30; lat += 5) {
    const y = top + ((30 - lat) / 0.25 + 0.5) * ch;
    c.beginPath();
    c.moveTo(left, y);
    c.lineTo(left + width, y);
    c.stroke();
    c.fillText(`${lat}°N`, 12, y + 5);
  }
  c.fillStyle = "#ced9e7";
  c.font = "600 19px system-ui";
  c.fillText(
    `${f.effectiveDate}  /  ${DIAGNOSTIC_NAME[kind]}  (${DIAGNOSTIC_UNIT[kind]})`,
    left,
    28,
  );
  if (relief) {
    c.font = "500 18px system-ui";
    c.fillStyle = "#91b2be";
    c.textAlign = "center";
    for (const [name, lon, lat] of [
      ["I N D I A", 78, 23],
      ["ARABIA", 49.5, 24],
      ["MYANMAR", 96, 22],
    ] as const) {
      c.fillText(
        name,
        left + ((lon - 45) / 0.25 + 0.5) * cw,
        top + ((30 - lat) / 0.25 + 0.5) * ch,
      );
    }
    c.textAlign = "start";
  }
  if (selection.row >= 0) {
    const x = left + (selection.col + 0.5) * cw,
      y = top + (f.lat.length - selection.row - 0.5) * ch;
    c.strokeStyle = "#ffffff";
    c.lineWidth = 3;
    c.beginPath();
    c.arc(x, y, 9, 0, Math.PI * 2);
    c.stroke();
    c.strokeStyle = "#060d19";
    c.lineWidth = 2;
    c.beginPath();
    c.arc(x, y, 12, 0, Math.PI * 2);
    c.stroke();
  }
  c.font = "14px system-ui";
  c.fillStyle = "#a3b4cb";
  c.fillText(
    `Smooth display interpolation · dark = unavailable · ${
      relief ? "ETOPO shaded land" : "land relief unavailable/loading"
    } · depth-integrated from the same reconstructed profiles, so the depth selector does not apply to this layer`,
    left,
    660,
  );
  if (range.count) {
    for (let x = 0; x < 300; x++) {
      // Same function the raster uses, so the bar cannot drift from the map.
      const [r, g, b] = diagnosticColor(
        range.min + (x / 299) * (range.max - range.min),
        range,
        kind,
      );
      c.fillStyle = `rgb(${r},${g},${b})`;
      c.fillRect(left + x, 680, 1, 12);
    }
    c.fillStyle = "#d5dfed";
    c.fillText(
      `${range.min.toFixed(1)} to ${range.max.toFixed(1)} ${DIAGNOSTIC_UNIT[kind]}` +
        `   ·   ${counts.shown.toLocaleString()} cells`,
      left + 315,
      693,
    );
  }
  // Each failure class is spelled out on the map itself, because a reader who
  // never opens the legend must still not read either as a low value — and the
  // two are scientifically different, so they never share a swatch.
  const swatch = (
    originX: number,
    rgb: readonly number[],
    dim: number,
    diagonal: 1 | -1,
    label: string,
  ) => {
    for (let x = 0; x < 26; x++)
      for (let y = 0; y < 12; y++) {
        const hatch =
          (diagonal === 1 ? (x + y) % 8 : (x - y + 8192) % 8) < 3;
        const [r, g, b] = hatch ? rgb : rgb.map((ch) => Math.round(ch * dim));
        c.fillStyle = `rgb(${r},${g},${b})`;
        c.fillRect(originX + x, 680 + y, 1, 1);
      }
    c.fillStyle = "#d5dfed";
    c.fillText(label, originX + 34, 693);
  };
  let legendX = left + 560;
  if (counts.noCrossing) {
    swatch(legendX, NO_CROSSING_RGB, 0.55, 1,
      `no 26 °C crossing (${counts.noCrossing.toLocaleString()})`);
    legendX += 300;
  }
  if (counts.unsupported) {
    swatch(legendX, UNSUPPORTED_RGB, 0.62, -1,
      `below local seafloor — insufficient water column (${counts.unsupported.toLocaleString()})`);
  }
  c.font = "12px system-ui";
  c.fillStyle = "#94a8c1";
  c.fillText(f.credits, left, 724);
  c.fillText(
    `OceanEmbed L2 · ${f.provenance.l2_state_dict_sha256} · ${f.provenance.inference_source}`,
    left,
    745,
  );
}

export function DiagnosticMap(props: DiagnosticMapProps) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [reliefReady, setReliefReady] = useState(!!currentMapRelief());
  useEffect(() => {
    let active = true;
    loadMapRelief()
      .then(() => {
        if (active) setReliefReady(true);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (ref.current) drawDiagnostic(ref.current, props);
  }, [props.field, props.kind, props.selection, reliefReady]);
  const range = diagnosticRange(props.field, props.kind);
  const convention = props.field.diagnostics?.convention ?? {};
  return (
    <>
      <canvas
        ref={ref}
        className="map-canvas"
        data-testid="diagnostic-map"
        data-kind={props.kind}
        data-relief={reliefReady ? "ready" : "unavailable"}
        aria-label={`${DIAGNOSTIC_NAME[props.kind]} map. Click to select a grid cell.`}
        role="img"
        onClick={(event) => {
          const rect = event.currentTarget.getBoundingClientRect(),
            x = ((event.clientX - rect.left) / rect.width) * W,
            y = ((event.clientY - rect.top) / rect.height) * H;
          const hit = pixelToLatLon(x, y, props.field);
          if (hit) props.onSelect(hit[0], hit[1]);
        }}
      />
      <div className="colorbar" data-testid="diagnostic-colorbar">
        <span className="colorbar-label">
          {DIAGNOSTIC_NAME[props.kind]} ({DIAGNOSTIC_UNIT[props.kind]})
        </span>
        <div
          className="colorbar-ramp"
          style={{ background: diagnosticGradient(props.kind) }}
        />
        <span className="colorbar-range">
          {range.count
            ? `${range.actualMin.toFixed(1)} to ${range.actualMax.toFixed(1)}`
            : "No values for this date"}
        </span>
      </div>
      <p className="muted small" data-testid="diagnostic-note">
        {String(convention[props.kind] ?? "")} {String(convention.constants_source ?? "")}{" "}
        Orange-hatched cells have no 26 °C crossing within the reconstructed
        column and carry no value — they are not zero. Charcoal-hatched cells
        resolved a value that sits <strong>below the local ETOPO seafloor</strong>,
        so there is no water column to support it; the raw Phase 7C value is
        preserved and exported unchanged, but it is not presented as a usable
        diagnostic. A column that is entirely below 26 °C keeps TCHP = 0, which
        is a real answer and not a support failure.
      </p>
    </>
  );
}
