import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { FieldView } from "../field/contract";
import {
  GLOSSARY,
  NOT_A_PROBABILITY,
  addDays,
  bandText,
  basinOf,
  categoryMeaning,
  contiguousRun,
  eventChanges,
  eventDates,
  monitoringAreas,
  oceanStory,
  outlinePath,
  phaseFor,
  phaseShort,
  signed,
  storyKeyFor,
  windowGaps,
  type DayState,
  type SeriesRow,
} from "../field/hazardIntelligence";

/** The frozen EVENT segmentation, read from the backend source rather than retyped. */
const appSource = readFileSync("../src/oceanembed/poc/app.py", "utf8");
const SEGMENTS = [
  ...appSource.matchAll(
    /\{"label": "([^"]+)", "start": "(\d{4}-\d{2}-\d{2})", "end": "(\d{4}-\d{2}-\d{2})"\}/g,
  ),
].map((m) => ({ label: m[1], start: m[2], end: m[3] }));
const WINDOW = {
  start: appSource.match(/"window_start": "(\d{4}-\d{2}-\d{2})"/)![1],
  end: appSource.match(/"window_end": "(\d{4}-\d{2}-\d{2})"/)![1],
};

describe("event playback dates and phases", () => {
  it("reads the frozen five-segment Mocha segmentation", () => {
    expect(SEGMENTS.map((s) => phaseShort(s.label))).toEqual([
      "PRE-EVENT",
      "APPROACH",
      "EVENT",
      "WAKE",
      "RECOVERY",
    ]);
  });

  it("plays every real calendar day of the window and nothing between them", () => {
    const dates = eventDates(WINDOW.start, WINDOW.end);
    expect(dates[0]).toBe(WINDOW.start);
    expect(dates.at(-1)).toBe(WINDOW.end);
    expect(new Set(dates).size).toBe(dates.length);
    for (let i = 1; i < dates.length; i++) expect(dates[i]).toBe(addDays(dates[i - 1], 1));
    for (const d of dates) expect(d).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(eventDates("2023-05-10", "2023-05-01")).toEqual([]);
    expect(eventDates("not-a-date", "2023-05-01")).toEqual([]);
  });

  it("assigns every window day to exactly one frozen segment", () => {
    for (const d of eventDates(WINDOW.start, WINDOW.end)) {
      const matches = SEGMENTS.filter((s) => d >= s.start && d <= s.end);
      expect(matches).toHaveLength(1);
      expect(phaseFor(d, SEGMENTS)?.label).toBe(matches[0].label);
    }
    expect(phaseFor(addDays(WINDOW.start, -1), SEGMENTS)).toBeNull();
    expect(storyKeyFor(SEGMENTS[0].label)).toBe("before");
    expect(storyKeyFor(SEGMENTS[3].label)).toBe("wake");
  });
});

function row(date: string, tchp: number, sst: number, d26: number, a100: number): SeriesRow {
  return {
    date,
    n_cells: 100,
    sst_nominal_0m_c: sst,
    temp_100m_c: 26,
    anomaly_100m_c: a100,
    d26_m: d26,
    tchp_kj_cm2: tchp,
    category_counts: { LOW: 50, MODERATE: 25, ELEVATED: 15, HIGH: 10, NOT_CATEGORIZED: 0 },
  };
}

