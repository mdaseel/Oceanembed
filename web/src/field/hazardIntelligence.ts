/**
 * Ocean Thermal Hazard Intelligence — the translation layer.
 *
 * Everything here turns quantities the BACKEND already computed (L2
 * temperature, L0 climatology, anomaly, Phase 7C D26/TCHP, the Phase 7D
 * thermal-support category, the pre-registered Mocha segments and the event
 * series) into plain-language context. Nothing here categorises a cell, holds a
 * threshold, fits a trend line, scores risk or produces a probability:
 *
 *  - categories are read from `hazard.category`, never re-derived;
 *  - boundary numbers are read from `hazard.thresholds`, never typed in;
 *  - every "change" is a subtraction between two real reconstructions;
 *  - monitoring areas are contiguous groups of backend-labelled HIGH/ELEVATED
 *    cells, ranked by a stated rule with no weights.
 */
import { displayDepthValid, type Bathymetry } from "./bathymetry";
import {
  diagnosticUsable,
  isSupported,
  offset,
  type FieldView,
  type Hazard,
  type Selection,
} from "./contract";

// ------------------------------------------------------------------ types
export interface EventSegment {
  label: string;
  start: string;
  end: string;
}
export interface TrackPoint {
  time: string;
  lat: number;
  lon: number;
  imd_wind_kt: number | null;
  imd_pressure_hpa: number | null;
}
export interface EventTrack {
  citation: string;
  agency: string;
  provider: string;
  dataset: string;
  role?: string;
  peak_imd_wind_kt: number | null;
  min_imd_pressure_hpa: number | null;
  first_time?: string;
  last_time?: string;
  points: TrackPoint[];
}
export interface EventInfo {
  name: string;
  basin: string;
  window_start: string;
  window_end: string;
  peak: string;
  landfall: string;
  segments: EventSegment[];
  independence_note: string;
  claim_note: string;
  track_available: boolean;
  track: EventTrack | null;
  event_id?: string;
  short_name?: string;
  season?: number;
  split?: string;
  in_sample?: boolean;
  split_note?: string;
}
export interface SeriesRow {
  date: string;
  n_cells: number;
  sst_nominal_0m_c: number | null;
  temp_100m_c: number | null;
  anomaly_100m_c: number | null;
  d26_m: number | null;
  tchp_kj_cm2: number | null;
  category_counts?: Record<string, number>;
}
export interface BasinBox {
  lat: [number, number];
  lon: [number, number];
}
export type Basins = Record<string, BasinBox>;
export type Thresholds = NonNullable<Hazard["thresholds"]>;

const finite = (v: number | null | undefined): v is number =>
  typeof v === "number" && Number.isFinite(v);

// ------------------------------------------------------------------ dates
const ISO = /^\d{4}-\d{2}-\d{2}$/;
export function addDays(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
/** Every real calendar day of a window, inclusive. Never a fractional frame. */
export function eventDates(start: string, end: string): string[] {
  if (!ISO.test(start) || !ISO.test(end) || start > end) return [];
  const out: string[] = [];
  for (let d = start; d <= end && out.length < 366; d = addDays(d, 1)) out.push(d);
  return out;
}
export const formatDay = (date: string) =>
  new Date(`${date}T00:00:00Z`)
    .toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    })
    .toUpperCase();
export const shortDay = (date: string) =>
  new Date(`${date}T00:00:00Z`)
    .toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" })
    .toUpperCase();

// ------------------------------------------------------------------ event phases
/** The pre-registered segment a date falls in, or null outside every segment. */
export function phaseFor(date: string, segments: EventSegment[]): EventSegment | null {
  return segments.find((s) => date >= s.start && date <= s.end) ?? null;
}
/** "Approach / intensification" -> "APPROACH". Display only; the label is frozen. */
export const phaseShort = (label: string) => label.split("/")[0].trim().toUpperCase();
const PHASE_TITLE: Record<string, string> = {
  "PRE-EVENT": "Pre-event ocean state",
  APPROACH: "Cyclone approach",
  EVENT: "Peak event environment",
  WAKE: "Cold-wake response window",
  RECOVERY: "Recovery window",
};
export const phaseTitle = (label: string) => PHASE_TITLE[phaseShort(label)] ?? label;

// ------------------------------------------------------------------ event series
export type SeriesKey =
  | "sst_nominal_0m_c"
  | "temp_100m_c"
  | "anomaly_100m_c"
  | "d26_m"
  | "tchp_kj_cm2";
const SERIES_KEYS: SeriesKey[] = [
  "sst_nominal_0m_c",
  "temp_100m_c",
  "anomaly_100m_c",
  "d26_m",
  "tchp_kj_cm2",
];
export function mean(values: (number | null | undefined)[]): number | null {
  const v = values.filter(finite);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}
export interface Extreme {
  value: number;
  date: string;
}
function minimum(rows: SeriesRow[], key: SeriesKey): Extreme | null {
  let best: Extreme | null = null;
  for (const r of rows) {
    const v = r[key];
    if (finite(v) && (!best || v < best.value)) best = { value: v, date: r.date };
  }
  return best;
}
const diff = (a: number | null | undefined, b: number | null | undefined) =>
  finite(a) && finite(b) ? a - b : null;
