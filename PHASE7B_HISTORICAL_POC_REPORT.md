# Phase 7B — Historical Proof of Concept

**OceanEmbed (SIH26066)** · INCOIS / Ministry of Earth Sciences · Theme: Disaster Management
Run 2026-09-08 · **501 tests passing** — 453 pytest, 44 Vitest, 4 Playwright
Scope: Historical Replay only. **No NRT tab, no NRT fetchers, no credentials, no network calls, no 2024 Argo.**

---

## 0. How this phase was worked, and what changed after the handoff

Phase 7B was started in a separate agent session (Codex) which built the
application skeleton and then hit its usage limit mid-verification. This session
audited that work, kept what was sound, and finished the phase. Two things the
handoff explicitly could not do were done here:

> *"No attached dashboard image was available."* — Codex's implementation plan

The team's reference dashboard was therefore never applied. It has now been,
and the visual identity is corrected (§2). The 3D view was also completed: it
previously rendered ocean only, floating in space with no land, which is the
second thing this session fixed (§3).

Everything inherited was re-verified from scratch, not taken on trust: all
suites were re-run, the 3D performance was re-measured after the geometry grew,
and one inherited test that my changes exposed as brittle was corrected (§6).

---

## 1. Architecture — no second inference path

```
replay_field(date)            ← Phase 7A, unchanged, the ONLY inference
   ↓  src/oceanembed/poc/app.py        (transport only)
GET /api/replay/view          ← one call returns temperature + climatology +
   ↓                            anomaly + masks + the seven surface inputs
web/src/field/replayAdapter   ← canonical field-view adapter (§7.0)
   ↓
FieldView  ──┬── MapView (2D canvas)
             ├── DepthRenderer (shared 3D, §7.0)
             ├── Profile (Plotly)
             └── Exports (CSV / PNG / NetCDF)
```

The frontend holds the complete 101×241×15 field in memory. **Changing depth,
layer, palette, clip range or the selected column issues no further request** —
verified by a Playwright test that counts `/api/replay/view` calls across a full
interaction sequence. That is possible because Phase 7A measured
`replay_field` at 0.116 s: one call per date is cheap enough to serve every view.

`src/oceanembed/replay/*` was **not modified**. The Phase 7A API router is
mounted unchanged at `/api`; the PoC adds `/api/replay/view`,
`/api/evidence`, `/api/evidence/document/{name}` and `/api/export/field.nc`
alongside it.

## 2. Visual identity — corrected against the reference

| | before this session | now |
|---|---|---|
| Ocean colormap | viridis (purple→green→yellow) | **thermal** — a `turbo` ramp, matching the reference and the convention operational SST products are read in |
| Ground | `#080f1d`, near-neutral | **`#070a10` — near-black** with a faint cool cast |
| Panels | flat grey-navy fill | barely-lifted `#0e131c → #090d14`, `#1b2430` hairline, cyan inset highlight |
| Sidebar / top bar | neutral | `#0a0e15 → #070a10`, cyan-tinted edge |
| Stat tiles | plain label + value | `#101720` body, icon, cyan top-edge glow, accent rule |
| Top bar | breadcrumb only | **coordinate / date quick-jump search**, matching the reference field |
| Map ground / land | `#0b1525` / neutral slate `#283547` | `#06080d` / neutral dark grey `#23272d`, matching the 3D view |

Two corrections were needed here, and the second reversed the first.

The first pass went near-black and neutral. On review I read "blue" in the
feedback as the target rather than the defect and re-based the whole palette onto
a saturated blue ramp (`#0a1729` ground, `#12263f` panels). That was wrong: the
reference is **black**, and the blue in it comes from the data, not the chrome.
The second pass took the ground back to `#070a10`, lifted the panels only enough
to separate them from it, and kept the cyan accent. The colour in the frame now
comes from the field.

On the colormap: `turbo` is a perceptually ordered rainbow designed as a
corrected replacement for `jet` — monotonic in lightness, no false banding. It
is a scientific colormap, not an arbitrary rainbow, and §5.1 permits the
`viridis`/`turbo` family. **`viridis` and `cividis` remain selectable in
Settings** for colour-vision accessibility, and the persisted preference is
respected. The anomaly layer always uses a diverging blue–white–red scale
centred at zero, regardless of palette — asserted by a test.

