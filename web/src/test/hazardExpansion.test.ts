import { describe, expect, it } from "vitest";
import type { FieldView } from "../field/contract";
import {
  cellAreaKm2,
  haversineKm,
  heatPenetration,
  median,
  monitoringAreas,
  trackAreaRelation,
  type LevelValue,
} from "../field/hazardIntelligence";

const DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000];

function level(depth: number, anomaly: number, supported = true): LevelValue {
  return { depth, temperature: 20 + anomaly, climatology: 20, anomaly, supported };
}

function field(cells: { row: number; col: number; label: string; tchp: number }[]): FieldView {
  const rows = 101,
    cols = 241,
    n = rows * cols;
  const labels: Record<number, string> = { 0: "LOW", 1: "MODERATE", 2: "ELEVATED", 3: "HIGH", 4: "NOT_CATEGORIZED" };
  const code = Object.fromEntries(Object.entries(labels).map(([k, v]) => [v, Number(k)]));
  const category = new Uint8Array(n);
  const tchp = new Float64Array(n).fill(10);
  for (const c of cells) {
    category[c.row * cols + c.col] = code[c.label];
    tchp[c.row * cols + c.col] = c.tchp;
  }
  return {
    lat: Float64Array.from({ length: rows }, (_, i) => 5 + i * 0.25),
    lon: Float64Array.from({ length: cols }, (_, i) => 45 + i * 0.25),
    depths: DEPTHS,
    anomaly: new Float64Array(n * DEPTHS.length),
    ocean: new Uint8Array(n).fill(1),
    inputValid: new Uint8Array(n).fill(1),
    diagnostics: { tchp } as FieldView["diagnostics"],
    hazard: { available: true, category, categoryLabels: labels } as unknown as FieldView["hazard"],
  } as unknown as FieldView;
}

describe("latitude-aware area", () => {
  it("shrinks with the cosine of latitude and is never a cell count", () => {
    const equator = cellAreaKm2(0),
      sixty = cellAreaKm2(60);
    expect(equator).toBeCloseTo(773.0, 0); // (0.25° ≈ 27.8 km)²
    expect(sixty / equator).toBeCloseTo(Math.cos(Math.PI / 3), 3);
  });

  it("reports area, median TCHP and centroid for a monitoring area", () => {
    const f = field([
      { row: 40, col: 150, label: "HIGH", tchp: 110 },
      { row: 40, col: 151, label: "HIGH", tchp: 120 },
      { row: 41, col: 150, label: "ELEVATED", tchp: 90 },
    ]);
    const [a] = monitoringAreas(f, null).areas;
    expect(a.cells).toBe(3);
    expect(a.medianTchp).toBe(110);
    expect(a.centroidLat).toBeCloseTo((15 + 15 + 15.25) / 3, 10);
    expect(a.areaKm2).toBeCloseTo(cellAreaKm2(15) * 2 + cellAreaKm2(15.25), 6);
  });

  it("computes a plain median", () => {
    expect(median([3, 1, 2])).toBe(2);
    expect(median([4, 1, 2, 3])).toBe(2.5);
    expect(median([NaN])).toBeNull();
  });
});

describe("heat penetration statements", () => {
  it("states the continuous positive extent and the maximum depth", () => {
    const levels = DEPTHS.map((d) => level(d, d <= 125 ? 0.2 + d / 200 : -0.3));
    const p = heatPenetration(levels);
    expect(p.continuousTo).toBe(125);
    expect(p.maxPositive).toEqual({ depth: 125, anomaly: 0.2 + 125 / 200 });
    expect(p.statements[0]).toContain("continuously from the nominal surface through 125 m");
    expect(p.statements.join(" ")).toContain("weaker than the largest anomaly at or below 50 m");
  });

  it("notices warm water below a non-positive surface", () => {
    const levels = DEPTHS.map((d) => level(d, d === 75 ? 1.2 : -0.1));
    const p = heatPenetration(levels);
    expect(p.continuousTo).toBeNull();
    expect(p.statements[0]).toContain("first at 75 m");
  });

  it("stops at the seafloor and never scores", () => {
    const levels = DEPTHS.map((d) => level(d, 0.5, d <= 50));
    const p = heatPenetration(levels);
    expect(p.continuousTo).toBe(50);
    expect(Object.keys(p)).toEqual(["statements", "continuousTo", "maxPositive"]);
    expect(heatPenetration([]).statements[0]).toContain("No anomaly");
  });
});

describe("track and monitoring-area relation", () => {
  const f = field([
    { row: 40, col: 150, label: "HIGH", tchp: 110 },
    { row: 40, col: 151, label: "HIGH", tchp: 120 },
  ]);
  const [area] = monitoringAreas(f, null).areas;

  it("is an intersection only when a sampled cell belongs to the area", () => {
    const hit = trackAreaRelation(area, [{ row: 40, col: 151, lat: 15, lon: 82.75 }], f);
    expect(hit).toEqual({ kind: "TRACK INTERSECTION", distanceKm: 0 });
  });

  it("otherwise reports the great-circle distance without a corridor", () => {
    const miss = trackAreaRelation(area, [{ row: 44, col: 151, lat: 16, lon: 82.75 }], f);
    expect(miss.kind).toBe("OUTSIDE TRACK LINE");
    expect(miss.distanceKm).toBeCloseTo(haversineKm(16, 82.75, 15, 82.75), 6);
  });
});
