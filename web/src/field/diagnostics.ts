/**
 * Display logic for the depth-integrated diagnostics.
 *
 * Values arrive already computed from the backend (§7C: one implementation, in
 * Python, shared by the map, the profile, the exports and the evaluation).
 * Nothing here computes science — it chooses colours and decides how a cell
 * with no 26 °C isotherm is drawn, which is deliberately NOT as a number.
 */
import type { DiagnosticKind, FieldView } from "./contract";
import { type Range, rangeOf } from "./colors";

/** Sequential, perceptually ordered, and distinct from the temperature ramp so
 *  a diagnostic map is never mistaken for a temperature map. */
const D26_RAMP = [
  [12, 24, 62],
  [30, 66, 122],
  [39, 122, 152],
  [86, 175, 148],
  [176, 213, 126],
  [246, 239, 148],
];
const TCHP_RAMP = [
  [10, 8, 30],
  [70, 20, 92],
  [143, 34, 96],
  [206, 68, 66],
  [242, 138, 42],
  [251, 219, 120],
];

/** Cells that are inside the population but have no isotherm to report. */
export const NO_CROSSING_RGB: [number, number, number] = [201, 111, 74];
/** Cells where the diagnostic resolved but sits below the local seafloor.
 *  Neutral charcoal, matching the 2D depth map's unsupported colour, and
 *  hatched on the opposite diagonal to the orange no-crossing class so the two
 *  failure modes stay distinguishable by shape as well as by colour. */
export const UNSUPPORTED_RGB: [number, number, number] = [48, 52, 58];
/** Land, or a date where the surface input stack is not valid. Matches the
 *  temperature map's unavailable colour so the shared ETOPO relief overlay
 *  sits on an identical background in both views. */
export const OUTSIDE_RGB: [number, number, number] = [10, 22, 30];

export const diagnosticRamp = (kind: DiagnosticKind) =>
  kind === "d26" ? D26_RAMP : TCHP_RAMP;

export function diagnosticGradient(kind: DiagnosticKind): string {
  return `linear-gradient(90deg, ${diagnosticRamp(kind)
    .map((c) => `rgb(${c.join(",")})`)
    .join(",")})`;
}

export function diagnosticColor(
  v: number,
  range: Range,
  kind: DiagnosticKind,
): [number, number, number] {
  const stops = diagnosticRamp(kind);
  const t =
    range.max === range.min
      ? 0.5
      : Math.max(0, Math.min(1, (v - range.min) / (range.max - range.min)));
  const p = t * (stops.length - 1),
    i = Math.min(stops.length - 2, Math.floor(p)),
    w = p - i;
  return stops[i].map((c, j) =>
    Math.round(c * (1 - w) + stops[i + 1][j] * w),
  ) as [number, number, number];
}

/** Range over the cells actually displayed, never a fixed invented span.
 *  Physically unsupported cells are excluded so a below-seafloor value cannot
 *  stretch the scale that the real ones share. */
export function diagnosticRange(f: FieldView, kind: DiagnosticKind): Range {
  const d = f.diagnostics;
  if (!d) return { min: NaN, max: NaN, actualMin: NaN, actualMax: NaN, count: 0 };
  const physical = kind === "d26" ? d.d26Physical : d.tchpPhysical;
  return rangeOf(
    (function* () {
      for (let i = 0; i < f.ocean.length; i++)
        if (
          f.ocean[i] &&
          f.inputValid[i] &&
          d.physicalLabels[physical[i]] === "SUPPORTED"
        )
          yield d[kind][i];
    })(),
    "temperature",
  );
}

export interface DiagnosticCounts {
  shown: number;
  noCrossing: number;
  outside: number;
  unsupported: number;
}

/**
 * Display raster, matching the temperature map's treatment so the two layers
 * read as one cartography: bilinear display resampling gated by the ORIGINAL
 * containing cell, with edge feathering, and no smoothing across coasts or
 * missing observations.
 *
 * A cell with no isotherm is drawn in its own colour AND hatched, and is never
 * smoothed into or out of, so it reads as "not applicable here" at a glance and
 * cannot be mistaken for a low value at the dark end of the ramp. That double
 * encoding is the point: colour alone would be ambiguous to a colour-vision-
 * deficient reader, and a smoothed edge would imply a value that has none.
 *
 * Display resampling never changes a reported value: the stat tiles, the
 * profile and the exports all read the unmodified array.
 */
