import { test, expect, type Page, type Route } from "@playwright/test";

/**
 * Phase 8B — Latest Qualified Ocean State.
 *
 * The risks: a qualified claim the decision artifact does not grant; a second
 * renderer for the latest field; a displayed value that differs from the
 * backend's; D26 shown although it is not operationally qualified; a stale
 * snapshot passed off as current; and a blank tab when nothing is available.
 *
 * The live provider is never contacted: the live endpoint is answered with the
 * backend's own last qualified snapshot, so the field is a real frozen-L2
 * output and the test stays offline. Requires a snapshot produced by a real
 * qualified run (scripts/nrt8b/run_operational_resilience_test.py).
 */

async function cachedPayload(page: Page) {
  const r = await page.request.get("/api/latest/qualified/cached");
  expect(r.ok()).toBeTruthy();
  const p = await r.json();
  test.skip(!p.field, "no qualified snapshot on this machine");
  // Default window stub so no test contacts a live provider; tests that need a
  // specific window register their own route afterwards, which then wins.
  await page.route("**/api/latest/available-dates**", (r2: Route) =>
    r2.fulfill({
      json: { newest_qualified_date: p.effective_date, window_days: 1,
              days: [{ date: p.effective_date, status: "AVAILABLE", is_newest: true }] },
      headers: { "content-type": "application/json" },
    }));
  return p;
}

/** The latest qualified state is a source of the Ocean State workspace. */
async function openLatestState(page: Page) {
  await page.goto("/");
  await page.getByRole("link", { name: "Ocean State", exact: true }).click();
  await page.getByTestId("source-latest").click();
}

async function serveLive(page: Page, body: unknown) {
  await page.route("**/api/latest/qualified", (r: Route) =>
    r.fulfill({ json: body, headers: { "content-type": "application/json" } }),
  );
}

test("the tab name and every qualified claim come from the decision artifact", async ({
  page,
}) => {
  const q = await (await page.request.get("/api/latest/qualification")).json();
  expect(q.qualified).toBe(true);
  const cached = await cachedPayload(page);
  await serveLive(page, { ...cached, state: "LATEST_QUALIFIED", label: null, live_attempt: null });
  await openLatestState(page);

  await expect(page.getByTestId("qualification-banner")).toContainText(q.banner);
  await expect(page.getByTestId("qualification-banner")).toContainText(
    "QUALIFIED WITH LIMITATIONS",
  );
  await expect(page.getByTestId("d26-withheld")).toContainText("NOT QUALIFIED");
  // Hardening: the three human-facing statements are shown, with the real
  // valid date and lag, and qualification is never passed off as timeliness.
  const lagDays = (cached.meta.reconstruction_lag_hours / 24).toFixed(1);
  const tl = page.getByTestId("timeliness-note");
  await expect(tl).toContainText("Operational timeliness has not been separately certified");
  await expect(tl).toContainText(`valid for ${cached.effective_date}`);
  await expect(tl).toContainText(`${lagDays}-day reconstruction lag`);
  await expect(page.getByTestId("d26-withheld")).toContainText(
    "not exposed as a qualified D26 product",
  );
  await expect(page.getByTestId("hazard-transfer-note")).toContainText(
    "not observationally validated as a cyclone forecast",
  );
  await expect(page.getByTestId("limitations")).toContainText("observational");
  await expect(page.getByTestId("effective-date")).toContainText(cached.effective_date);
  await expect(page.locator('[data-testid="latest-sources"] tbody tr')).toHaveCount(5);
  const body = await page.locator("body").innerText();
  expect(body).not.toContain("Live Ocean Right Now");
  // The disclosure "No numeric cyclone probability is produced" is required
  // wording; what must never appear is an actual number presented as one.
  expect(body).not.toMatch(/probability\s*(of\s*\w+\s*)?[:=]?\s*\d/i);
  expect(body).not.toMatch(/\d+(\.\d+)?\s*%\s*(chance|probability|likelihood)/i);
  expect(body).toContain("No numeric cyclone probability is produced");
});

test("the latest field is drawn by the SAME map, 3D renderer and profile, unchanged", async ({
  page,
}) => {
  const q = await (await page.request.get("/api/latest/qualification")).json();
  const cached = await cachedPayload(page);
  await serveLive(page, { ...cached, state: "LATEST_QUALIFIED", label: null, live_attempt: null });
  await openLatestState(page);

  // The historical 2D map component renders the latest field.
  await expect(page.getByTestId("field-map")).toBeVisible();
  // D26 is withheld: no layer offers it; TCHP is qualified and offered.
  const layerSelect = page.getByLabel("Display layer");
  await expect(layerSelect.locator('option[value="d26"]')).toHaveCount(0);
  await expect(layerSelect.locator('option[value="tchp"]')).toHaveCount(1);

  // A displayed value equals the backend's value for the same cell and depth
  // (default selection 15.25 N, 87.75 E -> row 41, col 171; default depth 100 m).
  const t = cached.field.temperature[41][171][7];
  if (t !== null) {
    await expect(page.locator(".stat", { hasText: "L2 TEMPERATURE / 100 M" })).toContainText(
      (t as number).toFixed(3),
    );
    await expect(page.getByTestId("profile-table")).toContainText((t as number).toFixed(3));
  }

  // The shared Phase-7B 3D renderer, not a second implementation.
  await page.getByRole("button", { name: "3D depth" }).click();
  await expect(page.getByTestId("depth-renderer")).toBeVisible();

  await expect(page.getByTestId("latest-hazard")).toContainText("does not predict");
  await expect(page.getByTestId("latest-hazard-transfer")).toContainText(
    "not observationally validated as a cyclone forecast",
  );
  await page.locator("main").screenshot({ path: "../outputs/phase8b/latest-qualified.png" });
});

