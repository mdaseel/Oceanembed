import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { terrainGeometry, terrainDisplayHeights, type TerrainData } from "../field/terrain";
import { position } from "../field/geometry";

const metadata = JSON.parse(readFileSync("public/assets/terrain/metadata.json", "utf8"));
const buffer = readFileSync("public/assets/terrain/land.bin");
const bytes = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
const data: TerrainData = {
  metadata,
  coordinates: new Float32Array(bytes, 0, metadata.vertices * 3),
  indices: new Uint32Array(bytes, metadata.vertices * 12),
};
describe("static DEM context", () => {
  it("bundles verified ETOPO provenance and non-uniform real elevations", () => {
    expect(createHash("sha256").update(buffer).digest("hex")).toBe(metadata.meshSha256);
    expect(metadata.dataset).toBe("NOAA ETOPO 2022");
    expect(metadata.contextOnly).toBe(true);
    const heights = data.coordinates.filter((_, i) => i % 3 === 2);
    expect(heights.every(h => Number.isFinite(h) && h >= 0)).toBe(true);
    expect(heights.some(h => h > 5000)).toBe(true);
    expect(heights.some(h => h > 0 && h < 100)).toBe(true);
    expect(data.indices.length).toBe(metadata.triangles * 3);
  });
  it("uses the exact horizontal mapping and changes only terrain height", () => {
    const copy = data.coordinates.slice();
    const heights = terrainDisplayHeights(data);
    const a = terrainGeometry(data, 50), b = terrainGeometry(data, 100);
    const pa = a.getAttribute("position"), pb = b.getAttribute("position");
    for (let v = 0; v < pa.count; v += 113) {
      const [lon, lat, h] = data.coordinates.subarray(v * 3, v * 3 + 3);
      const [x, , z] = position(lon, lat, 0, 1);
      expect(pa.getX(v)).toBeCloseTo(x, 5);
      expect(pa.getZ(v)).toBeCloseTo(z, 5);
      expect(pb.getX(v)).toBe(pa.getX(v));
      expect(pb.getZ(v)).toBe(pa.getZ(v));
      expect(pa.getY(v)).toBeCloseTo(heights[v] / 111000 * 50, 5);
      if (h === 0) expect(heights[v]).toBe(0);
      expect(pb.getY(v)).toBe(pa.getY(v) * 2);
    }
    expect(data.coordinates).toEqual(copy);
    a.dispose(); b.dispose();
    // Builds two full 620k-triangle geometries; the default 5s budget is too
    // tight for real work of this size and made the result depend on load.
  }, 30000);
  it("gently smooths display relief without altering the DEM or coastline", () => {
    const original = data.coordinates.slice();
    const heights = terrainDisplayHeights(data);
    // Same assertions as before, accumulated rather than asserted per vertex:
    // 317,826 vertices x ~3 expect() calls put this test on the edge of the
    // default timeout, so it passed or failed with machine load. Counting
    // violations and asserting once is exactly as strict and ~100x cheaper.
    let changed = 0,
      movedCoastline = 0,
      belowFloor = 0;
    for (let i = 0; i < heights.length; i++) {
      const h = original[i * 3 + 2];
      if (h === 0 && heights[i] !== 0) movedCoastline++;
      if (h !== heights[i]) changed++;
      if (!(heights[i] >= h * 0.75 ** 2 - 0.001)) belowFloor++;
    }
    expect(movedCoastline).toBe(0);
    expect(belowFloor).toBe(0);
    expect(changed).toBeGreaterThan(1000);
    expect(data.coordinates).toEqual(original);
  }, 30000);
});
