import { test, expect } from "@playwright/test";

/**
 * Phase 8A. The risks: a temperature or diagnostic appearing on a telemetry
 * tab; cached telemetry shown as fresh; the two clocks merged; and Historical
 * Replay going down because the live path did.
 *
 * The live provider is intercepted so these are deterministic and offline.
 */

const FRESH = {
  mode: "LATEST_INPUTS",
  phase: "8A",
  state: "ONLINE_CURRENT",
  generated_utc: "2026-09-10T19:30:24",
  is_cached: false,
  subsurface_reconstruction: "SUBSURFACE NRT RECONSTRUCTION NOT YET CERTIFIED",
  telemetry_banner: "NRT INPUT TELEMETRY AVAILABLE",
  why_these_inputs:
    "Controlled L2 channel ablation found clear incremental predictive value from SST near the surface and SLA through the thermocline. This does NOT mean those variables are physically unimportant.",
  scope_note:
    "Phase 8A is input telemetry only. The frozen L2 is not run on these inputs, no latest subsurface field is produced, and no latest D26, TCHP or hazard indicator is derived from them.",
  historical_note:
    "Historical Replay and historical Ocean Hazard Indicators are local capabilities and remain fully available regardless of this state.",
  sources: [
    {
      channel: "sst", product_key: "sst_nrt",
      product_id: "SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001",
      dataset_id: "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2",
      doi: "10.48670/moi-00165", provider: "Copernicus Marine",
      source_tier: "NRT", state: "OK",
      product_valid_time: "2026-09-09T00:00:00",
      local_retrieval_time: "2026-09-10T19:30:19",
      product_generated_time: null, data_age_hours: 43.5,
      nio_coverage_fraction: 0.499, nio_cells_valid: 299464,
      nio_cells_total: 600000, variables: ["analysed_sst"],
      error: null, notes: null,
    },
    {
      channel: "sla", product_key: "sla_nrt",
      product_id: "SEALEVEL_GLO_PHY_L4_NRT_008_046",
      dataset_id: "cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D",
      doi: "10.48670/moi-00149", provider: "Copernicus Marine",
      source_tier: "NRT", state: "OK",
      product_valid_time: "2026-09-10T00:00:00",
      local_retrieval_time: "2026-09-10T19:30:24",
      product_generated_time: null, data_age_hours: 19.5,
      nio_coverage_fraction: 0.507, nio_cells_valid: 48698,
      nio_cells_total: 96000, variables: ["sla"],
      error: null, notes: null,
    },
  ],
};

test("latest inputs reports telemetry and never a reconstruction", async ({ page }) => {
  await page.route("**/api/latest**", (r) =>
    r.fulfill({ json: FRESH, headers: { "content-type": "application/json" } }));
  await page.goto("/");
  await page.getByRole("link", { name: "Latest Inputs" }).click();

  await expect(page.getByTestId("not-certified")).toContainText(
    "SUBSURFACE NRT RECONSTRUCTION NOT YET CERTIFIED",
  );
  await expect(page.getByTestId("telemetry-state")).toContainText("ONLINE_CURRENT");
  await expect(page.getByTestId("telemetry-state")).toContainText(
    "Both requested sources retrieved",
  );
  // Retrieval is reported; inference fitness is not claimed.
  await expect(page.getByTestId("live-retrieval")).toContainText("LIVE RETRIEVAL");
  await expect(page.getByTestId("live-retrieval")).toContainText("Successful");
  await expect(page.getByTestId("live-retrieval")).toContainText("SST 43.5 h");
  await expect(page.getByTestId("coverage-note")).toContainText(
    "not an inference-readiness or ocean-only coverage metric",
  );
  await expect(page.getByTestId("credential-note")).toContainText(
    "authentication is delegated to the configured Copernicus Marine client",
  );

  // Both inputs, reported separately, with the two clocks kept apart.
  const rows = page.locator('[data-testid="source-table"] tbody tr');
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText("2026-09-09T00:00:00"); // valid time
  await expect(rows.nth(0)).toContainText("2026-09-10T19:30:19"); // retrieved at
  await expect(rows.nth(0)).toContainText("49.9%");
  await expect(rows.nth(0)).toContainText("NRT");
  await expect(rows.nth(1)).toContainText("SEALEVEL_GLO_PHY_L4_NRT_008_046");

  // Nothing on this tab may be a scientific field value.
  const body = (await page.locator("body").innerText());
  expect(body).not.toMatch(/\d+\.\d+\s*°C/);
  expect(body).not.toMatch(/kJ\/cm/);
  expect(body).not.toContain("Latest Qualified Ocean State");
  expect(body).not.toContain("FRESH TELEMETRY");
  expect(body).not.toContain("All sources current");
  await expect(page.getByTestId("not-produced")).toHaveText(
    "LATEST SUBSURFACE FIELD: NOT PRODUCED",
  );

  await page.getByRole("button", { name: "Why these inputs?" }).click();
  await expect(page.getByTestId("why-these-inputs")).toContainText("does NOT mean");

  await page.locator("main").screenshot({
    path: "../outputs/phase8a/latest-inputs-online.png",
  });
});