const inSegment = (rows: SeriesRow[], s: EventSegment) =>
  rows.filter((r) => r.date >= s.start && r.date <= s.end);

/** Share of categorised corridor cells that the BACKEND labelled ELEVATED or HIGH. */
export function supportShare(row: SeriesRow | undefined): number | null {
  const c = row?.category_counts;
  if (!c) return null;
  const categorised = (c.LOW ?? 0) + (c.MODERATE ?? 0) + (c.ELEVATED ?? 0) + (c.HIGH ?? 0);
  return categorised ? ((c.ELEVATED ?? 0) + (c.HIGH ?? 0)) / categorised : null;
}

export interface SegmentSummary {
  segment: EventSegment;
  days: number;
  means: Record<SeriesKey, number | null>;
  supportShare: number | null;
}
export interface EventChanges {
  segments: SegmentSummary[];
  pre: SegmentSummary | null;
  wake: SegmentSummary | null;
  wakeMin: { tchp: Extreme | null; sst: Extreme | null; d26: Extreme | null };
  final: SeriesRow | null;
  /** wake-segment minimum minus the pre-event mean */
  tchpChange: number | null;
  tchpChangePct: number | null;
  sstChange: number | null;
  d26Change: number | null;
  /** wake-segment mean minus the pre-event mean */
  anomaly100Change: number | null;
  tchpFinalVsPre: number | null;
  tchpFinalVsWakeMin: number | null;
}
/**
 * The before / event / wake / recovery comparison, derived only from the
 * event-series rows. Definitions are fixed here and shown in the UI:
 * segment values are means of the daily corridor means inside each frozen
 * segment; the wake minimum is the lowest daily corridor value in the Wake
 * segment; the final value is the last replayed day.
 */
export function eventChanges(series: SeriesRow[], segments: EventSegment[]): EventChanges {
  const rows = [...series].sort((a, b) => a.date.localeCompare(b.date));
  const summaries: SegmentSummary[] = segments.map((segment) => {
    const inside = inSegment(rows, segment);
    return {
      segment,
      days: inside.length,
      means: Object.fromEntries(
        SERIES_KEYS.map((k) => [k, mean(inside.map((r) => r[k]))]),
      ) as Record<SeriesKey, number | null>,
      supportShare: mean(inside.map(supportShare)),
    };
  });
  const pre = summaries[0] ?? null;
  const wake = summaries.find((s) => phaseShort(s.segment.label) === "WAKE") ?? null;
  const wakeRows = wake ? inSegment(rows, wake.segment) : [];
  const wakeMin = {
    tchp: minimum(wakeRows, "tchp_kj_cm2"),
    sst: minimum(wakeRows, "sst_nominal_0m_c"),
    d26: minimum(wakeRows, "d26_m"),
  };
  const final = [...rows].reverse().find((r) => finite(r.tchp_kj_cm2)) ?? null;
  const preTchp = pre?.means.tchp_kj_cm2;
  const tchpChange = diff(wakeMin.tchp?.value, preTchp);
  return {
    segments: summaries,
    pre,
    wake,
    wakeMin,
    final,
    tchpChange,
    tchpChangePct:
      tchpChange !== null && finite(preTchp) && preTchp > 0
        ? (tchpChange / preTchp) * 100
        : null,
    sstChange: diff(wakeMin.sst?.value, pre?.means.sst_nominal_0m_c),
    d26Change: diff(wakeMin.d26?.value, pre?.means.d26_m),
    anomaly100Change: diff(wake?.means.anomaly_100m_c, pre?.means.anomaly_100m_c),
    tchpFinalVsPre: diff(final?.tchp_kj_cm2, preTchp),
    tchpFinalVsWakeMin: diff(final?.tchp_kj_cm2, wakeMin.tchp?.value),
  };
}

/** Signed number with a true minus sign; "Unavailable" when undefined. */
export function signed(v: number | null | undefined, digits = 1, unit = ""): string {
  if (!finite(v)) return "Unavailable";
  const magnitude = Math.abs(v).toFixed(digits);
  const sign = Number(magnitude) === 0 ? "±" : v > 0 ? "+" : "−";
  return `${sign}${magnitude}${unit ? ` ${unit}` : ""}`;
}
export const fixed = (v: number | null | undefined, digits = 1) =>
  finite(v) ? v.toFixed(digits) : "—";

export type StoryKey = "before" | "during" | "wake" | "later";
export interface StoryStep {
  key: StoryKey;
  title: string;
  text: string;
}
export function storyKeyFor(label: string | undefined | null): StoryKey | null {
  switch (label ? phaseShort(label) : "") {
    case "PRE-EVENT":
      return "before";
    case "APPROACH":
    case "EVENT":
      return "during";
    case "WAKE":
      return "wake";
    case "RECOVERY":
      return "later";
    default:
      return null;
  }
}
/**
 * "What happened to the ocean?" Every sentence is conditional on the sign of a
 * real difference; causality is never claimed.
 */
