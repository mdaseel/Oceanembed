import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 90000,
  expect: { timeout: 20000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "../outputs/phase7b/browser-tests.json" }],
  ],
  use: {
    // Defaults to the documented port; overridable so a verification server can
    // run alongside an app the developer already has open on 8000.
    baseURL: process.env.OCEANEMBED_BASE_URL ?? "http://127.0.0.1:8000",
    channel: "msedge",
    headless: true,
    viewport: { width: 1440, height: 1050 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
