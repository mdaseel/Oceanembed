import { useCallback, useEffect, useRef, useState } from "react";
import { getJson } from "../../field/api";
import {
  summarize,
  type DayState,
  type DaySummary,
} from "../../field/hazardIntelligence";
import {
  adaptReplay,
  type ReplayData,
  type ReplayPayload,
} from "../../field/replayAdapter";

export interface NrtSource {
  product_key: string;
  channels: string[];
  product_id: string;
}
export interface NrtWindow {
  newest_qualified_date: string | null;
  days: DayState[];
  sources?: NrtSource[];
  per_product_newest?: Record<string, string | null>;
  discovery_errors?: Record<string, string>;
  discovery_refreshing?: boolean;
  discovery_age_seconds?: number;
  error?: string;
}
export interface NrtPayload {
  state: string;
  label: string | null;
  effective_date?: string;
  selected_date?: string;
  newest_qualified_date?: string | null;
  is_newest?: boolean;
  reason?: string;
  meta?: {
    retrieval_time_utc?: string;
    reconstruction_lag_hours?: number;
    joint_mask_coverage?: number;
    snapshot_generated_utc?: string;
    snapshot_staleness_hours?: number;
  };
  live_attempt?: { attempted: boolean; reasons?: string[] } | null;
  field: ReplayPayload | null;
}

/**
 * The latest qualified states, read through the SAME backend endpoints and the
 * SAME adapter as the Latest tab. Each date is one independent qualified
 * reconstruction; a date the backend refuses carries no field, and nothing is
 * ever filled from a neighbouring day.
 */
export function useNrtStates(enabled: boolean) {
  const [window7, setWindow7] = useState<NrtWindow | null>(null);
  const [windowError, setWindowError] = useState("");
  const [current, setCurrent] = useState<{
    payload: NrtPayload | null;
    data: ReplayData | null;
  }>({ payload: null, data: null });
  const [notice, setNotice] = useState<NrtPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [initialised, setInitialised] = useState(false);
  const [summaries, setSummaries] = useState<Record<string, DaySummary>>({});
  const [failed, setFailed] = useState<string[]>([]);
  const token = useRef(0);
  const live = useRef(true);
  const started = useRef(false);
  const hasData = useRef(false);
  const summaryRef = useRef(summaries);
  summaryRef.current = summaries;
  const inflight = useRef(new Set<string>());

  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);

  const remember = useCallback((data: ReplayData) => {
    const date = data.field.effectiveDate;
    setSummaries((s) => (s[date] ? s : { ...s, [date]: summarize(data.field) }));
  }, []);

  const adopt = useCallback(
    (p: NrtPayload, expected?: string) => {
      if (!p.field) {
        setNotice(p);
        if (!hasData.current) setCurrent({ payload: p, data: null });
        return;
      }
      const data = adaptReplay(p.field);
      if (expected && data.field.effectiveDate !== expected)
        throw Error(
          `The latest state for ${expected} returned ${data.field.effectiveDate}`,
        );
      hasData.current = true;
      setNotice(null);
      setCurrent({ payload: p, data });
      remember(data);
    },
    [remember],
  );

  const request = useCallback(
    async (url: string, expected?: string) => {
      const mine = ++token.current;
      setBusy(true);
      setError("");
      try {
        const p = await getJson<NrtPayload>(url, AbortSignal.timeout(120_000));
        if (live.current && mine === token.current) adopt(p, expected);
      } catch (e) {
        if (live.current && mine === token.current) setError((e as Error).name === "TimeoutError" ? "The reconstruction request timed out. The previous dated field remains available; try refreshing again." : (e as Error).message);
      } finally {
        if (live.current && mine === token.current) setBusy(false);
      }
    },
    [adopt],
  );

  const loadDate = useCallback(
    (date: string) =>
      request(`/api/latest/qualified?date=${encodeURIComponent(date)}`, date),
    [request],
  );
  const loadNewest = useCallback(() => request("/api/latest/qualified"), [request]);
  const refreshWindow = useCallback((refresh = false) => {
    return getJson<NrtWindow>(
      `/api/latest/available-dates${refresh ? "?refresh=true" : ""}`,
      AbortSignal.timeout(60_000),
    )
      .then((w) => {
        if (!live.current) return;
        if (w.error) throw Error(w.error);
        setWindow7(w);
        setWindowError(Object.entries(w.discovery_errors ?? {}).map(([key, message]) => `${key}: ${message}`).join(" · "));
        if (!w.discovery_refreshing) setCheckedAt(new Date().toISOString());
      })
      .catch((e) => live.current && setWindowError((e as Error).name === "TimeoutError" ? "Source discovery timed out. Previous availability is retained; try again when the providers respond." : (e as Error).message));
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    // Resolve current provider dates before loading the newest field. Parallel
    // requests could previously load yesterday's cached discovery first.
    try {
      await refreshWindow(true);
      if (live.current) await loadNewest();
    } finally {
      if (live.current) setRefreshing(false);
    }
  }, [refreshWindow, loadNewest]);

  useEffect(() => {
    if (!enabled || started.current) return;
    started.current = true;
    // Ask the server to pre-produce the recent states; it returns at once.
    getJson("/api/latest/prewarm").catch(() => {});
    const mine = ++token.current;
    setBusy(true);
    getJson<NrtPayload>("/api/latest/qualified/cached")
      .then((p) => {
        if (live.current && mine === token.current) adopt(p);
      })
      .catch(() => {})
      .finally(() => {
        if (!live.current) return;
        if (mine === token.current)
          void refresh().finally(() => live.current && setInitialised(true));
        else setInitialised(true);
      });
  }, [enabled, adopt, refresh, refreshWindow]);

  /** Per-day summaries for a change between REAL qualified states. */
  const ensureSummaries = useCallback(
    async (dates: string[]) => {
      for (const date of dates) {
        if (!live.current) return;
        if (summaryRef.current[date] || inflight.current.has(date)) continue;
        inflight.current.add(date);
        try {
          const p = await getJson<NrtPayload>(
            `/api/latest/qualified?date=${encodeURIComponent(date)}`,
          );
          const data = p.field ? adaptReplay(p.field) : null;
          if (data && data.field.effectiveDate === date) remember(data);
          else if (live.current)
            setFailed((f) => (f.includes(date) ? f : [...f, date]));
        } catch {
          if (live.current) setFailed((f) => (f.includes(date) ? f : [...f, date]));
        } finally {
          inflight.current.delete(date);
        }
      }
    },
    [remember],
  );

  return {
    window7,
    windowError,
    payload: current.payload,
    data: current.data,
    notice,
    busy: busy || refreshing,
    refreshing,
    checkedAt,
    error,
    initialised,
    summaries,
    failed,
    loadDate,
    refresh,
    ensureSummaries,
  };
}
