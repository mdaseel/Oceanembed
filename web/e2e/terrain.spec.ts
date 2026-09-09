import { test, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";

test("2D map loads local ETOPO relief with the scientific map intact", async ({ page }) => {
  await page.goto("/");
  const map = page.getByTestId("field-map");
  await expect(map).toHaveAttribute("data-relief", "ready");
  await map.screenshot({ path: "../outputs/phase7b/terrain/relief-map.png" });
  await expect(page.getByTestId("inference-source")).toHaveText("LIVE_MODEL_RUN");
});

test("real local DEM renders offline and terrain control leaves field requests and selection unchanged", async ({ page, context }) => {
  let fields = 0;
  const foreign: string[] = [];
  await context.route("**/*", route => {
    const url = new URL(route.request().url());
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) {
      foreign.push(url.href); return route.abort();
    }
    if (url.pathname.includes("/api/replay/view")) fields++;
    return route.continue();
  });
  await page.goto("/#depth");
  await expect(page.getByTestId("terrain-context")).toContainText("NOAA ETOPO 2022");
  const slider = page.getByRole("slider", { name: "Terrain relief exaggeration", exact: true });
  await expect(slider).toHaveValue("60");
  const lat = await page.getByLabel("Latitude", { exact: true }).inputValue();
  const lon = await page.getByLabel("Longitude", { exact: true }).inputValue();
  await slider.fill("110");
  await expect(page.getByTestId("terrain-context")).toContainText("110×");
  await slider.fill("60");
  await expect(page.getByLabel("Latitude", { exact: true })).toHaveValue(lat);
  await expect(page.getByLabel("Longitude", { exact: true })).toHaveValue(lon);
  const samples: number[] = [];
  for (let i = 0; i < 5; i++) {
    await page.waitForTimeout(1600);
    samples.push(parseFloat(await page.getByTestId("fps").innerText()));
  }
  expect(fields).toBe(1);
  expect(foreign).toEqual([]);
  const median = [...samples].sort((a,b) => a-b)[2];
  expect(median).toBeGreaterThanOrEqual(30);
  await page.getByTestId("depth-renderer").screenshot({ path: "../outputs/phase7b/terrain/default.png" });
  await page.screenshot({ path: "../outputs/phase7b/terrain/application.png", fullPage: true });
  await writeFile("../outputs/phase7b/terrain/performance.json", JSON.stringify({ samples, median, fieldRequests: fields, foreign }, null, 2));
});

test("missing DEM leaves ocean usable and never substitutes flat or invented terrain", async ({ page }) => {
  await page.route("**/assets/terrain/*", route => route.fulfill({ status: 404, body: "" }));
  await page.goto("/#depth");
  await expect(page.getByText("Terrain unavailable:", { exact: false })).toBeVisible();
  await expect(page.getByTestId("depth-canvas")).toBeVisible();
  await expect(page.getByTestId("terrain-context")).toHaveCount(0);
});
