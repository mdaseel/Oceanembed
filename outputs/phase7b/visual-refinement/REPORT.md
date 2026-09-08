# Phase 7B — focused 3D visual refinement

Only the existing 3D renderer, its camera/gap constants, and 3D-specific CSS were edited. The user's other UI changes were preserved.

## Appearance

| Setting | Before | After |
| --- | --- | --- |
| Camera position | (37, 33, 57) | (76, 49, 62) |
| Camera target | (0, -9, 0) | (0, -12, 0) |
| Vertical FOV | 43 degrees | 38 degrees; wider on narrow viewports to retain labels |
| Exploded sheet spacing | 4.6 scene units | 6 scene units |
| Constant sheet thickness | 0.598 | 0.75 |
| Clear gap / thickness | 6.69 | 7 |
| Default sheets | 5 | 5, same level-selection algorithm |
| Surface opacity | Selected-dependent | 1 |
| Lower top-face opacity | Selected-dependent, about 0.34–0.62 | 0.845 / 0.790 / 0.735 / 0.680 for the default stack |
| Slab sides | Same opacity as faces | 60% of face opacity |
| Coastline opacity | 0.85, cyan-white | 0.24, muted grey |
| Desktop canvas height | 470 px | 560 px (620 px at wide breakpoint) |

The camera now looks farther along longitude, so the long axis recedes. The default stack occupies approximately two-thirds of the canvas width and 70% of its height, with negative space around it. Each sheet retains the same geographic footprint. The land is an opaque, constant-height 0.975-unit extrusion of the existing land mask, with matte directional shading. There is no invented terrain or bathymetry.

The thermal faces retain MeshBasic materials and the existing vertex colors. Fog was removed so it cannot wash out the scientific colormap. No tone mapping is applied; output remains LinearSRGB. Land lighting uses neutral ambient 0.65, white directional key 2.1, and a subdued cool rim 0.35. Thin boundary walls provide translucent thickness; no solid enclosing box or interpolated volume was added.

Transparent sheets now draw from deepest to shallowest, independent of selection. Previously the selected sheet could render over shallower sheets. Depth labels are larger; frame lines are subdued. Reset flushes orbit momentum before restoring its saved pose. Canvas sizing and wrapping are scoped to 3D; optional mobile 3D now fits without horizontal overflow.

## Scientific and scope checks

- Longitude/latitude mapping, masks, actual values, color-scale computation, source depths, FieldView and API remain unchanged.
- `layerLayout` and `visibleLevels` are unchanged. Separation zero retains exact true-depth placement; positive separation retains the existing not-to-scale disclosure.
- Default levels remain 0 / 30 / 100 / 300 / 1000 m, selected 100 m; all 15 remain accessible.
- Picking remains two triangles per supported cell, using the selected sheet only. No picking tolerances or existing tests were changed.
- No 2D renderer, model, inference, frozen artifact, export, or NRT implementation was edited.
- Actual replay data drive the screenshots. Warm surface colors differ from the artistic reference because the existing temperature values and palette were preserved.

## Verification

- Baseline: 44 Vitest tests and the existing 3D Playwright test passed before editing.
- Production TypeScript/Vite build passed.
- 453 Python tests passed (7 existing deprecation warnings). The first sandboxed run had 11 temporary-fixture permission errors; the authorized rerun passed all 453.
- 44 Vitest tests passed.
- All 4 Playwright tests passed: replay/exports, 3D interactions and calibrated picking, unavailable-WebGL fallback, and mobile navigation.
- Browser 3D performance: latest median 143.3 fps in Microsoft Edge headless at 1440 × 1050, 734 × 560 canvas. This is a local measurement, not a hardware-independent guarantee. Raw samples are in `../3d-performance.json`.
- Additional screenshot check: orbit then Reset camera reproduced the default canvas byte-for-byte. `checks.json` records the result.
- Optional mobile 3D was explicitly enabled and visually checked at 390 × 844; canvas is 342 × 390 with no horizontal page overflow. The final narrower-screen lens keeps labels and footprint visible.

## Evidence

- `before.png`: actual default renderer before this refinement.
- `after.png`: actual revised default five-layer renderer.
- `reset.png`: the matching result after orbit and reset.
- `desktop.png`: full application view.
- `mobile.png`: final optional mobile 3D view.
- `DepthRenderer.before.tsx` and `geometry.before.ts`: focused pre-edit snapshots.

No Phase 8 work was performed.