describe("before / event / wake / recovery comparison", () => {
  const dates = eventDates(WINDOW.start, WINDOW.end);
  const tchp: Record<string, number> = {};
  dates.forEach((d, i) => (tchp[d] = 80 + i));
  // pre-event: 90, 88, 89, 87 -> mean 88.5; wake minimum 67.5 on its second day
  const pre = SEGMENTS[0],
    wake = SEGMENTS[3];
  eventDates(pre.start, pre.end).forEach((d, i) => (tchp[d] = [90, 88, 89, 87][i]));
  eventDates(wake.start, wake.end).forEach((d, i) => (tchp[d] = [70, 67.5, 69, 71][i]));
  tchp[WINDOW.end] = 78;
  const series = dates.map((d) =>
    row(d, tchp[d], d === eventDates(wake.start, wake.end)[1] ? 28.0 : 29.5, 60, 0.5),
  );
  const ch = eventChanges(series, SEGMENTS);

  it("derives every number from the series rows", () => {
    expect(ch.pre?.means.tchp_kj_cm2).toBeCloseTo(88.5, 10);
    expect(ch.wakeMin.tchp).toEqual({ value: 67.5, date: eventDates(wake.start, wake.end)[1] });
    expect(ch.tchpChange).toBeCloseTo(-21, 10);
    expect(ch.tchpChangePct).toBeCloseTo((-21 / 88.5) * 100, 10);
    expect(ch.sstChange).toBeCloseTo(-1.5, 10);
    expect(ch.final?.date).toBe(WINDOW.end);
    expect(ch.tchpFinalVsPre).toBeCloseTo(-10.5, 10);
    expect(ch.tchpFinalVsWakeMin).toBeCloseTo(10.5, 10);
    expect(ch.pre?.supportShare).toBeCloseTo(0.25, 10);
  });

  it("describes the pattern cautiously and never claims causality", () => {
    const text = oceanStory(ch)
      .map((s) => s.text)
      .join(" ");
    expect(text).toContain("consistent with cyclone-associated upper-ocean cooling and mixing");
    expect(text).toContain("does not establish the cause");
    expect(text).toContain("remained below its pre-event value");
    expect(text.toLowerCase()).not.toMatch(/\b(caused by|proves?|will intensify)\b/);
  });

  it("gives no cold-wake wording when the numbers show no cooling", () => {
    const flat = eventChanges(
      dates.map((d) => row(d, 90, 29.5, 60, 0.5)),
      SEGMENTS,
    );
    const text = oceanStory(flat)
      .map((s) => s.text)
      .join(" ");
    expect(text).not.toContain("consistent with");
    expect(text).toContain("did not fall below");
  });

  it("formats signed differences without inventing precision", () => {
    expect(signed(-21.44, 1, "kJ/cm²")).toBe("−21.4 kJ/cm²");
    expect(signed(0.3, 2, "°C")).toBe("+0.30 °C");
    expect(signed(-0.001, 1)).toBe("±0.0");
    expect(signed(NaN)).toBe("Unavailable");
  });
});

/** A synthetic canonical-size field carrying only what the hotspot rule reads. */
function syntheticField(
  cells: { row: number; col: number; label: string; tchp: number; valid?: boolean; a100?: number }[],
): FieldView {
  const rows = 101,
    cols = 241,
    n = rows * cols,
    depths = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000];
  const labels: Record<number, string> = {
    0: "LOW",
    1: "MODERATE",
    2: "ELEVATED",
    3: "HIGH",
    4: "NOT_CATEGORIZED",
  };
  const code = Object.fromEntries(Object.entries(labels).map(([k, v]) => [v, Number(k)]));
  const category = new Uint8Array(n).fill(0);
  const tchp = new Float64Array(n).fill(20);
  const inputValid = new Uint8Array(n).fill(1);
  const anomaly = new Float64Array(n * depths.length).fill(0);
  for (const c of cells) {
    const i = c.row * cols + c.col;
    category[i] = code[c.label];
    tchp[i] = c.tchp;
    if (c.valid === false) inputValid[i] = 0;
    anomaly[i * depths.length + depths.indexOf(100)] = c.a100 ?? 0;
  }
  return {
    lat: Float64Array.from({ length: rows }, (_, i) => 5 + i * 0.25),
    lon: Float64Array.from({ length: cols }, (_, i) => 45 + i * 0.25),
    depths,
    anomaly,
    ocean: new Uint8Array(n).fill(1),
    inputValid,
    diagnostics: { tchp } as FieldView["diagnostics"],
    hazard: {
      available: true,
      category,
      categoryLabels: labels,
    } as unknown as FieldView["hazard"],
  } as unknown as FieldView;
}

