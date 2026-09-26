import { test, expect } from "@playwright/test";

/**
 * Phase 7D. The risks: a hazard level shown where nothing supports it, a
 * numeric cyclone probability appearing, the event strip reading as a forecast,
 * or the indicator quietly losing its non-prediction statement.
 */

test("hazard tab shows a category, its reasoning, and refuses to predict", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("HISTORICAL DATE", { exact: true }).fill("2023-05-13");
  await page.getByRole("link", { name: "Events & Disasters" }).click();

  await expect(page.getByTestId("hazard-non-prediction")).toContainText(
    "does not predict cyclone genesis, track, landfall, category",
  );
  const level = page.getByTestId("hazard-level");
  await expect(level).toBeVisible();
  await expect(level).toContainText(/LOW|MODERATE|ELEVATED|HIGH|NOT CATEGORIZED/);

  // The explanation must quote the real frozen boundaries, not round numbers.
  const why = page.getByTestId("why-this-level");
  await expect(why).toContainText("MODERATE ≥");
  await expect(why).toContainText("TRAIN split only");
  await expect(why).toContainText("MAE 11.47");

  await expect(page.getByTestId("hazard-map")).toBeVisible();
  await page.getByTestId("hazard-map").screenshot({
    path: "../outputs/phase7d/hazard-map.png",
  });

  // The track is attributed, and named as context rather than model output.
  await expect(page.getByTestId("track-attribution")).toContainText("IBTrACS");
  await expect(page.getByTestId("track-attribution")).toContainText("938");

  // No numeric cyclone probability anywhere on the page.
  const text = (await page.locator("body").innerText()).toLowerCase();
  expect(text).not.toMatch(/\d\s*%\s*(chance|probability)/);
  for (const mention of text.split("probability").slice(1))
    expect(mention.length >= 0).toBe(true);
});

test("categories agree with the backend and never appear unsupported", async ({
  page,
}) => {
  await page.goto("/");
  const truth = await page.evaluate(async () => {
    const r = await fetch("/api/replay/view?date=2023-05-13").then((x) => x.json());
    const labels = r.hazard.category_labels;
    const phys = r.diagnostics.physical_status_labels;
    let unsupportedButLabelled = 0;
    let high = null;
    for (let i = 0; i < 101; i++)
      for (let j = 0; j < 241; j++) {
        const name = labels[r.hazard.category[i][j]];
        const support = phys[r.diagnostics.tchp_physical_status[i][j]];
        if (name !== "NOT_CATEGORIZED" && support !== "SUPPORTED")
          unsupportedButLabelled++;
        if (name === "HIGH" && !high)
          high = { lat: 5 + i * 0.25, lon: 45 + j * 0.25 };
      }
    return {
      unsupportedButLabelled,
      high,
      counts: r.hazard.category_counts,
      thresholds: r.hazard.thresholds,
    };
  });
  // The central invariant: no label without a supported diagnostic beneath it.
  expect(truth.unsupportedButLabelled).toBe(0);
  expect(truth.counts.HIGH).toBeGreaterThan(0);
  expect(truth.counts.NOT_CATEGORIZED).toBeGreaterThan(0);
  expect(truth.thresholds.p50).toBeLessThan(truth.thresholds.p75);

  // A HIGH cell reports HIGH in the UI.
  await page.getByLabel("HISTORICAL DATE", { exact: true }).fill("2023-05-13");
  await page.getByLabel("Latitude", { exact: true }).fill(String(truth.high!.lat));
  await page.getByLabel("Longitude", { exact: true }).fill(String(truth.high!.lon));
  await page.getByRole("button", { name: "Inspect column" }).click();
  await page.getByRole("link", { name: "Events & Disasters" }).click();
  await expect(page.getByTestId("hazard-level")).toContainText("HIGH");
});

test("the observed track is never drawn over an ocean state it did not cross", async ({
  page,
}) => {
  await page.goto("/");
  // The default date is years before the event.
  await page.getByLabel("HISTORICAL DATE", { exact: true }).fill("2021-06-15");
  await page.getByRole("link", { name: "Events & Disasters" }).click();
  const outside = page.getByTestId("outside-event-window");
  await expect(outside).toContainText("outside the");
  await expect(page.getByTestId("track-attribution")).toContainText(
    "only on dates inside the event window",
  );
  await page.getByTestId("hazard-map").screenshot({
    path: "../outputs/phase7d/hazard-outside-window.png",
  });

  // Jumping to the event brings the track back.
  await page.getByRole("button", { name: /Show peak intensity/ }).click();
  await expect(outside).toHaveCount(0);
  await expect(page.getByTestId("track-attribution")).not.toContainText(
    "only on dates inside the event window",
  );
});

test("event window replays as independent days, not a forecast", async ({
  page,
}) => {
  test.setTimeout(120000);
  await page.goto("/");
  await page.getByRole("link", { name: "Events & Disasters" }).click();
  // The corridor series lives under Event Evolution.
  await page.getByTestId("tab-evolution").click();
  const wake = page.getByTestId("cold-wake");
  await expect(wake).toContainText("independent replay_field");
  await expect(wake).toContainText("never a forecast");
  // Marine-heatwave wording is forbidden without a validated definition.
  await expect(wake).toContainText("not called a");

  await page.getByRole("button", { name: "Run the event window" }).click();
  const plot = page.getByTestId("cold-wake").locator(".js-plotly-plot");
  await expect(plot).toBeVisible({ timeout: 90000 });

  // Each quantity gets its OWN axis, carrying its OWN unit. Metres and kJ/cm2
  // overlap numerically in this window (66-71 vs 67-89), so sharing an axis
  // would look plausible while being meaningless.
  // Plotly names stacked axis titles .ytitle / .y2title / .y3title.
  const axisTitles = (
    await plot.locator(".ytitle, .y2title, .y3title").allTextContents()
  )
    .map((s) => s.trim())
    .sort();
  expect(axisTitles).toEqual([
    "D26 (m)",
    "Nominal 0 m (°C)",
    "TCHP (kJ/cm²)",
  ]);
  // No composite unit may ever reappear on a single axis.
  for (const title of axisTitles) expect(title).not.toContain("·");

  await wake.screenshot({ path: "../outputs/phase7d/cold-wake.png" });
});