test("cached telemetry is labelled and never shown as fresh", async ({ page }) => {
  const cached = {
    ...FRESH,
    state: "CACHED_TELEMETRY_NOT_CURRENT",
    is_cached: true,
    cache_label: "LAST SUCCESSFUL TELEMETRY - NOT CURRENT",
    cached_generated_utc: "2026-09-09T06:00:00",
    cached_staleness_hours: 37.5,
    live_attempt_sources: [
      { ...FRESH.sources[0], state: "UNREACHABLE", error: "OSError: blocked" },
      { ...FRESH.sources[1], state: "UNREACHABLE", error: "OSError: blocked" },
    ],
  };
  await page.route("**/api/latest**", (r) =>
    r.fulfill({ json: cached, headers: { "content-type": "application/json" } }));
  await page.goto("/#latest");

  await expect(page.getByTestId("cache-label")).toContainText("NOT CURRENT");
  await expect(page.getByTestId("telemetry-state")).toContainText(
    "CACHED_TELEMETRY_NOT_CURRENT",
  );
  await expect(page.getByText("No — cached")).toBeVisible();
  // The failed live attempt is reported separately from the cached reading.
  await expect(page.getByTestId("live-attempt")).toContainText("UNREACHABLE");
  await page.locator("main").screenshot({
    path: "../outputs/phase8a/latest-inputs-cached.png",
  });
});

test("with no snapshot the unavailable state is informative, never blank", async ({
  page,
}) => {
  await page.route("**/api/latest**", (r) =>
    r.fulfill({
      json: {
        ...FRESH, state: "OFFLINE_OR_SOURCE_UNAVAILABLE", is_cached: false,
        sources: [], unavailable_label: "DATA SOURCE CURRENTLY UNAVAILABLE",
      },
      headers: { "content-type": "application/json" },
    }));
  await page.goto("/#latest");
  await expect(page.getByTestId("unavailable-label")).toContainText(
    "DATA SOURCE CURRENTLY UNAVAILABLE",
  );
  await expect(page.getByTestId("source-table")).toContainText("No telemetry yet");
});

test("historical replay does not go down when the live path does", async ({ page }) => {
  // Every latest-inputs call fails outright.
  await page.route("**/api/latest**", (r) => r.abort());
  await page.goto("/#latest");
  await expect(page.getByTestId("telemetry-error")).toBeVisible();
  await expect(page.getByTestId("historical-unaffected")).toContainText(
    "remain fully available",
  );

  // The offline science must still be fully usable in the same session.
  await page.getByRole("link", { name: "Historical Replay" }).click();
  await expect(page.getByTestId("field-map")).toBeVisible();
  await expect(page.locator(".stat").first()).toContainText("L2 TEMPERATURE");

  // And the hazard tab must remain historical, with no latest variant offered.
  await page.getByRole("link", { name: "Ocean Hazard Indicators" }).click();
  await expect(page.getByTestId("hazard-level")).toBeVisible();
  const body = await page.locator("body").innerText();
  expect(body).not.toContain("Latest Qualified Ocean State");
});
