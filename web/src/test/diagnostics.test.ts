import { describe, expect, it } from "vitest";
import {
  diagnosticColor,
  diagnosticRange,
  diagnosticRaster,
  NO_CROSSING_RGB,
  OUTSIDE_RGB,
} from "../field/diagnostics";
import {
  DEPTHS,
  asLayer,
  diagnosticAt,
  isDiagnostic,
  validateField,
  type Diagnostics,
  type FieldView,
} from "../field/contract";
import { adaptReplay, type ReplayPayload } from "../field/replayAdapter";

const ROWS = 101,
  COLS = 241,
  N = ROWS * COLS;

const LABELS: Record<number, string> = {
  0: "OK",
  1: "SURFACE_BELOW_26",
  2: "NO_CROSSING_IN_SUPPORT",
  3: "INSUFFICIENT_SUPPORT",
  4: "NO_VALID_LEVELS",
};
const PHYSICAL: Record<number, string> = {
  0: "SUPPORTED",
  1: "INSUFFICIENT_WATER_COLUMN_SUPPORT",
  2: "NOT_APPLICABLE",
  3: "UNVERIFIED",
};

function diagnostics(overrides: Partial<Diagnostics> = {}): Diagnostics {
  return {
    d26: Float64Array.from({ length: N }, () => 80),
    tchp: Float64Array.from({ length: N }, () => 60),
    status: new Uint8Array(N),
    statusLabels: LABELS,
    statusCounts: { OK: N },
    convention: { d26: "shallowest crossing", constants_source: "TEOS-10" },
    d26Physical: new Uint8Array(N),
    tchpPhysical: new Uint8Array(N),
    physicalLabels: PHYSICAL,
    physicalCounts: { SUPPORTED: N },
    ...overrides,
  };
}

function field(d?: Diagnostics): FieldView {
  return {
    effectiveDate: "2023-06-25",
    lat: Float64Array.from({ length: ROWS }, (_, i) => 5 + i * 0.25),
    lon: Float64Array.from({ length: COLS }, (_, i) => 45 + i * 0.25),
    depths: DEPTHS,
    temperature: new Float64Array(N * 15).fill(20),
    climatology: new Float64Array(N * 15).fill(19),
    anomaly: new Float64Array(N * 15).fill(1),
    ocean: new Uint8Array(N).fill(1),
    inputValid: new Uint8Array(N).fill(1),
    climatologyDefined: new Uint8Array(N * 15).fill(1),
    provenance: {
      model_name: "L2",
      l2_state_dict_sha256: "hash",
      l2_encoder_sha256: "enc",
      latent_dim: 32,
      receptive_field: 33,
      n_parameters: 1,
      inference_source: "LIVE_MODEL_RUN",
      compute_seconds: 1,
      n_supported_cells: N,
      n_ocean_cells: N,
      nominal_zero_m_note: "",
      deep_skill_note: "",
      climatology_defined_note: "",
    },
    credits: "",
    diagnostics: d,
  };
}

describe("diagnostic layer typing", () => {
  it("treats only the depth-integrated kinds as diagnostics", () => {
    expect(isDiagnostic("d26")).toBe(true);
    expect(isDiagnostic("tchp")).toBe(true);
    expect(isDiagnostic("temperature")).toBe(false);
    expect(isDiagnostic("anomaly")).toBe(false);
  });

  it("falls a diagnostic back to a real depth-indexed layer for the 3D view", () => {
    expect(asLayer("d26")).toBe("temperature");
    expect(asLayer("tchp")).toBe("temperature");
    expect(asLayer("anomaly")).toBe("anomaly");
  });
});

