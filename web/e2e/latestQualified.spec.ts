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
  return p;
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
  await page.goto("/");
  await page.getByRole("link", { name: q.tab_name }).click();

  await expect(page.getByTestId("qualification-banner")).toContainText(q.banner);
  await expect(page.getByTestId("qualification-banner")).toContainText(
    "QUALIFIED WITH LIMITATIONS",
  );
  await expect(page.getByTestId("d26-withheld")).toContainText("NOT QUALIFIED");
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
  await page.goto("/");
  await page.getByRole("link", { name: q.tab_name }).click();

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
  await page.locator("main").screenshot({ path: "../outputs/phase8b/latest-qualified.png" });
});

test("a failed live attempt shows the snapshot labelled NOT CURRENT", async ({ page }) => {
  const q = await (await page.request.get("/api/latest/qualification")).json();
  const cached = await cachedPayload(page);
  await serveLive(page, {
    ...cached,
    live_attempt: { attempted: true, reasons: ["L1: current_u not retrieved (UNREACHABLE)"] },
  });
  await page.goto("/");
  await page.getByRole("link", { name: q.tab_name }).click();
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
  await page.goto("/");
  await page.getByRole("link", { name: q.tab_name }).click();
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
