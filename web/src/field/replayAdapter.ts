import {
  validateField,
  type Diagnostics,
  type FieldView,
  type Hazard,
  type Provenance,
} from "./contract";
export interface SurfaceInput {
  values: Float64Array;
  units: string;
  product: string;
}
export interface ReplayData {
  field: FieldView;
  surface: Record<string, SurfaceInput>;
}
type Cube = (number | null)[][][];
export interface ReplayPayload {
  schema: string;
  date: string;
  shape: number[];
  lat: number[];
  lon: number[];
  depths_m: number[];
  temperature: Cube;
  climatology: Cube;
  anomaly: Cube;
  ocean_mask: boolean[][];
  surface_input_valid: boolean[][];
  climatology_defined: boolean[][][];
  provenance: Provenance;
  credits: string;
  surface_inputs: Record<
    string,
    { values: (number | null)[][]; units: string; product: string }
  >;
  diagnostics?: {
    d26_m: (number | null)[][];
    tchp_kj_cm2: (number | null)[][];
    status: number[][];
    status_labels: Record<string, string>;
    status_counts: Record<string, number>;
    convention: Record<string, unknown>;
    d26_physical_status: number[][];
    tchp_physical_status: number[][];
    physical_status_labels: Record<string, string>;
    physical_status_counts: Record<string, number>;
  };
  hazard?: {
    indicator: string;
    available: boolean;
    category: number[][];
    category_labels: Record<string, string>;
    category_counts: Record<string, number>;
    thresholds: Hazard["thresholds"];
    protocol: string;
    reconstruction_error_kj_cm2: Hazard["error"];
    non_prediction_statement: string;
    uncertainty_note: string;
    scope_note: string;
  };
}
function checkShape(value: unknown, shape: number[]): void {
  if (!Array.isArray(value) || value.length !== shape[0])
    throw Error("Malformed field dimensions");
  if (shape.length > 1)
    for (const row of value) checkShape(row, shape.slice(1));
}
function numbers(value: unknown[], mask = false): number[] {
  return value.flat(Infinity).map((x) => {
    if (mask) {
      if (typeof x !== "boolean") throw Error("Malformed mask");
      return +x;
    }
    if (x === null) return NaN;
    if (typeof x !== "number" || !Number.isFinite(x))
      throw Error("Malformed scientific value");
    return x;
  });
}
export function adaptReplay(p: ReplayPayload): ReplayData {
  if (
    p.schema !== "oceanembed.field-view.v1" ||
    p.shape.join() !== "101,241,15"
  )
    throw Error("Unsupported replay transport");
  for (const k of [
    "temperature",
    "climatology",
    "anomaly",
    "climatology_defined",
  ] as const)
    checkShape(p[k], p.shape);
  for (const k of ["ocean_mask", "surface_input_valid"] as const)
    checkShape(p[k], p.shape.slice(0, 2));
  let diagnostics: Diagnostics | undefined;
  if (p.diagnostics) {
    const d = p.diagnostics;
    for (const k of ["d26_m", "tchp_kj_cm2", "status", "d26_physical_status",
                     "tchp_physical_status"] as const)
      checkShape(d[k], p.shape.slice(0, 2));
    diagnostics = {
      d26: Float64Array.from(numbers(d.d26_m)),
      tchp: Float64Array.from(numbers(d.tchp_kj_cm2)),
      status: Uint8Array.from(numbers(d.status)),
      statusLabels: Object.fromEntries(
        Object.entries(d.status_labels).map(([k, v]) => [Number(k), v]),
      ),
      statusCounts: d.status_counts,
      convention: d.convention,
      d26Physical: Uint8Array.from(numbers(d.d26_physical_status)),
      tchpPhysical: Uint8Array.from(numbers(d.tchp_physical_status)),
      physicalLabels: Object.fromEntries(
        Object.entries(d.physical_status_labels).map(([k, v]) => [Number(k), v]),
      ),
      physicalCounts: d.physical_status_counts,
    };
  }
  let hazard: Hazard | undefined;
  if (p.hazard) {
    const h = p.hazard;
    checkShape(h.category, p.shape.slice(0, 2));
    hazard = {
      indicator: h.indicator,
      available: h.available,
      category: Uint8Array.from(numbers(h.category)),
      categoryLabels: Object.fromEntries(
        Object.entries(h.category_labels).map(([k, v]) => [Number(k), v]),
      ),
      categoryCounts: h.category_counts,
      thresholds: h.thresholds,
      protocol: h.protocol,
      error: h.reconstruction_error_kj_cm2,
      nonPrediction: h.non_prediction_statement,
      uncertaintyNote: h.uncertainty_note,
      scopeNote: h.scope_note,
    };
  }
  const field = validateField({
    diagnostics,
    hazard,
    effectiveDate: p.date,
    lat: Float64Array.from(p.lat),
    lon: Float64Array.from(p.lon),
    depths: p.depths_m,
    temperature: Float64Array.from(numbers(p.temperature)),
    climatology: Float64Array.from(numbers(p.climatology)),
    anomaly: Float64Array.from(numbers(p.anomaly)),
    ocean: Uint8Array.from(numbers(p.ocean_mask, true)),
    inputValid: Uint8Array.from(numbers(p.surface_input_valid, true)),
    climatologyDefined: Uint8Array.from(numbers(p.climatology_defined, true)),
    provenance: p.provenance,
    credits: p.credits,
  });
  const surface: ReplayData["surface"] = {};
  for (const name of [
    "sst",
    "sss",
    "sla",
    "current_u",
    "current_v",
    "wind_u",
    "wind_v",
  ]) {
    const input = p.surface_inputs[name];
    if (!input) throw Error(`Missing ${name} input`);
    checkShape(input.values, [101, 241]);
    surface[name] = {
      ...input,
      values: Float64Array.from(numbers(input.values)),
    };
  }
  return { field, surface };
}
