import { validateField, type FieldView, type Provenance } from "./contract";
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
  const field = validateField({
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
