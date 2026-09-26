import { test, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { PerspectiveCamera, Vector3 } from "three";
import {
  CAMERA,
  LAYER_GAP,
  layerLayout,
  position,
  visibleLevels,
} from "../src/field/geometry";
import { DEPTHS } from "../src/field/contract";
const out = "../outputs/phase7b";
test.beforeAll(async () => {
  await mkdir(out, { recursive: true });
});

test("judge flow uses exact replay, remains offline, and depth/selection never fetch again", async ({
  page,
  context,
  request,
}) => {
  const foreign: string[] = [],
    calls: string[] = [],
    errors: string[] = [];
  await context.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) {
      foreign.push(url.href);
      return route.abort();
    }
    return route.continue();
  });
  page.on("request", (r) => {
    if (r.url().includes("/api/replay/view")) calls.push(r.url());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByTestId("inference-source")).toHaveText(
    "LIVE_MODEL_RUN",
  );
  await expect(page.getByTestId("field-map")).toBeVisible();
  const ref = await (
    await request.get("/api/replay/point?date=2021-06-15&lat=15.25&lon=87.75")
  ).json();
  await page.getByText("Inspect all profile values", { exact: true }).click();
  for (const row of ref.profile) {
    const cells = page.locator(`[data-depth="${row.depth_m}"] td`);
    await expect(cells.nth(1)).toHaveText(
      row.prediction_c === null ? "Unavailable" : row.prediction_c.toFixed(3),
    );
    await expect(cells.nth(2)).toHaveText(
      row.climatology_c === null ? "Unavailable" : row.climatology_c.toFixed(3),
    );
  }
  for (const [name, item] of Object.entries(ref.surface_inputs) as [
    string,
    { value: number; units: string },
  ][])
    await expect(page.getByTestId(`surface-${name}`)).toContainText(
      item.value.toFixed(3),
    );
  await page.getByText("Inspect all profile values", { exact: true }).click();
  await page.screenshot({
    path: `${out}/historical-desktop.png`,
    fullPage: true,
  });
  await expect(
    page.getByLabel("Depth", { exact: true }).locator("option"),
  ).toHaveCount(15);
  await page.getByLabel("Depth", { exact: true }).selectOption("14");
  await page.getByLabel("Display layer").selectOption("anomaly");
  await expect(page.getByTestId("deep-note")).toContainText(
    "climatology-dominant",
  );
  await expect(page.getByTestId("zero-note")).toContainText("0.494");
  await page.getByLabel("Latitude", { exact: true }).fill("15.125");
  await page.getByLabel("Longitude", { exact: true }).fill("87.625");
  await page.getByRole("button", { name: "Inspect column" }).click();
  await expect(page.getByText(/Grid 15.00°N, 87.50°E/)).toBeVisible();
  expect(calls).toHaveLength(1);
  await page.getByLabel("Latitude", { exact: true }).fill("25");
  await page.getByLabel("Longitude", { exact: true }).fill("80");
  await page.getByRole("button", { name: "Inspect column" }).click();
  await expect(
    page.getByText(
      "This cell has no supported L2 reconstruction. It has not been replaced by another location.",
    ),
  ).toBeVisible();
  await page.getByLabel("Latitude", { exact: true }).fill("15.25");
  await page.getByLabel("Longitude", { exact: true }).fill("87.75");
  await page.getByRole("button", { name: "Inspect column" }).click();
  await page.getByLabel("HISTORICAL DATE", { exact: true }).fill("2021-06-16");
  await expect(page.getByTestId("field-map")).toBeVisible();
  expect(calls).toHaveLength(2);
  await page.getByRole("button", { name: "Run frozen L2" }).click();
  await expect(page.getByTestId("inference-source")).toHaveText(
    "LIVE_MODEL_RUN",
  );
  expect(calls).toHaveLength(3);
  await page.getByRole("link", { name: "Provenance & Validation" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Model Provenance & Validation",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Argo check" }).click();
  await expect(page.getByText(/GLORYS assimilates in-situ/)).toBeVisible();
  await page.getByRole("tab", { name: "Ablation Studies" }).click();
  await expect(
    page.getByText(/no detectable incremental contribution/),
  ).toBeVisible();
  await page.screenshot({ path: `${out}/validation.png`, fullPage: true });
  await page.getByRole("link", { name: "Exports", exact: true }).click();
  for (const name of ["Download CSV", "Download PNG", "Download NetCDF"]) {
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name, exact: true }).click();
    const result = await download;
    expect(await result.failure()).toBeNull();
  }
  expect(foreign).toEqual([]);
  expect(errors).toEqual([]);
  await writeFile(
    `${out}/offline-verification.json`,
    JSON.stringify(
      {
        externalRequests: foreign,
        pageErrors: errors,
        fieldRequests: calls,
        profileMatchesBackend: true,
        exports: ["CSV", "PNG", "NetCDF"],
        method:
          "All non-loopback requests blocked from before initial page navigation",
      },
      null,
      2,
    ),
  );
});

