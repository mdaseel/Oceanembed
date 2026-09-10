import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { adaptReplay } from "../field/replayAdapter";
import { displayDepthValid, type Bathymetry } from "../field/bathymetry";
import {
  MISSING_RGB,
  UNSUPPORTED_DEPTH_RGB,
  mapRaster,
} from "../field/mapAppearance";
import { fieldRange, rangeFor } from "../field/colors";
import { depthColor } from "../field/depthColors";
import type { FieldView } from "../field/contract";

/**
 * Phase 7C corrective pass — the 2D selected-depth map must not paint
 * temperature over water that does not exist, and must keep "no data",
 * "no water column" and "a value" as three distinguishable outcomes.
 */
const f = adaptReplay(
  JSON.parse(readFileSync("../outputs/phase7b/test-field.json", "utf8")),
).field;
const metadata = JSON.parse(
  readFileSync("public/assets/bathymetry/metadata.json", "utf8"),
);
const raw = readFileSync("public/assets/bathymetry/depth.bin");
const depths = Float64Array.from({ length: 101 * 241 }, (_, i) =>
  raw.readDoubleLE(i * 8),
);
const bathy: Bathymetry = { metadata, depths };
const support =
  (field: FieldView, b: Bathymetry | null) =>
  (row: number, col: number, k: number) =>
    displayDepthValid(field, b, row, col, field.depths[k]);

const countSupported = (k: number) => {
  let n = 0;
  for (let r = 0; r < f.lat.length; r++)
    for (let c = 0; c < f.lon.length; c++) {
      const i = r * f.lon.length + c;
      if (f.ocean[i] && f.inputValid[i] && displayDepthValid(f, bathy, r, c, f.depths[k]))
        n++;
    }
  return n;
};

describe("2D selected-depth physical footprint", () => {
  it("keeps essentially the whole ocean at 0 m", () => {
    let population = 0;
    for (let i = 0; i < f.ocean.length; i++)
      if (f.ocean[i] && f.inputValid[i]) population++;
    // 0 m needs only a non-negative water depth, so support is the population.
    expect(countSupported(0)).toBe(population);
  });

  it("removes cells shallower than 100 m at the 100 m level", () => {
    const k = f.depths.indexOf(100);
    expect(countSupported(k)).toBeLessThan(countSupported(0));
    for (let r = 0; r < f.lat.length; r++)
      for (let c = 0; c < f.lon.length; c++)
        if (displayDepthValid(f, bathy, r, c, 100))
          expect(depths[r * f.lon.length + c]).toBeGreaterThanOrEqual(100);
  });

  it("removes more shelf at 300 m than at 100 m", () => {
    expect(countSupported(f.depths.indexOf(300))).toBeLessThan(
      countSupported(f.depths.indexOf(100)),
    );
  });

  it("contracts monotonically across every mandated depth", () => {
    const counts = f.depths.map((_, k) => countSupported(k));
    for (let k = 1; k < counts.length; k++)
      expect(counts[k]).toBeLessThanOrEqual(counts[k - 1]);
    expect(counts.at(-1)!).toBeLessThan(counts[0]);
    expect(counts.at(-1)!).toBeGreaterThan(0);
  });

  it("colours only cells with at least 1000 m of water at 1000 m", () => {
    for (let r = 0; r < f.lat.length; r++)
      for (let c = 0; c < f.lon.length; c++)
        if (displayDepthValid(f, bathy, r, c, 1000))
          expect(depths[r * f.lon.length + c]).toBeGreaterThanOrEqual(1000);
  });
});

