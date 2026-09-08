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
    baseURL: "http://127.0.0.1:8000",
    channel: "msedge",
    headless: true,
    viewport: { width: 1440, height: 1050 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