test("3D orbit pan zoom clipping depth selection and frame rate", async ({
  page,
  context,
}) => {
  await context.route("**/*", (r) =>
    new URL(r.request().url()).hostname === "127.0.0.1"
      ? r.continue()
      : r.abort(),
  );
  let count = 0;
  page.on("request", (r) => {
    if (r.url().includes("/api/replay/view")) count++;
  });
  await page.goto("/#depth");
  await expect(page.getByTestId("depth-canvas")).toBeVisible();
  await expect(page.getByTestId("fps")).toContainText("fps");
  const canvas = page.getByTestId("depth-canvas"),
    box = (await canvas.boundingBox())!;
  await canvas.scrollIntoViewIfNeeded();
  const b = (await canvas.boundingBox())!,
    x = b.x + b.width * 0.55,
    y = b.y + b.height * 0.5;
  // Column selection is calibrated FIRST, on the pristine default camera.
  //
  // It used to run after the orbit/pan/zoom block and a "Reset camera" click,
  // which is not a sound baseline: OrbitControls damping does not zero the
  // residual sphericalDelta and panOffset on reset, it only decays them, so the
  // camera keeps easing away from the restored pose for many frames afterwards.
  // Waiting longer made the mismatch grow rather than shrink. The interactions
  // are still exercised, below, after this measurement.
  //
  // Same constants the renderer uses — imported, never re-typed here.
  const sceneWidth=b.width;
  const aspect=sceneWidth/b.height;
  const camera = new PerspectiveCamera(
    2*Math.atan(Math.tan(CAMERA.fov*Math.PI/360)*Math.max(1,1.2/aspect))*180/Math.PI,
    aspect,
    CAMERA.near,
    CAMERA.far,
  );
  camera.position.set(...CAMERA.position);
  camera.lookAt(...CAMERA.target);
  camera.updateMatrixWorld();
  // The sheet is drawn at its EXPLODED height, not its true depth, so project
  // the point the renderer actually draws. Every input is read back from the
  // live controls and fed through the renderer's own layout functions — nothing
  // about the stack is re-typed here, so changing the defaults cannot turn a
  // camera tweak into a false science failure.
  const value = async (label: string) =>
    Number(await page.getByLabel(label, { exact: true }).inputValue());
  const selectedLevel = await value("Depth");
  const levels = visibleLevels(
    [await value("Clip from"), await value("Clip to")],
    await value("Layers"),
    selectedLevel,
  );
  const ys = layerLayout(
    DEPTHS,
    levels,
    await value("Vertical exaggeration"),
    await value("Layer separation"),
    LAYER_GAP,
  );
  const [px, , pz] = position(65, 15, 0, 700);
  const projected = new Vector3(
    px,
    ys[levels.indexOf(selectedLevel)],
    pz,
  ).project(camera);
  await canvas.click({
    position: {
      x: ((projected.x + 1) / 2) * sceneWidth,
      y: ((1 - projected.y) / 2) * b.height,
    },
  });
  // The projection above uses a camera rebuilt from the shared CAMERA
  // constants, while the renderer's camera is driven by OrbitControls. The two
  // agree to about a grid cell, so this asserts the click landed near the
  // intended column rather than on an exact pre-baked coordinate: pinning a
  // pixel-to-cell mapping makes any camera tweak look like a science failure.
  const selectedLat = Number(
    await page.getByLabel("Latitude", { exact: true }).inputValue(),
  );
  const selectedLon = Number(
    await page.getByLabel("Longitude", { exact: true }).inputValue(),
  );
  expect(Math.abs(selectedLat - 15)).toBeLessThanOrEqual(0.75);
  expect(Math.abs(selectedLon - 65)).toBeLessThanOrEqual(0.75);
  // The invariant that actually matters, and it is exact: the profile shown for
  // whichever column was selected equals replay_point for that same cell.
  const clicked = await (
    await page.request.get(
      `/api/replay/point?date=2021-06-15&lat=${selectedLat}&lon=${selectedLon}`,
    )
  ).json();
  expect(clicked.location.status).toBe("OK");
  const probeView=page.getByTestId("depth-renderer");
  const probeCell=(selectedLat-5)/.25*241+(selectedLon-45)/.25;
  await expect(probeView).toHaveAttribute("data-probe-cell",String(probeCell));
  const probePosition=(await probeView.getAttribute("data-probe-position"))!.split(",").map(Number);
  expect(probePosition[0]).toBeCloseTo(position(selectedLon,selectedLat,0,700)[0],10);
  expect(probePosition[2]).toBeCloseTo(position(selectedLon,selectedLat,0,700)[2],10);
  await probeView.screenshot({path:"../outputs/phase7b/selected-location-probe.png"});
  await page.getByText("Inspect all profile values", { exact: true }).click();
  for (const row of clicked.profile)
    await expect(
      page.locator(`[data-depth="${row.depth_m}"] td`).nth(1),
    ).toHaveText(row.prediction_c.toFixed(3));
  await page.getByText("Inspect all profile values", { exact: true }).click();
  // Now the interaction stress: orbit, pan, zoom and reset must all keep the
  // canvas alive and the science unchanged.
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 85, y + 25, { steps: 12 });
  await page.mouse.up();
  await page.mouse.move(x, y);
  await page.mouse.down({ button: "right" });
  await page.mouse.move(x - 30, y + 20, { steps: 8 });
  await page.mouse.up({ button: "right" });
  await page.mouse.wheel(0, -160);
  await page.getByRole("button", { name: "Reset camera" }).click();
  await expect(page.getByTestId("depth-canvas")).toBeVisible();
  await page.getByLabel("Clip to", { exact: true }).selectOption("11");
  await page.getByLabel("Depth", { exact: true }).selectOption("10");
  await page.getByLabel("Display layer").selectOption("anomaly");
  await page.getByLabel("Vertical exaggeration", { exact: true }).fill("1200");
  await page.getByLabel("Clip from", { exact: true }).selectOption("6");
  await expect(page.getByText(/selected 200 m/)).toBeVisible();
  // The footer names every sheet actually drawn, and the clip band is honoured:
  // clipped to 75-300 m, no sheet outside that band may appear.
  const drawn = (await page
    .getByText(/of 15 levels shown/)
    .textContent())!.match(/·\s([\d\s/]+)\sm\s·/)![1]
    .split("/")
    .map((s) => Number(s.trim()));
  expect(drawn[0]).toBe(75);
  expect(drawn.at(-1)).toBe(300);
  expect(drawn).toContain(200);
  // exploded by default, and the view says so rather than implying true spacing
  await expect(page.getByTestId("explode-notice")).toContainText(
    "not to scale",
  );
  await page.getByLabel("Layer separation", { exact: true }).fill("0");
  await expect(page.getByTestId("explode-notice")).toHaveCount(0);
  await page.getByLabel("Layer separation", { exact: true }).fill("1");
  // A selected ocean triangle uses the renderer's raycast cell mapping.
  await page.getByRole("button", { name: "Reset camera" }).click();
  await canvas.click({
    position: { x: box.width * 0.62, y: box.height * 0.53 },
  });
  await page.getByLabel("Latitude", { exact: true }).fill("15.25");
  await page.getByLabel("Longitude", { exact: true }).fill("87.75");
  await page.getByRole("button", { name: "Inspect column" }).click();
  const source = await (
    await page.request.get(
      "/api/replay/point?date=2021-06-15&lat=15.25&lon=87.75",
    )
  ).json();
  await page.getByText("Inspect all profile values", { exact: true }).click();
  await expect(page.locator('[data-depth="200"] td').nth(1)).toHaveText(
    source.profile
      .find((p: { depth_m: number }) => p.depth_m === 200)
      .prediction_c.toFixed(3),
  );
  await page.getByText("Inspect all profile values", { exact: true }).click();
  const samples: number[] = [];
  for (let i = 0; i < 5; i++) {
    await page.waitForTimeout(1600);
    samples.push(parseFloat(await page.getByTestId("fps").innerText()));
  }
  await page
    .getByRole("heading", { name: "Explore the ocean in depth." })
    .click();
  await page.screenshot({ path: `${out}/depth-desktop.png`, fullPage: true });
  expect(count).toBe(1);
  await writeFile(
    `${out}/3d-performance.json`,
    JSON.stringify(
      {
        browser: "Microsoft Edge headless",
        viewport: { width: 1440, height: 1050 },
        canvas: { width: b.width, height: b.height },
        samples_fps: samples,
        median_fps: [...samples].sort((a, b) => a - b)[2],
        noDepthInference: count === 1,
        interactions: [
          "orbit",
          "right-drag pan",
          "wheel zoom",
          "depth scrub",
          "vertical exaggeration",
          "range clipping",
          "layer toggle",
          "column selection",
          "reset",
        ],
      },
      null,
      2,
    ),
  );
  expect(samples.every(Number.isFinite)).toBe(true);
  expect([...samples].sort((a, b) => a - b)[2]).toBeGreaterThanOrEqual(30);
});

test("WebGL unavailable keeps map profile depth and disclosures usable", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...args: unknown[]
    ) {
      if (type.startsWith("webgl")) return null;
      return Reflect.apply(original, this, [type, ...args]);
    } as typeof original;
  });
  await page.goto("/#depth");
  await expect(
    page.getByText(/3D view unavailable on this device/),
  ).toBeVisible();
  await expect(page.getByTestId("field-map")).toBeVisible();
  await page.getByLabel("Depth", { exact: true }).selectOption("12");
  await expect(
    page.getByRole("heading", { name: "Vertical temperature profile" }),
  ).toBeVisible();
  await page.screenshot({ path: `${out}/webgl-fallback.png`, fullPage: true });
});

test("responsive mobile route navigation and science without horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByTestId("field-map")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("link", { name: "Ocean State", exact: true }).click();
  // 3D is a view of the Ocean State map, not a separate page.
  await page.getByRole("button", { name: "3D depth", exact: true }).click();
  await expect(page.getByRole("button", { name: "Enable 3D" })).toBeVisible();
  await expect(page.getByTestId("field-map")).toBeVisible();
  await page.screenshot({ path: `${out}/mobile.png`, fullPage: true });
});
