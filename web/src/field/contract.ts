/** Source-independent scientific boundary. Values retain float64 precision. */
export const DEPTHS = [
  0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000,
] as const;
export type Layer = "temperature" | "anomaly";
export type Palette = "thermal" | "viridis" | "cividis";
export interface Provenance {
  model_name: string;
  l2_state_dict_sha256: string;
  l2_encoder_sha256: string;
  latent_dim: number;
  receptive_field: number;
  n_parameters: number;
  inference_source: string;
  compute_seconds: number | null;
  n_supported_cells: number;
  n_ocean_cells: number;
  nominal_zero_m_note: string;
  deep_skill_note: string;
  climatology_defined_note: string;
  [key: string]: unknown;
}
export interface FieldView {
  effectiveDate: string;
  lat: Float64Array;
  lon: Float64Array;
  depths: readonly number[];
  temperature: Float64Array;
  climatology: Float64Array;
  anomaly: Float64Array;
  ocean: Uint8Array;
  inputValid: Uint8Array;
  climatologyDefined: Uint8Array;
  provenance: Provenance;
  credits: string;
}
export interface Selection {
  requestedLat: number;
  requestedLon: number;
  row: number;
  col: number;
  status: "OK" | "INVALID_OCEAN_CELL" | "INPUT_NOT_VALID" | "OUTSIDE_DOMAIN";
}
export const offset = (f: FieldView, row: number, col: number, depth: number) =>
  (row * f.lon.length + col) * f.depths.length + depth;
export const isSupported = (f: FieldView, row: number, col: number) =>
  !!(
    f.ocean[row * f.lon.length + col] && f.inputValid[row * f.lon.length + col]
  );
export function resolve(f: FieldView, lat: number, lon: number): Selection {
  const base = { requestedLat: lat, requestedLon: lon };
  if (
    !Number.isFinite(lat) ||
    !Number.isFinite(lon) ||
    lat < f.lat[0] ||
    lat > f.lat.at(-1)! ||
    lon < f.lon[0] ||
    lon > f.lon.at(-1)!
  )
    return { ...base, row: -1, col: -1, status: "OUTSIDE_DOMAIN" };
  // Match numpy argmin: ties select the first (south/west) index.
  const nearest = (axis: Float64Array, x: number) =>
    axis.reduce(
      (best, value, i) =>
        Math.abs(value - x) < Math.abs(axis[best] - x) ? i : best,
      0,
    );
  const row = nearest(f.lat, lat),
    col = nearest(f.lon, lon),
    i = row * f.lon.length + col;
  return {
    ...base,
    row,
    col,
    status: !f.ocean[i]
      ? "INVALID_OCEAN_CELL"
      : !f.inputValid[i]
        ? "INPUT_NOT_VALID"
        : "OK",
  };
}
export function profile(f: FieldView, s: Selection) {
  if (s.row < 0) return [];
  return f.depths.map((depth, k) => ({
    depth,
    temperature: f.temperature[offset(f, s.row, s.col, k)],
    climatology: f.climatology[offset(f, s.row, s.col, k)],
    anomaly: f.anomaly[offset(f, s.row, s.col, k)],
  }));
}
export function slice(f: FieldView, layer: Layer, k: number): Float64Array {
  if (!Number.isInteger(k) || k < 0 || k >= f.depths.length)
    throw Error("Unsupported depth");
  return Float64Array.from(f.ocean, (_, i) =>
    f.ocean[i] && f.inputValid[i] ? f[layer][i * f.depths.length + k] : NaN,
  );
}
export function validateField(f: FieldView): FieldView {
  if (
    f.lat.length !== 101 ||
    f.lon.length !== 241 ||
    f.depths.join() !== DEPTHS.join()
  )
    throw Error("Noncanonical grid or depth order");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f.effectiveDate))
    throw Error("Field date unavailable");
  if (!f.provenance?.l2_state_dict_sha256 || !f.provenance.inference_source)
    throw Error("Missing provenance");
  for (const [axis, start] of [
    [f.lat, 5],
    [f.lon, 45],
  ] as const)
    if (axis.some((x, i) => x !== start + i * 0.25))
      throw Error("Noncanonical coordinates");
  const n = f.lat.length * f.lon.length;
  for (const key of [
    "temperature",
    "climatology",
    "anomaly",
    "climatologyDefined",
  ] as const)
    if (f[key].length !== n * DEPTHS.length)
      throw Error(`${key} shape mismatch`);
  if (f.ocean.length !== n || f.inputValid.length !== n)
    throw Error("Mask shape mismatch");
  for (let i = 0; i < f.temperature.length; i++) {
    const t = f.temperature[i],
      c = f.climatology[i],
      a = f.anomaly[i];
    if (Boolean(f.climatologyDefined[i]) !== Number.isFinite(c))
      throw Error("Climatology support mismatch");
    if (
      Number.isFinite(t) && Number.isFinite(c)
        ? !Number.isFinite(a) || Math.abs(a - (t - c)) > 1e-10
        : Number.isFinite(a)
    )
      throw Error("Anomaly does not match L2 minus L0");
  }
  return f;
}
export const format = (v: number | null | undefined, digits = 3) =>
  typeof v === "number" && Number.isFinite(v)
    ? v.toFixed(digits)
    : "Unavailable";
