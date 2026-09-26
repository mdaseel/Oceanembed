import { test, expect, type Page, type Route } from "@playwright/test";

/**
 * Scientific + disaster intelligence expansion.
 *
 * The risks: a workspace that shows everything at once; an attribution read as
 * causation; a physics "score"; a coastal district called "at risk"; a replayed
 * historical track read as a forecast; an RI study that implies prediction; a
 * thermal extreme called a marine heatwave; and numbers on screen that are not
 * the backend's.
 *
 * External cyclone context is answered locally; every OceanEmbed number is real.
 */

const SHOTS = "../outputs/science_expansion";
const PROBABILITY = /\d+(\.\d+)?\s*%\s*(chance|probability|likelihood)/i;

const json = (route: Route, body: unknown) =>
  route.fulfill({ json: body, headers: { "content-type": "application/json" } });

async function offlineCyclones(page: Page) {
  await page.route("**/api/cyclones/current", (r) =>
    json(r, {
      state: "NO_ACTIVE_NORTH_INDIAN_CYCLONE",
      provider: "GDACS",
      retrieved_at: "2026-09-14T09:00:00Z",
      advisories: [],
      message: "No active North Indian Ocean cyclone reported by connected source (GDACS).",
      imd_status: "IMD / RSMC New Delhi official track: not connected in this build.",
    }),
  );
}

async function openOcean(page: Page) {
  await offlineCyclones(page);
  await page.goto("/");
  await expect(page.getByTestId("field-map")).toBeVisible({ timeout: 90000 });
}

async function bodyIsClean(page: Page) {
  const body = (await page.locator("body").innerText()).toLowerCase();
  expect(body).not.toMatch(PROBABILITY);
  for (const banned of ["risk score", "danger zone", "at risk", "marine heatwave detected", "physics score", "predicts rapid intensification"])
    expect(body).not.toContain(banned);
}

test("ocean state is map first: four workspaces, one map, one inspector, one tray", async ({ page }) => {
  await openOcean(page);
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await expect(nav.getByRole("link")).toHaveCount(4);
  for (const name of ["Ocean State", "Events & Disasters", "Model Science", "Scenario"])
    await expect(nav.getByRole("link", { name, exact: true })).toBeVisible();
  await expect(page.getByTestId("map-stage")).toHaveCount(1);
  await expect(page.getByTestId("inspector")).toHaveCount(1);
  await expect(page.getByTestId("analysis-tray")).toHaveCount(1);
  // Technical details are folded away until asked for.
  for (const id of ["inspector-inputs", "inspector-validation"])
    expect(await page.getByTestId(id).evaluate((d) => (d as HTMLDetailsElement).open)).toBe(false);
  await expect(page.getByTestId("inspector-location")).toHaveAttribute("open", "");
  await expect(page.getByTestId("integrity-drawer")).toHaveCount(0);
  await expect(page.getByTestId("tray-tab-profile")).toHaveAttribute("aria-selected", "true");
  await bodyIsClean(page);
  await page.screenshot({ path: `${SHOTS}/01-ocean-state-default.png` });

  // Scientific integrity is one click away, computed rather than asserted.
  await page.getByTestId("integrity-open").click();
  const drawer = page.getByTestId("integrity-drawer");
  await expect(drawer.locator('li[data-state="VERIFIED"]').first()).toBeVisible({ timeout: 60000 });
  await expect(drawer).toContainText("2024 Argo holdout");
  await expect(drawer.locator("li", { hasText: "2024 Argo holdout" })).toHaveAttribute("data-state", "PROTECTED");
  await expect(drawer.locator("li", { hasText: "Latest D26" })).toHaveAttribute("data-state", "WITHHELD");
  await expect(page.getByTestId("integrity-pipeline").locator("li")).toHaveCount(6);
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
});

test("coastal context describes geography for a monitoring area, never risk", async ({ page }) => {
  await openOcean(page);
  const area = page.locator('[data-testid^="hotspot-"][data-tier]').first();
  await expect(area).toBeVisible({ timeout: 60000 });
  const lat = Number(await area.getAttribute("data-lat"));
  const lon = Number(await area.getAttribute("data-lon"));
  await area.getByRole("button").click();
  const coastal = page.getByTestId("inspector-coastal");
  await expect(coastal).toHaveAttribute("open", "");
  const api = await (await page.request.get(`/api/science/coastal?lat=${lat}&lon=${lon}`)).json();
  const ctx = coastal.getByTestId("coastal-context");
  await expect(ctx).toHaveAttribute("data-status", api.status);
  if (api.status === "OK") {
    await expect(ctx.getByTestId("coastal-state")).toContainText(api.coastal_state);
    await expect(ctx.getByTestId("coastal-distance")).toContainText(String(api.offshore_distance_km));
  }
  await expect(ctx.getByTestId("coastal-wording")).toContainText("does not predict coastal damage");
  await bodyIsClean(page);
  await coastal.scrollIntoViewIfNeeded();
  await coastal.screenshot({ path: `${SHOTS}/05-coastal-context-inspector.png` });
});

