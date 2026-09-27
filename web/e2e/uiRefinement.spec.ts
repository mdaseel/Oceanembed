import { expect, test } from "@playwright/test";

const shots = "../outputs/ui-refinement";
test("column panels fit their available space on desktop and narrow screens", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("field-map")).toBeVisible({ timeout: 90000 });
  await page.screenshot({ path: `${shots}/ocean-state.png` });
  await page.getByTestId("tray-tab-column").click();
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    const panel = page.getByTestId("vertical-structure");
    await panel.scrollIntoViewIfNeeded();
    await expect(panel).toBeVisible();
    const fits = await page.locator(".column-insight").evaluate((el) => {
      const box = el.getBoundingClientRect();
      return [...el.children].every((child) => {
        const b = child.getBoundingClientRect();
        return b.left >= box.left - 1 && b.right <= box.right + 1 && child.scrollWidth <= child.clientWidth + 1;
      });
    });
    expect(fits).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.getByTestId("analysis-tray").screenshot({ path: `${shots}/column-${width}.png` });
  }
});

test("source freshness and direct archived cyclone preview remain explicit", async ({ page }) => {
  test.setTimeout(180000);
  const cached = await (await page.request.get("/api/latest/qualified/cached", { timeout: 90000 })).json();
  expect(cached.field).toBeTruthy();
  await page.route("**/api/latest/prewarm", (r) => r.fulfill({ json: { started: false } }));
  await page.route("**/api/latest/qualified", (r) => r.fulfill({ json: cached }));
  await page.route("**/api/latest/available-dates**", (r) => r.fulfill({ json: {
    newest_qualified_date: cached.effective_date,
    days: [{ date: cached.effective_date, status: "AVAILABLE", is_newest: true, warm: "ready" }],
    per_product_newest: { currents_nrt: cached.effective_date, sst_nrt: "2026-09-26", sss_nrt_multiobs: "2026-09-21", sla_nrt: "2026-09-27", wind_nrt: "2026-09-25" },
  } }));
  await page.route("**/api/cyclones/current", (r) => r.fulfill({ json: {
    state: "NO_ACTIVE_NORTH_INDIAN_CYCLONE", provider: "GDACS", advisories: [],
    message: "No active North Indian Ocean cyclone reported by connected source (GDACS).",
  } }));
  await page.goto("/");
  await page.getByTestId("source-latest").click();
  await expect(page.getByTestId("source-date-currents_nrt")).toContainText("Limits the common date");
  await expect(page.getByTestId("preview-cyclone")).toBeVisible({ timeout: 90000 });
  await page.screenshot({ path: `${shots}/latest-source-dates.png` });
  await page.getByTestId("preview-cyclone").click();
  await expect(page.getByTestId("analysis-tray")).toHaveAttribute("data-active", "cyclone");
  await expect(page.getByTestId("test-event-banner")).toBeVisible({ timeout: 120000 });
  await expect(page.getByTestId("cyclone-analysis")).toHaveAttribute("data-test-event", "true");
  await expect(page.getByTestId("map-test-banner")).toContainText("not the latest qualified state");
  await page.getByTestId("cyclone-watch").screenshot({ path: `${shots}/archived-preview.png` });
});