### The colour scale was the real defect behind "the water looks bad"

Every map and every 3D slice was calling `rangeFor(field, layer, [depth])` — the
range of the **displayed slice alone**. So each depth was auto-stretched across
the full colormap regardless of its actual temperatures. A 1000 m map at ~6 °C
and a surface map at ~30 °C rendered in the same colours, and a surface map,
whose real spread is only a few degrees, came out uniformly saturated. Two dates
were not comparable either.

The default is now `scaleMode: "field"`: **one scale spanning all 15 depths of
the requested date**. Warm surface water lands at the warm end of the ramp and
cold deep water at the cold end, so depths and dates are directly comparable —
visible in the 3D view as the depth stack reading orange at the top and blue at
1000 m, which under the old behaviour it could not.

Neither mode hardcodes a temperature range. Both are computed from the values
actually returned for that date; `fieldRange` is memoised per field object
because it reads all 15 depths. `actualMin` / `actualMax` / `count` continue to
describe **what is on screen**, so the colorbar still reports the displayed
data's own extremes ("6.09 to 32.45 °C" scale, "displayed data: 16.81 to
29.76 °C") and the map footer names which scale is in use.

The old per-slice behaviour is kept as an opt-in in Settings, labelled with what
it costs. Three tests pin this: that the default equals the whole-field range at
every depth while the reported extremes still track the slice; that the opt-in
mode demonstrably renders 0 m and 1000 m water in identical colours; and that a
uniformly warmed copy of the field shifts both ranges by the same amount, so
neither is a constant.

A caveat worth stating plainly: the reference image's ocean is predominantly
blue-cyan. That is mock content. Real North Indian Ocean water at 0–100 m in
June is 27–31 °C, which on an honest 6–32 °C scale is the warm end of any ramp.
Reproducing the mock's blue surface would require misrepresenting the scale, so
it was not done — the deep slices in the stack do read blue, correctly.

The reference's mock content was **not** reproduced: no Tsunami Risk, no Sea
Level Rise tile, no chlorophyll, no salinity output layer, no "Model 1 / Model 2",
no Model Training page, no Forecasting. Those are §5.4 exclusions and they stay
excluded.

## 3. The 3D depth view — now with land

Previously the renderer drew ocean cells only, so the volume was an unrecognisable
floating slab, and the selected layer was a flat sheet. Five changes:

**Land, raised and unpainted.** Cells where `ocean_mask === 0` are drawn as a
**constant-thickness slab** standing proud of the ocean surface, with side walls
only where land meets ocean and a lit coastline on top. India, Sri Lanka,
Lakshadweep, the Arabian peninsula and Southeast Asia read as solid raised
blocks rather than flat cut-outs.

It is deliberately **near-black, not tinted**. A green pass was tried against the
reference and rejected on review: a colour on land suggests land cover we have no
data for. All the form comes from **lighting** — the lit top face against the
unlit side walls — which is what makes the slab read as a block.

The land and coastline colours are declared in **linear** space
(`Color.setRGB(..., THREE.LinearSRGBColorSpace)`) rather than as sRGB hex
literals. The renderer outputs `LinearSRGBColorSpace` on purpose, so that the
`MeshBasicMaterial` ocean slices emit the colormap RGB byte-for-byte; a plain hex
literal is converted into that working space and comes out gamma-crushed toward
black, which is what a first attempt did.

**No relief, and this is a hard limit.** The reference image's land carries
surface texture. The model-ready store has only `ocean_mask` — a land/sea
boolean. There is no elevation, so none is invented: every land cell is exactly
as thick as every other, pinned by the two-distinct-heights test. Real relief
would require adding a topography source (GEBCO or ETOPO); that is a new dataset
dependency and a decision for the team, not something to fake.

Stated precisely, because the thickness could be misread: land comes from the
model-ready store's own `ocean_mask` ("the GLORYS target is defined at the
shallowest level"). The slab thickness is **identical for every land cell** — it
is a drawing device so the coastline reads in 3D, and it encodes **no
elevation**. The green cast is likewise fixed and encodes no land cover. Land is
**never** coloured by temperature. This is a land/sea distinction, **not a
topography or bathymetry product** — the same discipline applied to
`climatology_defined` in Phase 7A.

