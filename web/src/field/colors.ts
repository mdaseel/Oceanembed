import { type FieldView, type Layer, type Palette, slice } from "./contract";
/**
 * Default ocean-temperature ramp. Sampled from Google's `turbo`, which is a
 * perceptually ordered rainbow designed as a corrected replacement for `jet`:
 * monotonic in lightness, no false banding, and the convention operational
 * SST products are usually read in. It is a scientific colormap, not an
 * arbitrary rainbow. `viridis` and `cividis` remain selectable in Settings for
 * colour-vision accessibility.
 */
const thermal = [
  [48, 18, 59],
  [56, 90, 189],
  [39, 152, 233],
  [30, 200, 190],
  [93, 226, 116],
  [176, 235, 62],
  [242, 201, 48],
  [250, 137, 35],
  [222, 68, 18],
  [153, 22, 4],
];
const viridis = [
  [68, 1, 84],
  [59, 82, 139],
  [33, 145, 140],
  [94, 201, 98],
  [253, 231, 37],
];
const cividis = [
  [0, 34, 78],
  [67, 78, 108],
  [124, 123, 120],
  [188, 173, 108],
  [254, 232, 56],
];
const diverging = [
  [33, 102, 172],
  [146, 197, 222],
  [247, 247, 247],
  [244, 165, 130],
  [178, 24, 43],
];
export interface Range {
  min: number;
  max: number;
  actualMin: number;
  actualMax: number;
  count: number;
}
export function rangeOf(values: Iterable<number>, layer: Layer): Range {
  let min = Infinity,
    max = -Infinity,
    count = 0;
  for (const v of values)
    if (Number.isFinite(v)) {
      min = Math.min(min, v);
      max = Math.max(max, v);
      count++;
    }
  if (!count)
    return { min: NaN, max: NaN, actualMin: NaN, actualMax: NaN, count: 0 };
  const span = Math.max(Math.abs(min), Math.abs(max));
  return {
    min: layer === "anomaly" ? -span : min,
    max: layer === "anomaly" ? span : max,
    actualMin: min,
    actualMax: max,
    count,
  };
}
/**
 * Which values the colour scale is stretched over.
 *
 * `"field"` (default) — one scale spanning the WHOLE reconstruction: every
 * supported cell at all 15 depths of the displayed layer. Warm surface water
 * lands at the warm end of the ramp and cold deep water at the cold end, so a
 * 0 m map and a 500 m map are directly comparable, and so are two dates.
 *
 * `"slice"` — stretch to the displayed depth(s) only, maximising contrast
 * inside one slice. This is what the view used to do unconditionally, and it
 * is actively misleading across slices: every depth spanned the full colormap
 * regardless of its actual temperatures, so a 1000 m map at ~6 °C and a
 * surface map at ~30 °C rendered in the same colours. Offered in Settings for
 * inspecting structure within a single layer, never as the default.
 *
 * Neither mode hardcodes a temperature range: both are computed from the
 * values actually returned for the requested date.
 */
export type ScaleMode = "field" | "slice";
export const SCALE_MODES: ScaleMode[] = ["field", "slice"];
/** Whole-field range, memoised per field object — it reads all 15 depths. */
const wholeField = new WeakMap<FieldView, Partial<Record<Layer, Range>>>();
export function fieldRange(f: FieldView, layer: Layer): Range {
  let entry = wholeField.get(f);
  if (!entry) wholeField.set(f, (entry = {}));
  return (entry[layer] ??= rangeOf(
    (function* () {
      const nd = f.depths.length,
        values = f[layer];
      for (let i = 0; i < f.ocean.length; i++) {
        if (!f.ocean[i] || !f.inputValid[i]) continue;
        for (let k = 0; k < nd; k++) yield values[i * nd + k];
      }
    })(),
    layer,
  ));
}
export function rangeFor(
  f: FieldView,
  layer: Layer,
  depths: number[],
  mode: ScaleMode = "field",
): Range {
  // `actualMin` / `actualMax` / `count` always describe what is ON SCREEN, so
  // the colorbar can report the displayed data honestly whichever domain the
  // ramp is stretched over.
  const shown = rangeOf(
    depths.flatMap((k) => Array.from(slice(f, layer, k))),
    layer,
  );
  if (mode === "slice") return shown;
  const domain = fieldRange(f, layer);
  return domain.count ? { ...shown, min: domain.min, max: domain.max } : shown;
}
export function color(
  v: number,
  range: Range,
  layer: Layer,
  palette: Palette = "thermal",
): [number, number, number] {
  const stops = layer === "anomaly" ? diverging : ramp(palette);
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
function ramp(palette: Palette) {
  return palette === "cividis" ? cividis : palette === "viridis" ? viridis : thermal;
}
export function gradient(layer: Layer, palette: Palette) {
  const stops = layer === "anomaly" ? diverging : ramp(palette);
  return `linear-gradient(90deg, ${stops.map((c) => `rgb(${c.join(",")})`).join(",")})`;
}