export function oceanStory(ch: EventChanges): StoryStep[] {
  const steps: StoryStep[] = [];
  const pre = ch.pre;
  if (pre && finite(pre.means.tchp_kj_cm2)) {
    const share =
      pre.supportShare !== null
        ? ` On average ${Math.round(pre.supportShare * 100)} % of categorised corridor cells carried ELEVATED or HIGH thermal support.`
        : "";
    steps.push({
      key: "before",
      title: "Before the event",
      text:
        `Along the observed-track corridor, TCHP averaged ${pre.means.tchp_kj_cm2.toFixed(1)} kJ/cm² ` +
        `between ${pre.segment.start} and ${pre.segment.end}.${share} ` +
        `This is the upper-ocean warm-water reservoir present before the storm's approach.`,
    });
  }
  const min = ch.wakeMin.tchp;
  if (min && ch.tchpChange !== null) {
    const sst =
      ch.wakeMin.sst && ch.sstChange !== null
        ? ` Nominal 0 m temperature reached ${ch.wakeMin.sst.value.toFixed(2)} °C (${signed(ch.sstChange, 2, "°C")} against the pre-event mean).`
        : "";
    steps.push({
      key: "during",
      title: "During / after passage",
      text:
        ch.tchpChange < 0
          ? `Corridor TCHP fell to ${min.value.toFixed(1)} kJ/cm² on ${min.date}, ` +
            `${Math.abs(ch.tchpChange).toFixed(1)} kJ/cm²` +
            (ch.tchpChangePct !== null ? ` (${Math.abs(ch.tchpChangePct).toFixed(0)} %)` : "") +
            ` below the pre-event mean.${sst}`
          : `Corridor TCHP in the wake segment did not fall below its pre-event mean (${signed(ch.tchpChange, 1, "kJ/cm²")}).${sst}`,
    });
    const cooled = ch.tchpChange < 0 && ch.sstChange !== null && ch.sstChange < 0;
    const d26 =
      ch.d26Change !== null
        ? ` The 26 °C layer depth at its wake minimum differed from the pre-event mean by ${signed(ch.d26Change, 1, "m")}.`
        : "";
    steps.push({
      key: "wake",
      title: "Cold wake",
      text: cooled
        ? `The reconstructed pattern is consistent with cyclone-associated upper-ocean cooling and mixing.${d26} OceanEmbed reconstructs the ocean state; it does not establish the cause.`
        : `The reconstruction does not show cooling in both surface temperature and TCHP for this segment, so no cold-wake pattern is described.${d26}`,
    });
  }
  const final = ch.final;
  if (final && finite(final.tchp_kj_cm2) && ch.tchpFinalVsPre !== null) {
    const vsMin =
      ch.tchpFinalVsWakeMin !== null && ch.tchpFinalVsWakeMin > 0
        ? ` and ${ch.tchpFinalVsWakeMin.toFixed(1)} kJ/cm² above the wake minimum`
        : "";
    const partial =
      ch.tchpFinalVsPre < 0 && ch.tchpFinalVsWakeMin !== null && ch.tchpFinalVsWakeMin > 0
        ? " TCHP increased again from its minimum but remained below its pre-event value within the replay window."
        : "";
    steps.push({
      key: "later",
      title: "Later in the replay",
      text:
        `By ${final.date}, corridor TCHP was ${final.tchp_kj_cm2.toFixed(1)} kJ/cm²: ` +
        `${Math.abs(ch.tchpFinalVsPre).toFixed(1)} kJ/cm² ${ch.tchpFinalVsPre < 0 ? "below" : "above"} the pre-event mean${vsMin}.${partial}`,
    });
  }
  return steps;
}

// ------------------------------------------------------------------ category meaning
export const NOT_A_PROBABILITY =
  "This is ocean thermal support, not cyclone probability. Atmospheric conditions remain essential.";
export interface Meaning {
  headline: string;
  meaning: string;
  why: string;
  relevance: string;
  attention: string;
}
const DEEP_WARM_WHY =
  "Surface temperature alone does not reveal how deeply warm water extends. A cyclone mixes cooler water up from below; where warm water is deep, heat can remain available even as the immediate surface cools.";
