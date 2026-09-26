/**
 * Transport types for the event library, track x thermal analysis, change maps,
 * cyclone context and scenarios. Every number arrives from the backend, which
 * reads existing OceanEmbed fields through the frozen diagnostics.
 */
import { getJson } from "../../field/api";
export { getJson };

export async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw Error(
      typeof detail.detail === "string"
        ? detail.detail
        : `Local API unavailable (${response.status}).`,
    );
  }
  return response.json();
}

export interface Level {
  temperature: number | null;
  anomaly: number | null;
}
export interface TrackSample {
  distance_km: number;
  lat: number;
  lon: number;
  segment: number;
  point_type: string | null;
  from_time: string | null;
  to_time: string | null;
  length_km: number;
  in_domain: boolean;
  row: number | null;
  col: number | null;
  grid_lat: number | null;
  grid_lon: number | null;
  ocean: boolean;
  input_valid: boolean;
  category: string | null;
  tchp: number | null;
  d26: number | null;
  water_depth_m: number | null;
  levels: Record<string, Level>;
}
export interface Extreme {
  value: number;
  distance_km: number;
  lat: number;
  lon: number;
  category: string | null;
}
export interface StrongestSegment {
  category: string;
  start_km: number;
  end_km: number;
  length_km: number;
  lat_range: [number, number];
  lon_range: [number, number];
  peak_tchp: number | null;
  peak_lat: number;
  peak_lon: number;
  peak_distance_km: number;
  peak_anomaly_100m: number | null;
  n_samples: number;
  rule: string;
}
export interface TrackSummary {
  length_km: number;
  length_in_domain_km: number;
  n_samples: number;
  n_in_domain: number;
  n_with_tchp: number;
  tchp: { max: Extreme | null; median: number | null };
  d26: { withheld: boolean; median?: number | null; min?: number | null; max?: number | null };
  anomaly: Record<string, { max: Extreme | null; min: Extreme | null }>;
  category_distance_km: Record<string, number>;
  category_cells: Record<string, number>;
  highest_category: string | null;
  intersects: { HIGH: boolean; ELEVATED: boolean };
  strongest_segment: StrongestSegment | null;
}
export interface TrackAnalysis {
  date: string;
  samples: TrackSample[];
  summary: TrackSummary;
  withheld: string[];
  sample_depths_m: number[];
  rules: { sampling: string; distance: string; strongest_segment: string };
  labels?: Record<string, string>;
}
export interface SectionPayload {
  date: string;
  mode: "temperature" | "anomaly";
  depths_m: number[];
  distance_km: number[];
  lat: number[];
  lon: number[];
  values: (number | null)[][];
  water_depth_m: (number | null)[];
  length_km: number;
  bathymetry_available: boolean;
  note: string;
}
export interface Located {
  value: number;
  lat: number;
  lon: number;
}
export interface ChangeStats {
  n_cells: number;
  min: Located | null;
  max: Located | null;
  median: number | null;
}
export interface Footprint {
  temperature: Record<string, ChangeStats>;
  tchp: ChangeStats;
}
export interface DifferencePayload {
  from_dates: string[];
  to_dates: string[];
  rule: string;
  footprint: Footprint;
  grid?: { depth_m: number; values: (number | null)[][] };
  tchp_grid?: (number | null)[][];
  from_segment: string;
  to_segment: string;
  label: string;
  caution: string;
}
export interface ExternalMeta {
  intensity_source: string;
  peak_imd_wind_kt: number | null;
  peak_imd_wind_time: string;
  min_imd_pressure_hpa: number | null;
  first_landfall_fix_time: string;
}
export interface EventSummary {
  event_id: string;
  name: string;
  short_name: string;
  season: number;
  basin: string;
  window_start: string;
  window_end: string;
  peak: string;
  landfall: string;
  split: "train" | "validation" | "test" | "mixed";
  in_sample: boolean;
  split_note: string;
  frozen: boolean;
  external_metadata: ExternalMeta;
  track_source: string;
  track_agency: string;
  replay_days: number;
  track_fixes_inside_domain: number;
  track_fixes_total: number;
}
export interface Candidate {
  event_id: string;
  name: string;
  season: number;
  enabled: boolean;
  exclusion_reasons: string[];
  split?: string;
  basin?: string;
}
export interface EventLibraryPayload {
  events: EventSummary[];
  candidates: Candidate[];
  rule: string | null;
  source: { dataset: string; url: string; sha256: string } | null;
}
export interface EventMetrics {
  pre_event_tchp: number | null;
  event_tchp: number | null;
  wake_min_tchp: { value: number; date: string } | null;
  tchp_change: number | null;
  tchp_change_pct: number | null;
  temperature_change_c: Record<string, number | null>;
  sst_change_c: number | null;
  d26_change_m: number | null;
  max_pre_event_anomaly_100m_c: number | null;
  final: { date: string; tchp: number } | null;
  final_vs_pre_tchp: number | null;
  final_vs_wake_min_tchp: number | null;
  definitions: Record<string, string>;
}
export interface CompareEntry {
  event_id: string;
  name: string;
  basin: string;
  season: number;
  split: string;
  in_sample: boolean;
  window: [string, string];
  metrics: EventMetrics;
  pre_to_wake_footprint: Footprint;
  external_metadata: ExternalMeta;
  track_source: string;
}
export interface ComparePayload {
  events: CompareEntry[];
  note: string;
  corridor_deg: number;
}
export interface EventBriefPayload {
  title: string;
  event_id: string;
  event: string;
  basin: string;
  event_dates: [string, string];
  peak: string;
  landfall: string;
  segments: { label: string; start: string; end: string }[];
  track_source: string;
  external_metadata: ExternalMeta;
  metrics: EventMetrics;
  strongest_subsurface_cooling_c: Record<string, Located | null>;
  strongest_affected_thermal_region: (Located & { basin: string | null; quantity: string }) | null;
  pre_to_wake_footprint: Footprint;
  pre_to_recovery_footprint: Footprint;
  interpretation: string[];
  limitations: string[];
  provenance: Record<string, string | boolean>;
  non_prediction: string;
}
export interface ExternalPoint {
  valid_time: string;
  lat: number;
  lon: number;
  point_type: "observed" | "forecast";
  source: string;
  storm_class: string | null;
  wind_kt: number | null;
  pressure_hpa: number | null;
}
export interface CycloneAdvisory {
  source: string;
  provider: string;
  track_source: string;
  source_event_id: string;
  episode_id: string;
  storm_name: string;
  basin: string;
  advisory_issued_at: string;
  retrieved_at: string;
  status: string;
  observed_points: ExternalPoint[];
  forecast_points: ExternalPoint[];
  forecast_flag_disagreements: unknown[];
  report_url: string | null;
  attribution: string;
  provenance_label: string;
  alert_level: string | null;
}
export interface CycloneState {
  state: string;
  provider: string;
  retrieved_at: string | null;
  checked_at?: string;
  cached?: boolean;
  message?: string;
  advisories: CycloneAdvisory[];
  imd_status: string;
  current_outside_north_indian?: string[];
  error?: string;
  label?: string;
  note?: string;
  attribution?: string;
}
export interface ThermalFieldMeta {
  source: string;
  valid_date: string;
  served_from?: string;
  retrieval_time_utc?: string;
  reconstruction_lag_hours?: number;
  advisory_minus_valid_hours?: number;
  withheld: string[];
}
export interface CycloneAnalysis extends CycloneState {
  advisory: CycloneAdvisory | null;
  analysis: TrackAnalysis | null;
  section: SectionPayload | null;
  thermal_field?: ThermalFieldMeta;
  labels?: { track: string; thermal_state: string };
  latest_state?: string;
}
export interface ScenarioResult {
  badge: string;
  analysis: TrackAnalysis;
  section: SectionPayload;
  thermal_field: ThermalFieldMeta;
  labels: { path: string; thermal_state: string };
}