test("thermal extremes are computed, located on the map and not called marine heatwaves", async ({ page }) => {
  test.setTimeout(240000);
  await openOcean(page);
  await page.getByTestId("tray-tab-extremes").click();
  const panel = page.getByTestId("thermal-extremes");
  await expect(panel.getByTestId("extreme-extent")).toBeVisible({ timeout: 180000 });
  await expect(panel.getByTestId("extreme-extent").locator("tr")).toHaveCount(3);
  await expect(panel.getByTestId("mhw-decision")).toContainText("SUBSURFACE THERMAL EXTREME");
  await expect(panel.getByTestId("mhw-decision")).toContainText("30 years");
  const date = await panel.getAttribute("data-date");
  const api = await (await page.request.get(`/api/science/thermal-extremes?date=${date}&depth=100&grid=false`, { timeout: 180000 })).json();
  await expect(panel).toContainText(`${api.n_active_cells.toLocaleString("en-US")} active cells`);
  if (api.n_active_cells > 0) await expect(page.getByTestId("extreme-overlay")).toHaveCount(1);
  await bodyIsClean(page);
  await page.getByTestId("analysis-tray").scrollIntoViewIfNeeded();
  await page.getByTestId("ocean-state").screenshot({ path: `${SHOTS}/08-thermal-extremes.png` });
});

test("model science: attribution is the backend's and never worded as causation", async ({ page }) => {
  test.setTimeout(240000);
  await openOcean(page);
  const date = await page.getByLabel("HISTORICAL DATE", { exact: true }).inputValue();
  await page.getByRole("link", { name: "Model Science" }).click();
  const heat = page.getByTestId("attribution-heatmap");
  await expect(heat).toBeVisible({ timeout: 120000 });
  await expect(heat).toHaveAttribute("data-rows", "15");
  await expect(heat).toHaveAttribute("data-cols", "7");
  const api = await (
    await page.request.get(`/api/science/attribution?lat=15.25&lon=87.75&date=${date}&source=historical`, { timeout: 120000 })
  ).json();
  expect(api.channels).toEqual(["sst", "sss", "sla", "current_u", "current_v", "wind_u", "wind_v"]);
  const first = await heat.locator("title").first().textContent();
  expect(first).toContain(`${Math.round(api.gross_share[0][0] * 100)}`);
  await expect(page.getByTestId("attribution-wording")).toContainText("Not causal");
  await expect(page.getByTestId("attribution-bands")).toContainText("0–50 m");
  await bodyIsClean(page);
  await page.screenshot({ path: `${SHOTS}/03-model-science-attribution.png` });

  await page.getByTestId("tab-ablation").click();
  await expect(page.getByTestId("occlusion-tchp").locator("tbody tr")).toHaveCount(7, { timeout: 120000 });
  await expect(page.getByTestId("occlusion-wording")).toContainText("Not a production field");
  await expect(page.getByTestId("retrained-ablation")).toContainText("noise floor");
  await expect(page.getByTestId("sst-only")).toHaveAttribute("data-status", /COMPLETED|NOT_RUN/);

  await page.getByTestId("tab-qa").click();
  await expect(page.getByTestId("physical-qa-summary")).toContainText("GLORYS reference", { timeout: 60000 });
  await expect(page.getByTestId("physical-qa-argo")).toContainText("Argo observed inversions");
  await expect(page.getByTestId("profile-qa")).toBeVisible({ timeout: 60000 });
  // The page states that no score exists; what must never appear is a scored value.
  await expect(page.getByTestId("physical-qa")).toContainText("No single physics score is computed");
  await expect(page.getByTestId("physical-qa")).not.toContainText(/(physics|plausibility) score\s*[:=]?\s*\d/i);
  await page.getByTestId("model-science").screenshot({ path: `${SHOTS}/04-model-science-physical-qa.png` });
  await page.getByTestId("basin-physics-toggle").click();
  await expect(page.getByTestId("basin-caveat")).toContainText("does not diagnose barrier-layer thickness");

  await page.getByTestId("tab-validation").click();
  const vc = page.getByTestId("science-analysis").getByTestId("validation-context");
  await expect(vc).toHaveAttribute("data-depth", "100");
  await expect(vc.getByTestId("validation-wording")).toContainText("not a calibrated uncertainty interval");
});

