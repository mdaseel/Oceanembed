/** Source-independent scientific boundary. Values retain float64 precision. */
export const DEPTHS = [
  0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000,
] as const;
export type Layer = "temperature" | "anomaly";
export type Palette = "thermal" | "viridis" | "cividis";
/**
 * Depth-integrated diagnostics. They are (lat, lon) surfaces, not depth-indexed
 * layers, and they are computed by the BACKEND from the same authoritative
 * field the map and profile use. The frontend never recomputes them: a second
 * D26 implementation in TypeScript could drift from the Python one, and then a
 * map and a profile could disagree about the same cell.
 */
export type DiagnosticKind = "d26" | "tchp";
export type MapLayer = Layer | DiagnosticKind;
export const DIAGNOSTIC_KINDS: DiagnosticKind[] = ["d26", "tchp"];
export const isDiagnostic = (l: MapLayer): l is DiagnosticKind =>
  l === "d26" || l === "tchp";
/** The depth-indexed layer to fall back to when a diagnostic is selected. */
export const asLayer = (l: MapLayer): Layer =>
  isDiagnostic(l) ? "temperature" : l;
export const DIAGNOSTIC_UNIT: Record<DiagnosticKind, string> = {
  d26: "m",
  tchp: "kJ/cm²",
};
export const DIAGNOSTIC_NAME: Record<DiagnosticKind, string> = {
  d26: "Depth of the 26 °C isotherm",
  tchp: "Tropical cyclone heat potential",
};
export interface Diagnostics {
  /** Metres. NaN means undefined — never zero, never extrapolated. */
  d26: Float64Array;
  /** kJ/cm². NaN means undefined; 0 is a real value where the column is < 26 °C. */
  tchp: Float64Array;
  /** Per-cell reason code; `statusLabels` maps it to a name. */
  status: Uint8Array;
  statusLabels: Record<number, string>;
  statusCounts: Record<string, number>;
  convention: Record<string, unknown>;
  /**
   * Physical water-column support, decided by the BACKEND from the ETOPO
   * artifact. A separate axis from `status`: the Phase 7C diagnostic statuses
   * are frozen, so "the isotherm resolved" and "there is water that deep" are
   * carried independently and never collapsed into one code.
   */
  d26Physical: Uint8Array;
  tchpPhysical: Uint8Array;
  physicalLabels: Record<number, string>;
  physicalCounts: Record<string, number>;
}
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
/**
 * Ocean Thermal Support for Cyclone Intensification. Categorised by the
 * BACKEND from the same TCHP the diagnostics show, against thresholds frozen in
 * `outputs/phase7/HAZARD_INDICATOR_PROTOCOL.md`. The frontend never categorises
 * and never holds a threshold of its own.
 */
export interface Hazard {
  indicator: string;
  available: boolean;
  category: Uint8Array;
  categoryLabels: Record<number, string>;
  categoryCounts: Record<string, number>;
  thresholds: {
    p50: number;
    p75: number;
    p90: number;
    reference_period: string;
    n_dates: number;
    n_samples: number;
  } | null;
  protocol: string;
  error: { mae: number; rmse: number; bias: number; source: string };
  nonPrediction: string;
  uncertaintyNote: string;
  scopeNote: string;
}
export const HAZARD_ORDER = [
  "LOW",
  "MODERATE",
  "ELEVATED",
  "HIGH",
] as const;
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
  /**
   * Optional by design. A field-view source that cannot supply diagnostics
   * still renders; the UI then offers no diagnostic layer rather than
   * inventing one. This is what keeps the §7.0 renderer source-agnostic.
   */
  diagnostics?: Diagnostics;
  /** Optional for the same reason as `diagnostics`: a source that cannot
   *  supply it still renders, and the UI offers no indicator rather than
   *  inventing one. */
  hazard?: Hazard;
}
/** The category and its explanation at one resolved cell. */
export function hazardAt(
  f: FieldView,
  s: Selection,
): { label: string; tchp: number; supported: boolean } | null {
  if (!f.hazard || s.row < 0) return null;
  const i = s.row * f.lon.length + s.col;
  const label = f.hazard.categoryLabels[f.hazard.category[i]] ?? "NOT_CATEGORIZED";
  return {
    label,
    tchp: f.diagnostics ? f.diagnostics.tchp[i] : NaN,
    supported: label !== "NOT_CATEGORIZED",
  };
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
/** The diagnostic value, its reason code, and its physical support at a cell. */
export function diagnosticAt(
  f: FieldView,
  kind: DiagnosticKind,
  s: Selection,
): { value: number; status: string; physical: string } | null {
  if (!f.diagnostics || s.row < 0) return null;
  const d = f.diagnostics;
  const i = s.row * f.lon.length + s.col;
  const code = kind === "d26" ? d.d26Physical[i] : d.tchpPhysical[i];
  return {
    value: d[kind][i],
    status: d.statusLabels[d.status[i]] ?? "UNKNOWN",
    physical: d.physicalLabels[code] ?? "UNKNOWN",
  };
}
/** Whether a diagnostic is both defined AND standing on a real water column. */
export const diagnosticUsable = (
  f: FieldView,
  kind: DiagnosticKind,
  i: number,
): boolean => {
  const d = f.diagnostics;
  if (!d) return false;
  const code = kind === "d26" ? d.d26Physical[i] : d.tchpPhysical[i];
  return (
    Number.isFinite(d[kind][i]) && d.physicalLabels[code] === "SUPPORTED"
  );
};
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
  if (f.diagnostics) {
    const d = f.diagnostics;
    if (
      d.d26.length !== n ||
      d.tchp.length !== n ||
      d.status.length !== n ||
      d.d26Physical.length !== n ||
      d.tchpPhysical.length !== n
    )
      throw Error("Diagnostic shape mismatch");
    // Re-check the backend's own invariant rather than trusting it: a defined
    // D26 must carry an OK status, and a NaN must never be read as a zero.
    for (let i = 0; i < n; i++) {
      const label = d.statusLabels[d.status[i]];
      if (Number.isFinite(d.d26[i]) !== (label === "OK"))
        throw Error("D26 value disagrees with its status");
      if (
        Number.isFinite(d.tchp[i]) !==
        (label === "OK" || label === "SURFACE_BELOW_26")
      )
        throw Error("TCHP value disagrees with its status");
    }
  }
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