Three tests pin this. The decisive one asserts that across the entire landmass
there are **exactly two distinct heights** — the slab base and the slab top. If
any cell were ever extruded by its own elevation there would be more, so a
topography claim cannot sneak in later. The others assert the land geometry
carries no colour attribute at all, and that no temperature- or anomaly-coloured
cell ever falls on land.

**Volume.** The 14 non-selected levels changed from a sparse point cloud at 0.38
opacity — which read as noise — to translucent stacked slices. Same exact grid
values; nothing is interpolated between levels, and the gaps between them stay
honestly empty. The selected slice remains opaque and is the only pickable
surface.

**Every level has a body.** Levels previously rendered as sheets of paper. Each
now carries a downward **skirt** of constant depth, drawn only where a supported
cell borders an unsupported one — the coastline, the domain edge, or a data gap —
so the triangle count follows the perimeter, not the area. Each also carries a
line outline of the full domain rectangle, so every sheet shows the **identical
geographic footprint** even where few of its cells are supported.

The first attempt scaled the thickness to the depth axis alone, which on a
57-unit-wide basin came out under one percent of the frame and stayed invisible.

### The exploded stack

The bigger problem was that the true depth axis is unusable as a layout. Eleven
of the fifteen levels sit in the **top fifth** of 0–1000 m, so at true spacing
they overlap into a single band and only the deep levels are separable.

The stack is therefore **exploded**: `layerLayout` blends each level's true
height toward an evenly spaced slot, under a `separation` control. It shows four
to six sheets at a time (`visibleLevels`), chosen across the clip band with the
band ends anchored and the selected level always present; every level stays
reachable through the depth scrubber and the profile.

This trades a real property away, so it is disclosed rather than hidden:

- at `separation = 0` the layout is **exactly** the true-depth one — pinned by a
  test asserting bit-equality with `depthY`, not approximate equality;
- above 0 the view carries a standing notice that vertical spacing is **not to
  scale**, and a Playwright assertion requires that notice to be present by
  default and to disappear at 0;
- every sheet is labelled with **its own true depth in metres**, so depth is
  stated rather than inferred from height;
- the vertical profile, the CSV and the NetCDF export are untouched and use true
  depths;
- ordering is preserved at every separation — a test sweeps the control and
  asserts a deeper sheet never rises above a shallower one;
- exploding moves **height only**. A test asserts the plane's x and z vertex
  arrays and its colours are identical with and without the height override, so
  the footprint can never be stretched to fake depth. The lower
edge is drawn at 55% brightness of the cell's colormap colour; that is shading on
a vertical face, and the top face, which is the surface being read, keeps the
exact colormap value.

The skirt is a **separate mesh** from `selected-depth` specifically so the
click-picking arithmetic there stays exactly two triangles per grid cell, which
the Playwright selection test depends on. Two tests pin the skirt: that exactly
two distinct heights exist across the whole of it — so a warm cell is never drawn
thicker than a cold one and height carries no data — and that a field with a
single supported cell produces exactly four walls.

**No container prism, and a new camera.** An enclosing translucent box was
tried and then removed: it reads as an aquarium, implies base volume the data
does not have, and buries the vertical separation that is the point of the view.
Each sheet carries its own outline instead.

The white plumb line through the selected column was removed too. It was drawn
with depth testing off, so it painted over every sheet and over the land, and it
cut straight across the vertical separation the exploded view exists to show.
The selected column is still reported by the 2D map marker, the lat/lon fields
and the profile panel, none of which obstruct the stack. `selection` also left
the renderer's effect dependencies, so clicking a cell no longer rebuilds all
five sheets' geometry.

The default camera moved from `[16, 24, 34]` to `[37, 33, 57]`, targeting the
middle of the stack rather than the surface. The old view was close and nearly
edge-on, which hid the slab bodies completely and was a large part of why the
stack read as flat. `CAMERA` and `LAYER_GAP` are both exported from
`geometry.ts` and consumed by the renderer *and* the Playwright selection test,
so neither could silently break the click calibration.