test("a failed live attempt shows the snapshot labelled NOT CURRENT", async ({ page }) => {
  const q = await (await page.request.get("/api/latest/qualification")).json();
  const cached = await cachedPayload(page);
  await serveLive(page, {
    ...cached,
    live_attempt: { attempted: true, reasons: ["L1: current_u not retrieved (UNREACHABLE)"] },
  });
  await openLatestState(page);
  await expect(page.getByTestId("snapshot-label")).toContainText("NOT CURRENT");
  await expect(page.getByTestId("live-attempt")).toContainText("no inference was run");
  await expect(page.getByTestId("field-map")).toBeVisible();
  await page.locator("main").screenshot({ path: "../outputs/phase8b/latest-snapshot.png" });
});

test("with nothing available the unavailable state is informative, never blank", async ({
  page,
}) => {
  const q = await (await page.request.get("/api/latest/qualification")).json();
  const none = {
    mode: "LATEST_QUALIFIED_OCEAN_STATE", phase: "8B",
    state: "LATEST_QUALIFIED_OCEAN_STATE_CURRENTLY_UNAVAILABLE",
    label: "LATEST QUALIFIED OCEAN STATE CURRENTLY UNAVAILABLE",
    qualification: q, field: null,
    live_attempt: { attempted: true, reasons: ["no common valid date: currents_nrt UNREACHABLE"] },
  };
  await page.route("**/api/latest/qualified/cached", (r) =>
    r.fulfill({ json: none, headers: { "content-type": "application/json" } }));
  await serveLive(page, none);
  await openLatestState(page);
  await expect(page.getByTestId("unavailable-label")).toContainText("CURRENTLY UNAVAILABLE");
  await expect(page.getByTestId("latest-sources")).toContainText("No qualified reconstruction yet");
  await expect(page.getByTestId("field-map")).toHaveCount(0);
});

test("an unqualified decision keeps Latest Inputs and exposes no latest map", async ({
  page,
}) => {
  await page.route("**/api/latest/qualification", (r) =>
    r.fulfill({
      json: { qualified: false, tab_name: "Latest Inputs",
              temperature_category: "NOT QUALIFIED",
              banner: "LATEST SUBSURFACE RECONSTRUCTION NOT QUALIFIED" },
      headers: { "content-type": "application/json" },
    }));
  await page.route("**/api/latest/qualified**", (r) => r.abort());
  await page.goto("/");
  await page.getByRole("link", { name: "Latest Inputs" }).click();
  await expect(page.getByTestId("not-certified")).toBeVisible();
  await expect(page.getByTestId("qualification-banner")).toHaveCount(0);
});

test("historical replay keeps D26 and is untouched by the latest mode", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("field-map")).toBeVisible();
  const layerSelect = page.getByLabel("Display layer");
  await expect(layerSelect.locator('option[value="d26"]')).toHaveCount(1);
  await expect(page.locator(".mode-badge")).toHaveText("HISTORICAL REPLAY");
});

/**
 * Phase 8B follow-up (2026-09-12): the recent qualified states selector.
 *
 * The window is served from a fixture so the test is offline and deterministic;
 * the field itself is still the backend's own last qualified snapshot.
 */
function windowFixture(newest: string, dates: string[]) {
  return {
    newest_qualified_date: newest,
    window_days: dates.length,
    days: dates.map((d) => ({
      date: d,
      status: d === "2026-09-02" ? "UNAVAILABLE" : "AVAILABLE",
      is_newest: d === newest,
      ...(d === "2026-09-02"
        ? { reason: "no usable field for currents_nrt", missing_channels: ["currents_nrt"] }
        : {}),
    })),
  };
}

