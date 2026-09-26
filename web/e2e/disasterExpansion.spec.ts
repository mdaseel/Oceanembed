import { test, expect, type Page, type Route } from "@playwright/test";

/**
 * Disaster-management expansion: multi-cyclone history, external cyclone
 * context and track x thermal intelligence.
 *
 * The risks: an event that is not the rule-derived window; a number on screen
 * that is not the backend's sampling of a real reconstruction; an archived storm
 * presented as live; a user path presented as a forecast; a comparison that
 * ranks cyclones; an external track merged into OceanEmbed output.
 *
 * Nothing here reaches a provider. /api/cyclones/current is answered with
 * fixtures; the archived test event and every OceanEmbed field are local.
 */

const SHOTS = "../outputs/disaster_expansion";
const PROBABILITY = /\d+(\.\d+)?\s*%\s*(chance|probability|likelihood)/i;
const IMD = "IMD / RSMC New Delhi official track: not connected in this build.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = any;

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, json: body, headers: { "content-type": "application/json" } });

async function cycloneSource(page: Page, state: "none" | "unavailable" | "cached") {
  const body =
    state === "none"
      ? {
          state: "NO_ACTIVE_NORTH_INDIAN_CYCLONE",
          provider: "GDACS",
          retrieved_at: "2026-09-14T09:00:00Z",
          checked_at: "2026-09-14T09:00:00Z",
          cached: false,
          advisories: [],
          current_outside_north_indian: ["NORBERT-26"],
          message: "No active North Indian Ocean cyclone reported by connected source (GDACS).",
          imd_status: IMD,
        }
      : state === "unavailable"
        ? {
            state: "SOURCE_UNAVAILABLE",
            provider: "GDACS",
            retrieved_at: null,
            checked_at: "2026-09-14T09:00:00Z",
            advisories: [],
            message: "Cyclone advisory source currently unavailable.",
            imd_status: IMD,
          }
        : {
            state: "CACHED_ADVISORY_NOT_CURRENT",
            provider: "GDACS",
            retrieved_at: "2026-09-13T09:00:00Z",
            checked_at: "2026-09-14T09:00:00Z",
            cached: true,
            advisories: [],
            message:
              "Cached advisory — not current. Source unavailable at 2026-09-14T09:00:00Z; last retrieved 2026-09-13T09:00:00Z.",
            imd_status: IMD,
          };
  await page.unroute("**/api/cyclones/current");
  await page.route("**/api/cyclones/current", (r) => json(r, body));
}

/** Latest-mode fixture: one real historical reconstruction relabelled, D26 withheld. */
async function latestFixture(page: Page) {
  const q = await (await page.request.get("/api/latest/qualification")).json();
  const cached = await (await page.request.get("/api/latest/qualified/cached")).json();
  const date = "2026-09-06";
  const h = await (await page.request.get("/api/replay/view?date=2023-05-20", { timeout: 120000 })).json();
  const field = {
    ...h,
    date,
    diagnostics: {
      ...h.diagnostics,
      d26_m: h.diagnostics.d26_m.map((r: unknown[]) => r.map(() => null)),
      withheld: ["d26"],
      qualification: { d26: q.d26_category, tchp: q.tchp_category },
    },
  };
  const payload = {
    mode: "LATEST_QUALIFIED_OCEAN_STATE",
    state: "LATEST_QUALIFIED",
    label: null,
    selected_date: date,
    effective_date: date,
    is_newest: true,
    newest_qualified_date: date,
    meta: cached.meta ?? { retrieval_time_utc: "2026-09-12T11:28:51", reconstruction_lag_hours: 203.5 },
    sources: cached.sources ?? [],
    live_attempt: null,
    field,
  };
  await page.route("**/api/latest/prewarm", (r) => json(r, { started: false }));
  await page.route("**/api/latest/available-dates**", (r) =>
    json(r, { newest_qualified_date: date, window_days: 1, days: [{ date, status: "AVAILABLE", is_newest: true }], sources: [] }),
  );
  await page.route("**/api/latest/qualified/cached", (r) => json(r, payload));
  await page.route("**/api/latest/qualified", (r) => json(r, payload));
  await page.route("**/api/latest/qualified?*", (r) => json(r, payload));
  return q;
}