**Form.** Ambient + key + rim lighting and scene fog so the land slab and the
stack read as surfaces. Lighting is presentation only: the ocean slices stay
`MeshBasicMaterial`, so their colours remain the exact colormap values and **no
shading term can alter a displayed temperature**. Only the land, which carries
no data, is lit.

### Renderer choice: three.js, not Cesium (§5.6.2 note 4 decision)

The master prompt required this decision to be made in 7B and recorded.

**Chosen: bundled `three.js` 0.185.1.** Reasons, in order of weight:

1. **Offline is non-negotiable and Cesium fights it.** Cesium's globe expects Ion
   imagery/terrain; running it with no token and bundled base imagery is possible
   but adds a tile pipeline and a much larger asset payload for a view that never
   leaves a 60°×25° box.
2. **Cesium's `VoxelPrimitive` is still an evolving API** and is built for
   continuous volumetric data. OceanEmbed's vertical axis is 15 discrete,
   non-uniformly spaced levels. A voxel renderer would have to interpolate
   between them to look right — which is precisely what §7.4 forbids. Discrete
   slices represent the data honestly.
3. **Measured performance is ample** — see below.

Cesium remains a reasonable choice if a later phase wants a true globe with
basemap context. Nothing in this implementation blocks that: the renderer sits
behind the §7.0 canonical field-view contract, so swapping the engine means
replacing one component, not the science.

### Measured performance (re-measured after the geometry grew)

| | |
|---|---|
| median frame rate | **142.7 fps** (samples 132 · 142.7 · 143.3 · 143.3 · 142.7) (re-measured after the exploded stack, per-sheet outlines and the camera change) |
| environment | Edge headless, viewport 1440×1050, canvas 734×470 |
| requirement | ≥ 30 fps |

~144 fps is the display's vsync ceiling, so the true headroom is larger. This was
re-measured after every geometry change — the land slab with side walls, the
coastline, a slab body and outline on every drawn sheet, and the wider camera
framing. Codex's original figure was not reused.

**Interactions verified in-browser:** orbit, right-drag pan, wheel zoom, depth
scrub across all 15 levels, vertical exaggeration, depth-range clipping, layer
toggle, column selection, camera reset.

**Graceful degradation:** with WebGL unavailable the renderer catches the
failure and renders the 2D map, depth controls, profile and both disclosures,
with a visible "3D view unavailable on this device" notice. Covered by a
Playwright test that blocks WebGL.

## 4. Requirements checklist (§7B.2)

| requirement | status |
|---|---|
| NIO map driven by `replay_field()` | ✅ |
| Historical date selector | ✅ + prev/next day |
| Required-depth selector | ✅ scrubber + dropdown, all 15 levels |
| Layer selector (reconstructed / anomaly) | ✅ |
| Click / select an ocean location | ✅ map click, 3D column click, lat/lon entry |
| Vertical profile with L0 climatology | ✅ both series plotted together |
| Surface input panel | ✅ all seven, with units and product names |
| Model / provenance panel | ✅ name, both hashes, latent, RF, params, `inference_source` |
| Nominal-0 m note visible | ✅ dedicated notice, from backend provenance |
| 3D Depth View (§7.0 reusable) | ✅ |
| Model Provenance & Validation page | ✅ real executed tables from `outputs/tables/` |
| Exports page | ✅ CSV / PNG / NetCDF of real outputs, with data credits |
| Settings page | ✅ palette, default date/location, prefer-2D |

**Deep-ocean skill disclosure** is a permanent notice that highlights when the
selected depth is ≥ 500 m. Deep L2 output is **never** suppressed or replaced by
climatology — Phase 7A's `test_deep_l2_output_is_not_suppressed` still guards
that, and the UI simply discloses the limitation.

**Not built** (correctly): the optional Embeddings view. It is marked optional in
§5.3 and adding it was not worth expanding scope while the theme and 3D were
still wrong. Recorded as a deferral, not an omission.

## 5. Default demo behaviour and offline operation

