/** 3D presentation ramp; shared by the water faces, skirts and their legend.
 * Range normalization is unchanged. 2D and accessible palettes are untouched.
 */
import { color, gradient, type Range } from "./colors";
import type { Layer, Palette } from "./contract";
const thermal = [
  [25, 12, 100], [28, 43, 191], [15, 105, 244], [15, 181, 239],
  [64, 221, 215], [158, 237, 181], [242, 228, 127], [255, 162, 63],
  [255, 72, 35], [241, 29, 27], [194, 10, 30],
];
export function depthColor(v: number, range: Range, layer: Layer, palette: Palette = "thermal"): [number, number, number] {
  if (layer !== "temperature" || palette !== "thermal") return color(v, range, layer, palette);
  const t = range.max === range.min ? .5 : Math.max(0, Math.min(1, (v - range.min) / (range.max - range.min)));
  const p = t * (thermal.length - 1), i = Math.min(thermal.length - 2, Math.floor(p)), w = p - i;
  return thermal[i].map((c, j) => Math.round(c * (1-w) + thermal[i+1][j] * w)) as [number, number, number];
}
export function depthGradient(layer: Layer, palette: Palette) {
  return layer === "temperature" && palette === "thermal"
    ? `linear-gradient(90deg, ${thermal.map(c => `rgb(${c.join(",")})`).join(",")})`
    : gradient(layer, palette);
}
