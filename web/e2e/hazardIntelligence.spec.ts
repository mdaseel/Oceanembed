import { test, expect, type Page, type Route } from "@playwright/test";

/**
 * Ocean Thermal Hazard Intelligence.
 *
 * The risks: a playback frame that is not a real reconstruction; map, 3D,
 * profile and explanation drifting onto different dates; a missing NRT day
 * being requested, filled or hidden; a hotspot ranked by an invented score; a
 * comparison number that is not the event series; D26 reappearing in the
 * latest mode; a live cyclone track or a probability appearing anywhere.
 *
 * Historical tests use the real local replay. Latest-mode tests never contact a
 * provider: the qualified-state endpoints are answered with fixtures whose
 * fields are real frozen-L2 historical reconstructions, relabelled with fixture
 * dates and with D26 withheld. They exercise synchronisation and refusal logic
 * only; they are not scientific evidence.
 */

const SHOTS = "../outputs/hazard_intelligence";
const PROBABILITY = /\d+(\.\d+)?\s*%\s*(chance|probability|likelihood)/i;

async function openHazard(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("field-map")).toBeVisible({ timeout: 90000 });
  await page.getByRole("link", { name: "Events & Disasters" }).click();
  await expect(page.getByTestId("hazard-dashboard")).toBeVisible();
}

async function eventInfo(page: Page) {
  return (await page.request.get("/api/event")).json();
}