describe("2D raster rendering of unsupported depth", () => {
  const range = { min: 0, max: 30, actualMin: 0, actualMax: 30, count: 4 };
  const tiny = (): FieldView =>
    ({
      lat: new Float64Array([5, 5.25]),
      lon: new Float64Array([45, 45.25]),
      depths: [1000],
      temperature: new Float64Array([10, 10, 10, 10]),
      ocean: new Uint8Array([1, 1, 1, 1]),
      inputValid: new Uint8Array([1, 1, 1, 1]),
    }) as unknown as FieldView;
  const px = (p: Uint8ClampedArray, w: number, x: number, y: number) =>
    Array.from(p.slice((y * w + x) * 4, (y * w + x) * 4 + 3));

  it("paints the neutral unsupported colour, not a cold temperature", () => {
    const g = tiny();
    const pixels = mapRaster(g, "temperature", 0, "thermal", range, 2, 2, () => false);
    expect(px(pixels, 2, 0, 0)).toEqual(Array.from(UNSUPPORTED_DEPTH_RGB));
    expect(px(pixels, 2, 1, 1)).toEqual(Array.from(UNSUPPORTED_DEPTH_RGB));
    // Must not be mistakable for the cold end of any ramp, nor for no-data.
    expect(px(pixels, 2, 0, 0)).not.toEqual(
      depthColor(range.min, range, "temperature", "thermal"),
    );
    expect(px(pixels, 2, 0, 0)).not.toEqual(Array.from(MISSING_RGB));
  });

  it("keeps no-data, no-water-column and a value visually distinct", () => {
    const g = tiny();
    g.inputValid[3] = 0; // no data at cell (row 1, col 1)
    const pixels = mapRaster(g, "temperature", 0, "thermal", range, 2, 2,
      (r, c) => !(r === 0 && c === 0));
    // Latitude ascends in the field and descends down the canvas, so cell
    // (0,0) is the BOTTOM-left pixel.
    const unsupported = px(pixels, 2, 0, 1);
    const missing = px(pixels, 2, 1, 0);
    const value = px(pixels, 2, 0, 0);
    expect(unsupported).toEqual(Array.from(UNSUPPORTED_DEPTH_RGB));
    expect(missing).toEqual(Array.from(MISSING_RGB));
    expect(new Set([unsupported.join(), value.join(), missing.join()]).size).toBe(3);
  });

  it("does not smooth a value into an unsupported cell", () => {
    const g = tiny();
    g.temperature.set([30, 0, 0, 0]);
    const solid = mapRaster(g, "temperature", 0, "thermal", range, 2, 2);
    const gated = mapRaster(g, "temperature", 0, "thermal", range, 2, 2,
      (r, c) => !(r === 0 && c === 0));
    expect(px(gated, 2, 0, 1)).not.toEqual(px(solid, 2, 0, 1));
    expect(px(gated, 2, 0, 1)).toEqual(Array.from(UNSUPPORTED_DEPTH_RGB));
  });

  it("leaves the default (no bathymetry supplied) behaviour identical", () => {
    const g = tiny();
    expect(Array.from(mapRaster(g, "temperature", 0, "thermal", range, 1, 1))).toEqual(
      Array.from(mapRaster(g, "temperature", 0, "thermal", range, 1, 1, () => true)),
    );
  });

  it("never mutates the raw model array", () => {
    const g = tiny();
    const before = g.temperature.slice();
    mapRaster(g, "temperature", 0, "thermal", range, 4, 4, () => false);
    expect(g.temperature).toEqual(before);
  });
});

