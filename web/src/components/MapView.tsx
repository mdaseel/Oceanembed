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
import {
  UNSUPPORTED_DEPTH_RGB,
  currentMapRelief,
  loadMapRelief,
  mapRaster,
} from "../field/mapAppearance";
import {
  displayDepthValid,
  useBathymetry,
  type Bathymetry,
} from "../field/bathymetry";
export interface MapProps {
  field: FieldView;
  layer: Layer;
  depth: number;
  palette: Palette;
  selection: Selection;
  scaleMode: ScaleMode;
  onSelect: (lat: number, lon: number) => void;
  /** Physical water-column support, from the same artifact the 3D view reads. */
  bathymetry?: Bathymetry | null;
  bathymetryError?: boolean;
}
/** One rule, one utility. The 3D renderer, the profile and this map all call
 *  `displayDepthValid`; none of them re-derives the seafloor for itself. */
const supportFor = (f: FieldView, b: Bathymetry | null | undefined) =>
  b
    ? (row: number, col: number, depthIndex: number) =>
        displayDepthValid(f, b, row, col, f.depths[depthIndex])
    : undefined;
const W = 1440,
  H = 760,
  left = 66,
  top = 45,
  width = 1320,
  height = 555;
/** Shared so a diagnostic map projects and picks identically to this one. */
export const PROJECTION = { W, H, left, top, width, height } as const;
/** Canvas pixel -> geographic coordinate, or null outside the plotted area. */
export function pixelToLatLon(
  x: number,
  y: number,
  f: FieldView,
): [number, number] | null {
  if (x < left || x >= left + width || y < top || y >= top + height) return null;
  const lon = Math.max(
    45,
    Math.min(105, 45 + (((x - left) / width) * f.lon.length - 0.5) * 0.25),
  );
  const lat = Math.max(
    5,
    Math.min(30, 30 - (((y - top) / height) * f.lat.length - 0.5) * 0.25),
  );
  return [lat, lon];
}
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
    bathymetry,
  }: Omit<MapProps, "onSelect">,
) {
  canvas.width = W;
  canvas.height = H;
  const c = canvas.getContext("2d")!;
  c.fillStyle = "#06080d";
  c.fillRect(0, 0, W, H);
  const support = supportFor(f, bathymetry);
  const supportKey = bathymetry?.metadata.depthSha256 ?? "none";
  const valid = (row: number, col: number) =>
    !support || support(row, col, depth);
  const range = rangeFor(f, layer, [depth], scaleMode, support, supportKey),
    cw = width / f.lon.length,
    ch = height / f.lat.length;
  let cached = rasterCache.get(f);
  if (!cached) rasterCache.set(f, cached = new Map());
  const key = `${layer}/${depth}/${palette}/${range.min}/${range.max}/${supportKey}`;
  let pixels = cached.get(key);
  if (!pixels) {
    pixels = mapRaster(f,layer,depth,palette,range,width,height,valid);
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
  // How much ocean actually has this much water under it.
  let supported = 0,
    unsupported = 0;
  for (let r = 0; r < f.lat.length; r++)
    for (let col = 0; col < f.lon.length; col++) {
      const i = r * f.lon.length + col;
      if (!f.ocean[i] || !f.inputValid[i]) continue;
      if (valid(r, col)) supported++;
      else unsupported++;
    }
  c.font = "14px system-ui";
  c.fillStyle = "#a3b4cb";
  c.fillText(
    `Smooth display interpolation · dark = unavailable · ${relief ? "ETOPO shaded land" : "land relief unavailable/loading"} · ${
      bathymetry
        ? `physical depth support from ETOPO 2022 at ${f.depths[depth]} m`
        : "physical depth support UNVERIFIED — no cell is shown as supported"
    } · scale: ${
      scaleMode === "field"
        ? "whole reconstruction, all 15 physically supported depths (compare dates using their displayed ranges)"
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
  // Say what the neutral colour means, on the map itself. This is NOT land,
  // NOT missing input and NOT missing climatology; those stay distinguishable.
  if (unsupported) {
    c.fillStyle = `rgb(${UNSUPPORTED_DEPTH_RGB.join(",")})`;
    c.fillRect(left + 560, 680, 26, 12);
    c.strokeStyle = "#6b7686";
    c.lineWidth = 1;
    c.strokeRect(left + 560.5, 680.5, 25, 11);
    c.fillStyle = "#d5dfed";
    c.fillText(
      `depth not physically available — below local seafloor (${unsupported.toLocaleString()} cells)`,
      left + 594,
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
  return { supported, unsupported };
}
export function MapView(props: MapProps) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [reliefReady, setReliefReady] = useState(!!currentMapRelief());
  // Fall back to loading it here so the map is correct even when a parent does
  // not supply it; the loader is shared and cached, so this is not a second fetch.
  const own = useBathymetry();
  const bathymetry =
    props.bathymetry !== undefined ? props.bathymetry : own.data;
  const bathymetryError =
    props.bathymetryError !== undefined ? props.bathymetryError : own.error;
  useEffect(() => {
    let active = true;
    loadMapRelief().then(() => { if (active) setReliefReady(true); }).catch(() => {});
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!ref.current) return;
    const counts = drawMap(ref.current, { ...props, bathymetry });
    ref.current.dataset.supportedCells = String(counts.supported);
    ref.current.dataset.unsupportedCells = String(counts.unsupported);
    ref.current.dataset.bathymetry = bathymetry
      ? "ready"
      : bathymetryError
        ? "unavailable"
        : "loading";
  }, [
    props.field,
    props.layer,
    props.depth,
    props.palette,
    props.selection,
    props.scaleMode,
    reliefReady,
    bathymetry,
    bathymetryError,
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
          const hit = pixelToLatLon(x, y, props.field);
          if (hit) props.onSelect(hit[0], hit[1]);
        }}
      />
      <Colorbar
        range={rangeFor(
          props.field,
          props.layer,
          [props.depth],
          props.scaleMode,
          supportFor(props.field, bathymetry),
          bathymetry?.metadata.depthSha256 ?? "none",
        )}
        layer={props.layer}
        palette={props.palette}
        displayGradient={depthGradient(props.layer, props.palette)}
      />
      <p className="muted small" data-testid="map-depth-support">
        {bathymetry
          ? `Depth not physically available is shown in neutral grey: the local ETOPO 2022 water column does not reach ${props.field.depths[props.depth]} m there. It is distinct from land, from missing surface input and from missing climatology. The raw L2 value at those cells is unchanged and still exported.`
          : bathymetryError
            ? "Bathymetry unavailable: physical depth support cannot be verified, so no cell is shown as supported. Raw values are unchanged."
            : "Verifying physical depth support from local bathymetry…"}
      </p>
    </>
  );
}
