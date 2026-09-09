import { useEffect, useRef, useState } from "react";
import { rangeFor, type ScaleMode } from "../field/colors";
import { depthColor as color, depthGradient } from "../field/depthColors";
import {
  type FieldView,
  type Layer,
  type Palette,
  type Selection,
} from "../field/contract";
import { Colorbar } from "./Colorbar";
import { currentMapRelief, loadMapRelief, mapRaster } from "../field/mapAppearance";
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
const rasterCache = new WeakMap<FieldView, Map<string, Uint8ClampedArray>>();
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
  let cached = rasterCache.get(f);
  if (!cached) rasterCache.set(f, cached = new Map());
  const key = `${layer}/${depth}/${palette}/${range.min}/${range.max}`;
  let pixels = cached.get(key);
  if (!pixels) {
    pixels = mapRaster(f,layer,depth,palette,range,width,height);
    if (cached.size >= 6) cached.delete(cached.keys().next().value!);
    cached.set(key,pixels);
  }
  const imageData = c.createImageData(width,height);
  if (imageData?.data) {
    imageData.data.set(pixels);
    c.putImageData(imageData,left,top);
  }
  const relief = currentMapRelief();
  if (relief) {
    c.imageSmoothingEnabled = true;
    c.imageSmoothingQuality = "high";
    c.drawImage(relief,left,top,width,height);
  }
  c.font = "17px system-ui";
  c.strokeStyle = "#a2bad512";
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
  if (relief) {
    c.font = "500 18px system-ui";
    c.fillStyle = "#91b2be";
    c.textAlign = "center";
    for (const [name,lon,lat] of [
      ["I N D I A",78,23], ["ARABIA",49.5,24], ["MYANMAR",96,22],
    ] as const) {
      c.fillText(name,left+((lon-45)/.25+.5)*cw,top+((30-lat)/.25+.5)*ch);
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
    `Smooth display interpolation · dark = unavailable · ${relief ? "ETOPO shaded land" : "land relief unavailable/loading"} · scale: ${
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
  const [reliefReady, setReliefReady] = useState(!!currentMapRelief());
  useEffect(() => {
    let active = true;
    loadMapRelief().then(() => { if (active) setReliefReady(true); }).catch(() => {});
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (ref.current) drawMap(ref.current, props);
  }, [
    props.field,
    props.layer,
    props.depth,
    props.palette,
    props.selection,
    props.scaleMode,
    reliefReady,
  ]);
  return (
    <>
      <canvas
        ref={ref}
        className="map-canvas"
        data-testid="field-map"
        data-relief={reliefReady ? "ready" : "unavailable"}
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