describe("thermal monitoring areas", () => {
  const basins = {
    arabian_sea: { lat: [8, 25] as [number, number], lon: [50, 77] as [number, number] },
    bay_of_bengal: { lat: [5, 22] as [number, number], lon: [80, 100] as [number, number] },
  };
  const f = syntheticField([
    // Area A: 2x2 HIGH block plus one edge-adjacent ELEVATED cell (one area)
    { row: 40, col: 150, label: "HIGH", tchp: 110 },
    { row: 40, col: 151, label: "HIGH", tchp: 120, a100: 1.6 },
    { row: 41, col: 150, label: "HIGH", tchp: 112 },
    { row: 41, col: 151, label: "HIGH", tchp: 115 },
    { row: 40, col: 152, label: "ELEVATED", tchp: 85 },
    // Area B: ELEVATED only
    { row: 60, col: 40, label: "ELEVATED", tchp: 90 },
    { row: 60, col: 41, label: "ELEVATED", tchp: 88 },
    // Area C: a single HIGH cell with the largest TCHP, outside both basin boxes
    { row: 90, col: 200, label: "HIGH", tchp: 130 },
    // Ignored: uncategorised, and HIGH without valid input
    { row: 90, col: 10, label: "NOT_CATEGORIZED", tchp: 200 },
    { row: 95, col: 230, label: "HIGH", tchp: 190, valid: false },
    // Diagonal neighbour of C is a separate area (edge adjacency only)
    { row: 91, col: 201, label: "ELEVATED", tchp: 80 },
  ]);
  const result = monitoringAreas(f, basins);

  it("ranks HIGH areas by peak TCHP, then ELEVATED-only areas, with no score", () => {
    expect(result.areas.map((a) => [a.tier, a.tchp])).toEqual([
      ["HIGH", 130],
      ["HIGH", 120],
      ["ELEVATED", 90],
      ["ELEVATED", 80],
    ]);
    expect(result.areas.map((a) => a.rank)).toEqual([1, 2, 3, 4]);
    for (const a of result.areas)
      expect(Object.keys(a).some((k) => /score|risk|weight|prob/i.test(k))).toBe(false);
  });

  it("groups edge-adjacent cells and reports the peak cell's own values", () => {
    const a = result.areas[1];
    expect(a.cells).toBe(5);
    expect(a.highCells).toBe(4);
    expect([a.lat, a.lon]).toEqual([5 + 40 * 0.25, 45 + 151 * 0.25]);
    expect(a.anomaly100).toBe(1.6);
    expect(a.basin).toBe("Bay of Bengal");
    expect(result.areas[2].basin).toBe("Arabian Sea");
    expect(result.areas[0].basin).toBeNull();
    expect(result.highCells).toBe(5);
  });

  it("finds nothing where the protocol labels nothing, and nothing without a hazard block", () => {
    expect(monitoringAreas(syntheticField([]), basins).areas).toEqual([]);
    const none = { ...syntheticField([]), hazard: undefined } as FieldView;
    expect(monitoringAreas(none, basins).areas).toEqual([]);
  });

  it("outlines a single cell with four edges in map pixels", () => {
    const path = outlinePath([0], 101, 241, { left: 0, top: 0, width: 241, height: 101 });
    expect(path.match(/M/g)).toHaveLength(4);
  });

  it("names a place only from the served basin boxes", () => {
    expect(basinOf(15, 88, basins)).toBe("Bay of Bengal");
    expect(basinOf(28, 60, basins)).toBeNull();
    expect(basinOf(15, 88, null)).toBeNull();
  });
});

describe("recent qualified states", () => {
  const days: DayState[] = [
    { date: "2026-09-01", status: "AVAILABLE" },
    { date: "2026-09-02", status: "UNAVAILABLE", missing_channels: ["currents_nrt"] },
    { date: "2026-09-03", status: "AVAILABLE" },
    { date: "2026-09-04", status: "AVAILABLE" },
    { date: "2026-09-05", status: "AVAILABLE" },
  ];

  it("measures change only across consecutive qualified days", () => {
    expect(contiguousRun(days, "2026-09-05")).toEqual(["2026-09-03", "2026-09-04", "2026-09-05"]);
    expect(contiguousRun(days, "2026-09-03")).toEqual(["2026-09-03"]);
    expect(contiguousRun(days, "2026-09-02")).toEqual([]);
    expect(contiguousRun(days, null)).toEqual([]);
  });

  it("reports interior gaps as non-contiguous and never fills them", () => {
    expect(windowGaps(days)).toEqual({
      available: ["2026-09-01", "2026-09-03", "2026-09-04", "2026-09-05"],
      gaps: ["2026-09-02"],
    });
    expect(windowGaps([days[0]]).gaps).toEqual([]);
  });
});

describe("plain-language meaning", () => {
  const t = {
    p50: 11.11,
    p75: 22.22,
    p90: 33.33,
    reference_period: "TEST PERIOD",
    n_dates: 1,
    n_samples: 1,
  };

  it("is conditional for supportive categories and never a forecast", () => {
    for (const label of ["LOW", "MODERATE", "ELEVATED", "HIGH", "NOT_CATEGORIZED"]) {
      const m = categoryMeaning(label);
      for (const text of Object.values(m)) {
        expect(text.length).toBeGreaterThan(0);
        expect(text.toLowerCase()).not.toMatch(/will (intensify|form|make landfall)|probability|danger/);
      }
    }
    expect(categoryMeaning("HIGH").relevance.startsWith("If ")).toBe(true);
    expect(categoryMeaning("ELEVATED").relevance.startsWith("If ")).toBe(true);
    expect(NOT_A_PROBABILITY).toContain("not cyclone probability");
  });

  it("quotes boundaries only from the thresholds it is given", () => {
    expect(bandText("HIGH", t)).toContain("33.3");
    expect(bandText("MODERATE", t)).toContain("11.1–22.2");
    expect(bandText("HIGH", t)).toContain("TEST PERIOD");
    expect(bandText("HIGH", null)).toBe("");
  });

  it("explains every term without hazard-zone language", () => {
    for (const entry of Object.values(GLOSSARY)) {
      expect(entry.text.length).toBeGreaterThan(40);
      expect(entry.text.toLowerCase()).not.toMatch(/danger zone|risk score|probability of/);
    }
  });
});