test("events: the historical-track stress test and the RI study are labelled for what they are", async ({ page }) => {
  test.setTimeout(300000);
  await openOcean(page);
  await page.getByRole("link", { name: "Events & Disasters" }).click();
  await expect(page.getByTestId("event-library")).toBeVisible();
  await expect(page.getByTestId("tab-overview")).toHaveAttribute("aria-selected", "true");
  await bodyIsClean(page);
  await page.screenshot({ path: `${SHOTS}/02-events-disasters.png` });

  await page.getByTestId("tab-trackanalysis").click();
  await page.getByTestId("tab-stress").click();
  const stress = page.getByTestId("stress-test");
  await expect(stress.getByTestId("stress-label")).toHaveText("REPLAYED HISTORICAL GEOMETRY — NOT A FORECAST OR PREDICTION");
  const api = await (await page.request.get("/api/events/mocha-2023/stress-test", { timeout: 200000 })).json();
  expect(api.geometry.translated).toBe(false);
  if (api.comparison) {
    const peak = api.comparison.find((r: { metric: string }) => r.metric === "peak_tchp");
    const row = stress.getByTestId("stress-comparison").locator('tr[data-metric="peak_tchp"]');
    await expect(row).toContainText(peak.historical.toFixed(1), { timeout: 200000 });
    if (peak.latest !== null) await expect(row).toContainText(peak.latest.toFixed(1));
  }
  // Recurrence may only appear as a denial; intensity is never inferred.
  await expect(stress).toContainText("nothing implies that this storm, or any storm, will recur");
  await expect(stress).toContainText("no intensity is inferred");
  await expect(stress).not.toContainText(/will intensify|forecast track|is expected to/i);
  await page.getByTestId("analysis-tabs").screenshot({ path: `${SHOTS}/06-historical-track-stress-test.png` });

  await page.getByTestId("tab-research").click();
  const ri = page.getByTestId("ri-study");
  await expect(ri).toBeVisible({ timeout: 60000 });
  const summary = await (await page.request.get("/api/science/ri-study")).json();
  const imd = summary.results.imd;
  await expect(ri.getByTestId("ri-counts")).toContainText(String(imd.counts.eligible));
  await expect(ri).toContainText(`EXPLORATORY N=${imd.counts.eligible}`);
  await expect(ri.getByTestId("ri-null-statement")).toContainText(/retrospective association/i);
  await expect(ri.getByTestId("ri-wording")).toContainText("Not a predictor");
  await bodyIsClean(page);
  await page.getByTestId("analysis-tabs").screenshot({ path: `${SHOTS}/07-ri-research-panel.png` });
});

test("scenario keeps its non-forecast framing and offers the stress test", async ({ page }) => {
  await openOcean(page);
  await page.getByRole("link", { name: "Scenario", exact: true }).click();
  await expect(page.getByTestId("intel-mode-badge")).toHaveText("USER-DRAWN SCENARIO");
  await expect(page.getByTestId("scenario-badge")).toContainText("NOT AN OFFICIAL FORECAST");
  await expect(page.getByTestId("tray-tab-stress")).toBeVisible();
  await bodyIsClean(page);
  await page.screenshot({ path: `${SHOTS}/09-scenario.png` });
});

test("narrow screens keep the map, the essentials and the navigation without overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openOcean(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(page.getByTestId("inspector-location")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/10-mobile.png` });
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("link", { name: "Model Science", exact: true }).click();
  await expect(page.getByTestId("model-science")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("the expanded workspaces talk only to the local server", async ({ page, baseURL }) => {
  test.setTimeout(240000);
  const origin = new URL(baseURL!).origin;
  const foreign: string[] = [];
  page.on("request", (r) => {
    const url = r.url();
    if (!url.startsWith(origin) && !url.startsWith("data:") && !url.startsWith("blob:")) foreign.push(url);
  });
  await openOcean(page);
  for (const name of ["Events & Disasters", "Model Science", "Scenario", "Ocean State"]) {
    await page.getByRole("link", { name, exact: true }).click();
    await page.waitForTimeout(1500);
  }
  expect(foreign).toEqual([]);
});
