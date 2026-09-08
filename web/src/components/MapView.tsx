import { useEffect, useRef } from "react";
import { rangeFor, type ScaleMode } from "../field/colors";
import { depthColor as color, depthGradient } from "../field/depthColors";
import {
  type FieldView,
  type Layer,
  type Palette,
  type Selection,
  offset,
} from "../field/contract";
import { Colorbar } from "./Colorbar";
export interface MapProps {
  field: FieldView;
  layer: Layer;
  depth: number;
  palette: Palette;
  selection: Selection;
  scaleMode: ScaleMode;
  onSelect: (lat: number, lon: number) => void;
}
const W = 1440,
  H = 760,
  left = 66,
  top = 45,
  width = 1320,
  height = 555;
export function drawMap(
  canvas: HTMLCanvasElement,
  {
    field: f,
    layer,
    depth,
    palette,
    selection,
    scaleMode,
  }: Omit<MapProps, "onSelect">,
) {
  canvas.width = W;
  canvas.height = H;
  const c = canvas.getContext("2d")!;
  c.fillStyle = "#06080d";
  c.fillRect(0, 0, W, H);
  const range = rangeFor(f, layer, [depth], scaleMode),
    cw = width / f.lon.length,
    ch = height / f.lat.length;
  for (let r = 0; r < f.lat.length; r++)
    for (let col = 0; col < f.lon.length; col++) {
      const i = r * f.lon.length + col,
        v = f[layer][offset(f, r, col, depth)];
      // Land is a neutral dark grey, matching the 3D view; cells with no valid
      // input for this date stay near-black. Neither is ever coloured by
      // temperature, and neither carries any elevation.
      c.fillStyle = !f.ocean[i]
        ? "#182a30"
        : !f.inputValid[i] || !Number.isFinite(v)
          ? "#0d1119"
          : `rgb(${color(v, range, layer, palette).join(",")})`;
      c.fillRect(
        left + col * cw,
        top + (f.lat.length - 1 - r) * ch,
        cw + 0.25,
        ch + 0.25,
      );
    }
  c.font = "17px system-ui";
  c.strokeStyle = "#a2bad52b";
  c.lineWidth = 1;
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
    `${f.effectiveDate}  /  ${f.depths[depth]} m  /  ${layer === "temperature" ? "Reconstructed Subsurface Temperature" : "Anomaly from Climatology"}`,
    left,
    28,
  );
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
  c.font = "16px system-ui";
  c.fillStyle = "#a3b4cb";
  c.fillText(
    `Equirectangular grid · neutral land / dark unavailable · no spatial interpolation · color scale: ${
      scaleMode === "field"
        ? "whole reconstruction, all 15 depths (compare dates using their displayed ranges)"
        : "this depth only (NOT comparable across depths or dates)"
    }`,
    left,
    660,
  );
  if (range.count) {
    for (let x = 0; x < 300; x++) {
      c.fillStyle = `rgb(${color(range.min + (x / 299) * (range.max - range.min), range, layer, palette)})`;
      c.fillRect(left + x, 680, 1, 12);
    }
    c.fillStyle = "#d5dfed";
    c.fillText(
      `${range.min.toFixed(2)} to ${range.max.toFixed(2)} °C`,
      left + 315,
      693,
    );
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
export function MapView(props: MapProps) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (ref.current) drawMap(ref.current, props);
  }, [
    props.field,
    props.layer,
    props.depth,
    props.palette,
    props.selection,
    props.scaleMode,
  ]);
  return (
    <>
      <canvas
        ref={ref}
        className="map-canvas"
        data-testid="field-map"
        aria-label="North Indian Ocean map. Click to select a grid cell, or use the coordinate form."
        role="img"
        onClick={(event) => {
          const rect = event.currentTarget.getBoundingClientRect(),
            x = ((event.clientX - rect.left) / rect.width) * W,
            y = ((event.clientY - rect.top) / rect.height) * H;
          if (x < left || x >= left + width || y < top || y >= top + height)
            return;
          const lon = Math.max(
            45,
            Math.min(
              105,
              45 + (((x - left) / width) * props.field.lon.length - 0.5) * 0.25,
            ),
          );
          const lat = Math.max(
            5,
            Math.min(
              30,
              30 - (((y - top) / height) * props.field.lat.length - 0.5) * 0.25,
            ),
          );
          props.onSelect(lat, lon);
        }}
      />
      <Colorbar
        range={rangeFor(
          props.field,
          props.layer,
          [props.depth],
          props.scaleMode,
        )}
        layer={props.layer}
        palette={props.palette}
        displayGradient={depthGradient(props.layer, props.palette)}
      />
    </>
  );
}