test("the recent-states selector lists a 7-day window and marks the newest", async ({
  page,
}) => {
  const q = await (await page.request.get("/api/latest/qualification")).json();
  const cached = await cachedPayload(page);
  const dates = ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03",
                 "2026-09-04", "2026-09-05", "2026-09-06"];
  await page.route("**/api/latest/available-dates**", (r) =>
    r.fulfill({ json: windowFixture("2026-09-06", dates),
                headers: { "content-type": "application/json" } }));
  await page.route("**/api/latest/qualified?*", async (route) => {
    const date = new URL(route.request().url()).searchParams.get("date")!;
    await route.fulfill({
      json: { ...cached, state: "QUALIFIED_STATE_FOR_DATE", label: null,
              selected_date: date, effective_date: date, is_newest: date === "2026-09-06",
              newest_qualified_date: "2026-09-06", live_attempt: null,
              field: { ...cached.field, date } },
      headers: { "content-type": "application/json" },
    });
  });
  await serveLive(page, { ...cached, state: "LATEST_QUALIFIED", label: null,
                          selected_date: "2026-09-06", effective_date: "2026-09-06",
                          is_newest: true, newest_qualified_date: "2026-09-06",
                          live_attempt: null,
                          field: { ...cached.field, date: "2026-09-06" } });
  await openLatestState(page);

  // One recent-states control: the Ocean State playback timeline.
  await expect(page.getByTestId("nrt-playback")).toBeVisible();
  for (const d of dates) await expect(page.getByTestId(`nrt-day-${d}`)).toBeVisible();
  await expect(page.getByTestId("newest-qualified-state")).toContainText("2026-09-06");
  await expect(page.getByTestId("nrt-day-2026-09-06")).not.toHaveAttribute("data-state", "UNAVAILABLE");
  // an unavailable day stays visible, is never a frame, and says what is missing
  const gap = page.getByTestId("nrt-day-2026-09-02");
  await expect(gap).toHaveAttribute("data-state", "UNAVAILABLE");
  await expect(gap).toHaveAttribute("aria-disabled", "true");
  await expect(gap).toHaveAttribute("title", /currents_nrt/);
});

test("choosing another day re-renders that day's field, and cannot be faked for an unavailable day", async ({
  page,
}) => {
  const q = await (await page.request.get("/api/latest/qualification")).json();
  const cached = await cachedPayload(page);
  const dates = ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03",
                 "2026-09-04", "2026-09-05", "2026-09-06"];
  const asked: string[] = [];
  await page.route("**/api/latest/available-dates**", (r) =>
    r.fulfill({ json: windowFixture("2026-09-06", dates),
                headers: { "content-type": "application/json" } }));
  await page.route("**/api/latest/qualified?*", async (route) => {
    const date = new URL(route.request().url()).searchParams.get("date")!;
    asked.push(date);
    await route.fulfill({
      json: { ...cached, state: "QUALIFIED_STATE_FOR_DATE", label: null,
              selected_date: date, effective_date: date, is_newest: false,
              newest_qualified_date: "2026-09-06", live_attempt: null,
              field: { ...cached.field, date } },
      headers: { "content-type": "application/json" },
    });
  });
  await serveLive(page, { ...cached, state: "LATEST_QUALIFIED", label: null,
                          selected_date: "2026-09-06", effective_date: "2026-09-06",
                          is_newest: true, newest_qualified_date: "2026-09-06",
                          live_attempt: null,
                          field: { ...cached.field, date: "2026-09-06" } });
  await openLatestState(page);
  await expect(page.getByTestId("effective-date")).toContainText("2026-09-06");

  await page.getByTestId("nrt-day-2026-09-04").click();
  await expect(page.getByTestId("effective-date")).toContainText("2026-09-04");
  // A qualified older state must never read as "Unavailable" (live UI defect,
  // found 2026-09-12): the state tile has a label for every served state.
  await expect(page.getByTestId("latest-state")).toContainText(
    "Qualified state for this date",
  );
  await expect(page.getByTestId("latest-state")).not.toContainText("Unavailable");
  await expect(page.getByTestId("effective-date")).toContainText("not the newest state");
  await expect(page.getByTestId("newest-qualified-state")).toContainText("2026-09-06");
  await expect(page.getByTestId("nrt-day-2026-09-04")).toHaveAttribute("data-state", "SELECTED");
  // the shared renderer and profile still draw the selected day
  await expect(page.getByTestId("field-map")).toBeVisible();
  // the profile lives in the same collapsible panel as in Historical Replay
  await expect(page.getByTestId("profile-table")).toHaveCount(1);
  await page.getByRole("button", { name: "3D depth" }).click();
  await expect(page.getByTestId("depth-renderer")).toBeVisible();

  // an unavailable day never triggers a request, so no inference can happen
  await page.getByTestId("nrt-day-2026-09-02").click({ force: true }).catch(() => {});
  expect(asked).not.toContain("2026-09-02");
  // lag and the non-"now" wording remain for the selected day
  await expect(page.getByTestId("timeliness-note")).toContainText("reconstruction lag");
  // "not the ocean now" is the required disclaimer; what must never appear is
  // the affirmative claim. Every occurrence has to be negated.
  const body = await page.locator("body").innerText();
  expect(body).not.toContain("Live Ocean Right Now");
  const claims = [...body.matchAll(/.{0,16}ocean\s+now/gi)].map((m) => m[0]);
  for (const c of claims) expect(c).toMatch(/\b(not|never)\b/i);
  await page.locator("main").screenshot({ path: "../outputs/phase8b/recent-states.png" });
});