**Default: 2021-06-15, 15.25 °N, 87.75 °E.** Selection rule, recorded before use:
this is the Phase 7A test coordinate — a central Bay of Bengal point chosen for
**geography** (inside the PS's stated PoC region, well clear of the coast, all
seven inputs present), **not** by inspecting model error there. The date is a
mid-year validation-split day, likewise chosen without looking at error.

**On launch the app runs the real frozen model.** The initial request carries
`force_recompute=true`, so the demonstration is genuine local inference, not a
replayed artefact. A "Run frozen L2" button forces recomputation at any time and
the `inference_source` chip shows `LIVE_MODEL_RUN` or `VALIDATED_CACHE`
throughout.

**Offline verified two ways:**

1. Playwright with **all non-loopback requests aborted from before the first
   navigation** — the app loads, reconstructs, changes date, selects columns,
   and exports, with `externalRequests: []` and `pageErrors: []`
   (`outputs/phase7b/offline-verification.json`).
2. A live browser network log across a full session in this report's own
   verification: every request went to `127.0.0.1`. Zero external.

No Cesium Ion token, no CDN, no font fetch, no telemetry. Total shipped bundle
2.1 MB. Plotly's modebar is disabled everywhere, so its cloud-export links are
unreachable dead strings in the bundle rather than live affordances.

**No emergency fallback snapshot was shipped.** With uncached inference at
0.116 s there is nothing for it to protect against, and an unused fallback path
is a liability rather than a safety net.

## 6. Test results, and one inherited test I had to fix

| suite | tests | result |
|---|---|---|
| pytest (backend + all prior phases) | 453 | ✅ |
| Vitest (frontend units, contract, geometry) | 44 | ✅ |
| Playwright (browser end-to-end) | 4 | ✅ |
| **total** | **501** | ✅ |

Phase 7A's own 53 tests are inside the 453 and still pass unchanged, including
every frozen-hash guard.

### The brittle test

Changing the 3D default camera to frame the volume better broke
`3D orbit pan zoom clipping depth selection and frame rate`. The cause was worth
understanding rather than patching: the test built its **own** `PerspectiveCamera`
with the camera constants **re-typed by hand**, projected a world point into
screen space, clicked there, and asserted an exact hard-coded lat/lon came back.
Any camera tweak therefore looked like a science failure.

Two fixes, both structural:

1. The camera defaults now live in one exported constant, `CAMERA` in
   `web/src/field/geometry.ts`, consumed by both the renderer and the test. They
   cannot drift apart again.
2. Even sharing constants, the renderer's camera is driven by `OrbitControls`
   (spherical internals, damping, save/restore) while the test's is a plain
   camera, so they agree to about one grid cell. The assertion was rewritten to
   check the click landed **near** the intended column (±0.75°), and then to
   assert the thing that actually matters, exactly: **the profile displayed for
   whichever column was selected equals `/api/replay/point` for that same cell,
   to three decimals, at all 15 depths.**

The scientific assertion got stronger — it now validates whatever cell was
chosen rather than a pre-baked one — while the pixel-perfect coordinate
assertion, which tested the camera rather than the science, was dropped.

### Tests added this session

- land is a **constant-thickness slab**: exactly two distinct heights exist
  across the whole landmass, and it **carries no colour attribute**
- no temperature- or anomaly-coloured cell ever falls on land
- the coastline traces ocean cells that touch land, in whole segments
- `thermal` is the default ocean ramp, is cold-blue → warm-red, and the anomaly
  layer ignores the palette entirely
- the **default colour scale is the whole reconstruction, not the displayed
  slice**: it equals the whole-field range at every depth, while the reported
  extremes still track the slice on screen
- the opt-in per-slice mode is demonstrably **not comparable** — it renders 0 m
  and 1000 m water in identical colours
- **neither scale mode is hardcoded**: a uniformly warmed copy of the field
  shifts both ranges by exactly the same amount
- the selected slice's skirt has exactly **two distinct heights**, so a warm cell
  is never drawn thicker than a cold one and height carries no data
- a field with a single supported cell produces exactly four skirt walls
- **separation 0 is bit-identical to the true-depth layout**
- full separation spaces the sheets evenly, and **order is preserved at every
  separation in between**
