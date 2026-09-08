import { expect, it } from "vitest";
import { color, gradient } from "../field/colors";
import { depthColor, depthGradient } from "../field/depthColors";
const range = { min: 0, max: 30, actualMin: 0, actualMax: 30, count: 10 };
it("uses a rich red for warm 3D water and matches the legend endpoints", () => {
  const red = depthColor(27, range, "temperature", "thermal");
  expect(red).toEqual([241,29,27]);
  const end = depthColor(30, range, "temperature", "thermal");
  expect(depthGradient("temperature", "thermal")).toContain(`rgb(${end.join(",")})`);
  expect(depthColor(0, range, "temperature", "thermal")).toEqual([25,12,100]);
});
it("leaves anomalies, accessible palettes, and the original 2D ramp unchanged", () => {
  for (const palette of ["viridis", "cividis"] as const) {
    expect(depthColor(15, range, "temperature", palette)).toEqual(color(15, range, "temperature", palette));
    expect(depthGradient("temperature", palette)).toBe(gradient("temperature", palette));
  }
  expect(depthColor(5, range, "anomaly", "thermal")).toEqual(color(5, range, "anomaly", "thermal"));
  expect(color(30, range, "temperature", "thermal")).toEqual([153,22,4]);
});