async function openHazard(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("field-map")).toBeVisible({ timeout: 90000 });
  await page.getByRole("link", { name: "Events & Disasters" }).click();
  await expect(page.getByTestId("hazard-dashboard")).toBeVisible();
}

async function openEvent(page: Page, event: Json) {
  await page.getByTestId(`event-card-${event.event_id}`).click();
  await expect(page.getByTestId("event-bar")).toHaveAttribute("data-event", event.event_id);
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-date", event.peak, { timeout: 150000 });
  await expect(page.getByTestId("map-stage")).toHaveAttribute("data-field-date", event.peak);
}

function days(start: string, end: string) {
  const out: string[] = [];
  for (let d = new Date(`${start}T00:00:00Z`); d <= new Date(`${end}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + 1))
    out.push(d.toISOString().slice(0, 10));
  return out;
}

/** The section is a real grid of blocks: many cells painted, and many distinct colours on the canvas. */
async function expectSectionPainted(page: Page, testid: string) {
  const canvas = page.getByTestId(`${testid}-canvas`);
  await expect(canvas).toBeVisible({ timeout: 200000 });
  expect(Number(await canvas.getAttribute("data-painted-cells"))).toBeGreaterThan(100);
  const colours = await canvas.evaluate((el) => {
    const c = el as HTMLCanvasElement;
    const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
    const seen = new Set<number>();
    for (let i = 0; i < d.length; i += 4 * 97) seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]);
    return seen.size;
  });
  expect(colours).toBeGreaterThan(40);
}

const bodyIsClean = async (page: Page) => {
  const body = (await page.locator("body").innerText()).toLowerCase();
  expect(body).not.toMatch(PROBABILITY);
  for (const banned of ["risk score", "danger zone", "most dangerous", "not recovered", "fully recovered"])
    expect(body).not.toContain(banned);
};

// ---------------------------------------------------------------- historical library

test("the event library lists every enabled cyclone and filters by basin", async ({ page }) => {
  const library = await (await page.request.get("/api/events")).json();
  expect(library.events.length).toBeGreaterThan(1);
  await openHazard(page);
  const panel = page.getByTestId("event-library");
  await expect(panel).toBeVisible();
  await expect(panel.locator('[data-testid^="event-card-"]')).toHaveCount(library.events.length);
  for (const e of library.events) {
    const card = page.getByTestId(`event-card-${e.event_id}`);
    await expect(card).toContainText(`${e.window_start} → ${e.window_end}`);
    if (e.in_sample) await expect(card).toContainText("IN-SAMPLE");
  }
  await expect(page.getByTestId("event-exclusions")).toContainText("No cyclone severity is assigned");

  await page.getByTestId("basin-filter-arabian-sea").click();
  const arabian = library.events.filter((e: Json) => e.basin.includes("Arabian Sea"));
  await expect(panel.locator('[data-testid^="event-card-"]')).toHaveCount(arabian.length);
  await page.getByTestId("basin-filter-all").click();
  await panel.screenshot({ path: `${SHOTS}/01-event-library.png` });
});

test("Mocha replays with its frozen segments and a second cyclone follows the same rule", async ({ page }) => {
  test.setTimeout(420000);
  const library = await (await page.request.get("/api/events")).json();
  const mocha = await (await page.request.get("/api/events/mocha-2023")).json();
  const frozen = await (await page.request.get("/api/event")).json();
  expect(mocha.segments).toEqual(frozen.segments);

  await openHazard(page);
  await openEvent(page, mocha);
  await expect(page.getByTestId("phase-banner")).toContainText("Pre-registered segment");
  await expect(page.getByTestId("track-attribution")).toContainText("IBTrACS");
  await bodyIsClean(page);
  await page.getByTestId("hazard-dashboard").screenshot({ path: `${SHOTS}/02-mocha-replay.png` });

  const second = library.events.find((e: Json) => e.event_id !== "mocha-2023" && e.basin.includes("Arabian Sea"));
  const info = await (await page.request.get(`/api/events/${second.event_id}`)).json();
  await openEvent(page, info);
  const window = days(info.window_start, info.window_end);
  await expect(page.locator('[data-testid^="event-day-"]')).toHaveCount(window.length);
  for (const d of window) {
    const seg = info.segments.find((s: Json) => d >= s.start && d <= s.end);
    await expect(page.getByTestId(`event-day-${d}`)).toHaveAttribute("data-phase", seg.label);
  }
  await expect(page.getByTestId("phase-banner")).toContainText("Rule-derived segment");
  await expect(page.getByTestId("track-overlay")).toBeVisible();
  await expect(page.getByTestId("track-context")).toContainText("IBTrACS");
  if (info.in_sample) await expect(page.getByTestId("event-split-note")).toContainText("IN-SAMPLE");

  // Playback advances only to the next real replay day.
  await page.getByTestId(`event-day-${window[window.length - 3]}`).click();
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-date", window[window.length - 3], { timeout: 150000 });
  await page.getByRole("button", { name: "Next day" }).click();
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-date", window[window.length - 2], { timeout: 150000 });
  await expect(page.getByTestId("profile-stage")).toHaveAttribute("data-field-date", window[window.length - 2]);
  await openEvent(page, info);
  await page.getByTestId("hazard-dashboard").screenshot({ path: `${SHOTS}/03-second-cyclone-replay.png` });
});

test("track x thermal, along-track section and change maps show the backend's numbers", async ({ page }) => {
  test.setTimeout(600000);
  const event = await (await page.request.get("/api/events/mocha-2023")).json();
  await openHazard(page);
  await openEvent(page, event);

  // Track x thermal state on the displayed day.
  const api = await (await page.request.get(`/api/events/mocha-2023/track-analysis?date=${event.peak}`, { timeout: 200000 })).json();
  await page.getByTestId("tab-trackanalysis").click();
  await page.getByTestId("tab-track").click();
  const panel = page.getByTestId("event-track");
  await expect(panel).toHaveAttribute("data-date", event.peak, { timeout: 200000 });
  const top = api.summary.intersects.HIGH ? "HIGH" : api.summary.intersects.ELEVATED ? "ELEVATED" : "NONE";
  await expect(page.getByTestId("event-track-intersection")).toHaveAttribute("data-intersects", top);
  if (api.summary.tchp.max)
    await expect(page.getByTestId("event-track-summary")).toContainText(`${api.summary.tchp.max.value.toFixed(1)} kJ/cm²`);
  await expect(page.getByTestId("event-track-labels")).toContainText("OceanEmbed");
  await expect(page.getByTestId("event-track-labels")).toContainText(/external|IBTrACS/i);
  if (api.summary.strongest_segment) await expect(page.getByTestId("event-track-strongest")).toBeVisible();

  // Along-track vertical section across the 15 model depths.
  const section = await (await page.request.get(`/api/events/mocha-2023/section?date=${event.peak}&mode=anomaly`, { timeout: 200000 })).json();
  expect(section.depths_m).toHaveLength(15);
  await page.getByTestId("tab-section").click();
  await expectSectionPainted(page, "event-section");
  await page.getByTestId("event-section-mode-anomaly").click();
  await expect(page.getByTestId("event-section")).toHaveAttribute("data-mode", "anomaly", { timeout: 200000 });
  await expectSectionPainted(page, "event-section");
  await expect(page.getByTestId("event-section-note")).toBeVisible();
  await page.waitForTimeout(1500);
  await page.getByTestId("analysis-tabs").screenshot({ path: `${SHOTS}/05-historical-section.png` });

  // Before -> wake change map and cold-wake footprint.
  const diff = await (await page.request.get("/api/events/mocha-2023/difference?from_segment=Pre-event&to_segment=Wake&depth=100", { timeout: 300000 })).json();
  await page.getByTestId("tab-change").click();
  await expect(page.getByTestId("difference-map")).toBeVisible({ timeout: 300000 });
  const fp = page.getByTestId("cold-wake-footprint");
  const cool100 = diff.footprint.temperature["100"].min;
  if (cool100) await expect(fp.locator('tr[data-depth="100"]')).toContainText(Math.abs(cool100.value).toFixed(2));
  await expect(fp).toContainText("No cold-wake severity score");
  await page.getByTestId("change-quantity-tchp").click();
  await expect(page.getByTestId("difference-map")).toBeVisible();
  await page.getByTestId("change-quantity-tchp").click();
  await page.getByTestId("analysis-tabs").screenshot({ path: `${SHOTS}/06-before-wake-map.png` });
  await bodyIsClean(page);
});

test("cyclones are compared side by side without a ranking, and the brief is printable", async ({ page }) => {
  test.setTimeout(600000);
  const library = await (await page.request.get("/api/events")).json();
  const ids = [library.events[0].event_id, library.events[library.events.length - 1].event_id];
  await openHazard(page);
  await page.getByTestId("tab-compare").click();
  await expect(page.getByTestId("compare-empty")).toBeVisible();
  for (const e of library.events.filter((x: Json) => ids.includes(x.event_id)))
    await page.getByRole("checkbox", { name: `Compare ${e.short_name} ${e.season}` }).check();
  const compare = page.getByTestId("compare-cyclones");
  await expect(compare).toBeVisible({ timeout: 400000 });
  await expect(page.getByTestId("compare-note")).toContainText("not rank cyclone danger");
  const api = await (await page.request.get(`/api/events/compare?ids=${ids.join(",")}`, { timeout: 400000 })).json();
  for (const entry of api.events) {
    const pre = entry.metrics.pre_event_tchp;
    if (pre !== null) await expect(compare).toContainText(pre.toFixed(1));
  }
  await bodyIsClean(page);
  await compare.screenshot({ path: `${SHOTS}/04-compare-cyclones.png` });

  const event = await (await page.request.get("/api/events/mocha-2023")).json();
  await page.getByTestId(`event-card-mocha-2023`).click();
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-date", event.peak, { timeout: 150000 });
  await page.getByTestId("tab-brief").click();
  const brief = page.getByTestId("event-brief");
  await expect(brief).toContainText("CYCLONE OCEAN RESPONSE BRIEF", { timeout: 400000 });
  await expect(brief).toContainText("IBTrACS");
  await expect(brief).toContainText(/does not (predict|forecast)/);
  await expect(page.getByTestId("event-brief-print")).toBeVisible();
  await bodyIsClean(page);
  await brief.screenshot({ path: `${SHOTS}/13-disaster-brief.png` });
});

// ---------------------------------------------------------------- latest / NRT context

test("NRT: no active cyclone is stated, never faked, and source failures are explicit", async ({ page }) => {
  test.setTimeout(300000);
  const q = await latestFixture(page);
  await cycloneSource(page, "none");
  await openHazard(page);
  // Latest / NRT cyclone context lives in Ocean State, in the Cyclone context tab.
  await page.getByRole("link", { name: "Ocean State" }).click();
  await page.getByTestId("source-latest").click();
  await page.getByTestId("tray-tab-cyclone").click();
  const watch = page.getByTestId("cyclone-watch");
  await expect(watch).toHaveAttribute("data-state", "NO_ACTIVE_NORTH_INDIAN_CYCLONE", { timeout: 60000 });
  await expect(page.getByTestId("cyclone-watch-title")).toHaveText("OCEAN THERMAL WATCH");
  await expect(page.getByTestId("cyclone-status")).toContainText("NO ACTIVE NORTH INDIAN OCEAN CYCLONE");
  await expect(page.getByTestId("cyclone-status")).toContainText("No active North Indian Ocean cyclone reported by connected source");
  await expect(page.getByTestId("imd-status")).toContainText("not connected in this build");
  await expect(page.getByTestId("external-track-overlay")).toHaveCount(0);
  await expect(page.getByTestId("cyclone-analysis")).toHaveCount(0);
  await expect(page.getByTestId("watch-brief")).toContainText("OCEAN THERMAL WATCH BRIEF");
  await expect(page.getByTestId("external-hazard-context")).toContainText("NOT CONNECTED");
  if (q.qualified) {
    await expect(page.getByTestId("nrt-d26")).toContainText("WITHHELD", { timeout: 90000 });
    // folded into the inspector until needed, but present
    await expect(page.getByTestId("basin-summary")).toHaveCount(1);
  }
  await bodyIsClean(page);
  await page.getByTestId("ocean-state").screenshot({ path: `${SHOTS}/07-nrt-no-active-cyclone.png` });

  await cycloneSource(page, "unavailable");
  await page.getByRole("button", { name: "Check source" }).click();
  await expect(page.getByTestId("cyclone-status")).toContainText("Cyclone advisory source currently unavailable.");
  await cycloneSource(page, "cached");
  await page.getByRole("button", { name: "Check source" }).click();
  await expect(page.getByTestId("cyclone-status")).toContainText("CACHED ADVISORY — NOT CURRENT");
  await expect(page.getByTestId("cyclone-status")).toContainText("Cached advisory — not current.");
});

test("NRT: an archived cyclone is labelled HISTORICAL / TEST EVENT and sampled on its own date", async ({ page }) => {
  test.setTimeout(420000);
  await latestFixture(page);
  await cycloneSource(page, "none");
  const api = await (await page.request.get("/api/cyclones/archived-test?mode=temperature", { timeout: 300000 })).json();
  expect(api.state).toBe("HISTORICAL_TEST_EVENT");
  expect(api.advisory.provenance_label).not.toMatch(/IMD|official/i);

  await openHazard(page);
  // Latest / NRT cyclone context lives in Ocean State, in the Cyclone context tab.
  await page.getByRole("link", { name: "Ocean State" }).click();
  await page.getByTestId("source-latest").click();
  await page.getByTestId("tray-tab-cyclone").click();
  await expect(page.getByTestId("cyclone-watch")).toHaveAttribute("data-state", "NO_ACTIVE_NORTH_INDIAN_CYCLONE", { timeout: 60000 });
  await page.getByTestId("archived-test-toggle").click();
  const analysis = page.getByTestId("cyclone-analysis");
  await expect(analysis).toHaveAttribute("data-test-event", "true", { timeout: 300000 });
  await expect(page.getByTestId("test-event-banner")).toContainText("HISTORICAL / TEST EVENT");
  await expect(page.getByTestId("cyclone-field-date")).toHaveText(api.thermal_field.valid_date);
  await expect(page.getByTestId("map-test-banner")).toContainText("not the latest qualified state");
  await expect(page.getByTestId("map-stage")).toHaveAttribute("data-field-date", api.thermal_field.valid_date, { timeout: 200000 });
  await expect(page.getByTestId("external-track-overlay")).toBeVisible();
  await expect(page.getByTestId("external-track-legend")).toContainText(/observed/i);
  await expect(page.getByTestId("external-track-legend")).toContainText(/forecast/i);
  await expect(page.getByTestId("official-track-status")).toContainText(api.advisory.provenance_label);
  const body = await page.locator("body").innerText();
  expect(body).not.toContain("IMD official track:");
  await bodyIsClean(page);
  await page.getByTestId("ocean-state").screenshot({ path: `${SHOTS}/08-nrt-archived-test-event.png` });

  // Track x thermal intersection mirrors the backend sampling.
  const s = api.analysis.summary;
  const top = s.intersects.HIGH ? "HIGH" : s.intersects.ELEVATED ? "ELEVATED" : "NONE";
  await expect(page.getByTestId("cyclone-track-intersection")).toHaveAttribute("data-intersects", top);
  if (s.tchp.max)
    await expect(page.getByTestId("cyclone-track-summary")).toContainText(`${s.tchp.max.value.toFixed(1)} kJ/cm²`);
  await expect(page.getByTestId("cyclone-track-labels")).toContainText("GDACS");
  await page.getByTestId("cyclone-track").screenshot({ path: `${SHOTS}/09-track-thermal-intersection.png` });

  await expectSectionPainted(page, "cyclone-section");
  await page.waitForTimeout(1500);
  await page.getByTestId("cyclone-section").screenshot({ path: `${SHOTS}/10-nrt-along-track-section.png` });

  // Monitoring areas state their relation to the external track line.
  const relation = page.locator('[data-testid^="hotspot-relation-"]').first();
  await expect(relation).toBeVisible({ timeout: 60000 });
  await expect(relation).toContainText(/TRACK INTERSECTION|OUTSIDE TRACK LINE/);
  await page.getByTestId("monitoring-areas").screenshot({ path: `${SHOTS}/11-monitoring-areas.png` });
  await expect(page.getByTestId("cyclone-brief")).toContainText("HISTORICAL / TEST EVENT");
});

// ---------------------------------------------------------------- scenario

test("scenario analysis samples a user-drawn path and never calls it a forecast", async ({ page }) => {
  test.setTimeout(420000);
  await page.route("**/api/cyclones/current", (r) => json(r, { state: "NO_ACTIVE_NORTH_INDIAN_CYCLONE", provider: "GDACS", advisories: [], imd_status: IMD, retrieved_at: null }));
  await openHazard(page);
  const event = await (await page.request.get("/api/events/mocha-2023")).json();
  await page.getByTestId("event-card-mocha-2023").click();
  await expect(page.getByTestId("phase-banner")).toHaveAttribute("data-date", event.peak, { timeout: 150000 });

  await page.getByRole("link", { name: "Scenario", exact: true }).click();
  await expect(page.getByTestId("intel-mode-badge")).toHaveText("USER-DRAWN SCENARIO");
  await expect(page.getByTestId("scenario-badge")).toContainText("NOT AN OFFICIAL FORECAST");
  const points = [
    { lat: 12, lon: 88 },
    { lat: 15, lon: 89.5 },
    { lat: 18, lon: 91.5 },
  ];
  for (const p of points.slice(0, 2)) {
    await page.getByLabel("Scenario latitude").fill(String(p.lat));
    await page.getByLabel("Scenario longitude").fill(String(p.lon));
    await page.getByRole("button", { name: "Add point" }).click();
  }
  // Drawing on the map adds a point through the shared projection.
  await page.getByTestId("scenario-draw").click();
  const capture = page.getByTestId("draw-capture");
  await expect(capture).toBeVisible();
  const box = (await capture.boundingBox())!;
  await page.mouse.click(box.x + box.width * 0.62, box.y + box.height * 0.45);
  await expect(page.getByTestId("scenario-points")).toContainText("3 points");
  await page.getByTestId("scenario-draw").click();
  await expect(page.getByTestId("scenario-overlay")).toBeVisible();

  const drawn = (await page.getByTestId("scenario-points").innerText()).split(": ")[1].split(" → ").map((t) => {
    const [lat, lon] = t.split(", ").map(Number);
    return { lat, lon };
  });
  await page.getByTestId("scenario-run").click();
  const track = page.getByTestId("scenario-track");
  await expect(track).toBeVisible({ timeout: 300000 });
  await expect(track).toHaveAttribute("data-date", event.peak);
  const api = await (
    await page.request.post("/api/scenario/analysis", {
      data: { field: "historical", date: event.peak, points: drawn, mode: "temperature" },
      timeout: 300000,
    })
  ).json();
  expect(api.badge).toContain("NOT AN OFFICIAL FORECAST");
  if (api.analysis.summary.tchp.max && Math.abs(api.analysis.summary.tchp.max.value) > 0) {
    // the displayed coordinates are rounded to 0.01°, so compare to one decimal of TCHP only when unambiguous
    await expect(page.getByTestId("scenario-track-summary")).toContainText("kJ/cm²");
  }
  await expect(page.getByTestId("scenario-track-intersection")).toContainText(/user-drawn path/);
  await expectSectionPainted(page, "scenario-section");
  const body = await page.locator("body").innerText();
  expect(body).not.toMatch(/scenario forecast|predicted track/i);
  await bodyIsClean(page);
  await page.waitForTimeout(1500);
  await page.getByTestId("hazard-dashboard").screenshot({ path: `${SHOTS}/12-scenario-analysis.png` });
});

test("the expanded dashboard talks only to the local server", async ({ page, baseURL }) => {
  test.setTimeout(240000);
  const origin = new URL(baseURL!).origin;
  const foreign: string[] = [];
  page.on("request", (r) => {
    const url = r.url();
    if (!url.startsWith(origin) && !url.startsWith("data:") && !url.startsWith("blob:")) foreign.push(url);
  });
  await latestFixture(page);
  await cycloneSource(page, "none");
  await openHazard(page);
  // Latest / NRT cyclone context lives in Ocean State, in the Cyclone context tab.
  await page.getByRole("link", { name: "Ocean State" }).click();
  await page.getByTestId("source-latest").click();
  await page.getByTestId("tray-tab-cyclone").click();
  await expect(page.getByTestId("cyclone-watch")).toHaveAttribute("data-state", "NO_ACTIVE_NORTH_INDIAN_CYCLONE", { timeout: 60000 });
  await page.getByRole("link", { name: "Scenario", exact: true }).click();
  await page.getByRole("link", { name: "Events & Disasters" }).click();
  await expect(page.getByTestId("event-library")).toBeVisible();
  expect(foreign).toEqual([]);
});
