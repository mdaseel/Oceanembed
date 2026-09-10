import { test, expect } from "@playwright/test";

/**
 * Phase 7C UI guards. The risk these target is a diagnostic map that renders a
 * plausible-looking number where the isotherm does not exist, or that shows a
 * value the backend never produced.
 */

test("D26 and TCHP render as their own map layers from real backend values", async ({
  page,
}) => {
  let views = 0;
  page.on("request", (r) => {
    if (r.url().includes("/api/replay/view")) views++;
  });
  await page.goto("/");
  await expect(page.getByTestId("field-map")).toBeVisible();

  // The authoritative values, read straight from the transport.
  const truth = await page.evaluate(async () => {
    const r = await fetch("/api/replay/view?date=2021-06-15").then((x) => x.json());
    const row = Math.round((15.25 - 5) / 0.25),
      col = Math.round((87.75 - 45) / 0.25);
    return {
      d26: r.diagnostics.d26_m[row][col] as number,
      tchp: r.diagnostics.tchp_kj_cm2[row][col] as number,
      counts: r.diagnostics.status_counts as Record<string, number>,
    };
  });
  expect(truth.d26).toBeGreaterThan(0);

  // What the stat tiles display must equal it, to the displayed precision.
  // Scoped to .stat: the same wording also appears as a dropdown option.
  const tile = page.locator(".stat", { hasText: "D26 · 26 °C ISOTHERM DEPTH" });
  await expect(tile).toBeVisible();
  await expect(tile).toContainText(truth.d26.toFixed(1));
  const heat = page.locator(".stat", { hasText: "TCHP · HEAT POTENTIAL" });
  await expect(heat).toContainText(truth.tchp.toFixed(1));

  // Baseline taken AFTER the verification fetch above, which is this test's
  // own request and not the app's.
  const beforeSwitching = views;
  for (const kind of ["d26", "tchp"] as const) {
    await page.getByLabel("Display layer").selectOption(kind);
    const map = page.getByTestId("diagnostic-map");
    await expect(map).toHaveAttribute("data-kind", kind);
    // The colorbar reports the ACTUAL displayed span, never a fixed range.
    await expect(page.getByTestId("diagnostic-colorbar")).toContainText(" to ");
    await expect(page.getByTestId("diagnostic-note")).toContainText(
      "no 26 °C crossing",
    );
    await map.screenshot({ path: `../outputs/phase7c/ui-${kind}.png` });
  }

  // The convention and its constants are disclosed, not hidden in code.
  await expect(page.getByTestId("diagnostic-note")).toContainText("TEOS-10");

  // Selecting a diagnostic must not trigger another inference: the diagnostics
  // came down with the field that was already fetched.
  expect(views).toBe(beforeSwitching);
});

test("a cell with no 26 °C crossing shows a reason, never a number", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Display layer").selectOption("d26");

  // Somali upwelling in June: the surface is below 26 °C, so D26 does not
  // exist there while TCHP is legitimately exactly zero.
  const cell = await page.evaluate(async () => {
    const r = await fetch("/api/replay/view?date=2021-06-15").then((x) => x.json());
    const labels = r.diagnostics.status_labels;
    for (let i = 0; i < 101; i++)
      for (let j = 0; j < 241; j++)
        if (labels[r.diagnostics.status[i][j]] === "SURFACE_BELOW_26")
          return {
            lat: 5 + i * 0.25,
            lon: 45 + j * 0.25,
            d26: r.diagnostics.d26_m[i][j],
            tchp: r.diagnostics.tchp_kj_cm2[i][j],
          };
    return null;
  });
  expect(cell).not.toBeNull();
  expect(cell!.d26).toBeNull();
  expect(cell!.tchp).toBe(0);

  await page.getByLabel("Latitude", { exact: true }).fill(String(cell!.lat));
  await page.getByLabel("Longitude", { exact: true }).fill(String(cell!.lon));
  await page.getByRole("button", { name: "Inspect column" }).click();

  const tile = page.locator(".stat", { hasText: "D26 · 26 °C ISOTHERM DEPTH" });
  await expect(tile).toContainText("No 26 °C crossing");
  // The one thing that must never happen: an undefined D26 shown as 0.
  await expect(tile).not.toContainText("0.0");
});

test("the 3D view says why it has no diagnostic stack instead of faking one", async ({
  page,
}) => {
  await page.goto("/#depth");
  await page.getByLabel("Display layer").selectOption("tchp");
  await expect(page.getByTestId("diagnostic-3d-note")).toContainText(
    "depth-integrated",
  );
  // The volume itself keeps showing a real depth-resolved layer.
  await expect(page.getByTestId("depth-renderer")).toBeVisible();
});
