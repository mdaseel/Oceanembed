import { test, expect } from "@playwright/test";

/**
 * Phase 7C corrective pass. The risk: the 2D map painting temperature over a
 * shelf at 1000 m, where there is no water. The footprint must contract with
 * depth in the 2D map exactly as it already does in the corrected 3D view.
 */

const DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000];

test("2D selected-depth footprint contracts with depth and names the unsupported class", async ({
  page,
}) => {
  let views = 0;
  page.on("request", (r) => {
    if (r.url().includes("/api/replay/view")) views++;
  });
  await page.goto("/");
  const map = page.getByTestId("field-map");
  await expect(map).toBeVisible();
  await expect(map).toHaveAttribute("data-bathymetry", "ready");
  await expect(page.getByTestId("map-depth-support")).toContainText(
    "neutral grey",
  );

  const counts: Record<number, number> = {};
  for (const metres of [0, 100, 300, 500, 700, 1000]) {
    await page
      .getByLabel("Depth", { exact: true })
      .selectOption(String(DEPTHS.indexOf(metres)));
    await expect(page.getByTestId("map-depth-support")).toContainText(
      `${metres} m`,
    );
    counts[metres] = Number(await map.getAttribute("data-supported-cells"));
    await map.screenshot({ path: `../outputs/phase7c/map-${metres}m.png` });
  }

  // Progressive contraction, and a real shelf loss between the surface and 1000 m.
  const order = [0, 100, 300, 500, 700, 1000];
  for (let i = 1; i < order.length; i++)
    expect(counts[order[i]]).toBeLessThanOrEqual(counts[order[i - 1]]);
  expect(counts[1000]).toBeLessThan(counts[0]);
  expect(counts[1000]).toBeGreaterThan(0);
  expect(Number(await map.getAttribute("data-unsupported-cells"))).toBeGreaterThan(0);

  // Changing depth must not trigger another model run.
  expect(views).toBe(1);
});

test("anomaly layer obeys the same physical depth support", async ({ page }) => {
  await page.goto("/");
  const map = page.getByTestId("field-map");
  await page.getByLabel("Depth", { exact: true }).selectOption(String(DEPTHS.indexOf(1000)));
  await page.getByLabel("Display layer").selectOption("temperature");
  const temperature = await map.getAttribute("data-supported-cells");
  await page.getByLabel("Display layer").selectOption("anomaly");
  await expect(map).toHaveAttribute("data-supported-cells", temperature!);
  expect(Number(await map.getAttribute("data-unsupported-cells"))).toBeGreaterThan(0);
});

test("D26 and TCHP separate a below-seafloor result from no 26 °C crossing", async ({
  page,
}) => {
  await page.goto("/");
  const truth = await page.evaluate(async () => {
    const r = await fetch("/api/replay/view?date=2021-06-15").then((x) => x.json());
    const labels = r.diagnostics.physical_status_labels;
    let unsupported = null,
      supported = null;
    for (let i = 0; i < 101; i++)
      for (let j = 0; j < 241; j++) {
        const name = labels[r.diagnostics.d26_physical_status[i][j]];
        if (name === "INSUFFICIENT_WATER_COLUMN_SUPPORT" && !unsupported)
          unsupported = {
            lat: 5 + i * 0.25,
            lon: 45 + j * 0.25,
            d26: r.diagnostics.d26_m[i][j],
            water: r.bathymetry.local_water_depth_m[i][j],
          };
        if (name === "SUPPORTED" && !supported)
          supported = { lat: 5 + i * 0.25, lon: 45 + j * 0.25 };
      }
    return { unsupported, supported, counts: r.diagnostics.physical_status_counts };
  });
  expect(truth.unsupported).not.toBeNull();
  // The raw Phase 7C value survives, and really is below the seafloor.
  expect(truth.unsupported!.d26).toBeGreaterThan(truth.unsupported!.water);

  await page.getByLabel("Display layer").selectOption("d26");
  await expect(page.getByTestId("diagnostic-note")).toContainText(
    "below the local ETOPO seafloor",
  );
  await page.getByTestId("diagnostic-map").screenshot({
    path: "../outputs/phase7c/ui-d26-qualified.png",
  });
  await page.getByLabel("Display layer").selectOption("tchp");
  await page.getByTestId("diagnostic-map").screenshot({
    path: "../outputs/phase7c/ui-tchp-qualified.png",
  });

  // A below-seafloor cell reports the reason, not a usable number.
  await page.getByLabel("Latitude", { exact: true }).fill(String(truth.unsupported!.lat));
  await page.getByLabel("Longitude", { exact: true }).fill(String(truth.unsupported!.lon));
  await page.getByRole("button", { name: "Inspect column" }).click();
  const tile = page.locator(".stat", { hasText: "D26 · 26 °C ISOTHERM DEPTH" });
  await expect(tile).toContainText("Below local seafloor");
  await expect(tile).toContainText("no water column");
});