describe("field contract validation of diagnostics", () => {
  it("accepts a field with no diagnostics at all", () => {
    expect(() => validateField(field(undefined))).not.toThrow();
  });

  it("rejects a defined D26 whose status is not OK", () => {
    const d = diagnostics();
    d.status[7] = 3; // INSUFFICIENT_SUPPORT, but d26 is still a number
    expect(() => validateField(field(d))).toThrow(/status/i);
  });

  it("rejects a NaN D26 that claims OK", () => {
    const d = diagnostics();
    d.d26[11] = NaN;
    expect(() => validateField(field(d))).toThrow(/status/i);
  });

  it("accepts TCHP = 0 for a column entirely below 26 degrees", () => {
    const d = diagnostics();
    d.status[3] = 1; // SURFACE_BELOW_26
    d.d26[3] = NaN; // no isotherm
    d.tchp[3] = 0; // but zero heat above 26 is a real value
    expect(() => validateField(field(d))).not.toThrow();
  });

  it("rejects a NaN TCHP where the status says the column is below 26", () => {
    const d = diagnostics();
    d.status[3] = 1;
    d.d26[3] = NaN;
    d.tchp[3] = NaN;
    expect(() => validateField(field(d))).toThrow(/TCHP/i);
  });

  it("rejects a shape mismatch", () => {
    const d = diagnostics({ d26: new Float64Array(5) });
    expect(() => validateField(field(d))).toThrow(/shape/i);
  });

  // Phase 8B: the latest mode withholds D26 (not operationally qualified).
  it("accepts a withheld D26 that carries no value anywhere", () => {
    const d = diagnostics({
      d26: new Float64Array(N).fill(NaN),
      withheld: ["d26"],
    });
    expect(() => validateField(field(d))).not.toThrow();
  });

  it("rejects a withheld D26 that still carries a value", () => {
    const d = diagnostics({
      d26: new Float64Array(N).fill(NaN),
      withheld: ["d26"],
    });
    d.d26[42] = 80;
    expect(() => validateField(field(d))).toThrow(/Withheld D26/);
  });

  it("keeps the full TCHP check when only D26 is withheld", () => {
    const d = diagnostics({
      d26: new Float64Array(N).fill(NaN),
      withheld: ["d26"],
    });
    d.tchp[9] = NaN; // status OK, so TCHP must be defined
    expect(() => validateField(field(d))).toThrow(/TCHP/);
  });
});

describe("reading a diagnostic at a cell", () => {
  it("returns the value and the status name", () => {
    const f = field(diagnostics());
    const got = diagnosticAt(f, "d26", {
      requestedLat: 0,
      requestedLon: 0,
      row: 2,
      col: 3,
      status: "OK",
    });
    expect(got).toEqual({ value: 80, status: "OK", physical: "SUPPORTED" });
  });

  it("returns null when the field carries no diagnostics", () => {
    expect(
      diagnosticAt(field(undefined), "d26", {
        requestedLat: 0,
        requestedLon: 0,
        row: 2,
        col: 3,
        status: "OK",
      }),
    ).toBeNull();
  });

  it("reports an undefined cell as NaN with its reason, never as zero", () => {
    const d = diagnostics();
    const i = 2 * COLS + 3;
    d.status[i] = 3;
    d.d26[i] = NaN;
    d.tchp[i] = NaN;
    const got = diagnosticAt(field(d), "d26", {
      requestedLat: 0,
      requestedLon: 0,
      row: 2,
      col: 3,
      status: "OK",
    });
    expect(got!.value).toBeNaN();
    expect(got!.value).not.toBe(0);
    expect(got!.status).toBe("INSUFFICIENT_SUPPORT");
  });
});

describe("diagnostic range and colours", () => {
  it("spans the values actually present, not a fixed invented range", () => {
    const d = diagnostics();
    d.d26.fill(50);
    d.d26[0] = 20;
    d.d26[1] = 130;
    const r = diagnosticRange(field(d), "d26");
    expect(r.actualMin).toBe(20);
    expect(r.actualMax).toBe(130);
    expect(r.count).toBe(N);
  });

  it("ignores cells outside the population when ranging", () => {
    const d = diagnostics();
    const f = field(d);
    f.inputValid = new Uint8Array(N); // nothing valid
    expect(diagnosticRange(f, "d26").count).toBe(0);
  });

  it("maps the range endpoints to the ends of the ramp", () => {
    const range = { min: 0, max: 100, actualMin: 0, actualMax: 100, count: 2 };
    const lo = diagnosticColor(0, range, "d26");
    const hi = diagnosticColor(100, range, "d26");
    expect(lo).not.toEqual(hi);
    // D26 and TCHP must not share a ramp, or one map could be read as the other.
    expect(diagnosticColor(50, range, "d26")).not.toEqual(
      diagnosticColor(50, range, "tchp"),
    );
  });
});