export function diagnosticRaster(
  f: FieldView,
  kind: DiagnosticKind,
  range: Range,
  width: number,
  height: number,
): { pixels: Uint8ClampedArray; counts: DiagnosticCounts } {
  const d = f.diagnostics;
  const pixels = new Uint8ClampedArray(width * height * 4);
  const counts: DiagnosticCounts = {
    shown: 0, noCrossing: 0, outside: 0, unsupported: 0,
  };
  if (!d) return { pixels, counts };
  const nr = f.lat.length,
    nc = f.lon.length;
  const values = d[kind];
  const physical = kind === "d26" ? d.d26Physical : d.tchpPhysical;
  const inPopulation = (cell: number) => !!(f.ocean[cell] && f.inputValid[cell]);
  // A value standing on no water column is not a displayable value. It is not
  // smoothed into or out of either, for the same reason the no-crossing class
  // is not: a feathered edge would imply a measurement inside the seabed.
  const supported = (cell: number) =>
    d.physicalLabels[physical[cell]] === "SUPPORTED";
  const sample = (r: number, c: number) => {
    const cell = r * nc + c;
    return inPopulation(cell) && supported(cell) ? values[cell] : NaN;
  };
  const seen = new Uint8Array(nr * nc);
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      // Latitude ascends in the field and descends down the canvas.
      const rr = nr - 0.5 - ((y + 0.5) / height) * nr,
        cc = ((x + 0.5) / width) * nc - 0.5;
      const r = Math.max(0, Math.min(nr - 1, Math.round(rr)));
      const c = Math.max(0, Math.min(nc - 1, Math.round(cc)));
      const cell = r * nc + c;
      const inside = inPopulation(cell);
      let value = sample(r, c);
      let rgb: number[] = OUTSIDE_RGB as unknown as number[];

      if (!inside) {
        if (!seen[cell]) counts.outside++;
      } else if (Number.isFinite(values[cell]) && !supported(cell)) {
        // The diagnostic resolved, but below the local seafloor. Charcoal, and
        // hatched on the OPPOSITE diagonal to the no-crossing class.
        const hatch = (x - y + 8192) % 8 < 3;
        rgb = hatch
          ? UNSUPPORTED_RGB
          : UNSUPPORTED_RGB.map((ch) => Math.round(ch * 0.62));
        if (!seen[cell]) counts.unsupported++;
      } else if (!Number.isFinite(value)) {
        // Hatch in canvas pixels, so the texture stays constant regardless of
        // how many grid cells are on screen. Deliberately not feathered.
        const hatch = (x + y) % 8 < 3;
        rgb = hatch
          ? NO_CROSSING_RGB
          : NO_CROSSING_RGB.map((ch) => Math.round(ch * 0.55));
        if (!seen[cell]) counts.noCrossing++;
      } else {
        const r0 = Math.max(0, Math.min(nr - 1, Math.floor(rr)));
        const c0 = Math.max(0, Math.min(nc - 1, Math.floor(cc)));
        const r1 = Math.min(nr - 1, r0 + 1),
          c1 = Math.min(nc - 1, c0 + 1);
        const ry = Math.max(0, Math.min(1, rr - r0)),
          cx = Math.max(0, Math.min(1, cc - c0));
        const corners = [
          sample(r0, c0),
          sample(r0, c1),
          sample(r1, c0),
          sample(r1, c1),
        ];
        // Require full support: never smooth across a coast, a missing
        // observation, or a cell where the isotherm does not exist.
        if (corners.every(Number.isFinite))
          value =
            corners[0] * (1 - ry) * (1 - cx) +
            corners[1] * (1 - ry) * cx +
            corners[2] * ry * (1 - cx) +
            corners[3] * ry * cx;
        rgb = diagnosticColor(value, range, kind);
        const weights = [(1 - ry) * (1 - cx), (1 - ry) * cx, ry * (1 - cx), ry * cx];
        const coverage = corners.reduce(
          (sum, v, i) => sum + (Number.isFinite(v) ? weights[i] : 0),
          0,
        );
        const t = Math.max(0, Math.min(1, (coverage - 0.4) / 0.6));
        const alpha = t * t * (3 - 2 * t);
        rgb = rgb.map((v, i) => OUTSIDE_RGB[i] * (1 - alpha) + v * alpha);
        if (!seen[cell]) counts.shown++;
      }
      seen[cell] = 1;
      pixels.set([rgb[0], rgb[1], rgb[2], 255], (y * width + x) * 4);
    }
  return { pixels, counts };
}