describe("colour normalisation", () => {
  it("excludes physically unsupported values from the whole-field scale", () => {
    const plain = fieldRange(f, "temperature");
    const gated = fieldRange(f, "temperature", support(f, bathy), metadata.depthSha256);
    expect(gated.count).toBeLessThan(plain.count);
    expect(gated.count).toBeGreaterThan(0);
  });

  it("is unchanged when no support predicate is supplied", () => {
    expect(fieldRange(f, "temperature")).toEqual(fieldRange(f, "temperature"));
    const a = rangeFor(f, "temperature", [7], "field");
    const b = rangeFor(f, "temperature", [7], "field", undefined, "none");
    expect(a).toEqual(b);
  });

  it("reports on-screen extremes over supported cells only", () => {
    const k = f.depths.indexOf(1000);
    const gated = rangeFor(f, "temperature", [k], "slice",
      support(f, bathy), metadata.depthSha256);
    const plain = rangeFor(f, "temperature", [k], "slice");
    expect(gated.count).toBeLessThanOrEqual(plain.count);
    expect(gated.count).toBeGreaterThan(0);
  });

  it("memoises separately per support, so the two never collide", () => {
    const plain = fieldRange(f, "anomaly");
    const gated = fieldRange(f, "anomaly", support(f, bathy), metadata.depthSha256);
    expect(fieldRange(f, "anomaly")).toEqual(plain);
    expect(fieldRange(f, "anomaly", support(f, bathy), metadata.depthSha256)).toEqual(gated);
  });
});

describe("missing input is never reported as below seafloor", () => {
  const range = { min: 0, max: 30, actualMin: 0, actualMax: 30, count: 4 };
  const px = (p: Uint8ClampedArray, w: number, x: number, y: number) =>
    Array.from(p.slice((y * w + x) * 4, (y * w + x) * 4 + 3));

  /** Two deep cells; one has no surface input that day. */
  const deep = (): FieldView =>
    ({
      lat: new Float64Array([5, 5.25]),
      lon: new Float64Array([45, 45.25]),
      depths: [1000],
      temperature: new Float64Array([10, 10, 10, 10]),
      ocean: new Uint8Array([1, 1, 1, 1]),
      inputValid: new Uint8Array([1, 1, 1, 1]),
    }) as unknown as FieldView;

  it("draws a deep cell with no surface input as missing, not unsupported", () => {
    const g = deep();
    g.inputValid[0] = 0; // cell (0,0): deep water, but no observation today
    // Bathymetry says this cell IS deep enough; only the input is absent.
    const pixels = mapRaster(g, "temperature", 0, "thermal", range, 2, 2, () => true);
    // Cell (0,0) is the bottom-left pixel.
    expect(px(pixels, 2, 0, 1)).toEqual(Array.from(MISSING_RGB));
    expect(px(pixels, 2, 0, 1)).not.toEqual(Array.from(UNSUPPORTED_DEPTH_RGB));
  });

  it("reserves the unsupported colour for a real bathymetric failure", () => {
    const g = deep();
    const pixels = mapRaster(g, "temperature", 0, "thermal", range, 2, 2,
      (r, c) => !(r === 0 && c === 0));
    expect(px(pixels, 2, 0, 1)).toEqual(Array.from(UNSUPPORTED_DEPTH_RGB));
  });

  it("keeps the two reasons distinct in the same frame", () => {
    const g = deep();
    g.inputValid[1] = 0; // cell (0,1): missing input
    const pixels = mapRaster(g, "temperature", 0, "thermal", range, 2, 2,
      (r, c) => !(r === 0 && c === 0)); // cell (0,0): below seafloor
    const belowSeafloor = px(pixels, 2, 0, 1);
    const missingInput = px(pixels, 2, 1, 1);
    expect(belowSeafloor).toEqual(Array.from(UNSUPPORTED_DEPTH_RGB));
    expect(missingInput).toEqual(Array.from(MISSING_RGB));
    expect(belowSeafloor).not.toEqual(missingInput);
  });
});

describe("independence from other validity concepts", () => {
  it("is unaffected by climatology support", () => {
    const stripped = {
      ...f,
      climatology: f.climatology.map(() => NaN),
      climatologyDefined: f.climatologyDefined.map(() => 0),
    } as FieldView;
    const r = 40, c = 170;
    expect(displayDepthValid(stripped, bathy, r, c, 1000)).toBe(
      displayDepthValid(f, bathy, r, c, 1000),
    );
  });

  it("fails closed when bathymetry is missing rather than assuming support", () => {
    expect(displayDepthValid(f, null, 40, 170, 0)).toBe(false);
  });
});