- **exploding moves height only** — the plane's x/z vertices and colours are
  unchanged by the height override, so the footprint cannot be stretched
- every sheet outline is the **same footprint**, differing only in height, and
  carries no colour attribute
- the sheet selection always keeps the clip band's ends and the selected level
- a collapsed clip band degrades to that single level, not to an empty stack

### §7.0 reusability, verified

- the renderer drives a **synthetic in-memory field** with **no backend running**
  and no transport import — the test that proves Phase 8B can reuse it
- the adapter output validates against the canonical contract (shape 101×241×15,
  15 ordered depths, lat/lon lengths, masks, date)
- a source-level assertion that `DepthRenderer.tsx` contains no `fetch(`, no
  `replayAdapter`, no `field/api`, no `node:fs`, no `replay_field`, no
  `forward_from_z`

### §6 no-fabrication, verified

- transported `temperature`, `climatology` and `anomaly` arrays are
  `assert_array_equal` against `replay_field` — exact, not tolerance
- the displayed profile and CSV equal the selected field column at full precision
- API failure renders an explicit error state, never a sample reconstruction
- cells with a prediction but no L0 baseline keep the raw L2 value and show a
  missing anomaly

## 7. Frozen state

All frozen artifacts byte-identical: L2 checkpoint, L2 encoder, L1, both scalers,
L0 climatology. **2024 Argo untouched** — the PoC reads no Argo at all, and the
Validation page renders the existing 2022–2023 tables read-only from
`outputs/tables/`.

The Validation page labels the Argo comparison as an *external Argo
observational check*, notes that GLORYS assimilates in-situ observations so it is
not perfectly independent truth, and states that only surface inputs are used at
inference.

## 8. Judge-usability gate (§7B.6)

Walked end to end in a live browser. A person with no knowledge of the code can:
open OceanEmbed → choose a historical date → choose a depth → inspect the North
Indian Ocean map → click an ocean location → see the 15-depth reconstructed
profile → compare it with climatology → inspect the anomaly. **Gate passed.**

Screenshots: `outputs/phase7b/historical-desktop.png`, `depth-desktop.png`,
`validation.png`, `webgl-fallback.png`, `mobile.png`.

Launch: `Start-OceanEmbed.cmd`, or
`python scripts/poc/serve.py` (see `PHASE7B_README.md`).

## 9. Limitations and deviations

1. **Embeddings view not built** — optional in §5.3, deferred.
2. **Land is a land/sea mask, not topography.** From `ocean_mask` at 0.25°, so
   coastlines are blocky at grid resolution, and the slab thickness is constant
   and arbitrary. It is context, not cartography.
3. **The thermal default is a `turbo` sampling**, chosen to match the reference
   and operational SST convention. Accessible alternatives ship and are one
   click away in Settings.
4. **144 fps is vsync-capped**, so it is a floor on available headroom, not a
   measured ceiling.
5. **Cesium was evaluated and not adopted** for this phase — reasoning in §3, and
   the §7.0 contract keeps the door open.
6. **Phase 7B ran across two agent sessions.** Everything inherited was re-run
   and re-measured here rather than reported from the handoff.

---

# PHASE 7B GATE

```
Dashboard: WORKING
Historical Replay mode: WORKING
Map driven by replay_field(): YES
3D Depth View: WORKING
3D interactions (rotate/pan/zoom/depth-scrub): WORKING
3D renderer is source-agnostic and reusable (§7.0): YES
Canonical field-view adapter implemented: YES
2D fallback for 3D-unavailable devices: WORKING
Default path uses real frozen replay: YES (force_recompute on launch)
No fabricated data in UI (contract tests): PASS
Fallback snapshot exists and labelled: N/A (none shipped; uncached inference is 0.116 s)
0m tooltip visible: YES
Deep-ocean skill disclosure visible: YES
Judge-usability gate passed: YES
Frozen L2 preserved: YES
2024 Argo: PROTECTED
Tests passing: 501 / 501  (453 pytest · 44 Vitest · 4 Playwright)
```

**PHASE 7B COMPLETE — AWAITING REVIEW.**
**Do not proceed to the next phase until the user explicitly replies "CONTINUE".**