export function categoryMeaning(label: string): Meaning {
  switch (label) {
    case "LOW":
      return {
        headline: "LOW OCEAN THERMAL SUPPORT",
        meaning:
          "The upper-ocean warm-water reservoir here is limited compared with OceanEmbed's reference period.",
        why: "Where the warm layer is thin, storm-driven mixing can bring cooler water to the surface quickly, which limits the ocean heat available to a storm.",
        relevance:
          "If a tropical cyclone passes through this location, the upper ocean would offer comparatively limited thermal support.",
        attention:
          "No thermal-support flag. Follow official cyclone and atmospheric guidance as usual.",
      };
    case "MODERATE":
      return {
        headline: "MODERATE OCEAN THERMAL SUPPORT",
        meaning: "A meaningful warm-water reservoir is present, but it is not unusually large.",
        why: DEEP_WARM_WHY,
        relevance:
          "If a tropical cyclone passes through this location, ocean heat could contribute to storm maintenance, but thermal support is not unusually strong.",
        attention:
          "Routine monitoring. Compare with official cyclone and atmospheric guidance if a track approaches.",
      };
    case "ELEVATED":
      return {
        headline: "ELEVATED OCEAN THERMAL SUPPORT",
        meaning: "A substantial reservoir of warm water exists below the surface.",
        why: DEEP_WARM_WHY,
        relevance:
          "If an official tropical cyclone track intersects this region, ocean thermal conditions could support storm maintenance or intensification.",
        attention: "Compare this region with official cyclone and atmospheric guidance.",
      };
    case "HIGH":
      return {
        headline: "HIGH OCEAN THERMAL SUPPORT",
        meaning: "A large reservoir of warm water extends below the surface.",
        why: `${DEEP_WARM_WHY} A larger reservoir can reduce the stabilising effect of that mixing.`,
        relevance:
          "If an official tropical cyclone track enters this region, the ocean could provide strong thermal support.",
        attention:
          "Increased thermal-state attention: compare with official cyclone forecasts and atmospheric intensification guidance.",
      };
    default:
      return {
        headline: "NOT CATEGORIZED",
        meaning: "No thermal-support category can be defended at this cell.",
        why: "The frozen protocol labels a cell only where TCHP is defined and stands on a real water column.",
        relevance: "Nothing is inferred for this cell.",
        attention: "Select an ocean cell with a supported reconstruction.",
      };
  }
}
/** Where a category sits in OceanEmbed's own reference distribution. */
export function bandText(label: string, t: Thresholds | null): string {
  if (!t) return "";
  const ref = `OceanEmbed's own TCHP over ${t.reference_period}`;
  switch (label) {
    case "LOW":
      return `TCHP below ${t.p50.toFixed(1)} kJ/cm² — the lower half of ${ref}.`;
    case "MODERATE":
      return `TCHP ${t.p50.toFixed(1)}–${t.p75.toFixed(1)} kJ/cm² — between the median and upper quartile of ${ref}.`;
    case "ELEVATED":
      return `TCHP ${t.p75.toFixed(1)}–${t.p90.toFixed(1)} kJ/cm² — the upper quartile, below the top tenth, of ${ref}.`;
    case "HIGH":
      return `TCHP at or above ${t.p90.toFixed(1)} kJ/cm² — the top tenth of ${ref}.`;
    default:
      return "";
  }
}
/** Distance to the nearest frozen boundary; read together with the TCHP error. */
export function boundaryDistance(tchp: number, t: Thresholds | null): number | null {
  if (!t || !finite(tchp)) return null;
  return Math.min(...[t.p50, t.p75, t.p90].map((b) => Math.abs(tchp - b)));
}

