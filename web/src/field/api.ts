import { adaptReplay, type ReplayData } from "./replayAdapter";
export async function getJson<T>(
  url: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Error(
      typeof body.detail === "string"
        ? body.detail
        : `Local API unavailable (${response.status}). Check the OceanEmbed server.`,
    );
  }
  return response.json();
}
// Bounded session cache. Renderer and profile components never access this module.
const cache = new Map<string, ReplayData>();
export async function loadReplay(
  date: string,
  force = false,
  signal?: AbortSignal,
): Promise<ReplayData> {
  if (!force && cache.has(date)) return cache.get(date)!;
  const data = adaptReplay(
    await getJson(
      `/api/replay/view?date=${encodeURIComponent(date)}&force_recompute=${force}`,
      signal,
    ),
  );
  if (data.field.effectiveDate !== date)
    throw Error("Replay returned a different date");
  cache.delete(date);
  cache.set(date, data);
  if (cache.size > 3) cache.delete(cache.keys().next().value!);
  return data;
}