describe("raster rendering of undefined cells", () => {
  const pixelAt = (px: Uint8ClampedArray, w: number, x: number, y: number) =>
    Array.from(px.slice((y * w + x) * 4, (y * w + x) * 4 + 3));

  it("draws no-crossing cells in the hatch colour, never as a low value", () => {
    const d = diagnostics();
    d.d26.fill(NaN);
    d.status.fill(3);
    const f = field(d);
    const range = { min: 0, max: 100, actualMin: 0, actualMax: 100, count: 1 };
    const { pixels, counts } = diagnosticRaster(f, "d26", range, 64, 32);
    expect(counts.shown).toBe(0);
    expect(counts.noCrossing).toBeGreaterThan(0);
    const seen = new Set<string>();
    for (let x = 0; x < 16; x++) seen.add(pixelAt(pixels, 64, x, 0).join(","));
    // Both the hatch colour and its darker stripe must appear: the texture is
    // what makes the class readable without relying on colour alone.
    expect(seen.has(NO_CROSSING_RGB.join(","))).toBe(true);
    expect(seen.size).toBeGreaterThan(1);
  });

  it("draws land and invalid-input cells as outside, not as a diagnostic", () => {
    const f = field(diagnostics());
    f.ocean = new Uint8Array(N);
    const range = { min: 0, max: 100, actualMin: 0, actualMax: 100, count: 1 };
    const { pixels, counts } = diagnosticRaster(f, "d26", range, 32, 16);
    expect(counts.shown).toBe(0);
    expect(counts.outside).toBeGreaterThan(0);
    expect(pixelAt(pixels, 32, 5, 5)).toEqual(OUTSIDE_RGB);
  });

  it("renders a defined cell with the ramp", () => {
    const f = field(diagnostics());
    const range = { min: 0, max: 100, actualMin: 0, actualMax: 100, count: 1 };
    const { pixels, counts } = diagnosticRaster(f, "d26", range, 32, 16);
    expect(counts.shown).toBeGreaterThan(0);
    expect(pixelAt(pixels, 32, 5, 5)).toEqual(
      Array.from(diagnosticColor(80, range, "d26")),
    );
  });
});

describe("transport adapter", () => {
  const grid = <T,>(v: T): T[][] =>
    Array.from({ length: ROWS }, () => Array.from({ length: COLS }, () => v));

  const payload = (withDiagnostics: boolean): ReplayPayload => ({
    schema: "oceanembed.field-view.v1",
    date: "2023-06-25",
    shape: [ROWS, COLS, 15],
    lat: Array.from({ length: ROWS }, (_, i) => 5 + i * 0.25),
    lon: Array.from({ length: COLS }, (_, i) => 45 + i * 0.25),
    depths_m: [...DEPTHS],
    temperature: grid(Array.from({ length: 15 }, () => 20)) as never,
    climatology: grid(Array.from({ length: 15 }, () => 19)) as never,
    anomaly: grid(Array.from({ length: 15 }, () => 1)) as never,
    ocean_mask: grid(true),
    surface_input_valid: grid(true),
    climatology_defined: grid(Array.from({ length: 15 }, () => true)) as never,
    provenance: field().provenance,
    credits: "",
    surface_inputs: Object.fromEntries(
      ["sst", "sss", "sla", "current_u", "current_v", "wind_u", "wind_v"].map(
        (n) => [n, { values: grid(1), units: "x", product: "y" }],
      ),
    ),
    ...(withDiagnostics
      ? {
          diagnostics: {
            d26_m: grid(80) as (number | null)[][],
            tchp_kj_cm2: grid(60) as (number | null)[][],
            status: grid(0),
            status_labels: Object.fromEntries(
              Object.entries(LABELS).map(([k, v]) => [k, v]),
            ),
            status_counts: { OK: N },
            convention: { d26: "shallowest crossing" },
            d26_physical_status: grid(0),
            tchp_physical_status: grid(0),
            physical_status_labels: Object.fromEntries(
              Object.entries(PHYSICAL).map(([k, v]) => [k, v]),
            ),
            physical_status_counts: { SUPPORTED: N },
          },
        }
      : {}),
  });

  it("adapts diagnostics when the transport carries them", () => {
    const { field: f } = adaptReplay(payload(true));
    expect(f.diagnostics).toBeDefined();
    expect(f.diagnostics!.d26.length).toBe(N);
    expect(f.diagnostics!.d26[0]).toBe(80);
    expect(f.diagnostics!.statusLabels[0]).toBe("OK");
  });

  it("still adapts a field-view that has no diagnostics block", () => {
    const { field: f } = adaptReplay(payload(false));
    expect(f.diagnostics).toBeUndefined();
    expect(f.temperature.length).toBe(N * 15);
  });

  it("turns a null diagnostic into NaN, never into zero", () => {
    const p = payload(true);
    p.diagnostics!.d26_m[0][0] = null;
    p.diagnostics!.tchp_kj_cm2[0][0] = null;
    p.diagnostics!.status[0][0] = 3;
    const { field: f } = adaptReplay(p);
    expect(f.diagnostics!.d26[0]).toBeNaN();
    expect(f.diagnostics!.d26[0]).not.toBe(0);
  });
});
