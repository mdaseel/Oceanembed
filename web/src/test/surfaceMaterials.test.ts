import { expect, it } from "vitest";
import { smoothWaterColors } from "../field/surfaceMaterials";

it("smooths only supported water patches without changing source colors or cell order", () => {
  const data = { cells: [0,1,2,3], colors: new Float32Array(72) };
  data.cells.forEach((_, i) => data.colors.fill(i / 3, i * 18, (i + 1) * 18));
  const copy = data.colors.slice();
  const colors = smoothWaterColors(data, 2, 2);
  // The four-cell common corner is averaged; the outer edge is untouched.
  expect(colors[6]).toBeCloseTo(.5);
  expect(colors[0]).toBe(0);
  expect(data.colors).toEqual(copy);
  expect(data.cells).toEqual([0,1,2,3]);
  const hole = { cells: [0,1,2], colors: data.colors.slice(0,54) };
  expect(smoothWaterColors(hole, 2, 2)).toEqual(hole.colors);
});