function dateRange(start: string, end: string) {
  const out: string[] = [];
  for (let d = new Date(`${start}T00:00:00Z`); d <= new Date(`${end}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + 1))
    out.push(d.toISOString().slice(0, 10));
  return out;
}

async function chooseDay(page: Page, date: string) {
  await page.getByTestId(`event-day-${date}`).click();
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-date", date, {
    timeout: 90000,
  });
  await expect(page.getByTestId("map-stage")).toHaveAttribute("data-field-date", date);
}

// ---------------------------------------------------------------- historical

test("historical: the dashboard explains the category and follows the frozen segments", async ({
  page,
}) => {
  const event = await eventInfo(page);
  await openHazard(page);
  await expect(page.getByRole("heading", { name: "Ocean Thermal Hazard Intelligence" })).toBeVisible();
  await expect(page.getByTestId("intel-mode-badge")).toHaveText("HISTORICAL EVENT REPLAY");

  // The default launch date is outside the event: the phase says so.
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-phase", "OUTSIDE");
  await page.getByRole("button", { name: /Show peak intensity/ }).click();
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-date", event.peak, {
    timeout: 90000,
  });

  // Every real window day has a chip, and each chip carries its frozen segment.
  const dates = dateRange(event.window_start, event.window_end);
  await expect(page.locator('[data-testid^="event-day-"]')).toHaveCount(dates.length);
  for (const d of dates) {
    const seg = event.segments.find((s: { start: string; end: string }) => d >= s.start && d <= s.end);
    await expect(page.getByTestId(`event-day-${d}`)).toHaveAttribute("data-phase", seg.label);
  }
  const peakSegment = event.segments.find(
    (s: { start: string; end: string }) => event.peak >= s.start && event.peak <= s.end,
  );
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-phase", peakSegment.label);

  // HIGH / MODERATE / ... never stands alone.
  const card = page.getByTestId("interpretation");
  await expect(page.getByTestId("hazard-level")).toContainText(
    /(LOW|MODERATE|ELEVATED|HIGH) OCEAN THERMAL SUPPORT|NOT CATEGORIZED/,
  );
  for (const heading of ["WHAT THIS MEANS", "WHY THIS MATTERS", "DISASTER RELEVANCE", "ATTENTION"])
    await expect(card).toContainText(heading);
  await expect(page.getByTestId("not-probability")).toContainText("not cyclone probability");
  await expect(page.getByTestId("hazard-non-prediction")).toContainText(
    "does not predict cyclone genesis, track, landfall, category",
  );

  // Plain-language help is one hover away.
  await page.getByTestId("tip-tchp").first().hover();
  await expect(page.getByRole("tooltip").filter({ hasText: "warmer than 26 °C" }).first()).toBeVisible();

  // The track is attributed external context, never model output.
  await expect(page.getByTestId("track-attribution")).toContainText("IBTrACS");
  await expect(page.getByTestId("track-attribution")).toContainText("never a model input or output");
  await expect(page.getByTestId("track-context")).toContainText("IBTrACS");

  const body = await page.locator("body").innerText();
  expect(body).not.toMatch(PROBABILITY);
  expect(body.toLowerCase()).not.toContain("risk score");
  expect(body.toLowerCase()).not.toContain("danger zone");
});

test("historical playback animates only real replay dates with every view in step", async ({
  page,
}) => {
  test.setTimeout(300000);
  const event = await eventInfo(page);
  const window = dateRange(event.window_start, event.window_end);
  const requested: string[] = [];
  page.on("request", (r) => {
    const url = new URL(r.url());
    if (url.pathname === "/api/replay/view") requested.push(url.searchParams.get("date") ?? "");
  });

  await openHazard(page);
  await chooseDay(page, event.window_start);
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-phase", event.segments[0].label);
  await expect(page.getByTestId("track-context")).toContainText("No best-track position");
  await page.getByTestId("hazard-dashboard").screenshot({ path: `${SHOTS}/01-mocha-pre-event.png` });

  const snapshot = async () => ({
    date: await page.getByTestId("phase-banner").getAttribute("data-date"),
    stage: await page.getByTestId("map-stage").getAttribute("data-field-date"),
    profile: await page.getByTestId("profile-stage").getAttribute("data-field-date"),
    areas: await page.getByTestId("monitoring-areas").getAttribute("data-date"),
    tchp: await page.getByTestId("interp-tchp").innerText(),
    table: await page.getByTestId("profile-table").innerText(),
    canvas: await page.getByTestId("hazard-map").evaluate((c) => {
      const url = (c as HTMLCanvasElement).toDataURL();
      let h = 0;
      for (let i = 0; i < url.length; i += 7) h = (h * 31 + url.charCodeAt(i)) | 0;
      return h;
    }),
  });
  const first = await snapshot();

  await page.getByLabel("Playback speed").selectOption("750");
  await page.getByTestId("event-play").click();
  await expect(page.getByTestId("event-playback")).toHaveAttribute("data-playing", "true");
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-date", window[3], {
    timeout: 150000,
  });
  await page.getByTestId("event-pause").click();
  await expect(page.getByTestId("event-playback")).toHaveAttribute("data-playing", "false");
  await expect(page.getByTestId("event-playback")).toHaveAttribute("data-busy", "false", {
    timeout: 60000,
  });
  const paused = await snapshot();
  await page.waitForTimeout(3500);
  expect((await snapshot()).date).toBe(paused.date); // pause really stops

  // Map, profile, monitoring areas and the banner all describe the same day.
  expect(paused.stage).toBe(paused.date);
  expect(paused.profile).toBe(paused.date);
  expect(paused.areas).toBe(paused.date);
  expect(paused.canvas).not.toBe(first.canvas);
  expect(paused.table === first.table && paused.tchp === first.tchp).toBe(false);

  // Only real window days were requested, consecutively, with none invented.
  const inPlay = requested.filter((d) => d >= event.window_start);
  for (const d of inPlay) expect(window).toContain(d);
  const shown = window.slice(0, window.indexOf(paused.date!) + 1);
  for (const d of shown) expect(requested).toContain(d);

  // Step forward across a frozen segment boundary.
  await page.getByRole("button", { name: "Next day" }).click();
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-date", window[4], {
    timeout: 90000,
  });
  const segment4 = event.segments.find((s: { start: string; end: string }) => window[4] >= s.start && window[4] <= s.end);
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-phase", segment4.label);

  // The shared 3D renderer follows the same day.
  await page.getByRole("button", { name: "3D depth" }).click();
  await expect(page.getByTestId("depth-renderer")).toBeVisible();
  await expect(page.getByTestId("map-stage")).toHaveAttribute("data-view", "3d");
  await page.getByRole("button", { name: "Next day" }).click();
  await expect(page.getByTestId("map-stage")).toHaveAttribute("data-field-date", window[5], {
    timeout: 90000,
  });
  await expect(page.getByTestId("profile-stage")).toHaveAttribute("data-field-date", window[5]);
  await expect(page.getByTestId("explode-notice")).toContainText("not to scale");
  await page.getByRole("button", { name: "2D map" }).click();

  // Choosing a date while playing stops playback and jumps to that real day.
  await page.getByTestId("event-play").click();
  const wake = event.segments.find((s: { label: string }) => s.label === "Wake");
  await page.getByTestId(`event-day-${wake.start}`).click();
  await expect(page.getByTestId("event-playback")).toHaveAttribute("data-playing", "false");
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-date", wake.start, {
    timeout: 90000,
  });
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-phase", "Wake");
  await expect(page.getByTestId("track-position")).toBeVisible();
  await page.getByTestId("hazard-dashboard").screenshot({ path: `${SHOTS}/03-mocha-cold-wake.png` });

  await chooseDay(page, event.peak);
  await expect(page.getByTestId("track-position")).toBeVisible();
  await page.getByTestId("hazard-dashboard").screenshot({ path: `${SHOTS}/02-mocha-event.png` });

  const recovery = event.segments.find((s: { label: string }) => s.label === "Recovery");
  await chooseDay(page, recovery.start);
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-phase", "Recovery");
  await page.getByTestId("hazard-dashboard").screenshot({ path: `${SHOTS}/04-mocha-recovery.png` });
});

test("before / wake / recovery numbers are derived from the event series", async ({ page }) => {
  test.setTimeout(240000);
  const event = await eventInfo(page);
  const response = await page.request.get("/api/event/series", { timeout: 200000 });
  const rows: { date: string; tchp_kj_cm2: number | null; sst_nominal_0m_c: number | null }[] = (
    await response.json()
  ).series;
  const inside = (s: { start: string; end: string }) => rows.filter((r) => r.date >= s.start && r.date <= s.end);
  const mean = (xs: (number | null)[]) => {
    const v = xs.filter((x): x is number => x !== null);
    return v.reduce((a, b) => a + b, 0) / v.length;
  };
  const pre = event.segments[0];
  const wake = event.segments.find((s: { label: string }) => s.label === "Wake");
  const preTchp = mean(inside(pre).map((r) => r.tchp_kj_cm2));
  const wakeTchp = inside(wake).filter((r) => r.tchp_kj_cm2 !== null);
  const minTchp = Math.min(...wakeTchp.map((r) => r.tchp_kj_cm2!));
  const change = minTchp - preTchp;
  const last = [...rows].reverse().find((r) => r.tchp_kj_cm2 !== null)!;
  const finalVsPre = last.tchp_kj_cm2! - preTchp;
  const sstChange = Math.min(...inside(wake).map((r) => r.sst_nominal_0m_c!)) - mean(inside(pre).map((r) => r.sst_nominal_0m_c));

  await openHazard(page);
  await page.getByRole("button", { name: /Show peak intensity/ }).click();
  await page.getByTestId("tab-evolution").click();
  const changes = page.getByTestId("event-changes");
  await expect(changes).toBeVisible({ timeout: 200000 });
  await expect(page.getByTestId("tchp-pre")).toHaveText(`${preTchp.toFixed(1)} kJ/cm²`);
  await expect(page.getByTestId("tchp-min")).toHaveText(`${minTchp.toFixed(1)} kJ/cm²`);
  await expect(page.getByTestId("tchp-change")).toContainText(Math.abs(change).toFixed(1));
  await expect(page.getByTestId("tchp-change")).toContainText(
    `${Math.abs((change / preTchp) * 100).toFixed(0)} %`,
  );
  await expect(page.getByTestId("ocean-recovery")).toContainText(Math.abs(finalVsPre).toFixed(1));
  await expect(page.getByTestId("ocean-recovery")).toContainText("No recovery category is assigned");
  for (const banned of ["NOT RECOVERED", "PARTIALLY RECOVERED", "NEAR PRE-EVENT STATE"])
    await expect(page.getByTestId("hazard-dashboard")).not.toContainText(banned);

  const story = page.getByTestId("ocean-story");
  if (change < 0 && sstChange < 0)
    await expect(story).toContainText("consistent with cyclone-associated upper-ocean cooling");
  else await expect(story).not.toContainText("consistent with");
  await expect(story).not.toContainText(/caused by|proves/i);

  // The cold-wake chart keeps one unit per axis and highlights the frozen phases.
  const plot = page.getByTestId("cold-wake").locator(".js-plotly-plot");
  await expect(plot).toBeVisible({ timeout: 60000 });
  const titles = (await plot.locator(".ytitle, .y2title, .y3title").allTextContents())
    .map((s) => s.trim())
    .sort();
  expect(titles).toEqual(["D26 (m)", "Nominal 0 m (°C)", "TCHP (kJ/cm²)"]);
  await expect(page.getByTestId("cold-wake")).toContainText("never a forecast");
});

// ---------------------------------------------------------------- latest qualified states

const WINDOW = ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"];
const MISSING: Record<string, string> = {
  "2026-09-01": "currents_nrt",
  "2026-09-02": "currents_nrt",
  "2026-09-03": "sss_nrt_multiobs",
};
const SOURCE_FOR: Record<string, string> = {
  "2026-08-31": "2023-05-05",
  "2026-09-04": "2023-05-12",
  "2026-09-05": "2023-05-16",
  "2026-09-06": "2023-05-20",
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = any;

async function latestFixtures(page: Page, options: { window?: string[]; newest?: string } = {}) {
  const q = await (await page.request.get("/api/latest/qualification")).json();
  test.skip(!q.qualified, "latest mode is not qualified on this machine");
  const cached = await (await page.request.get("/api/latest/qualified/cached")).json();
  const dates = options.window ?? WINDOW;
  const newest = options.newest ?? dates[dates.length - 1];
  const fields: Record<string, Json> = {};
  for (const [date, historical] of Object.entries(SOURCE_FOR)) {
    if (!dates.includes(date)) continue;
    const h = await (await page.request.get(`/api/replay/view?date=${historical}`, { timeout: 120000 })).json();
    fields[date] = {
      ...h,
      date,
      diagnostics: {
        ...h.diagnostics,
        d26_m: h.diagnostics.d26_m.map((r: unknown[]) => r.map(() => null)),
        withheld: ["d26"],
        qualification: { d26: q.d26_category, tchp: q.tchp_category },
      },
    };
  }
  const payload = (date: string, state: string) => ({
    mode: "LATEST_QUALIFIED_OCEAN_STATE",
    state,
    label: null,
    selected_date: date,
    effective_date: date,
    is_newest: date === newest,
    newest_qualified_date: newest,
    meta: cached.meta ?? { retrieval_time_utc: "2026-09-12T11:28:51", reconstruction_lag_hours: 203.5 },
    sources: cached.sources ?? [],
    live_attempt: null,
    field: fields[date],
  });
  const asked: string[] = [];
  const json = (route: Route, body: unknown) =>
    route.fulfill({ json: body, headers: { "content-type": "application/json" } });
  await page.route("**/api/latest/prewarm", (r) => json(r, { started: false }));
  // External cyclone context is answered locally so this suite never reaches a provider.
  await page.route("**/api/cyclones/current", (r) =>
    json(r, {
      state: "NO_ACTIVE_NORTH_INDIAN_CYCLONE",
      provider: "GDACS",
      retrieved_at: "2026-09-06T12:00:00Z",
      checked_at: "2026-09-06T12:00:00Z",
      cached: false,
      advisories: [],
      message: "No active North Indian Ocean cyclone reported by connected source (GDACS).",
      imd_status: "IMD / RSMC New Delhi official track: not connected in this build.",
    }),
  );
  await page.route("**/api/latest/available-dates**", (r) =>
    json(r, {
      newest_qualified_date: newest,
      window_days: dates.length,
      days: dates.map((d) => ({
        date: d,
        status: fields[d] ? "AVAILABLE" : "UNAVAILABLE",
        is_newest: d === newest,
        ...(fields[d]
          ? {}
          : { reason: `no usable field for ${MISSING[d] ?? "currents_nrt"}`, missing_channels: [MISSING[d] ?? "currents_nrt"] }),
      })),
      sources: [
        { product_key: "currents_nrt", channels: ["current_u", "current_v"], product_id: "OSCAR_L4_OC_NRT_V2.0" },
        { product_key: "sss_nrt_multiobs", channels: ["sss"], product_id: "MULTIOBS_GLO_PHY_S_SURFACE_MYNRT_015_013" },
      ],
    }),
  );
  await page.route("**/api/latest/qualified/cached", (r) => json(r, payload(newest, "LATEST_QUALIFIED")));
  await page.route("**/api/latest/qualified", (r) => json(r, payload(newest, "LATEST_QUALIFIED")));
  await page.route("**/api/latest/qualified?*", (r) => {
    const date = new URL(r.request().url()).searchParams.get("date")!;
    asked.push(date);
    return json(
      r,
      fields[date]
        ? payload(date, date === newest ? "LATEST_QUALIFIED" : "QUALIFIED_STATE_FOR_DATE")
        : { state: "DATE_NOT_QUALIFIED", label: "NO QUALIFIED STATE FOR THIS DATE", reason: "fixture", field: null },
    );
  });
  return { q, fields, asked };
}

async function openLatest(page: Page) {
  // The latest qualified state is a source of the Ocean State workspace.
  await page.goto("/");
  await expect(page.getByTestId("field-map")).toBeVisible({ timeout: 90000 });
  await page.getByTestId("source-latest").click();
  await expect(page.getByTestId("intel-mode-badge")).toHaveText("LATEST QUALIFIED STATE");
  await expect(page.getByTestId("nrt-header")).toBeVisible({ timeout: 90000 });
}

test("latest: every calendar day shows its state and unavailable days are never requested", async ({
  page,
}) => {
  test.setTimeout(240000);
  const { asked } = await latestFixtures(page);
  await openLatest(page);

  await expect(page.getByTestId("nrt-valid-date")).toHaveText("2026-09-06");
  await expect(page.getByTestId("nrt-day-2026-09-06")).toHaveAttribute("data-state", "SELECTED");
  await expect(page.getByTestId("nrt-day-2026-08-31")).toHaveAttribute("data-state", "AVAILABLE");
  for (const d of ["2026-09-01", "2026-09-02", "2026-09-03"]) {
    const chip = page.getByTestId(`nrt-day-${d}`);
    await expect(chip).toHaveAttribute("data-state", "UNAVAILABLE");
    await expect(chip).toHaveAttribute("title", /missing\/incomplete source/);
  }
  await expect(page.getByTestId("nrt-day-2026-09-02")).toHaveAttribute("title", /OSCAR_L4_OC_NRT_V2\.0/);
  // The chip is aria-disabled (it is never a frame) but stays clickable to explain why.
  await page.getByTestId("nrt-day-2026-09-02").click({ force: true });
  await expect(page.getByTestId("nrt-gap-notice")).toContainText("2026-09-02");
  await expect(page.getByTestId("nrt-gap-notice")).toContainText("OSCAR_L4_OC_NRT_V2.0");
  expect(asked.filter((d) => MISSING[d])).toEqual([]);
  await expect(page.getByTestId("nrt-noncontiguous")).toContainText("Missing days were not interpolated");

  // D26 stays withheld; TCHP stays qualified.
  await expect(page.getByTestId("nrt-d26")).toContainText("WITHHELD");
  await expect(page.getByTestId("nrt-d26")).toContainText("Operational qualification did not pass");
  await expect(page.getByTestId("nrt-tchp-qual")).toHaveText("QUALIFIED");
  await expect(page.getByTestId("interp-d26")).toHaveText("WITHHELD");
  const layers = page.getByLabel("Display layer");
  await expect(layers.locator('option[value="d26"]')).toHaveCount(0);
  await expect(layers.locator('option[value="tchp"]')).toHaveCount(1);

  // No live cyclone track is fabricated.
  await expect(page.getByTestId("official-track-status")).toContainText("Not connected in this build");
  await expect(page.getByTestId("track-overlay")).toHaveCount(0);
  await expect(page.getByTestId("nrt-timeliness")).toContainText("not the present moment");
  const body = await page.locator("body").innerText();
  expect(body).not.toMatch(PROBABILITY);
  expect(body).not.toContain("Live Ocean Right Now");
  await page.getByTestId("ocean-state").screenshot({ path: `${SHOTS}/05-latest-qualified.png` });
});

test("latest playback visits independent qualified states, skips gaps visibly and updates hotspots", async ({
  page,
}) => {
  test.setTimeout(300000);
  const { fields, asked } = await latestFixtures(page);
  await openLatest(page);

  const areaSignature = async () =>
    page
      .locator('[data-testid^="hotspot-"][data-tier]')
      .evaluateAll((els) => els.map((e) => `${e.getAttribute("data-lat")},${e.getAttribute("data-lon")},${e.getAttribute("data-tchp")}`).join("|"));

  await page.getByLabel("Playback speed").selectOption("750");
  await page.getByTestId("nrt-play").click();
  await expect(page.getByTestId("nrt-valid-date")).toHaveText("2026-08-31", { timeout: 90000 });
  await expect(page.getByTestId("monitoring-areas")).toHaveAttribute("data-date", "2026-08-31");
  const firstAreas = await areaSignature();

  await expect(page.getByTestId("nrt-valid-date")).toHaveText("2026-09-04", { timeout: 90000 });
  await expect(page.getByTestId("nrt-skipped")).toContainText("2026-09-01, 2026-09-02, 2026-09-03");
  await expect(page.getByTestId("map-stage")).toHaveAttribute("data-field-date", "2026-09-04");
  await expect(page.getByTestId("profile-stage")).toHaveAttribute("data-field-date", "2026-09-04");
  await expect(page.getByTestId("monitoring-areas")).toHaveAttribute("data-date", "2026-09-04");
  expect(await areaSignature()).not.toBe(firstAreas);

  await expect(page.getByTestId("nrt-playback")).toHaveAttribute("data-playing", "false", { timeout: 120000 });
  await expect(page.getByTestId("nrt-valid-date")).toHaveText("2026-09-06");
  for (const d of asked) expect(Object.keys(fields)).toContain(d);

  // A trend appears only across the three consecutive qualified states.
  const at = (date: string) => fields[date].diagnostics.tchp_kj_cm2[41][171] as number | null;
  const trend = page.getByTestId("trend-line");
  await expect(trend).toContainText("across 3 consecutive qualified states (2026-09-04 → 2026-09-06)", {
    timeout: 90000,
  });
  if (at("2026-09-06") !== null && at("2026-09-05") !== null)
    await expect(page.getByTestId("change-tchp")).toContainText(
      Math.abs(at("2026-09-06")! - at("2026-09-05")!).toFixed(1),
    );
  await page.getByTestId("ocean-state").screenshot({ path: `${SHOTS}/06-recent-evolution.png` });

  // After a gap there is no change to compute, and the page says so.
  await page.getByTestId("nrt-day-2026-08-31").click();
  await expect(page.getByTestId("nrt-valid-date")).toHaveText("2026-08-31", { timeout: 90000 });
  await expect(page.getByTestId("trend-fallback")).toContainText("Insufficient consecutive qualified days");
});

test("a thermal monitoring hotspot synchronises map, 3D, profile and explanation", async ({ page }) => {
  test.setTimeout(240000);
  await latestFixtures(page);
  await openLatest(page);

  const list = page.locator('[data-testid^="hotspot-"][data-tier]');
  await expect(list.first()).toBeVisible();
  const tiers = await list.evaluateAll((els) => els.map((e) => e.getAttribute("data-tier")));
  const peaks = await list.evaluateAll((els) => els.map((e) => Number(e.getAttribute("data-tchp"))));
  // Transparent rule: HIGH areas first, each group by descending peak TCHP.
  const firstElevated = tiers.indexOf("ELEVATED");
  if (firstElevated > 0) expect(tiers.slice(firstElevated)).not.toContain("HIGH");
  for (const group of ["HIGH", "ELEVATED"]) {
    const values = peaks.filter((_, i) => tiers[i] === group);
    expect(values).toEqual([...values].sort((a, b) => b - a));
  }
  await expect(page.getByTestId("hotspot-rule")).toContainText("never weighted");

  const second = list.nth(Math.min(1, (await list.count()) - 1));
  const lat = Number(await second.getAttribute("data-lat"));
  const lon = Number(await second.getAttribute("data-lon"));
  const tchp = (await second.getAttribute("data-tchp"))!;
  await second.getByRole("button").click();
  await expect(page.getByTestId("hotspot-card")).toContainText("WHY MONITOR THIS AREA?");
  await expect(page.getByTestId("hotspot-card")).toContainText("not a cyclone forecast");
  await expect(page.getByTestId("interp-tchp")).toHaveText(`${tchp} kJ/cm²`);
  await expect(page.getByTestId("interpretation")).toContainText(`${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E`);
  await expect(page.getByTestId("profile-stage")).toContainText(`Grid ${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E`);
  await expect(page.locator('[data-testid^="hotspot-mark-"].active')).toHaveCount(1);
  await page.getByTestId("ocean-state").screenshot({ path: `${SHOTS}/07-hotspot-selected.png` });

  await page.getByRole("button", { name: "3D depth" }).click();
  await expect(page.getByTestId("depth-renderer")).toBeVisible();
  await expect(page.getByTestId("profile-stage")).toContainText(`Grid ${lat.toFixed(2)}°N`);
  await expect(page.getByTestId("interp-tchp")).toHaveText(`${tchp} kJ/cm²`);
  expect((await page.locator("body").innerText()).toLowerCase()).not.toContain("risk score");
});

test("failure states are explicit: one state, provider outage, and no hotspot", async ({ page }) => {
  test.setTimeout(240000);

  // Only one qualified state.
  await latestFixtures(page, { window: ["2026-09-06"] });
  await openLatest(page);
  await expect(page.getByTestId("nrt-disabled")).toContainText(
    "Recent evolution unavailable: only one qualified state is currently available.",
  );
  await expect(page.getByTestId("nrt-play")).toBeDisabled();
  await expect(page.getByTestId("trend-fallback")).toContainText("only one qualified state");

  // Provider outage: nothing qualified, nothing shown in its place.
  await page.unrouteAll({ behavior: "ignoreErrors" });
  const none = { state: "LATEST_QUALIFIED_OCEAN_STATE_CURRENTLY_UNAVAILABLE", label: "LATEST QUALIFIED OCEAN STATE CURRENTLY UNAVAILABLE", field: null, live_attempt: { attempted: true, reasons: ["L1: currents_nrt UNREACHABLE"] } };
  await page.route("**/api/latest/prewarm", (r) => r.fulfill({ json: {} }));
  await page.route("**/api/cyclones/current", (r) =>
    r.fulfill({ json: { state: "SOURCE_UNAVAILABLE", provider: "GDACS", advisories: [], retrieved_at: null, message: "Cyclone advisory source currently unavailable.", imd_status: "IMD / RSMC New Delhi official track: not connected in this build." } }),
  );
  await page.route("**/api/latest/available-dates**", (r) => r.fulfill({ status: 503, json: { detail: "providers unreachable" } }));
  await page.route("**/api/latest/qualified/cached", (r) => r.fulfill({ json: none }));
  await page.route("**/api/latest/qualified", (r) => r.fulfill({ json: none }));
  await page.goto("/");
  await page.getByTestId("source-latest").click();
  const outage = page.getByTestId("nrt-unavailable");
  await expect(outage).toContainText("Latest reconstruction currently unavailable.", { timeout: 60000 });
  await expect(outage).toContainText("Historical Event Intelligence remains available.");
  await expect(page.getByTestId("map-stage")).toHaveCount(0);
  await page.getByRole("button", { name: "Open Historical Event Intelligence" }).click();
  await expect(page.getByTestId("event-bar")).toBeVisible();

  // A reconstruction with no HIGH/ELEVATED cell yields an explicit statement.
  await page.unrouteAll({ behavior: "ignoreErrors" });
  const date = "2023-05-06";
  const real = await (await page.request.get(`/api/replay/view?date=${date}`, { timeout: 120000 })).json();
  const lowCode = Number(Object.entries(real.hazard.category_labels).find(([, v]) => v === "LOW")![0]);
  const low = {
    ...real,
    hazard: {
      ...real.hazard,
      category: real.hazard.category.map((r: number[]) => r.map((c: number) => (real.hazard.category_labels[c] === "NOT_CATEGORIZED" ? c : lowCode))),
    },
  };
  await page.route(`**/api/replay/view?date=${date}*`, (r) => r.fulfill({ json: low }));
  await openHazard(page);
  await page.getByTestId(`event-day-${date}`).click();
  await expect(page.getByTestId("no-hotspot")).toContainText(
    "No HIGH/ELEVATED thermal monitoring area found under the frozen thermal-support protocol.",
    { timeout: 90000 },
  );
});

test("the dashboard talks only to the local server", async ({ page, baseURL }) => {
  const origin = new URL(baseURL!).origin;
  const foreign: string[] = [];
  page.on("request", (r) => {
    const url = r.url();
    if (!url.startsWith(origin) && !url.startsWith("data:") && !url.startsWith("blob:")) foreign.push(url);
  });
  await openHazard(page);
  await page.getByRole("button", { name: /Show peak intensity/ }).click();
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-phase", "Event", { timeout: 90000 });
  expect(foreign).toEqual([]);
});
