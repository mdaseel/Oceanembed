/**
 * Transport types for Model Science and disaster-context endpoints. Every value
 * is produced by the backend over the frozen model or a provenance-carrying
 * artefact; nothing here is computed from a guess.
 */
import type { SectionPayload, TrackAnalysis } from "../hazard/api";

export interface FieldMeta {
  source: string;
  valid_date: string;
}

export interface AttributionResult {
  date: string;
  lat: number;
  lon: number;
  depths_m: number[];
  channels: string[];
  channel_labels: string[];
  channel_short: string[];
  net_c: number[][];
  gross_c: number[][];
  gross_share: number[][];
  prediction_c: number[];
  baseline_prediction_c: number[];
  completeness_residual_c: number[];
  method: Record<string, string | number>;
  wording: string;
  model_sha256: string;
  version: string;
  cached: boolean;
  field: FieldMeta;
}

export interface OcclusionPoint {
  delta_c: (number | null)[];
  depth_supported: boolean[];
  tchp_original: number | null;
  tchp_occluded: number | null;
  delta_tchp: number | null;
  tchp_status_original: string;
  tchp_status_occluded: string;
}
export interface OcclusionResult {
  date: string;
  lat: number;
  lon: number;
  depths_m: number[];
  channels: string[];
  channel_labels: string[];
  channel_short: string[];
  original_c: (number | null)[];
  point: Record<string, OcclusionPoint>;
  domain: Record<string, { median_abs_delta_c: (number | null)[]; p90_abs_delta_c: (number | null)[]; n_cells: number[] }>;
  method: Record<string, string | boolean>;
  wording: string;
  production_field: false;
  field: FieldMeta;
}

export interface RetrainedAblation {
  experiment: string;
  split: string;
  report: string;
  noise_floor_percent: { mean: number; max: number };
  groups: Record<string, { rmse_change_percent: number[]; anomaly_corr_change: number[] }>;
  depths_m: number[];
  sst_only: {
    status: "COMPLETED" | "NOT_RUN";
    note?: string;
    depths_m?: number[];
    models?: Record<string, { rmse_c: number[]; anomaly_correlation: (number | null)[]; skill_vs_l0_percent: number[] }>;
    protocol?: string;
  };
}

export interface BandQA {
  pairs: number;
  inversion_frequency: number | null;
  strong_inversion_frequency: number | null;
}
export interface RegionQA {
  profiles: number;
  profiles_with_inversion: number | null;
  bands: Record<string, BandQA>;
  per_pair: { from_m: number; to_m: number; pairs: number; inversion_frequency: number | null }[];
  strongest_gradient_quantiles: number[];
}
export interface PhysicalQASummary {
  protocol: string;
  rule: string;
  inversion_tolerance_c: number;
  strong_inversion_c: number;
  dates: { n: number; first: string; last: string; rule: string };
  support: string;
  reconstruction: Record<string, RegionQA>;
  reference_glorys: Record<string, RegionQA>;
  gradient_envelope: Record<string, {
    reference_p1: number;
    reference_p99: number;
    fraction_within_reference_envelope: number;
    fraction_steeper_than_reference_p1: number;
    reference_fraction_steeper_than_p1: number;
    profiles: number;
  }>;
  argo: {
    levels_m: number[];
    profiles: number;
    period: string;
    argo_observed: { pairs: number; inversion_frequency: number | null; profiles_with_inversion: number; strongest_gradient_median: number | null };
    l2_collocated: { pairs: number; inversion_frequency: number | null; profiles_with_inversion: number; strongest_gradient_median: number | null };
  };
  model_sha256: string;
}
export interface ColumnQA {
  date: string;
  lat: number;
  lon: number;
  water_depth_m: number | null;
  profile: {
    n_supported_levels: number;
    n_pairs: number;
    inversion_count: number;
    strong_inversion_count: number;
    max_inversion_c: number | null;
    strongest_gradient_c_per_m: number | null;
    strongest_gradient_depth_m: number | null;
    pairs: { from_m: number; to_m: number; gradient_c_per_m: number | null; delta_c: number | null; inversion: boolean }[];
    rule: string;
  };
  context: {
    region: string;
    reference_percentile: number | null;
    reconstruction_percentile: number | null;
    reference_inversion_frequency: Record<string, number | null>;
    note: string;
  } | null;
}

export interface Distribution {
  n: number;
  p5?: number;
  p25?: number;
  p50?: number;
  p75?: number;
  p95?: number;
}
export interface BasinPhysics {
  regions: Record<string, {
    mean_profile_l2_c: number[];
    mean_profile_glorys_c: number[];
    tchp_l2: Distribution;
    tchp_glorys: Distribution;
    d26_l2: Distribution;
    d26_glorys: Distribution;
    anomaly_50m_l2: Distribution;
    anomaly_100m_l2: Distribution;
    inversion_frequency_l2: Record<string, BandQA>;
    inversion_frequency_glorys: Record<string, BandQA>;
  }>;
  argo_skill: Record<string, { depth_m: number; model: string; n: number; rmse_c: number }[]>;
  attribution: {
    basins: Record<string, { n_cells: number; mean_gross_share: number[][] }>;
    depths_m: number[];
    channel_short: string[];
    dates: string[];
  } | null;
  caveat: string;
  depths_m: number[];
}