// ------------------------------------------------------------------ basins
export const basinName = (key: string) =>
  key
    .split("_")
    .map((w, i) => (i > 0 && w === "of" ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
/** The existing analysis basin containing a point, or null (then coordinates are used). */
export function basinOf(lat: number, lon: number, basins: Basins | null): string | null {
  for (const [key, b] of Object.entries(basins ?? {}))
    if (lat >= b.lat[0] && lat <= b.lat[1] && lon >= b.lon[0] && lon <= b.lon[1])
      return basinName(key);
  return null;
}
export const coordText = (lat: number, lon: number) =>
  `${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E`;

// ------------------------------------------------------------------ monitoring areas
export interface MonitoringArea {
  rank: number;
  tier: "HIGH" | "ELEVATED";
  row: number;
  col: number;
  lat: number;
  lon: number;
  tchp: number;
  anomaly100: number;
  cells: number;
  highCells: number;
  basin: string | null;
  members: Int32Array;
  medianTchp: number;
  centroidLat: number;
  centroidLon: number;
  areaKm2: number;
  anomaly50: number;
  anomaly75: number;
}
export interface MonitoringResult {
  areas: MonitoringArea[];
  components: number;
  highCells: number;
  elevatedCells: number;
}
/**
 * THERMAL MONITORING AREAS. Transparent rule, no weights:
 *  1. take cells the backend labelled HIGH or ELEVATED;
 *  2. group edge-adjacent cells into contiguous areas;
 *  3. an area containing any HIGH cell ranks first, ordered by its peak TCHP;
 *     areas of ELEVATED cells only follow, ordered by peak TCHP.
 * The 100 m anomaly is reported beside each area and never enters the ranking.
 */
export function monitoringAreas(
  f: FieldView,
  basins: Basins | null,
  limit = 5,
): MonitoringResult {
  const h = f.hazard,
    d = f.diagnostics;
  const rows = f.lat.length,
    cols = f.lon.length,
    n = rows * cols;
  const empty = { areas: [], components: 0, highCells: 0, elevatedCells: 0 };
  if (!h || !h.available || !d) return empty;
  const tier = new Uint8Array(n);
  let highCells = 0,
    elevatedCells = 0;
  for (let i = 0; i < n; i++) {
    const name = h.categoryLabels[h.category[i]];
    if (
      (name === "HIGH" || name === "ELEVATED") &&
      f.ocean[i] &&
      f.inputValid[i] &&
      Number.isFinite(d.tchp[i])
    ) {
      tier[i] = name === "HIGH" ? 2 : 1;
      if (name === "HIGH") highCells++;
      else elevatedCells++;
    }
  }
  const seen = new Uint8Array(n),
    queue = new Int32Array(n),
    k100 = f.depths.indexOf(100);
  const found: Omit<MonitoringArea, "rank">[] = [];
  for (let s = 0; s < n; s++) {
    if (!tier[s] || seen[s]) continue;
    let head = 0,
      tail = 0,
      peak = s,
      high = 0;
    queue[tail++] = s;
    seen[s] = 1;
    while (head < tail) {
      const i = queue[head++];
      if (tier[i] === 2) high++;
      if (d.tchp[i] > d.tchp[peak] || (d.tchp[i] === d.tchp[peak] && i < peak)) peak = i;
      const r = (i / cols) | 0,
        c = i % cols;
      if (r > 0 && tier[i - cols] && !seen[i - cols]) (seen[i - cols] = 1), (queue[tail++] = i - cols);
      if (r < rows - 1 && tier[i + cols] && !seen[i + cols]) (seen[i + cols] = 1), (queue[tail++] = i + cols);
      if (c > 0 && tier[i - 1] && !seen[i - 1]) (seen[i - 1] = 1), (queue[tail++] = i - 1);
      if (c < cols - 1 && tier[i + 1] && !seen[i + 1]) (seen[i + 1] = 1), (queue[tail++] = i + 1);
    }
    const row = (peak / cols) | 0,
      col = peak % cols;
    const members = queue.slice(0, tail);
    let latSum = 0,
      lonSum = 0,
      areaKm2 = 0;
    const values: number[] = [];
    for (let m = 0; m < tail; m++) {
      const i = members[m],
        r = (i / cols) | 0;
      latSum += f.lat[r];
      lonSum += f.lon[i % cols];
      areaKm2 += cellAreaKm2(f.lat[r]);
      values.push(d.tchp[i]);
    }
    const k50 = f.depths.indexOf(50),
      k75 = f.depths.indexOf(75);
    found.push({
      medianTchp: median(values) ?? NaN,
      centroidLat: latSum / tail,
      centroidLon: lonSum / tail,
      areaKm2,
      anomaly50: k50 >= 0 ? f.anomaly[offset(f, row, col, k50)] : NaN,
      anomaly75: k75 >= 0 ? f.anomaly[offset(f, row, col, k75)] : NaN,
      tier: high > 0 ? "HIGH" : "ELEVATED",
      row,
      col,
      lat: f.lat[row],
      lon: f.lon[col],
      tchp: d.tchp[peak],
      anomaly100: k100 >= 0 ? f.anomaly[offset(f, row, col, k100)] : NaN,
      cells: tail,
      highCells: high,
      basin: basinOf(f.lat[row], f.lon[col], basins),
      members,
    });
  }
  found.sort(
    (a, b) =>
      (a.tier === b.tier ? 0 : a.tier === "HIGH" ? -1 : 1) ||
      b.tchp - a.tchp ||
      b.cells - a.cells ||
      a.row * cols + a.col - (b.row * cols + b.col),
  );
  return {
    areas: found.slice(0, limit).map((a, i) => ({ ...a, rank: i + 1 })),
    components: found.length,
    highCells,
    elevatedCells,
  };
}
/** SVG path tracing the outer edges of an area's cells in map-canvas pixels. */
export function outlinePath(
  members: ArrayLike<number>,
  rows: number,
  cols: number,
  p: { left: number; top: number; width: number; height: number },
): string {
  const mark = new Uint8Array(rows * cols);
  for (let k = 0; k < members.length; k++) mark[members[k]] = 1;
  const cw = p.width / cols,
    ch = p.height / rows,
    parts: string[] = [];
  const r2 = (v: number) => Math.round(v * 10) / 10;
  for (let k = 0; k < members.length; k++) {
    const i = members[k],
      r = (i / cols) | 0,
      c = i % cols;
    const x0 = r2(p.left + c * cw),
      x1 = r2(p.left + (c + 1) * cw),
      y0 = r2(p.top + (rows - 1 - r) * ch),
      y1 = r2(p.top + (rows - r) * ch);
    if (r === rows - 1 || !mark[i + cols]) parts.push(`M${x0} ${y0}H${x1}`);
    if (r === 0 || !mark[i - cols]) parts.push(`M${x0} ${y1}H${x1}`);
    if (c === 0 || !mark[i - 1]) parts.push(`M${x0} ${y0}V${y1}`);
    if (c === cols - 1 || !mark[i + 1]) parts.push(`M${x1} ${y0}V${y1}`);
  }
  return parts.join("");
}

// ------------------------------------------------------------------ recent qualified states
export interface DayState {
  date: string;
  status: "AVAILABLE" | "UNAVAILABLE";
  is_newest?: boolean;
  reason?: string;
  missing_channels?: string[];
  warm?: string;
  cached?: boolean;
}
/** Consecutive AVAILABLE calendar days ending at `selected` (ascending). */
export function contiguousRun(days: DayState[], selected: string | null): string[] {
  const ok = new Set(days.filter((d) => d.status === "AVAILABLE").map((d) => d.date));
  if (!selected || !ok.has(selected)) return [];
  const run = [selected];
  for (let d = addDays(selected, -1); ok.has(d); d = addDays(d, -1)) run.unshift(d);
  return run;
}
/** Unavailable days lying between the first and last available day of the window. */
export function windowGaps(days: DayState[]): { available: string[]; gaps: string[] } {
  const sorted = [...days].sort((a, b) => a.date.localeCompare(b.date));
  const available = sorted.filter((d) => d.status === "AVAILABLE").map((d) => d.date);
  if (available.length < 2) return { available, gaps: [] };
  const first = available[0],
    last = available[available.length - 1];
  return {
    available,
    gaps: sorted
      .filter((d) => d.status !== "AVAILABLE" && d.date > first && d.date < last)
      .map((d) => d.date),
  };
}
/** The small per-day record a change needs, so full fields need not be retained. */
export interface DaySummary {
  date: string;
  tchp: Float64Array;
  anomaly100: Float64Array;
  counts: Record<string, number>;
}
export function summarize(f: FieldView): DaySummary {
  const n = f.lat.length * f.lon.length,
    k100 = f.depths.indexOf(100);
  const anomaly100 = new Float64Array(n);
  for (let i = 0; i < n; i++)
    anomaly100[i] = k100 >= 0 ? f.anomaly[i * f.depths.length + k100] : NaN;
  return {
    date: f.effectiveDate,
    tchp: f.diagnostics ? Float64Array.from(f.diagnostics.tchp) : new Float64Array(n).fill(NaN),
    anomaly100,
    counts: { ...(f.hazard?.categoryCounts ?? {}) },
  };
}
export const supportCells = (s: DaySummary) => (s.counts.HIGH ?? 0) + (s.counts.ELEVATED ?? 0);

// ------------------------------------------------------------------ column structure
export interface LevelValue {
  depth: number;
  temperature: number;
  climatology: number;
  anomaly: number;
  supported: boolean;
}
export function levelAt(
  f: FieldView,
  s: Selection,
  depthIndex: number,
  b: Bathymetry | null,
): LevelValue | null {
  if (s.row < 0 || depthIndex < 0 || depthIndex >= f.depths.length) return null;
  const o = offset(f, s.row, s.col, depthIndex),
    depth = f.depths[depthIndex];
  return {
    depth,
    temperature: f.temperature[o],
    climatology: f.climatology[o],
    anomaly: f.anomaly[o],
    supported: displayDepthValid(f, b, s.row, s.col, depth),
  };
}
export const PROFILE_KEY_DEPTHS = [0, 50, 100, 150, 200];
export function keyLevels(f: FieldView, s: Selection, b: Bathymetry | null): LevelValue[] {
  return PROFILE_KEY_DEPTHS.map((d) => levelAt(f, s, f.depths.indexOf(d), b)).filter(
    (v): v is LevelValue => v !== null,
  );
}
/** Warmest anomaly at one depth, over cells whose water column reaches that depth. */
export function strongestAnomaly(
  f: FieldView,
  depthIndex: number,
  b: Bathymetry | null,
): { row: number; col: number; lat: number; lon: number; anomaly: number } | null {
  if (!b || depthIndex < 0) return null;
  const cols = f.lon.length,
    depth = f.depths[depthIndex];
  let best: { row: number; col: number; lat: number; lon: number; anomaly: number } | null = null;
  for (let row = 0; row < f.lat.length; row++)
    for (let col = 0; col < cols; col++) {
      if (!isSupported(f, row, col) || !displayDepthValid(f, b, row, col, depth)) continue;
      const a = f.anomaly[offset(f, row, col, depthIndex)];
      if (Number.isFinite(a) && (!best || a > best.anomaly))
        best = { row, col, lat: f.lat[row], lon: f.lon[col], anomaly: a };
    }
  return best;
}

// ------------------------------------------------------------------ plain-language glossary
export type GlossaryKey =
  | "tchp"
  | "d26"
  | "anomaly"
  | "climatology"
  | "coldWake"
  | "thermalSupport"
  | "lag"
  | "qualified"
  | "monitoring"
  | "corridor";
export const GLOSSARY: Record<GlossaryKey, { term: string; text: string }> = {
  tchp: {
    term: "TCHP",
    text: "Tropical Cyclone Heat Potential: an estimate of heat stored in upper-ocean water warmer than 26 °C. Larger values indicate a larger warm-water reservoir.",
  },
  d26: {
    term: "D26",
    text: "Depth of the 26 °C isotherm: how far below the surface water stays warmer than 26 °C. A deeper D26 means a thicker warm layer.",
  },
  anomaly: {
    term: "Anomaly",
    text: "Reconstructed temperature minus the climatological expectation for the same place, depth and time of year. Positive means warmer than usual.",
  },
  climatology: {
    term: "Climatology",
    text: "The typical temperature for this location, depth and time of year (OceanEmbed's L0 baseline). Anomalies are measured against it.",
  },
  coldWake: {
    term: "Cold wake",
    text: "Cooler upper-ocean water left along a cyclone's path, as strong winds mix deeper, colder water towards the surface.",
  },
  thermalSupport: {
    term: "Thermal support",
    text: "How much upper-ocean heat is available to a passing cyclone, grouped as LOW, MODERATE, ELEVATED or HIGH by frozen TCHP boundaries. It is not a cyclone probability.",
  },
  lag: {
    term: "Reconstruction lag",
    text: "Time between the date a reconstruction is valid for and when its inputs were retrieved. With a lag, the map describes that valid date, not the present moment.",
  },
  qualified: {
    term: "Qualified state",
    text: "A daily reconstruction whose seven surface inputs all exist for the same valid date and pass the pre-registered Phase 8B checks. Missing days are never filled from other days.",
  },
  monitoring: {
    term: "Thermal monitoring area",
    text: "A contiguous group of cells the frozen protocol labels HIGH or ELEVATED thermal support. It shows where upper-ocean heat is concentrated; it does not say where a cyclone will form, move or strengthen.",
  },
  corridor: {
    term: "Track corridor",
    text: "Ocean cells within 1.5° of any observed best-track position. Corridor values are averages over the water the storm actually crossed.",
  },
};

// ------------------------------------------------------------------ area, penetration, basins, relations
export const EARTH_RADIUS_KM = 6371.0088;
export const AREA_RULE =
  "Area sums each grid cell's spherical area, R² · Δλ · |sin(φ + Δφ/2) − sin(φ − Δφ/2)| with R = 6371.0 km and 0.25° cells. A cell count is never reported as km².";

export function cellAreaKm2(lat: number, dLat = 0.25, dLon = 0.25): number {
  const rad = Math.PI / 180;
  return (
    EARTH_RADIUS_KM ** 2 *
    dLon *
    rad *
    Math.abs(Math.sin((lat + dLat / 2) * rad) - Math.sin((lat - dLat / 2) * rad))
  );
}

export function median(values: number[]): number | null {
  const v = values.filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
  if (!v.length) return null;
  const mid = v.length >> 1;
  return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2;
}

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const rad = Math.PI / 180;
  const dp = (lat2 - lat1) * rad,
    dl = (lon2 - lon1) * rad;
  const a =
    Math.sin(dp / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dl / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

export const HEAT_PENETRATION_RULE =
  "Read from the anomaly at the 15 model depths of the selected column, only where the local water column reaches that depth: the continuous positive extent from the nominal surface, the depth of the largest positive anomaly, and the surface anomaly compared with the largest anomaly at or below 50 m. No score is computed.";

export function allLevels(f: FieldView, s: Selection, b: Bathymetry | null): LevelValue[] {
  return f.depths
    .map((_, k) => levelAt(f, s, k, b))
    .filter((v): v is LevelValue => v !== null);
}

export function heatPenetration(levels: LevelValue[]): {
  statements: string[];
  continuousTo: number | null;
  maxPositive: { depth: number; anomaly: number } | null;
} {
  const usable = levels.filter((l) => l.supported && Number.isFinite(l.anomaly));
  if (!usable.length)
    return {
      statements: ["No anomaly is available in the supported column."],
      continuousTo: null,
      maxPositive: null,
    };
  const statements: string[] = [];
  const surface = usable.find((l) => l.depth === 0);
  let continuousTo: number | null = null;
  if (surface && surface.anomaly > 0) {
    for (const l of levels) {
      if (!(l.supported && Number.isFinite(l.anomaly) && l.anomaly > 0)) break;
      continuousTo = l.depth;
    }
    statements.push(
      continuousTo === 0
        ? "A positive anomaly is present only at the nominal surface level."
        : `Positive temperature anomaly extends continuously from the nominal surface through ${continuousTo} m.`,
    );
  } else {
    const first = usable.find((l) => l.anomaly > 0);
    if (first)
      statements.push(
        `The nominal surface anomaly is not positive, but positive anomalies occur below, first at ${first.depth} m.`,
      );
  }
  const positives = usable.filter((l) => l.anomaly > 0);
  const top = positives.length ? positives.reduce((a, b) => (b.anomaly > a.anomaly ? b : a)) : null;
  statements.push(
    top
      ? `Maximum positive anomaly: ${signed(top.anomaly, 2, "°C")} at ${top.depth} m.`
      : "No positive temperature anomaly in the supported column.",
  );
  const deep = usable.filter((l) => l.depth >= 50);
  const deepTop = deep.length ? deep.reduce((a, b) => (b.anomaly > a.anomaly ? b : a)) : null;
  if (surface && deepTop && deepTop.anomaly > 0 && surface.anomaly < deepTop.anomaly)
    statements.push(
      `The surface anomaly (${signed(surface.anomaly, 2, "°C")}) is weaker than the largest anomaly at or below 50 m (${signed(deepTop.anomaly, 2, "°C")} at ${deepTop.depth} m).`,
    );
  return {
    statements,
    continuousTo,
    maxPositive: top ? { depth: top.depth, anomaly: top.anomaly } : null,
  };
}

/** Warmest/coolest value of a layer at one depth over physically supported cells. */
export function extremeAt(
  f: FieldView,
  depthIndex: number,
  b: Bathymetry | null,
  layer: "anomaly" | "temperature",
  largest: boolean,
): { lat: number; lon: number; value: number } | null {
  if (!b || depthIndex < 0) return null;
  const depth = f.depths[depthIndex];
  let best: { lat: number; lon: number; value: number } | null = null;
  for (let row = 0; row < f.lat.length; row++)
    for (let col = 0; col < f.lon.length; col++) {
      if (!isSupported(f, row, col) || !displayDepthValid(f, b, row, col, depth)) continue;
      const v = f[layer][offset(f, row, col, depthIndex)];
      if (Number.isFinite(v) && (!best || (largest ? v > best.value : v < best.value)))
        best = { lat: f.lat[row], lon: f.lon[col], value: v };
    }
  return best;
}

export interface BasinStats {
  key: string;
  name: string;
  cells: number;
  categorised: number;
  medianTchp: number | null;
  maxTchp: number | null;
  highFraction: number | null;
  elevatedFraction: number | null;
  maxAnomaly50: number | null;
  maxAnomaly100: number | null;
}

export function basinSummary(f: FieldView, basins: Basins, b: Bathymetry | null): BasinStats[] {
  const d = f.diagnostics,
    h = f.hazard,
    cols = f.lon.length;
  const tchpWithheld = !!d?.withheld?.includes("tchp");
  const k50 = f.depths.indexOf(50),
    k100 = f.depths.indexOf(100);
  return Object.entries(basins).map(([key, box]) => {
    const tchp: number[] = [];
    let cells = 0,
      categorised = 0,
      high = 0,
      elevated = 0;
    let a50: number | null = null,
      a100: number | null = null;
    for (let r = 0; r < f.lat.length; r++) {
      if (f.lat[r] < box.lat[0] || f.lat[r] > box.lat[1]) continue;
      for (let c = 0; c < cols; c++) {
        if (f.lon[c] < box.lon[0] || f.lon[c] > box.lon[1]) continue;
        const i = r * cols + c;
        if (!f.ocean[i] || !f.inputValid[i]) continue;
        cells++;
        if (d && !tchpWithheld && diagnosticUsable(f, "tchp", i)) tchp.push(d.tchp[i]);
        if (h?.available) {
          const name = h.categoryLabels[h.category[i]];
          if (name && name !== "NOT_CATEGORIZED") {
            categorised++;
            if (name === "HIGH") high++;
            if (name === "ELEVATED") elevated++;
          }
        }
        if (b && k50 >= 0 && displayDepthValid(f, b, r, c, 50)) {
          const v = f.anomaly[offset(f, r, c, k50)];
          if (Number.isFinite(v) && (a50 === null || v > a50)) a50 = v;
        }
        if (b && k100 >= 0 && displayDepthValid(f, b, r, c, 100)) {
          const v = f.anomaly[offset(f, r, c, k100)];
          if (Number.isFinite(v) && (a100 === null || v > a100)) a100 = v;
        }
      }
    }
    return {
      key,
      name: basinName(key),
      cells,
      categorised,
      medianTchp: median(tchp),
      maxTchp: tchp.length ? Math.max(...tchp) : null,
      highFraction: categorised ? high / categorised : null,
      elevatedFraction: categorised ? elevated / categorised : null,
      maxAnomaly50: a50,
      maxAnomaly100: a100,
    };
  });
}

export const TRACK_RELATION_RULE =
  "TRACK INTERSECTION when a sampled path cell belongs to the area; otherwise the great-circle distance from the nearest path sample to the nearest area cell centre. No corridor width is assumed.";

export function trackAreaRelation(
  area: MonitoringArea,
  samples: { row: number | null; col: number | null; lat: number; lon: number }[],
  f: FieldView,
): { kind: "TRACK INTERSECTION" | "OUTSIDE TRACK LINE"; distanceKm: number | null } {
  const cols = f.lon.length;
  const members = new Set(Array.from(area.members));
  for (const s of samples)
    if (s.row !== null && s.col !== null && members.has(s.row * cols + s.col))
      return { kind: "TRACK INTERSECTION", distanceKm: 0 };
  let best = Infinity;
  for (const m of members) {
    const lat = f.lat[(m / cols) | 0],
      lon = f.lon[m % cols];
    for (const s of samples) best = Math.min(best, haversineKm(s.lat, s.lon, lat, lon));
  }
  return { kind: "OUTSIDE TRACK LINE", distanceKm: Number.isFinite(best) ? best : null };
}