export interface ValidationContext {
  depth_m: number;
  requested_depth_m: number;
  scope: string;
  basin: string | null;
  models: Record<string, { n: number; rmse_c: number | null; bias_c: number | null; correlation: number | null; anomaly_correlation: number | null }>;
  l2_improvement_vs_l0_percent: number | null;
  bootstrap_l2_minus_l0: { rmse_difference_c: number; ci_lo: number; ci_hi: number; significant: boolean; clusters: number; cluster_unit: string } | null;
  regional_sample_note: string | null;
  period: string;
  wording: string;
  source: string;
}

export interface IntegrityItem {
  label: string;
  state: string;
  value: string;
  how: string;
}
export interface Integrity {
  items: IntegrityItem[];
  pipeline: { stage: string; detail: string }[];
}

export interface CoastalContext {
  status: string;
  grid_lat?: number;
  grid_lon?: number;
  nearest_coast_lat?: number;
  nearest_coast_lon?: number;
  offshore_distance_km?: number;
  coastal_state?: string;
  country?: string;
  coastal_segment?: string;
  coastal_district?: string | null;
  district_note?: string | null;
  precision_note?: string;
  wording: string;
  sources?: { name: string; version: string; license: string }[];
  distance_along_path_km?: number;
}

export interface ThermalExtremes {
  date: string;
  depth_m: number;
  name: string;
  rule: string;
  window: string[];
  window_days: number;
  extent_km2: Record<string, number>;
  n_active_cells: number;
  mhw_decision: string;
  baseline: Record<string, string | number | string[]>;
  extent_note: string;
  active?: number[][];
  excess_c?: (number | null)[][];
}
export interface ExtremePoint {
  date: string;
  depth_m: number;
  lat: number;
  lon: number;
  supported: boolean;
  active: boolean;
  duration_days: number;
  duration_at_least: boolean;
  excess_over_threshold_c: number | null;
  percentile_in_baseline_window: number | null;
  name: string;
}

export interface GroupStats {
  median: number;
  q1: number;
  q3: number;
  min: number;
  max: number;
}
export interface RiVariable {
  variable: string;
  label: string;
  unit: string;
  primary: boolean;
  n_ri: number;
  n_non_ri: number;
  ri: GroupStats | null;
  non_ri: GroupStats | null;
  p_value: number | null;
  p_holm: number | null;
  mann_whitney_u?: number;
  rank_biserial?: number;
  median_difference?: number;
  median_difference_ci95?: [number, number];
}
export interface RiComparison {
  n_ri: number;
  n_non_ri: number;
  tests_run: boolean;
  tests_note: string | null;
  variables: RiVariable[];
}
export interface RiStorm {
  sid: string;
  name: string;
  season: number;
  eligible: boolean;
  exclusion: string | null;
  ri: boolean | null;
  max_dv_kt?: number;
  split?: string;
  pair?: { t0: string; sample_date: string; v0: number; v1: number; dv: number };
  values?: Record<string, number | null>;
}
export interface RiResult {
  wind_source: string;
  counts: { storms_in_file_2015_2024: number; eligible: number; ri: number; non_ri: number; excluded: number };
  exclusion_reasons: Record<string, number>;
  comparison: RiComparison;
  sensitivity_2021_2024: RiComparison & { n_storms: number };
  storm_level_spearman_max_dv_vs_tchp: { rho: number; p_value: number; n: number; note: string } | null;
  storms: RiStorm[];
}
export interface RiSummary {
  title: string;
  definition: string;
  sampling: string;
  wording: string;
  protocol: string;
  split_disclosure: string;
  source: { dataset: string; sha256: string };
  generated_utc: string;
  results: Record<string, RiResult>;
}

export interface StressTestPayload {
  label: string;
  note: string;
  event_id: string;
  event: string;
  geometry: { source: string; translated: boolean; retimed: boolean; points: { lat: number; lon: number; time: string }[] };
  historical: { date: string; analysis: TrackAnalysis; section: SectionPayload; field: string };
  latest: { date: string; analysis: TrackAnalysis; section: SectionPayload; withheld: string[]; reconstruction_lag_hours: number | null; field: string } | null;
  comparison: { metric: string; label: string; unit: string; historical: number | null; latest: number | null; difference: number | null }[] | null;
  coastal_approach: CoastalContext | null;
  latest_state?: string;
}
