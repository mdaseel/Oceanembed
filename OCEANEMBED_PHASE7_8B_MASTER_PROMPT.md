# OceanEmbed — Phase 7 + 8A + 8B Master Build Prompt (Gated Execution)

**Project:** SIH26066 — OceanEmbed
**Organization:** INCOIS / Ministry of Earth Sciences · Theme: Disaster Management
**Project root:** `C:\sih2\`
**Repository:** `https://github.com/mdaseel/Oceanembed.git`

> This document supersedes
> `OCEANEMBED_PHASE7_8B_MASTER_PROMPT_OFFLINE_FIRST_FULL_NRT_QUALIFICATION.txt`.
> It preserves every scientific constraint, gate, and prohibition of that file
> **unchanged**, and adds:
> - **§5 UI / Visual Design Contract**, **§6 No Fabricated Data**, **§7 3D
>   Visualization Contract** — derived from the team's reference dashboard image.
> - **§8 Problem-statement alignment** — the official SIH26066 PS text has been
>   read; §8 maps each PS requirement to what is already built and confirms the
>   scope (temperature only; PoC over Bay of Bengal / Arabian Sea; Phases 7A–7E
>   satisfy the PS; 8A/8B are a team extension beyond it).
> - **§9 Work completed vs work remaining** and the confirmed **technology
>   stack** (§5.6) with binding conflict resolutions.
>
> Nothing in the reference image or the new sections relaxes any scientific
> scope limit. The image is a **style and layout reference only**; its numbers,
> labels, and several of its pages are mock content and must not be reproduced
> literally (§5.4). The reference image will be re-attached by the team to the
> session that runs Phase 7B.

---

## 0. Mandatory Gate Protocol — read before doing anything

This document contains the FULL gated roadmap: Phase 7A through Phase 8B.
Phase 8B is specified here but is **not** authorized merely because the
specification exists. It may begin ONLY after Phase 8A has completed, its report
has been reviewed, and the user explicitly authorizes continuation into 8B.

**You are NOT authorized to execute more than one phase per session.**

Execution order (strict, no reordering, no skipping):

```
PHASE 7A → PHASE 7B → PHASE 7C → PHASE 7D → PHASE 7E → PHASE 8A → PHASE 8B
```

At the END of every phase, and ONLY at the end, you must:

1. stop all work — do not begin the next phase's tasks
2. write that phase's required report file(s), in full
3. print that phase's required status block
4. print exactly:

   > PHASE [X] COMPLETE — AWAITING REVIEW.
   > Do not proceed to the next phase until the user explicitly replies "CONTINUE".

5. take no further action until the user's next message

You must NOT, under any circumstances:

- pre-build scaffolding for a later phase "to save time"
- create an empty/disabled UI tab for a mode that hasn't been authorized yet
- touch any NRT/live-fetch code, credentials, or network calls before Phase 8A is explicitly opened
- combine two phases into a single response
- infer that a later phase's requirements license doing that phase's work early
- execute Phase 8B before Phase 8A has completed and the user has explicitly authorized Phase 8B

If you are unsure which phase is currently authorized: **STOP and ask.** Do not guess forward.

---

## 1. Closed work — do not reopen (applies to ALL phases)

The model-research / architecture-selection phase is **CLOSED**. Phases 7 / 8A /
8B exist to build and qualify an application **around** the frozen model, not to
change the model.

**Final scientific core:** existing frozen **L2 Spatial Satellite Embedding Engine**.

| Artifact | Expected SHA256 |
|---|---|
| L2 state-dict | `b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d` |
| L2 encoder | `30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808` |

**Latest completed test baseline before Phase 7:** `384 passed`.

Architecture closure (all final, none reopened):

- **L0 climatology** → retained as baseline
- **L1 pointwise MLP** → retained as baseline
- **L2 spatial CNN** → **FINAL CORE**
- **L3 temporal GRU** → tested, **rejected**
- train-only EOF/PCA diagnostic → completed, **no EOF decoder adopted**
- climatology-residual L2 → tested, **rejected** (`RESIDUAL_REJECTED`)
- channel ablation / Experiment D → completed
- ViT / GNN / Transformer → **not justified before SIH**
- **2024 Argo** → **PROTECTED**, untouched

Before writing or modifying any code, inspect the repository and read:

- `ARCHITECTURE_CLOSURE_REPORT.md`
- `ARCHITECTURE_REVIEW.md`
- `outputs/architecture_closure/PREREGISTRATION.md`
- `PHASE6B_L2_REPORT.md`, `PHASE6B_L3_REPORT.md`
- `PHASE6C_ARGO_VALIDATION_REPORT.md`, `PHASE6C_FALLBACK_ARGO_REPORT.md`, `PHASE6C_NRT_COMPATIBILITY_REPORT.md`

Also inspect: the frozen L2 inference path (`src/oceanembed/ml/l2_model.py` —
`embed_field`, `forward_field`, `forward_from_z`), the L2 checkpoint
(`outputs/models/phase6b_l2_final.pt`), the L0 climatology
(`outputs/baselines/phase6b_climatology.nc` — `HarmonicClimatology.predict`),
the feature scaler (`phase6b_feature_scaler.json`), the target scaler
(`phase6b_target_scaler.json`), the model-ready Zarr stores
(`data/processed/model_ready/oceanembed_YYYY.zarr`), grid coordinates
(`src/oceanembed/grid.py`), validity masks (`surface_input_valid`, `ocean_mask`),
existing plotting utilities, existing API/frontend code (currently **none** —
`src/oceanembed/` has no `api`/`web`/`app` package and there is no
`package.json`), and existing tests (`tests/`).

**Repository artifacts and executed reports are source of truth.** If an old
roadmap conflicts with executed evidence, executed evidence wins. Do not infer
implementation details from this prompt where the repository can answer them
directly.

---

## 2. Global non-destructive contract (applies to ALL phases)

**IMMUTABLE — never modified, retrained, or refit in Phase 7, 8A, or 8B:**

frozen L2 checkpoint · frozen L2 encoder · L1 checkpoint · L0 climatology ·
feature scaler · target scaler · processed historical Zarr stores · existing
Argo outputs · existing NRT audit outputs · existing architecture-closure
artifacts · split definitions.

**NEVER, at any phase, without a separate explicit new approval:**

- retrain or fine-tune L2; change L2 input width, patch size, latent dimension, or decoder; add temporal history; rerun L3
- train a Transformer, ViT, GNN, EOF decoder, uncertainty head, or availability-aware model
- use the rejected `L2_RESIDUAL` model
- refit climatology or frozen scalers
- change historical product families
- download / open / collocate / score 2024 Argo
- apply quantile / CDF mapping to any input
- use zero-filled or mean-filled SSS as an approved fallback
- use climatology-substituted SSS as an approved fallback — **historical SSS persistence is the only currently observationally supported SSS fallback policy**
- physically delete, rename, corrupt, overwrite, or mutate any existing project data file for a testing purpose

New work must be **additive**. Suggested areas: `src/oceanembed/replay/`,
`src/oceanembed/diagnostics/`, `src/oceanembed/poc/`, `src/oceanembed/api/`,
`scripts/replay/`, `scripts/diagnostics/`, `scripts/poc/`, `outputs/phase7/`,
`outputs/phase8a/`, `outputs/tables/`, `outputs/figures/`, and a new frontend
directory (§5.6). Follow existing repository conventions where better paths
already exist.

---

## 3. Canonical historical input contract (applies to ALL phases)

Validated historical model inputs:

| Channel | Product |
|---|---|
| SST | OSTIA |
| SSS | MULTIOBS |
| SLA | DUACS |
| current U/V | OSCAR Final |
| wind U/V | CCMP v3.1 |

**Canonical processed stores:** `data/processed/model_ready/oceanembed_2015.zarr`
… `oceanembed_2024.zarr`.

**Domain:** 5°N–30°N, 45°E–105°E. **Grid:** 0.25°, **101 × 241**.

**Required output depths, exact order:**
`0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000 m`.

**Nominal 0 m convention:** nominal 0 m corresponds to the shallowest GLORYS
target level at ≈ 0.494 m. Do not silently change this. It is **not** simply a
copy of the OSTIA SST input — OSTIA SST is a surface satellite-derived analysis
used as one predictor; the model's nominal 0 m target is the shallowest GLORYS
subsurface temperature level. The quantities are related but must not be
described as identical or fully independent. **This note must be reachable from
every UI view that shows the 0 m value or the profile** (§5).

**Preserved evidence from prior phases — do not overwrite or contradict:**

- raw full NRT substitution stack was **not viable as-is** (`NRT_STACK_NOT_VIABLE_RAW`)
- SSS was the largest raw-stack problem
- historical SSS persistence was observationally supported
- SSS climatology substitution was **not** observationally supported
- currents **age** matters, not only product family
- NRT substitution approval means **sensitivity** approval, not observational NRT accuracy
- Experiment D found: **SST** — clear incremental predictive value near surface; **SLA** — strong incremental predictive value through the thermocline; **SSS / currents / winds** — no detectable incremental contribution above the measured run-to-run noise floor under that controlled retraining ablation. This does **not** mean those channels are physically useless, and it does **not** mean the frozen L2 can accept arbitrary values in those channels. Controlled retraining ablation and operational substitution are different experiments.

**Do not recursively load `data/raw/_extracted/`** — archive/provenance material only.
**CCMP remains the canonical historical wind product.**

---

## 4. Global jury-safe language (applies to ALL UI text and reports)

| Use | Not |
|---|---|
| Historical Replay | Historical Forecast |
| Latest Inputs / Operational Status (before 8B qualification) | Latest Qualified Ocean State |
| — | Live Ocean Right Now (never) |
| external Argo observational check | perfectly independent truth |
| SST and SLA showed clear incremental predictive value under the controlled L2 ablation | only SST/SLA physically matter |
| SSS persistence was supported under the historical Argo replay | stale SSS is always safe |
| 500–1000 m anomaly skill is weaker / more climatology-dominant | equal 0–1000 m accuracy |

`Latest Qualified Ocean State` is reserved for a Phase 8B result **only if** the
complete NRT subsurface reconstruction is successfully qualified.

Where a derived indicator has been transparently defined and validated, these
are acceptable: *"ocean thermal support for cyclone intensification"*,
*"cyclone-intensification-relevant ocean thermal conditions"*, *"ocean thermal
indicators that can support cyclone risk assessment"*. **OceanEmbed never claims
to forecast** cyclone genesis, track, landfall, category, wind speed, or exact
intensity evolution. OceanEmbed MAY support disaster decision-making by
reconstructing and deriving the oceanic thermal conditions that can favour or
limit cyclone intensification. Any categorical hazard indicator must remain an
explainable derived decision-support layer, not a claim that OceanEmbed predicts
the cyclone.

---

## 5. UI / Visual Design Contract *(new — applies to Phases 7B onward)*

The team supplied a dark-themed dashboard reference image ("OceanEmbed"). It is
the **visual identity and layout target**. Each card in that image represents a
**distinct page/route** in the real application — it is not one screen — and the
image also shows a **mobile / responsive** target. Do not build it as a single
crowded dashboard, and do not build it card-for-card: build the pages that
correspond to real, phase-authorized OceanEmbed capabilities (§5.3), styled to
match the reference.

### 5.1 Visual identity

- **Theme:** dark, deep-ocean. Background a near-black navy graduating to dark
  slate. Panels/cards: slightly lighter translucent slate, thin 1 px hairline
  borders, ~12 px corner radius, soft shadow / faint inner glow.
- **Accent:** cyan / teal for interactive elements, active navigation, links,
  focus rings.
- **Ocean temperature colormap:** a perceptually-ordered scientific colormap
  (e.g. `cmocean.thermal`, or a `viridis`/`turbo` family map) — **never an
  arbitrary rainbow**. The **anomaly** layer uses a **diverging** colormap
  (blue–white–red) centred at zero. Colorbars always visible, always labelled
  with units and the **actual** displayed min/max (never a fixed fake range).
- **Typography:** clean sans-serif (system UI / Inter). Numeric readouts use
  tabular figures.
- **Chrome:** collapsible left sidebar navigation; top bar with a
  location / coordinate / date search; subtle wave motif acceptable in
  header/footer.
- **Layout:** card-grid on wide screens where several summary panels share a
  page; each *page* is a route. Generous spacing, one clear primary action per
  panel.
- **States:** every panel MUST have explicit **loading**, **empty**, and
  **error** states. Never a blank box. Never filler numbers (§6).
- **Theme-aware:** dark is the primary theme. A light theme is optional; if
  shipped it must be fully consistent and switchable in Settings.
- **Accessibility:** sufficient contrast, keyboard-navigable controls, colormap
  choices that remain distinguishable for common colour-vision deficiencies,
  focus-visible styles.

### 5.2 Responsive / mobile

The image's "Mobile View (Unified Experience)" is a **responsive breakpoint of
the same application** — not a separate app, not a separate codebase. On narrow
viewports: single-column layout, bottom tab bar or hamburger navigation, the map
fills the width, the profile and stat tiles stack beneath it, the 3D view offers
its 2D fallback by default with an opt-in to the full 3D view. One app, one
build, responsive.

### 5.3 Page inventory — reference card → real OceanEmbed page

The reference image's sidebar (Overview, Explore, Model Training, Model
Comparison, Validation, Downloads, Settings; and Ocean Temperature, Wave &
Depth, Hazard Prediction, Forecasting) is a **design reference, not a literal
requirement**. Build these pages, gated by phase:

| Reference card / nav item | Real OceanEmbed page | First appears in | Notes |
|---|---|---|---|
| "North Indian Ocean — Corrected Ocean State" map; "Overview"; "Explore" | **Historical Replay — Map + Point** | 7B | Driven by `replay_field(date)`. Rename to **"Reconstructed Subsurface Temperature"**, not "Corrected Ocean State". Layer selector: *Reconstructed temperature* / *Anomaly from climatology* only. Surface inputs (incl. SSS) shown in a separate **input panel**, not as prediction layers. |
| "Model 2 — 3D Ocean & Depth Reconstruction / 3D Flythrough" | **3D Depth View** (a view mode of Historical Replay) | 7B | Interactive volume rendering of the same `replay_field` 101×241×15 array. See §7. Drop "Single-View Height Estimation" wording — there is no height estimation; it is subsurface temperature. |
| "Latest Ocean State — AI-processed, real-time" | **Latest Inputs / Operational Status** | **8A only** (telemetry) → **8B only if qualified** → "Latest Qualified Ocean State" | MUST NOT exist before Phase 8A. In 8A shows input telemetry only + explicit "SUBSURFACE NRT RECONSTRUCTION NOT YET CERTIFIED". |
| "Historical Replay (Model 1)" — date range, event selection, small multiples | **Historical Replay — multi-date** and **Event Replay** | 7B (multi-date), 7D (one event) | "Model 1" is **not a model** — it is the historical replay *mode* of the single frozen L2 core. |
| "Hazard Indicators (Model 2)" — Cyclone Risk / Heat Wave / Sea Level Rise / Tsunami Risk | **Ocean Hazard Indicators** | 7D (historical) → 8B (latest, only if qualified) | See §5.4 — Tsunami and Sea Level Rise are **removed**; "Cyclone Risk 76 kJ/cm²" is TCHP mislabelled and must be relabelled; "Heat Wave" only if a validated marine-heatwave definition is implemented. |
| "Diagnostics & Validation" — R²/RMSE/MAE/MAPE, accuracy chart, tabs | **Model Provenance & Validation** (read-only) | 7B | Shows the **real executed metrics** from `outputs/tables/` (Phase 6B/6C): per-depth RMSE in °C, skill vs L0, anomaly correlation, Argo validation, the frozen L2 hash, architecture-closure summary. Tabs: *Performance* (real per-depth table), *Ablation Studies* (real Experiment D results), *Error Analysis* (real bias/correlation by depth & basin), *Acceptability* (the executed gate decisions). No "MAPE", no "MAE 1.2 m", no invented "Model 1 vs Model 2" curves. |
| "Model Comparison" | part of **Model Provenance & Validation** — L0 vs L1 vs L2 by depth (real) | 7B | Not "Model 1 vs Model 2". |
| "Model Training" | **REMOVE.** The model is frozen; there is no training in the app. At most a read-only **"Architecture & Provenance"** page linking `ARCHITECTURE_CLOSURE_REPORT.md`. |
| "Downloads" | **Exports** — real NetCDF / CSV / PNG exports of actual `replay_field` / profile / diagnostic outputs | 7B | Never exports fabricated data. |
| "Wave & Depth", "Forecasting" | **REMOVE.** OceanEmbed does not do wave modelling and does not forecast — L3 (temporal) was tested and rejected; every date is an independent reconstruction. |
| "Settings" | **keep** — units, colormap, default date/location, theme, local data paths | 7B | |
| "Mobile View (Unified Experience)" | responsive breakpoints of the **same** app (§5.2) | 7B | |

Illustrative numbers and the event card in the image (e.g. "Cyclone — Bay of
Bengal, 2020-11-12, 120 km/h, 245,000 km²") are **mock content**. The real event
and its window are chosen in Phase 7D under `outputs/phase7/EVENT_SELECTION.md`
by an external criterion, and its metadata comes from the cited official track
source.

### 5.4 DO NOT replicate from the reference image

The following are placeholder or out-of-scope and must **not** appear:

- **Any hardcoded value** — SST 28.4 °C, Salinity 34.7 PSU, Thermocline 118 m,
  R² 0.92, RMSE 0.87, Cyclone Risk 76, MAE 1.2, MAPE 3.6 %, "SST 102 m",
  "Salinity 0.87/1.0", "Temp (Avg) 78 kJ/cm²", the Model-Accuracy-Comparison
  curve, the Error-Distribution curve, the Performance-Comparison table, the
  before/during/after thumbnails. Every value is computed live from the real
  pipeline for the selected date/location, or shown as loading / unavailable.
- **Tsunami Risk** — remove entirely. Tsunamis are a seismic hazard; OceanEmbed
  is a subsurface *temperature* reconstruction and has no basis to assess them.
- **Sea Level Rise** as a hazard tile — SLA is an *input*, not a derived
  OceanEmbed hazard; long-term sea-level rise is climate-scale. Drop unless a
  separately validated definition exists (none is authorized here).
- **Chlorophyll-a**, and **Bathymetry as a data/prediction layer** —
  chlorophyll is not an OceanEmbed output. Bathymetry may appear only as a
  static basemap context layer, never as a "prediction".
- **Salinity as an output/prediction layer** — SSS is one of the seven
  *inputs*; it is **not** one of the 15-depth reconstruction targets. Do not
  present a "predicted salinity" field or profile. (If the SIH26066 problem
  statement requires subsurface salinity reconstruction, that needs a separately
  trained and validated model and is **out of scope** for Phases 7–8B — see §8.)
- **"Model 1" / "Model 2"** as two trained networks — there is exactly **one**
  frozen scientific core (L2). L0 and L1 are baselines shown only in the
  validation page. Use *modes*: Historical Replay / Ocean Hazard Indicators /
  Latest Inputs.
- **"Model Training", "Forecasting", "Wave & Depth"** pages.
- **Banned / reserved wording**: "Live Ocean Right Now" (banned), "Corrected
  Ocean State" (misleading — it is a reconstruction), "Latest Qualified Ocean
  State" (reserved until Phase 8B passes), "Historical Forecast".
- **"Cyclone chance = NN%"** or any numeric cyclone probability — not authorized
  in any phase of this document.

### 5.5 No component ships with mock data

The reference image's content is **untrusted mock data**. No view may use its
numbers as a default, a fallback, or a "demo mode". The default/rest state of
every view is the deterministic default date/location (§ Phase 7B) actually run
through the real pipeline. See §6.

### 5.6 Frontend / backend technology stack

The team has chosen the stack below. It is compatible with the repository with
**four conflict resolutions** that are binding (§5.6.2). Do not introduce
Kubernetes, microservice sprawl, an authentication system, or any cloud
dependency required for the core demo.

#### 5.6.1 Confirmed stack

| Layer | Technology | Status in repo | Introduced in |
|---|---|---|---|
| Backend API | **FastAPI + Uvicorn** | not present | Phase 7A |
| Frontend | **React + TypeScript + Vite** | not present | Phase 7B |
| UI kit | **Tailwind + shadcn/ui** | not present | Phase 7B |
| Map + 3D | **CesiumJS** (see §5.6.2 note 4) | not present | Phase 7B |
| Charts | **Plotly** (`react-plotly.js`) | not present | Phase 7B |
| Frontend tests | **Vitest** | not present | Phase 7B |
| ML inference | **PyTorch** | present, frozen L2 | done |
| Numerical | **NumPy + SciPy** | present | done |
| Scientific data | **xarray** | present | done |
| NetCDF | **netCDF4 + h5netcdf** | present | done |
| Large arrays | **Zarr** | present | done |
| Tabular | **Pandas** | present | done |
| Geo overlays (coastline, tracks, basin polygons) | **GeoPandas + Shapely** | not present | Phase 7D (UI overlays only — see note 5) |
| Backend tests | **pytest** | present, 384 passing | done |
| Version control | **Git + GitHub** | present | done |

#### 5.6.2 Binding conflict resolutions

1. **Regridding: use `xarray.interp` — NOT xESMF.** The frozen preprocessing
   contract (Phase 6A.5, `src/oceanembed/preprocessing/regrid.py`) used
   `xarray.interp` (bilinear). Phase 6C-D deliberately kept the same function
   (`regrid_horizontal`) so NRT inputs stay bit-consistent with training.
   Switching to xESMF would change the frozen preprocessing contract and
   invalidate the frozen model. xESMF is **not** added.
2. **Cache: on-disk file cache + in-process memory cache — NOT Redis.** Redis is
   a server process and conflicts with the zero-infrastructure, offline-first,
   "runs on a laptop with no setup" requirement (§8A.4, §7B.4). The replay cache
   (§7A.2A) is a provenance-keyed local file store plus an in-process LRU. The
   repo already caches this way (`outputs/embeddings/`, `outputs/targets_cache/`).
3. **Database: SQLite only, and only if needed — NOT PostgreSQL.** A local
   PoC does not need a client-server database. If the replay/provenance cache
   index genuinely benefits from indexed queries, a single-file **SQLite** DB
   (Python stdlib, zero-config, offline) is acceptable. Otherwise keep the
   existing Parquet/JSON approach (`outputs/nrt/latency_log.parquet`, manifests).
   PostgreSQL is **not** introduced.
4. **CesiumJS must be configured for fully offline operation, and the
   volumetric depth view needs a decision recorded in Phase 7B.**
   - Cesium normally streams base imagery and terrain from Cesium Ion (cloud).
     For the offline demo: **no Ion token**, bundle a small local base-imagery
     source (e.g. a low-resolution Natural Earth / bathymetry raster via
     `SingleTileImageryProvider` or a bundled TMS tileset), and disable terrain
     streaming. The North Indian Ocean map view is well suited to Cesium's globe
     camera (rotate / pan / zoom for free) with this offline configuration.
   - For the **3D depth / volume reconstruction** (§7): Cesium's
     `VoxelPrimitive` is designed for gridded volumetric geospatial data and can
     render the 101×241×15 field with `scene.verticalExaggeration` for the depth
     axis; it is still an evolving API. In **Phase 7B**, evaluate Cesium
     `VoxelPrimitive` vs a small bundled `three.js` volume/ray-march renderer,
     pick whichever meets §7.2 interactions + §7.3 offline + ≥ 30 fps, and
     **document the choice and why** in `PHASE7B_HISTORICAL_POC_REPORT.md`.
     Prefer a single 3D engine if one clears the bar.
   - Cesium (~3 MB) and Plotly (~3 MB) are large. Fine for a local demo; lazy-
     load / code-split them so the initial app shell is light.
5. **scikit-learn: not currently used and not needed.** L0 (harmonic
   regression via NumPy `lstsq`) and L1 (a PyTorch MLP) are already trained and
   frozen. Add scikit-learn only if a specific Phase 7C diagnostic genuinely
   requires it, and say so in the report.
6. **GeoPandas + Shapely: UI overlays only.** Basin evaluation masks are the
   frozen lat/lon boxes in `src/oceanembed/ml/metrics.py` and
   `validation/argo_metrics.py` — **do not change them**. GeoPandas/Shapely may
   be used to draw coastlines, cyclone track lines (Phase 7D), and nicer basin
   *outlines* in the UI. Note the GDAL dependency chain; install via pip wheels.

Document the final choices and versions in each phase's report.

---

## 6. No Fabricated Data in the UI *(new — applies to Phases 7B onward)*

Every map pixel, chart point, stat tile, profile value, hazard label, diagnostic
number, and metric shown in the UI MUST trace to one of:

1. a real `replay_field(date)` / `replay_point(date, lat, lon)` output from the
   authoritative frozen-L2 pipeline (§ Phase 7A); or
2. a real executed diagnostic artifact (`outputs/tables/…`, `outputs/phase7/…`,
   `outputs/architecture_closure/…`); or
3. real input telemetry (Phase 8A onward), with provenance and age; or
4. a clearly-labelled `FALLBACK SNAPSHOT` / `LAST SUCCESSFUL QUALIFIED SNAPSHOT`
   that is itself a provenance-valid prior output of the exact pipeline.

Rules:

- No component ships with hardcoded sample numbers as its default or rest state.
- No `Math.random()`, no lorem filler, no "demo data" / "mock" module in the
  shipped build.
- A chart with no data shows an **empty state**, never a fake curve.
- Stat tiles show correctly-typed quantities with units (SST in °C, thermocline
  depth in m, D26 in m, TCHP in kJ/cm², SST anomaly in °C, …) for the **actual**
  selected cell — never a generic placeholder.
- The reference image is a style/layout reference; its content is untrusted.
- **Tests (per phase that adds UI):** for a known fixed date/location, assert the
  rendered numbers in each view equal the backend response (a contract /
  snapshot test); assert no shipped module exports static "sample" datasets;
  assert the map layer array equals the `replay_field` array for that date.

---

## 7. 3D Visualization Contract *(new — applies wherever 3D is shown)*

The reference image requires a **3D Ocean & Depth Reconstruction** with a
"flythrough". This is a **view of the authoritative field**, not a second
inference path.

### 7.0 Reusable 3D architecture contract

The 3D visualization implemented in **Phase 7B** MUST be built as a **reusable,
source-agnostic component**. It is the canonical 3D visualization subsystem for
the remainder of the application.

**Phase 7B owns the implementation**, including: volume / slice rendering;
camera controls; rotate / pan / zoom; depth scrub; depth-range clipping;
vertical exaggeration; temperature ↔ anomaly layer switching; colour scales and
colourbars; land and invalid-cell masking; column selection; profile
interaction; the 2D fallback; responsive behaviour; and flythrough / guided
camera behaviour if implemented.

**This renderer MUST NOT be rebuilt or independently reimplemented in Phase 8B.**

#### Canonical field-view contract

The renderer consumes a **canonical field-view object** containing, at minimum:

| field | notes |
|---|---|
| temperature field | 101 × 241 × 15 |
| anomaly field | where available |
| climatology field | where available (the profile panel shows L0 alongside L2) |
| latitude array | canonical 101 values |
| longitude array | canonical 241 values |
| depth levels | exactly the 15 mandated depths, in order |
| ocean / validity mask | drives land and invalid-cell rendering |
| field / effective date | the date or effective reconstruction time |
| operating-mode / provenance metadata | model hash, `inference_source`, and — in Phase 8B — source ages, qualification state, persisted-input status |

The scientific source of that contract depends on application mode:

```
Historical Replay (Phases 7B–7E)
    replay_field(date)
        → canonical field-view adapter
        → shared 3D renderer

Phase 8B — ONLY IF the latest operational mode is successfully qualified
    latest_qualified_field()
        → canonical field-view adapter
        → THE SAME shared 3D renderer
```

If `replay_field()` and `latest_qualified_field()` return different
transport/API schemas, **normalize them at the adapter boundary**. Do **not**
fork the renderer merely because the backend source differs.

#### What Phase 8B may and may not do

Phase 8B **may extend** the shared renderer only where genuinely required for
operational provenance / status display — e.g. effective latest reconstruction
time; per-source ages; qualification state; persisted-input status;
`LAST SUCCESSFUL QUALIFIED SNAPSHOT` labelling.

Phase 8B **must not duplicate** the visualization engine, shaders,
camera/controller logic, depth controls, colour logic, profile interaction, or
scientific field handling already validated in Phase 7B.

**Regression continuity:** all Phase 7B 3D regression tests MUST continue to
pass after any Phase 8B change. If Phase 8B reaches a qualified latest mode,
equivalent integrity tests must show that the shared renderer displays
`latest_qualified_field()` values **without changing their scientific meaning**.

### 7.1 Data source

The 3D renderer consumes an **authoritative OceanEmbed field**, never a separate
inference path. The renderer itself performs **no model inference**.

- Historical Replay (Phases 7B–7E): exactly `replay_field(date)`.
- Phase 8B latest-state view — **only if** the operational qualification gate
  passes: exactly `latest_qualified_field()`.

Both are normalized into the canonical field-view contract of §7.0 and rendered
by the **same** Phase-7B component.

Scientific constraints on the rendered field, in every mode:

- MUST NOT run its own inference.
- MUST NOT interpolate through land.
- MUST NOT extrapolate below the deepest valid level or below the seafloor.
- MUST NOT alter, smooth, rescale, or reinterpret the values it is given —
  display transforms (colour mapping, vertical exaggeration, display-only
  downsampling per §7.3) must never change the underlying scientific values
  reported for a profile or a point.

**Reuse requirement:** any later 3D view MUST use the existing Phase-7B shared
renderer. Do not create a second NRT/latest-state 3D implementation — only adapt
the new source into the canonical field-view contract defined in §7.0.

### 7.2 Required interactions

- **Orbit / rotate** — drag; full 360° azimuth; elevation clamped so the volume
  stays readable.
- **Pan** — right-drag or modifier-drag.
- **Zoom** — scroll / pinch, with sensible min/max limits.
- **Depth scrub** — a slider/handle that moves a horizontal slice plane through
  the 15 levels, showing the field at that depth. Snap to the 15 mandated
  levels; between levels either snap or use documented linear interpolation
  (state which in a tooltip).
- **Vertical exaggeration** — a z-scale control (the depth axis spans ~3000 m
  vs ~2000 km horizontally). Document the default.
- **Depth-range clip** — the image's "0 – 300 m" selector; clips the rendered
  volume to a depth band.
- **Layer toggle** — reconstructed temperature ↔ anomaly-from-climatology, with
  the matching colormap (§5.1).
- **Click a column** → the 15-depth profile for that (lat, lon), consistent with
  `replay_point` at the resolved cell.
- **Flythrough / guided tour** — an optional animated camera path. Must be
  pausable and must **not** be the only way to inspect the data.

### 7.3 Rendering / performance / offline

- Use the stack decided in §5.6.2 note 4 — **CesiumJS `VoxelPrimitive`** or a
  bundled **`three.js`** volume renderer, chosen in Phase 7B against §7.2 +
  offline + ≥ 30 fps and documented. Runs with **no internet**. No cloud
  rendering. No Cesium Ion token. No asset CDN required for core function.
- Target ≥ 30 fps on a typical laptop for the 101×241×15 grid. If the raw grid
  is too heavy for the volume renderer, downsample **for display only** (never
  for the profile / point values) and state so in a tooltip.
- **Graceful degradation:** if WebGL/3D is unavailable, fall back to the 2D map
  + depth slider + profile with a visible "3D view unavailable on this device"
  note. The full science must remain accessible without the 3D view.
- Land / invalid cells rendered as land (neutral), never as temperature.
- Colorbar always visible with units and the true displayed min/max.

### 7.4 Scientific honesty in 3D

- The 500–1000 m portion of the volume carries the same **deep-skill
  disclosure** as the 2D UI ("deep daily anomaly skill is weaker / more
  climatology-dominant; interpret L2 departures from climatology cautiously").
- Vertical axis labels reflect the true, non-uniformly spaced depths
  (`0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000 m`) —
  shown honestly, either true-to-scale under the exaggeration control or clearly
  labelled as a non-linear depth axis.
- The nominal-0 m note (§3) must be reachable from the 3D view.

### 7.5 Tests (add to the phase that first ships 3D — Phase 7B)

**Scientific integrity**

- 3D view consumes only `replay_field()` output — no second inference path.
- depth-slice values at a level equal the `replay_field` field at that level
  within documented tolerance.
- clicking a column yields the same 15-depth profile as `replay_point` at the
  resolved cell.
- land/invalid cells are not rendered as temperature.
- 3D unavailable → 2D fallback renders and the profile is still reachable.
- deep-skill disclosure present in the 3D view.

**Reusability (§7.0) — these are what make Phase 8B reuse possible**

- the renderer is **source-agnostic**: it renders correctly when driven by a
  synthetic in-memory field-view fixture, with **no backend running** and no
  import of any replay/transport module. This is the test that proves there is
  no hidden coupling to `replay_field`'s wire schema.
- the **adapter** converts a real `replay_field()` response into a canonical
  field-view object that validates against the §7.0 contract (shape 101×241×15,
  15 ordered depths, lat/lon lengths, mask present, date present).
- the renderer module exports no function that fetches, and performs no network
  or filesystem access.

These tests are **regression tests for the rest of the project**: Phase 8B must
keep them green.

---

## 8. Problem-statement alignment (SIH26066, INCOIS / Ministry of Earth Sciences)

The official problem statement text
(`SIH26066_exact.txt`; PS #01, SIH 2026; category Software; theme Disaster
Management) has been read in full. Title: *"OceanEmbed — Satellite
Embedding-Based Deep Learning Framework for Reconstruction of Subsurface Ocean
Temperature from Surface Satellite Observations."*

### 8.1 What the PS requires vs what the repository has built

| PS "the proposed system shall" | Status | Where |
|---|---|---|
| 1. Preprocessing & harmonization pipeline for multi-source satellite/ocean datasets | **DONE** | `src/oceanembed/preprocessing/`, `scripts/download/`, `scripts/preprocess/` → `data/processed/model_ready/oceanembed_YYYY.zarr` |
| 2. Standardize to 0.25° × 0.25°, daily | **DONE** | canonical 101×241 grid, daily; `PHASE6A5_REPORT.md` |
| 3. Inputs: SST, SSS, SSH/SLA, currents U/V, winds U/V | **DONE** | the seven frozen L2 channels |
| 4. Compact satellite embeddings via a DL architecture (CNN / ViT / autoencoder / GNN / attention hybrid — *"such as"*, examples) | **DONE — CNN selected after evaluating all listed families** | `ARCHITECTURE_REVIEW.md` (decision matrix: ViT / GNN / autoencoder all evaluated and **DEFER**red with reasons), `ARCHITECTURE_CLOSURE_REPORT.md`. L2 encoder → 32-dim latent per cell. |
| 5. Reconstruction model: surface ocean state → temperature profiles | **DONE** | L2 decoder, `src/oceanembed/ml/l2_model.py` |
| 6. Reconstruct temperature at the 15 standard depths (0…1000 m) | **DONE** | exact 15-depth list matches the PS |
| 7. Evaluate with independent observations + skill metrics (correlation, RMSE, bias, …) | **DONE** | Phase 6C-A: per-depth RMSE / bias / correlation / anomaly correlation vs Argo, float-clustered bootstrap CIs; `PHASE6C_ARGO_VALIDATION_REPORT.md` |

| PS "Expected Solution" | Status |
|---|---|
| End-to-end preprocessing pipeline | **DONE** |
| Satellite embedding engine (latent ocean representations from surface obs) | **DONE** (L2 encoder) |
| Deep-learning reconstruction model for subsurface temperature | **DONE** (L2 decoder) |
| Standardized output, daily, 0.25° | **DONE** (as a capability; the PoC exposes it) |
| Validation framework using independent ARGO observations | **DONE** (Phase 6C-A) |
| **Demonstration of a working PoC over the Bay of Bengal / Arabian Sea** | **← THIS IS WHAT PHASES 7A–7E BUILD** |

### 8.2 Scope boundary — what satisfies the PS, and what is beyond it

- **Phases 7A → 7E fully satisfy the problem statement.** 7E leaves a frozen,
  offline, jury-usable PoC over the Bay of Bengal / Arabian Sea with historical
  replay, the 15-depth reconstruction, D26/TCHP disaster-management diagnostics,
  one cyclone event replay, and the Argo validation surfaced in the UI — plus a
  pre-registered (unexecuted) 2024 Argo holdout evaluation.
- **Phases 8A and 8B (NRT / live inputs) are a team extension *beyond* the PS.**
  The PS says nothing about real-time or operational inference. 8A/8B are
  "above and beyond" work and must not delay or compromise the 7-series PoC.
  Prioritize 7A–7E for submission; treat 8A/8B as enhancement.
- The **2024 Argo holdout evaluation** is separate again and needs its own
  explicit approval (§ Phase 7E).

### 8.3 Temperature only — salinity confirmed out of scope

The PS title, the "shall reconstruct" list (item 6: *Temperature at standard
depth levels*), and the target dataset (*GLORYS … Variables: Temperature*) are
all **temperature only**. SSS is an **input**, not an output. The reference
image's "Salinity" layer stays removed (§5.4). No "predicted salinity" field or
profile appears anywhere in the UI.

### 8.4 Product choices — all PS-compliant

| Channel | PS recommends | Project uses | Compliant? |
|---|---|---|---|
| SST | OSTIA, `moi-00168` | OSTIA `moi-00168` | exact |
| SSS | "SMAP, SMOS 0.125° daily", DOI `moi-00051` | CMEMS MULTIOBS `cmems_obs-mob_glo_phy-sss_my_multi_P1D` (**DOI `moi-00051`** — SMAP+SMOS+in-situ blended) | **exact DOI**; the "SMAP, SMOS" label describes MULTIOBS's inputs |
| SSH / SLA | DUACS, `moi-00145` | DUACS `moi-00145` | exact |
| Currents | OSCAR_L4_OC_FINAL_V2.0 | OSCAR Final V2.0 | exact |
| Winds | **ASCATC-L2-Coastal** *or* **CCMP_WINDS_10M6HR_L4_V3.1** (both listed) | CCMP v3.1 | **compliant** — the PS lists CCMP explicitly; ASCAT-Coastal is L2 swath from 2019-10, unsuitable for the 2015–2024 daily-gridded window, and the PS's own clause ("select the openly available product and perform appropriate interpolation/regridding") covers this |
| Target | GLORYS, `moi-00021` | GLORYS12V1 `moi-00021` | exact |
| In-situ validation | "Gridded ARGO / INCOIS LAS – Gridded ARGO" | **individual** Argo profiles (Argo GDAC), per-profile QC, TEOS-10 potential-temperature, ocean-aware collocation, 2022–2023 | see §8.5 |

The **Model Provenance & Validation** page (§5.3) must surface this table and the
architecture decision matrix, so the jury sees every PS-listed option was
considered.

### 8.5 Argo — individual profiles vs INCOIS LAS gridded Argo

The PS recommends gridded Argo (INCOIS LAS). The project validated against
**individual QC'd Argo profiles**, which is the more rigorous choice — gridded
Argo is itself an interpolated reconstruction, so validating a reconstruction
against another reconstruction is weaker evidence. This is a **jury talking
point, not a gap**. *Optional, not required:* if INCOIS LAS gridded-Argo access
is available, a supplementary cross-check may be added as a secondary validation
panel, clearly labelled as against a gridded product; the individual-profile
validation remains primary. Do not open 2024 in either case.

### 8.6 "Using only surface satellite observations"

The PS twice stresses reconstruction from **surface observations only**. The
frozen pipeline already enforces this (no target leakage — Phase 7A.3). The
**Model Provenance & Validation** page must state visibly: *"Reconstruction uses
only surface satellite inputs at inference. GLORYS and Argo are used only for
training and validation, never at inference time."*

### 8.7 PoC region

The PS PoC is *"over the Bay of Bengal / Arabian Sea"*. Therefore: the Phase 7B
deterministic default demo location MUST be a valid ocean point in the Bay of
Bengal or the Arabian Sea, and the Phase 7D event MUST be a Bay of Bengal or
Arabian Sea cyclone / thermal-extreme event.

---

## 9. Work completed vs work remaining

### 9.1 Completed and frozen (Phases 6A–6C + architecture closure)

| Area | Artifact |
|---|---|
| Preprocessing / harmonization pipeline | `src/oceanembed/preprocessing/`, `scripts/download/`, `scripts/preprocess/`, `data/processed/model_ready/*.zarr` (10 years, 2015–2024) |
| L0 climatology (baseline) | `outputs/baselines/phase6b_climatology.nc` — frozen, hash-pinned |
| L1 pointwise MLP (baseline) | `outputs/models/phase6b_l1_mlp.pt` — frozen |
| **L2 Satellite Embedding Engine (FINAL CORE)** | `outputs/models/phase6b_l2_final.pt` — frozen, `sha256 b715bb2b…`; encoder `30cfd2db…` |
| Feature + target scalers | `outputs/baselines/phase6b_*_scaler.json` — frozen |
| Frozen-L2 inference path | `src/oceanembed/ml/l2_model.py` (`embed_field` → `forward_from_z`), `scripts/baselines/evaluate_l2.py`, `scripts/baselines/extract_embedding.py` |
| Grid-benchmark validation (2022–2024) | `outputs/tables/phase6b_l2_metrics_by_depth_test.csv` — L2 at 100 m: 1.19 °C RMSE, +33.5 % skill vs L0 |
| **Independent Argo validation (2022–2023)** | Phase 6C-A, `outputs/argo/`, `outputs/tables/phase6c_argo_*`, `PHASE6C_ARGO_VALIDATION_REPORT.md` |
| Architecture selection (CNN vs ViT / GNN / autoencoder / temporal / EOF / residual) | `ARCHITECTURE_REVIEW.md`, `ARCHITECTURE_CLOSURE_REPORT.md`, `outputs/architecture_closure/` |
| Input-availability / fallback study | Phase 6C-B, 6C-C, `PHASE6C_FALLBACK_ARGO_REPORT.md` |
| NRT product compatibility audit | Phase 6C-D, `PHASE6C_NRT_COMPATIBILITY_REPORT.md` (verdict: raw NRT stack **not viable as-is**) |
| Test suite | **384 passing** |
| 2024 Argo | **PROTECTED, never downloaded** |

**PS "Expected Solution" items 1–5 are done. Item 6 (the PoC) is what this
document builds.**

### 9.2 Remaining — this document

| Phase | Deliverable | Frontend/backend work | New Python deps |
|---|---|---|---|
| **7A** | `replay_field` / `replay_point` scientific backend + CLI + manifest + tests; uncached timing | **FastAPI + Uvicorn** service wrapping the frozen L2 path; optional **SQLite** cache index | `fastapi`, `uvicorn` (`sqlite3` is stdlib) |
| **7B** | Historical Replay PoC UI (map, depth selector, layers, click-profile, surface-input panel, provenance/validation page, 3D depth view, exports, settings) | **React + TS + Vite + Tailwind + shadcn/ui + CesiumJS + Plotly + Vitest**; Cesium offline config; Cesium-voxel-vs-three.js volume decision recorded | — (backend unchanged); frontend `package.json` |
| **7C** | D26 / TCHP diagnostics + pre-registered protocol + 3-stage discretization experiment + D26/TCHP map layers | diagnostics module `src/oceanembed/diagnostics/`; new map layers in the UI | possibly none (`gsw` already present) |
| **7D** | One Bay of Bengal / Arabian Sea cyclone event replay + **Ocean Hazard Indicators** tab + "Why this level?" explainability | event view + hazard tab; track overlay | **GeoPandas + Shapely** (UI overlays only) |
| **7E** | Freeze the PoC protocol + `FINAL_POC_MANIFEST.json` + **pre-register (do not run)** the 2024 Argo holdout evaluation + full test suite | version freeze | — |
| **8A** *(beyond PS)* | `Latest Inputs` telemetry tab (SST + SLA NRT), offline-first state machine, demo-resilience test | new tab; live-fetch reuse of `src/oceanembed/nrt/` | — (`copernicusmarine`, `earthaccess` already present) |
| **8B** *(beyond PS)* | Full seven-channel NRT qualification, hindcast-the-NRT, `Latest Qualified Ocean State` **iff qualified** | conditional latest-state tab + 3D | — |

### 9.3 Data prerequisites before Phase 7A

The following must be present locally (they are `.gitignore`d — obtain from the
team's shared drive, or regenerate with `scripts/download/` +
`scripts/preprocess/`):

- `data/processed/model_ready/oceanembed_2015.zarr … oceanembed_2024.zarr` (~4.7 GB)
- `outputs/baselines/phase6b_climatology.nc`, `phase6cb_surface_climatology.nc`
- `outputs/models/phase6b_l2_final.pt`, `phase6b_l1_mlp.pt`
- `outputs/baselines/phase6b_feature_scaler.json`, `phase6b_target_scaler.json`

`outputs/targets_cache/` and `outputs/embeddings/` are **not** required for
replay (they are training/L3 caches) and normal replay must not touch them
(Phase 7A.3).

---

# PHASE 7A — Historical Replay Backend Only

**Goal:** build the authoritative historical scientific inference backend.
**No UI. No NRT. No D26/TCHP. No event replay. No 2024 Argo.**

Conceptual pipeline:

```
historical date
  → canonical 101×241 historical surface fields
  → exact frozen preprocessing
  → frozen whole-field L2
  → 101×241×15 reconstruction
  → frozen L0 climatology
  → anomaly
  → field + point replay interfaces
```

### 7A.1 Final core manifest

Create if absent: `outputs/phase7/final_core_manifest.json`. Record: model name;
model class; checkpoint path; L2 state-dict SHA256; encoder SHA256;
receptive-field / patch info; latent width; the seven physical inputs; mask
semantics; the 15 target depths; feature scaler path/hash; target scaler
path/hash; L0 path/hash; architecture-closure report reference; final-core
decision; `2024 Argo status = PROTECTED`; nominal-0 m convention note;
processing/grid version used for replay. **Do not duplicate or rewrite the
checkpoint.**

### 7A.2 Authoritative full-field inference

The frozen L2 scientific inference primitive is **`replay_field(date)`**. It MUST
execute the **existing** whole-field frozen-L2 inference path over the canonical
101×241 grid (`L2EmbeddingModel.embed_field` → `forward_from_z`). **Do not create
a scientifically independent second implementation.**

`replay_field(date)` returns: the requested date; the full 101×241×15 frozen-L2
reconstruction; the full L0 climatology field at the 15 depths; the full anomaly
field (`anomaly = frozen_L2_prediction − frozen_L0_climatology`); surface-input
validity / ocean mask; latitude array; longitude array; model/hash/provenance
metadata. Final prediction is the **direct frozen-L2 absolute-temperature
output**. **Never use the rejected residual formulation.**

Then expose **`replay_point(date, lat, lon)`**, which MUST: (1) resolve lat/lon
to the canonical grid; (2) obtain the authoritative `replay_field(date)` result;
(3) sample the requested/resolved cell from THAT field result; (4) return the
15-depth profile and metadata. Do **not** implement point inference as an
independent neural path, and do **not** reconstruct `replay_field()` as thousands
of independent point calls unless inspection proves the existing frozen
implementation itself uses that exact strategy and exact equivalence is
demonstrated. Point/profile views derive from the authoritative field output.

`replay_point` returns: requested date; requested lat/lon; resolved grid
indices; resolved lat/lon; model name; checkpoint hash; encoder hash; the seven
surface input values at the resolved cell; surface product names; validity
status; 15 predicted temperatures; 15 L0 climatology temperatures; 15 anomalies;
metadata/provenance; nominal-0 m note.

**Field schema for the frontend and 3D renderer (§7):** document the actual
field response schema. It should be directly consumable by a 3D volume renderer
— prefer row-major typed arrays (or a compact binary form) plus `lat`, `lon`,
`depths`, and the mask, rather than nested per-cell JSON.

### 7A.2A Caching — performance only

Caching is allowed **only** as a performance optimization. A cache entry may
contain **only** an output previously produced by the actual frozen-L2 replay
pipeline. **Never cache** fabricated / manually-authored / placeholder /
hand-picked values. Cache identity must include at minimum: historical date;
frozen L2 checkpoint hash; processing/scaler version; canonical grid version. On
**cache miss**, real frozen-L2 inference is mandatory. On **valid cache hit**,
reuse is allowed. Every replay response should expose where practical
`inference_source = LIVE_MODEL_RUN` or `VALIDATED_CACHE`. For the jury demo:
provide a way to force a real local recomputation, or demonstrate at least one
date change that causes genuine local frozen-model execution. A valid persistent
cache from an earlier real run is allowed across restarts. The key rule: **cache
must be a provenance-valid output of the exact frozen pipeline.**

### 7A.3 No target leakage

Normal replay MUST NOT require the GLORYS `thetao` target, `outputs/targets_cache`,
Argo, or future-day observations. Prove this **without touching existing project
files** — monkeypatch target/cache/Argo paths to nonexistent paths, deny access
via a test fixture, or run against an isolated temp environment containing copies
of only the required inference artifacts. **Do not delete/rename/corrupt/move/
overwrite real project target/cache/Argo files.** Optionally perform one manual
isolated-environment sanity run.

### 7A.4 Location handling

For a requested lat/lon: (1) validate domain; (2) resolve to nearest canonical
0.25° cell; (3) return requested and resolved coordinates; (4) detect
invalid/land cells; (5) never silently jump to another ocean cell. Structured
statuses: `OK`, `OUTSIDE_DOMAIN`, `INVALID_OCEAN_CELL`, `INPUT_NOT_VALID`. A
nearest valid ocean cell may be *suggested* separately; it must never silently
replace the requested cell.

### 7A.5 Multi-date replay

Support `start_date`, `end_date`, `lat`, `lon`. Each day is an independent
`replay_field(date)`. Do not introduce temporal state. Do not use L3.

### 7A.6 Point JSON contract

Provide clean frontend-ready point output conceptually equivalent to:

```json
{
  "mode": "HISTORICAL_REPLAY",
  "date": "...",
  "location": { "requested_lat": 0, "requested_lon": 0, "grid_lat": 0, "grid_lon": 0 },
  "model": {
    "name": "L2 Spatial Satellite Embedding Engine",
    "checkpoint_sha256": "...", "encoder_sha256": "...",
    "latent_dim": 32, "receptive_field": 33
  },
  "surface_inputs": {
    "sst": {}, "sss": {}, "sla": {},
    "current_u": {}, "current_v": {}, "wind_u": {}, "wind_v": {}
  },
  "profile": [
    { "depth_m": 0, "prediction_c": 0, "climatology_c": 0, "anomaly_c": 0 }
  ],
  "nominal_zero_m_note": "...",
  "status": {
    "operating_mode": "HISTORICAL_COMPLETE_INPUT",
    "target_used_for_inference": false,
    "argo_used_for_inference": false,
    "inference_source": "LIVE_MODEL_RUN or VALIDATED_CACHE"
  }
}
```

Do not fabricate unavailable provenance fields.

### 7A.7 CLI

Provide a CLI following repository conventions, e.g.:

```
python scripts/replay/historical_replay.py --date 2023-05-14 --lat 15.25 --lon 85.75
python scripts/replay/historical_replay.py --field --date 2023-05-14
```

Support short date ranges. Point mode produces: console profile table, JSON
output, optional profile figure. Field mode exercises `replay_field()` directly.

### 7A.8 Tests

At minimum: all 15 depths; exact depth ordering; valid coordinate resolution;
invalid locations rejected; outside-domain requests rejected; `replay_field` uses
exact frozen L2; `replay_point` samples the `replay_field` result;
**`replay_point` at a resolved cell equals `replay_field` at that exact cell
within documented numerical tolerance — THIS TEST IS MANDATORY**;
`replay_field` / direct frozen-L2 equivalence; climatology equals frozen L0;
anomaly arithmetic correct; target data not required; `targets_cache` not
required; Argo not required; no future-day input used; point JSON
finite/serializable; frozen checkpoint / encoder / feature scaler / target
scaler / L0 unchanged.

**Measure and report the wall-clock time for one uncached `replay_field(date)`
call.** State whether it is fast enough to drive an interactive 3D depth-scrub
(§7.2) directly, or whether the field must be computed once per date and cached
for the session.

### 7A.9 Gate

Phase 7A passes only if BOTH `replay_field(date)` and `replay_point(date, lat,
lon)` work end-to-end using actual historical input fields → exact frozen L2 →
15-depth reconstruction → frozen L0 → anomaly, and all required tests pass.

**Required report:** `PHASE7_HISTORICAL_REPLAY_REPORT.md`. It must answer: is
frozen L2 still the final core; is the L2 hash unchanged; can a full field be
reconstructed; can a date/location be reconstructed; are all 15 depths returned;
does point replay derive from field replay; is climatology correct; is anomaly
correct; is target leakage avoided; were target-leakage tests non-destructive;
is the nominal-0 m convention documented; what is the uncached `replay_field`
wall-clock time.

**Status printout:**

```
Final core: existing frozen L2
Frozen L2 preserved: YES / NO
Historical point replay: WORKING / BLOCKED
Historical field replay: WORKING / BLOCKED
Point/field equivalence test: PASS / FAIL
15-depth profile: WORKING / BLOCKED
Climatology + anomaly: WORKING / BLOCKED
0m convention documented: YES / NO
replay_field() uncached time: <N> seconds
Tests passing: <N> / <total>
```

Then print exactly:

> PHASE 7A COMPLETE — AWAITING REVIEW.
> Do not proceed to the next phase until the user explicitly replies "CONTINUE".

**STOP.**

---

# PHASE 7B — Historical PoC (single mode — no second tab)

**Do not begin until explicitly authorized after 7A review.**

**Goal:** give the validated 7A backend a usable UI. **Historical Replay ONLY.**

Do **not**: build an NRT tab (even disabled); build an empty "Latest Inputs"
tab; build NRT fetchers; add NRT credentials or network calls; pre-build Phase
8A scaffolding.

### 7B.1 Apply the global UI contracts

Phase 7B is the first phase that ships UI. It MUST implement §5 (Visual Design),
§6 (No Fabricated Data), and §7 (3D Visualization) in full. The reference image
is the visual target; its content is mock data (§5.4–5.5).

### 7B.2 Pages / features

- **North Indian Ocean map** driven by `replay_field()`.
- **Historical date selector.**
- **Required-depth selector / slider** (the 15 mandated depths).
- **Layer selector:** reconstructed temperature; anomaly from climatology.
- **Click / select an ocean location.**
- **Vertical profile** panel showing **OceanEmbed** and **L0 climatology**
  together.
- **Surface input panel** — the seven input values at the selected cell, with
  product names.
- **Model / provenance panel** — model name, checkpoint hash, encoder hash,
  latent dim, receptive field, `inference_source`.
- **Visible nominal-0 m tooltip / info note** (§3).
- **3D Depth View** (§7) as a view mode of the same field. **Build it as the
  canonical reusable, source-agnostic 3D subsystem defined in §7.0** — renderer
  behind a canonical field-view contract, fed by an adapter over
  `replay_field()`. Phase 8B is forbidden from reimplementing it, so it must be
  decoupled from the replay transport schema **from the start**; retrofitting
  this later is the failure mode §7.0 exists to prevent.
- **Model Provenance & Validation** page (§5.3, §8) — real executed metrics
  only; must include the PS-compliance table (§8.4), the architecture decision
  matrix (`ARCHITECTURE_REVIEW.md`), the L0 / L1 / L2 per-depth comparison, the
  frozen L2 hash, and the **"only surface inputs at inference"** statement
  (§8.6).
- **Embeddings view** *(optional but recommended — the PS is literally
  "Satellite Embedding-Based")*: a small read-only page showing the 32-dim
  latent structure from `outputs/architecture_closure/` / Phase 6B-B (≈ 7 PCs
  explain 90 % of embedding variance; 12 of 32 dims inactive), and, for a
  selected cell, its embedding vector via the existing
  `scripts/baselines/extract_embedding.py` path. This directly answers the PS's
  "compact satellite embeddings / latent ocean representations" framing. No new
  inference path — reuse `embed_field`.
- **Exports** page — real outputs only (NetCDF / CSV / PNG of actual
  `replay_field` / profile / diagnostic results), with data-source attribution
  (§8, Copernicus Marine + NASA PO.DAAC + Argo credits).
- **Settings** page.

The clicked profile MUST derive from the same authoritative field result used
for the map (and for the 3D view). **Do not create another frontend inference
implementation.**

### 7B.3 Deep-ocean skill disclosure

OceanEmbed must still return the frozen L2 prediction at **all 15** depths,
including 500 / 700 / 1000 m. **Do not silently replace deep L2 outputs with L0
climatology.** For depths 500–1000 m, show a concise note such as:

> "Deep-ocean daily anomaly skill is weaker and more climatology-dominant.
> Interpret L2 departures from climatology cautiously."

L0 climatology must remain visible alongside L2 in the vertical profile. Do not
claim equal 0–1000 m skill. Any future rule that replaces or blends L2 with
climatology at selected depths would require a separately pre-registered and
validated operating-rule experiment and is **not authorized in Phase 7**.

### 7B.4 Default demo behaviour (offline-first)

The app must work with **no internet connection**. Choose one deterministic
default historical date/location: a valid ocean point **in the Bay of Bengal or
the Arabian Sea** (§8.7 — the PS PoC region), complete historical input,
selected **without** inspecting how good the GLORYS/Argo error happens to be
there. **Record the selection rule** in the report. On normal launch, run the
**real** local replay backend and frozen L2 — the primary demonstration must NOT
simply load a precomputed output standing in for the model. A **validated**
replay cache (§7A.2A) is allowed, but the demo must provide an easy way to
demonstrate genuine local computation (change date / force recompute). An
emergency fallback snapshot MAY exist only as a last-resort safety mechanism; if
shown it must visibly say **`FALLBACK SNAPSHOT`** and must never masquerade as
current model inference.

### 7B.5 Tests

- frontend consumes the Phase 7A replay API; contains **no** duplicate model
  inference path
- map comes from `replay_field()`; profile corresponds to the selected cell
- changing depth changes the mapped layer correctly
- changing historical date works
- app loads **without internet** and remains functional without internet
- nominal-0 m disclosure visible
- all 15 L2 depths remain available in the UI
- 500–1000 m displays the deep-skill / climatology-dominant disclosure
- real inference can be demonstrated (not only static output)
- **§6 no-fabrication tests** — rendered numbers equal the backend response for a
  fixed date/location; no shipped "sample data" module; map array equals
  `replay_field` array
- **§7.5 3D integrity tests** — 3D consumes only `replay_field`; depth-slice
  equals field; column click equals `replay_point`; land not rendered as
  temperature; 2D fallback works; deep-skill disclosure present in 3D
- **§7.5 3D reusability tests** — the renderer drives a synthetic field-view
  fixture with **no backend running**; the adapter output validates against the
  §7.0 canonical contract; the renderer module performs no network or filesystem
  access. These become regression tests Phase 8B must keep green.

### 7B.6 Gate

A person with no knowledge of the code must be able to, unassisted: open
OceanEmbed; choose a historical date; choose a required depth; inspect the North
Indian Ocean map; click an ocean location; see the 15-depth reconstructed
profile; compare with climatology; inspect the temperature anomaly.

**Required report:** `PHASE7B_HISTORICAL_POC_REPORT.md`. Report: gate test
performed; screenshots / flow description; default date/location selection rule;
no duplicate inference path; map uses `replay_field`; offline operation
confirmed; real local inference demonstrated; cache/fallback behaviour; deep-
ocean skill limitations visibly disclosed; no unvalidated L0/L2 hybrid
replacement introduced; **which frontend/3D technology was chosen and why**;
**§6 and §7 compliance**; and — because Phase 8B depends on it — **document the
canonical field-view contract as implemented** (exact object shape, the adapter
module path, the renderer's public props/API, and which reusability tests pin
it). A later phase must be able to plug a new authoritative source into that
boundary without touching the renderer.

**Status printout:**

```
Dashboard: WORKING / BLOCKED
Historical Replay mode: WORKING / BLOCKED
Map driven by replay_field(): YES / NO
3D Depth View: WORKING / BLOCKED
3D interactions (rotate/pan/zoom/depth-scrub): WORKING / PARTIAL / BLOCKED
3D renderer is source-agnostic and reusable (§7.0): YES / NO
Canonical field-view adapter implemented: YES / NO
2D fallback for 3D-unavailable devices: WORKING / BLOCKED
Default path uses real frozen replay: YES / NO
No fabricated data in UI (contract tests): PASS / FAIL
Fallback snapshot exists and labelled: YES / NO / N/A
0m tooltip visible: YES / NO
Deep-ocean skill disclosure visible: YES / NO
Judge-usability gate passed: YES / NO
Tests passing: <N> / <total>
```

Then print exactly:

> PHASE 7B COMPLETE — AWAITING REVIEW.
> Do not proceed to the next phase until the user explicitly replies "CONTINUE".

**STOP.**

---

# PHASE 7C — D26 / TCHP Diagnostics

**Do not begin until explicitly authorized after 7B review.**

**Goal:** derive disaster-relevant thermal diagnostics from OceanEmbed's 15-depth
profile and quantify **separately**: (1) error caused by the mandated 15-depth
vertical sampling; (2) error caused by OceanEmbed reconstruction. Primary
diagnostics: **D26**, **TCHP**. Do not add OHC unless D26/TCHP are complete and
OHC is genuinely trivial with existing code.

### 7C.1 Scientific definitions

**D26:** depth of the 26 °C isotherm, via documented linear interpolation
between bracketing depth levels. **Never extrapolate** where no valid crossing
exists. Explicit statuses must cover: surface already below 26 °C; profile
remains above 26 °C through available support; insufficient valid vertical
support; below-seafloor invalidity; other scientifically meaningful invalid
cases.

**TCHP:** `rho * Cp * ∫_0^D26 [T(z) − 26 °C] dz`. Before implementing final
calculations: (1) inspect the repo for an existing OceanEmbed/INCOIS convention;
(2) if absent, identify a named published/operational D26/TCHP convention;
(3) verify numerical constants from a primary source; (4) document the source
before final validation. The AOML/Goni-style formulation may be investigated as
a common reference family, but **do not copy numerical constants from this
prompt — verify them.**

`PHASE7C_D26_TCHP_REPORT.md` must record: D26 definition; TCHP
convention/source; `rho`; `Cp`; interpolation method; integration method; output
unit; kJ/cm² conversion if used. **Freeze the diagnostic convention before
generating final metrics. Do not tune constants to improve agreement.**

### 7C.2 Pre-register the application evaluation population

**Before** calculating D26/TCHP performance errors, create
`outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md` recording (before seeing final
results): exact evaluation date/range; date-selection rule; grid-cell
population; ocean-validity rule; depth-validity rule; whole-NIO definition;
Arabian Sea mask; Bay of Bengal mask; native GLORYS vertical levels used;
method to obtain the 15 mandated GLORYS depths; D26 convention; TCHP convention;
`rho`; `Cp`; interpolation method; integration method; invalid/non-crossing
handling; metrics to report.

The population and metric protocol must **not** be altered after inspecting
D26/TCHP errors, unless correcting a documented implementation error (which must
be documented, regression-tested, and scientifically justified). **Do not select
dates/cells because OceanEmbed performs unusually well there.** Describe this as
*historical application validation* / *historical application benchmark* — **not**
a pristine never-inspected test set.

### 7C.3 Three-stage vertical discretization experiment

For the same pre-registered dates and cells:

- **A — Native reference:** GLORYS native/full accepted vertical profile →
  `D26_A`, `TCHP_A`.
- **B — 15-depth reference:** reduce/interpolate the **same** GLORYS reference
  profile to exactly the 15 mandated depths → `D26_B`, `TCHP_B`.
- **C — OceanEmbed:** OceanEmbed's predicted 15-depth profile → `D26_C`,
  `TCHP_C`.

Interpretation: **A vs B** = vertical-discretization error; **B vs C** =
reconstruction-model contribution under identical 15-depth support; **A vs C** =
total end-to-end application error.

### 7C.4 Data discipline

This is **application validation**. Do not retrain L2, change L2, tune using
D26/TCHP, change the model based on diagnostic results, or use 2024 Argo. Use the
pre-registered historical evaluation population.

### 7C.5 Metrics

For D26 and for TCHP: MAE, RMSE, bias, correlation, valid sample count. Report
separately where valid: whole NIO, Arabian Sea, Bay of Bengal. Report A vs B,
B vs C, A vs C. **Do not collapse discretization and reconstruction errors into
a single story.**

### 7C.6 Figures + UI

At minimum: (1) D26 comparison — native / 15-depth reference / OceanEmbed;
(2) TCHP comparison — same three; (3) error attribution — discretization vs
reconstruction; (4) a representative vertical profile showing the D26
interpolation. **Do not hide** invalid or no-crossing cases.

Once validated, add **D26 and TCHP layers to the existing Historical Replay
dashboard**, following §5 (design system) and §6 (no fabrication): D26 as a map
layer in metres with its own colormap; TCHP as a map layer in kJ/cm²;
invalid / no-crossing cells shown with a **distinct rendering** (e.g. a hatched
"no 26 °C crossing" style), never a fake number. The representative-profile
figure with the D26 interpolation should be viewable in-app. **Still NO NRT tab.**

### 7C.7 Tests

Synthetic profile crossing 26 °C; interpolation result correct; exact-26 depth
handled; no-crossing case handled; surface-below-26 handled; no extrapolation;
invalid depth/gap behaviour; TCHP analytic/simple synthetic profile; integration
terminates at D26; unit conversion correct; invalid D26 propagates correctly;
**pre-registration file exists before final metric generation**; D26/TCHP UI
layers render real computed values only (§6); invalid cells render distinctly.

### 7C.8 Gate

**Required report:** `PHASE7C_D26_TCHP_REPORT.md`. It must answer: which
scientific convention was used; what source supports it; what `rho`/`Cp`; how
was D26 interpolated; how was TCHP integrated; what application population was
pre-registered; what is the A vs B discretization error; what is the B vs C
reconstruction error; what is the A vs C total application error; are D26/TCHP
now visible in Historical Replay.

**Status printout:**

```
D26: VALIDATED / BLOCKED
TCHP: VALIDATED / BLOCKED
Convention source documented: YES / NO
Evaluation protocol preregistered: YES / NO
Discretization error quantified: YES / NO
Reconstruction contribution quantified: YES / NO
D26/TCHP visible in Historical Replay: YES / NO
Tests passing: <N> / <total>
```

Then print exactly:

> PHASE 7C COMPLETE — AWAITING REVIEW.
> Do not proceed to the next phase until the user explicitly replies "CONTINUE".

**STOP.**

---

# PHASE 7D — One Historical Event Replay

**Do not begin until explicitly authorized after 7C review.**

**Goal:** create one strong disaster-management demonstration. OceanEmbed remains
a **general** subsurface reconstruction system; the event is an
application / stress test, not the definition of OceanEmbed.

### 7D.1 Event selection

Choose one historical **Bay of Bengal or Arabian Sea** cyclone or thermal-extreme
event (§8.7 — the PS PoC region) using an **external** significance criterion (a
major officially documented cyclone; a useful multi-day period inside the
2015–2024 data window; accessible official track/event data — e.g. IMD RSMC New
Delhi best-track, IBTrACS). Candidate cyclones in-window include Ockhi (2017,
AS), Fani (2019, BoB), Amphan (2020, BoB), Nivar (2020, BoB), Tauktae (2021,
AS), Yaas (2021, BoB) — pick from a sensible shortlist by the recorded rule.
**Do not select based on OceanEmbed having low model error during the event.**

**Before** inspecting event-specific model-reference errors, create
`outputs/phase7/EVENT_SELECTION.md` recording: event-selection rule; the event;
why selected; event window; external source/provenance (with its citation and
any licensing/attribution required for the track overlay).

### 7D.2 Event window

Keep the sequence understandable: pre-event → approach → event → wake →
recovery. Each date is an independent `replay_field(date)`. **No temporal
model.**

### 7D.3 Event visuals

Where scientifically supported: SST; SLA; reconstructed temperature at selected
depth(s); vertical temperature profile; anomaly from climatology; D26; TCHP;
official/event track overlay (with retained source/provenance). The
before/during/after strip in the reference image is allowed as **independent
daily `replay_field` snapshots** — never implying a temporal forecast model.

Never imply OceanEmbed predicted the storm track. Correct wording: *"OceanEmbed
reconstructs the subsurface ocean thermal state encountered by the cyclone"* or
*"cyclone-relevant thermal environment"*. Never *"OceanEmbed cyclone forecast"*.

### 7D.4 Ocean Hazard Indicators — historical decision-support tab

After Phase 7C validated D26 and TCHP, extend the Historical PoC with an
additional view/tab: `[ Historical Replay ] [ Ocean Hazard Indicators ]`. This
tab is **HISTORICAL** in Phase 7D — do **not** connect it to live/NRT data. Its
purpose is to translate the reconstructed thermal state into transparent,
jury-auditable ocean hazard indicators **without** claiming direct cyclone
prediction. Follow §5 and §6. This is the properly-scoped version of the
reference image's "Hazard Indicators" card — with **Tsunami Risk removed**,
**Sea Level Rise removed**, "Cyclone Risk" relabelled (§5.4).

**Primary indicator:** *Ocean Thermal Support for Cyclone Intensification*.
Preferred categorical display: `LOW`, `MODERATE`, `ELEVATED`, `HIGH`. **Do not
display a numeric cyclone probability** ("Cyclone chance = 73 %") — no such model
is authorized in Phase 7.

The indicator may use only validated / documented quantities available from the
historical OceanEmbed pipeline: D26; TCHP; upper-ocean / thermocline temperature
anomaly; other directly temperature-derived quantities already validated in
Phase 7C.

**Before** defining category thresholds or combination logic, create
`outputs/phase7/HAZARD_INDICATOR_PROTOCOL.md` recording (before inspecting the
event's final labels): exact indicator name; exact input quantities;
threshold / category logic; whether thresholds come from a named published
source or a pre-specified historical/climatological distributional rule (and the
reference period if distributional); handling of invalid D26/TCHP; handling of
deep-skill limitations; wording shown to users; an explicit statement that this
is an ocean thermal decision-support indicator, not cyclone
genesis/track/landfall prediction.

**Do not tune thresholds** because the chosen event "looks better" under a
different rule. If no defensible threshold/category rule can be documented, show
the underlying continuous diagnostics and explanation **without** forcing a
`LOW/MODERATE/ELEVATED/HIGH` label (display `NOT CATEGORIZED`).

The tab should show, where valid: *Ocean Thermal Support for Cyclone
Intensification* (`LOW/MODERATE/ELEVATED/HIGH` or `NOT CATEGORIZED`); D26; TCHP;
thermocline / upper-ocean temperature anomaly; *Subsurface Thermal Anomaly*;
*Upper-Ocean Heat Reservoir*.

For the selected event window, also show where scientifically supported:
*Cyclone Cold-Wake / Thermal Recovery*, using before/after changes in SST,
subsurface temperature, D26, TCHP. **Do not** call a single warm anomaly a
"marine heatwave" unless a recognized duration/percentile marine-heatwave
definition is explicitly implemented and validated.

**Explainability:** provide a visible *"Why this level?"* panel showing the
actual supporting quantities (e.g. `D26: <value>`, `TCHP: <value>`,
`thermocline anomaly: <value>`) and a concise interpretation, plus: *"This
indicator does not predict cyclone genesis, track, landfall, category, or exact
future intensity."* The indicator must derive from the **same** `replay_field()`
/ Phase 7C diagnostic outputs used elsewhere — no duplicate inference path.

### 7D.5 Tests

Ocean Hazard Indicators tab uses historical replay outputs only; no NRT/live
fetch code introduced in Phase 7D; indicator uses validated D26/TCHP where
required; threshold/category protocol exists before event-specific labels are
inspected; no numeric cyclone probability shown; `LOW/MODERATE/ELEVATED/HIGH`
not shown unless category logic is documented and defensible; *"Why this level?"*
exposes the supporting quantities; invalid D26/TCHP does not silently produce a
hazard category; deep-ocean skill disclosure remains visible where relevant;
cold-wake/recovery view (if shown) derived from independent daily replay outputs
and does not imply a temporal forecast model; the UI explicitly states cyclone
genesis/track/landfall are not predicted; **no Tsunami / Sea Level Rise tile
present** (§5.4); **§6 no-fabrication tests** pass for the hazard tab.

### 7D.6 Gate

**Required report:** `PHASE7D_EVENT_REPLAY_REPORT.md`. State: the event; the
event-selection criterion; when selection was recorded relative to error
inspection; the replay window; external track source; visuals produced;
wording/provenance constraints followed; the hazard-indicator protocol path; the
Ocean Hazard Indicators tab status; exact indicator inputs / threshold rule;
whether categorical labels were scientifically supported; whether *"Why this
level?"* is visible; whether cold-wake / recovery diagnostics were shown.

**Status printout:**

```
Historical event replay: WORKING / BLOCKED
Ocean Hazard Indicators: WORKING / BLOCKED
Cyclone thermal-support indicator: VALIDATED / CONTINUOUS-ONLY / BLOCKED
Hazard indicator protocol frozen: YES / NO
Numeric cyclone probability shown: NO
Event selected before error inspection: YES / NO
Tsunami / Sea-Level-Rise tiles removed: YES / NO
Tests passing: <N> / <total>
```

Then print exactly:

> PHASE 7D COMPLETE — AWAITING REVIEW.
> Do not proceed to the next phase until the user explicitly replies "CONTINUE".

**STOP.**

---

# PHASE 7E — Final PoC Freeze + 2024 Argo Pre-Registration (DO NOT OPEN 2024 ARGO)

**Do not begin until explicitly authorized after 7D review.**

**Goal:** freeze the complete Historical OceanEmbed application protocol built in
7A–7D. Pre-register — but **do not execute** — the protected 2024 Argo
evaluation.

Create `PHASE7_FINAL_POC_REPORT.md` and `outputs/phase7/FINAL_POC_MANIFEST.json`
recording: frozen L2 checkpoint/hash; encoder hash; replay API version (field,
point); processing/grid version; cache semantics/version; frontend version;
diagnostic algorithm version; D26/TCHP source; `rho`/`Cp`; diagnostic evaluation
protocol; event-selection rule; hazard-indicator protocol/version; Ocean Hazard
Indicators frontend status; historical demonstration date; application metrics;
test counts; known limitations; `NRT status = NOT STARTED`;
`2024 Argo status = PROTECTED`.

### 7E.1 Final 2024 Argo pre-registration

Create `outputs/phase7/FINAL_2024_ARGO_PREREGISTRATION.md` **before** any 2024
Argo is downloaded or inspected. State explicitly: frozen final model = existing
L2; no architecture changes after viewing 2024; no scaler changes after viewing
2024; no climatology changes after viewing 2024; same Argo QC philosophy as
Phase 6C-A; same physical temperature conversion philosophy; same target-depth
definitions; same metrics; all 15 depths reported; no cherry-picking; no
threshold movement; no event-selection changes based on 2024.

**Pre-commit interpretation:** if 2024 is similar or better → report temporal
robustness. If moderately worse → report degradation quantitatively; investigate
possible interannual/domain shift; **do not tune to 2024**. If substantially
worse → report the limitation honestly; **do not tune to 2024**. Implementation
bugs may be corrected only if documented, regression-tested, and the correction
does not amount to model selection.

**CRITICAL: DO NOT DOWNLOAD OR OPEN 2024 ARGO IN PHASE 7E.**

### 7E.2 Full test suite

Run the full test suite. Previous baseline: `384 passed`. Report the actual
current result. Do not manufacture a target test count.

### 7E.3 Status

Print exactly, filled in:

```
OceanEmbed Phase 7 PoC complete.

Final core: existing frozen L2
Frozen L2 preserved: YES / NO

Historical point replay: WORKING / BLOCKED
Historical field replay: WORKING / BLOCKED

15-depth profile: WORKING / BLOCKED
Climatology + anomaly: WORKING / BLOCKED

Dashboard: WORKING / BLOCKED
3D Depth View: WORKING / BLOCKED

D26: VALIDATED / BLOCKED
TCHP: VALIDATED / BLOCKED

Historical event replay: WORKING / BLOCKED
Ocean Hazard Indicators: WORKING / BLOCKED

2024 Argo: PROTECTED / COMPROMISED
Final holdout preregistration: READY / MISSING

Full test suite: <N> passed
```

Then print exactly:

> PHASE 7E COMPLETE — AWAITING REVIEW.
>
> Two SEPARATE approvals are possible from here, and granting one does NOT grant the other:
>   (1) approval to open the protected 2024 Argo holdout
>   (2) approval to begin Phase 8A (NRT-Lite / live input telemetry)
>
> Take no action on either until explicitly told which to proceed with.
> Phase 8B full NRT subsurface qualification is specified later in this document but is NOT authorized at the end of Phase 7E. Phase 8A must be completed and reviewed first.

**STOP.**

---

# PHASE 8A — NRT-Lite / Live Input Telemetry

**Only begin after explicit approval following 7E review.**

Phase 8A does **not** certify an NRT subsurface temperature reconstruction. It
adds **live/NRT input telemetry only.**

Add a live/NRT telemetry tab called **`Latest Inputs`** or **`Operational
Status`**. The Historical Replay and Ocean Hazard Indicators capability from
Phase 7 must remain intact. Preferred UI after 8A:
`[ Historical Replay ] [ Ocean Hazard Indicators ] [ Latest Inputs ]`.

The Ocean Hazard Indicators tab remains **HISTORICAL** in Phase 8A. Do **not**
use incomplete SST/SLA telemetry to generate a latest cyclone thermal-support
label, latest D26/TCHP, or any latest subsurface hazard indicator. Do **not**
call the NRT tab `Latest Qualified Ocean State` yet.

### 8A.1 Scope

Implement the smallest reliable live-fetch path for the two inputs Experiment D
showed have clear incremental predictive value: **SST** (prefer OSTIA NRT),
**SLA** (prefer DUACS NRT). Reuse existing Phase 6C-D product/fetch definitions
where possible (`src/oceanembed/nrt/`). Do not duplicate NRT download machinery.
Historical Replay must remain frozen from Phase 7E.

### 8A.2 Latest input telemetry

For each successfully retrieved input show: product; requested / analysis date;
product valid time; local retrieval time; generated/product time where actually
available; computed data age; spatial coverage in the North Indian Ocean;
qualification/status; `source tier = NRT`. **Do not fabricate exact acquisition
times.**

Display clearly: `NRT INPUT TELEMETRY AVAILABLE` and `SUBSURFACE NRT
RECONSTRUCTION NOT YET CERTIFIED`. **Do not run the frozen L2 on an incomplete
ad-hoc input stack merely to make the latest screen display temperature.**

### 8A.3 Why SST + SLA first?

Make the reason visible in the UI, concisely:

> **Why SST + SLA first?**
> Controlled L2 channel ablation found clear incremental predictive value from
> SST near the surface and SLA through the thermocline. SSS, currents and winds
> showed no detectable incremental contribution above the measured training-run
> noise floor in that experiment. This does NOT mean those variables are
> physically unimportant or that the frozen L2 can accept arbitrary values in
> those channels. Full operational input qualification remains future work.

Do not say "Only SST and SLA matter" or "SSS/currents/winds are useless." An
expandable *"Why these inputs?"* panel is acceptable.

### 8A.4 One application — offline-first connectivity state machine

There is **one** OceanEmbed application. Do NOT create a separate "offline
version", a separate demo executable, or a second app to launch when Wi-Fi
fails. Historical Replay and historical Ocean Hazard Indicators are local
capabilities usable regardless of network state. The `Latest Inputs` tab is the
network-enhanced capability. Operational availability is determined from the
**actual fetch/source result**, not merely from a Wi-Fi flag.

```
launch OceanEmbed → local Historical Replay available (always usable)
user opens / refreshes Latest Inputs → attempt real source fetches
  all sources succeed        → show freshly retrieved telemetry
  only some sources succeed   → show PARTIAL SOURCE AVAILABILITY, source-by-source
  network / source / auth fails → show clearly labelled last-successful telemetry
                                   if available, else DATA SOURCE CURRENTLY UNAVAILABLE
```

Recommended states (expose a clearer user-facing message if better):
`ONLINE_CURRENT`, `ONLINE_PARTIAL`, `OFFLINE_OR_SOURCE_UNAVAILABLE`,
`CACHED_TELEMETRY_NOT_CURRENT`.

**Key behaviour: Historical Replay does NOT go down because Latest Inputs goes
down.** A failed Latest Inputs request must never crash the app, disable
Historical Replay or historical Ocean Hazard Indicators, require launching
another version, or silently present old telemetry as current.

When connectivity returns: `Retry / Refresh` (or the next controlled retry)
attempts fresh fetches and updates the active `Latest Inputs` state **in the
same running app** — no restart. **Phase 8A remains telemetry-only** — even on
successful reconnect, 8A must NOT start frozen-L2 latest subsurface inference.

### 8A.5 Network / login failure & recovery

Success → current telemetry. Failure → clearly labelled last-successful
telemetry, or `DATA SOURCE CURRENTLY UNAVAILABLE`. **Never disguise cached
telemetry as fresh.** Store separately: source valid time; local retrieval time.
On recovery: re-fetch latest SST/SLA telemetry; replace the error state; update
source-valid time, retrieval time, and displayed data age; stop presenting stale
cached telemetry as current. Recovery must not restart or interrupt Historical
Replay.

### 8A.6 Not-certified state

Never show a blank panel. Example:

```
SUBSURFACE RECONSTRUCTION NOT YET CERTIFIED
Fresh operational inputs:  SST available   SLA available
Remaining frozen-L2 input contract:  not yet qualified for operational inference
Historical Replay remains available.
Historical Ocean Hazard Indicators remain available.
Latest / NRT hazard indicators remain NOT CERTIFIED.
```

### 8A.7 Demo-day resilience test

Do not assume the failure path works merely because exception handling exists.
Perform one **deliberate** offline / fetch-failure test: disable the network (or
force the fetch path to fail deterministically), then (1) launch OceanEmbed;
(2) verify Historical Replay still works; (3) verify the `Latest Inputs` tab
renders; (4) verify no crash; (5) verify cached telemetry is visibly labelled if
present; (6) verify source-valid time remains visible; (7) verify retrieval time
remains visible; (8) verify a missing cache produces an informative unavailable
state.

Record `outputs/phase8a/demo_resilience_test.json` with at minimum:
`tested_at`, `failure_method`, `historical_replay_available`,
`latest_tab_rendered`, `cached_snapshot_used`, `cached_snapshot_label_visible`,
`unavailable_state_rendered`, `application_crashed`, `result`. **Required:
`result = PASS`.** Add an automated regression test where practical, and also
perform the actual offline/manual launch once. The final report must state:
*"Demo resilience was tested with the live-data path deliberately unavailable."*
The primary OceanEmbed demonstration must never depend on venue Wi-Fi.

### 8A.8 Still NOT authorized in Phase 8A

Full NRT subsurface reconstruction; a latest temperature map; claiming a latest
qualified subsurface ocean state; quantile/CDF mapping; testing/approving
zero-filled or mean-filled SSS; inventing a new SSS fallback; promoting SSS
climatology; training a reduced-channel model, availability-aware model, or
uncertainty model; adding source-age neural inputs; evidential regression;
touching 2024 Argo; changing architecture. Historical SSS persistence remains
prior evidence; Phase 8A does **not** authorize extending its validated age
envelope.

### 8A.9 Tests

Historical Replay remains unchanged; works without internet; the `Latest Inputs`
tab contains no model inference; historical Ocean Hazard Indicators remain
available and unchanged; no latest/NRT cyclone thermal-support label is
generated in 8A; no latest/NRT D26/TCHP from the incomplete telemetry stack;
live telemetry path works where credentials/network permit; fetch failure never
crashes the app; app launched offline still provides Historical Replay and
historical Ocean Hazard Indicators; online → offline/fetch-failure → online
recovers `Latest Inputs` without an app restart; partial SST/SLA source success
is represented source-by-source and not misrepresented as complete; cached
telemetry always labelled; no-cache state informative; source valid time kept
separate from retrieval time; channel-choice explanation visible; no wording
says SST/SLA are the only physically important inputs; latest subsurface
reconstruction remains `NOT CERTIFIED`.

### 8A.10 Report

Create `PHASE8A_NRT_LITE_REPORT.md`. Answer: can live SST/SLA telemetry be
retrieved; which products; what valid dates/times observed; what data ages
observed; is provenance visible; is the `Latest Inputs` tab working; do
historical Ocean Hazard Indicators remain available; does the UI avoid
presenting any latest/NRT hazard indicator as certified; is the channel-choice
explanation visible; does the UI avoid overclaiming; is subsurface NRT
reconstruction still not certified; was the offline/failure path actually
rehearsed; after connectivity was restored, did `Latest Inputs` recover without
an app restart; did `demo_resilience_test.json` pass.

**Status printout:**

```
Latest Inputs mode: TELEMETRY READY / BLOCKED
Latest NRT subsurface reconstruction: NOT CERTIFIED
Historical Ocean Hazard Indicators: AVAILABLE / BLOCKED
Latest/NRT Ocean Hazard Indicators: NOT CERTIFIED
Channel-choice explanation visible: YES / NO
Offline failure path rehearsed: YES / NO
Connection recovery without app restart: PASS / FAIL
demo_resilience_test.json: PASS / FAIL
Tests passing: <N> / <total>
```

Then print exactly:

> PHASE 8A COMPLETE — AWAITING REVIEW.
>
> Historical OceanEmbed PoC: COMPLETE
> Latest operational telemetry: READY / BLOCKED
> Latest subsurface reconstruction: NOT YET CERTIFIED
>
> STOP — awaiting review before any Phase 8B work.
> Phase 8B may begin ONLY after the user explicitly authorizes it following review of this Phase 8A report.
> Approval to begin Phase 8B does NOT authorize access to 2024 Argo. 2024 Argo remains PROTECTED pending its own separate explicit approval.

---

# PHASE 8B — Full NRT Subsurface Qualification (Latest Qualified Ocean State Gate)

**Only begin after explicit approval following 8A review.**

Phase 8B is a **qualification** phase. It does not guarantee that a latest
15-depth reconstruction will be certified. A scientifically valid outcome may be
`QUALIFIED`, `QUALIFIED WITH LIMITATIONS`, or `NOT QUALIFIED`. **Do not force a
successful operational result for presentation purposes.**

The frozen scientific core remains the existing frozen L2. Do **not** in Phase
8B: retrain or fine-tune L2; change the seven-channel input width, architecture,
or latent width; add temporal memory; rerun L3; train a reduced-channel
replacement or availability-aware model; apply quantile/CDF mapping (unless
separately authorized by a NEW research approval outside 8B); use zero/mean-filled
SSS as an approved operating mode; promote climatological SSS;
open/download/collocate/score 2024 Argo. **Approval for Phase 8B is NOT approval
for the protected 2024 Argo holdout.**

### 8B Goal

Answer one narrow question: **can the COMPLETE frozen-L2 operational input
contract support a scientifically qualified latest available 15-depth subsurface
temperature reconstruction?**

- **If yes:** implement and expose **`Latest Qualified Ocean State`** with full
  provenance, age, coverage, operating-mode disclosure, depth-dependent
  limitations, D26/TCHP where qualified, and latest Ocean Hazard Indicators
  where qualified.
- **If no:** retain **`Latest Inputs`** as the operational-facing mode and
  report clearly: `LATEST SUBSURFACE RECONSTRUCTION NOT QUALIFIED`.

**Do not weaken the acceptance logic merely to obtain a latest map.**

### 8B.1 Pre-register the NRT qualification protocol

**Before** final NRT-stack scoring, create
`outputs/phase8b/NRT_SUBSURFACE_QUALIFICATION_PROTOCOL.md`. Inspect first:
`PHASE6C_NRT_COMPATIBILITY_REPORT.md`, `PHASE6C_FALLBACK_ARGO_REPORT.md`,
`PHASE6C_ARGO_VALIDATION_REPORT.md`, `PHASE8A_NRT_LITE_REPORT.md`,
`outputs/phase8a/demo_resilience_test.json`, the Phase 7 final manifest, existing
NRT product fetch/config code, and the actual available historical overlap of
the candidate operational product families.

The protocol must freeze **before** final qualification metrics are viewed:
candidate operational product family for each of the seven physical L2 channels;
exact temporal-alignment rule; per-source source-valid-time handling; product-age
computation; coverage/mask rules; candidate SSS operating policy/policies; any
allowed persistence rule and its maximum age envelope; invalid/missing-source
behaviour; latest-state effective-date definition; hindcast / replay evaluation
dates; evaluation population; whole-NIO / Arabian Sea / Bay of Bengal masks;
temperature metrics; D26 metrics; TCHP metrics; observational/reference sources;
operational qualification categories; acceptance/rejection logic; all wording for
qualified vs non-qualified states.

Reuse existing executed Phase 6C-D qualification thresholds/terminology where the
repository already defines them. **Do not invent a more permissive threshold**
merely because a candidate stack otherwise fails. If no defensible acceptance
logic exists in executed evidence, document the gap and use conservative
scientific judgment. If a valid decision still cannot be made without inventing
an arbitrary threshold: **STOP Phase 8B qualification** and report
`QUALIFICATION CRITERION BLOCKED` rather than silently tuning a gate.

### 8B.2 Complete seven-channel operational contract

The frozen L2 still expects `SST, SSS, SLA, current U, current V, wind U, wind
V`. Phase 8B must qualify the **complete** input contract. Do not infer that
Experiment D allows missing channels merely because some retrained ablations
showed no detectable incremental contribution.

Starting evidence: **SST** — OSTIA NRT preferred candidate family; **SLA** —
DUACS NRT preferred; **currents** — inspect/reuse the already-audited NRT current
candidate and explicitly account for source age; **winds** — inspect/reuse the
already-audited NRT wind candidate; **SSS** — remains the critical unresolved
operational channel.

For SSS: raw SMAP/SMOS substitution is not automatically qualified; historical
SSS persistence is prior observational evidence; climatological SSS substitution
remains rejected; zero/mean SSS is not an approved fallback. A candidate SSS
persistence policy in 8B must mean *use the last **qualified** available SSS
field* with source/product identity, source-valid time, exact age, persistence
age envelope, and status exposed to the user. **Do not describe an arbitrarily
old SSS field as near-real-time.** If no scientifically qualified SSS operating
mode exists, the complete latest frozen-L2 reconstruction is `NOT QUALIFIED`.

### 8B.3 Temporal alignment — "latest available" ≠ "right now"

Operational products may have different valid times. Do not silently pretend all
seven channels describe the same instant. Define and document the temporal
alignment policy. Every latest-state inference candidate must preserve at
minimum: requested/retrieval time; per-product source-valid time; per-product
source age; oldest input age; newest input age; effective reconstruction
date/time or analysis-date convention; any persisted-input age; operating-policy
name. Acceptable wording: `Latest Qualified Ocean State`, *latest available
qualified reconstruction*, *near-real-time input stack*. **Not** `Live Ocean
Right Now`.

### 8B.4 Hindcast-the-NRT qualification

Before enabling a latest temperature map, reproduce the operational driving
conditions over historical overlap as faithfully as the archives permit:

```
historical date
  → operational/NRT product families that would drive the system
  → actual source-age / persistence / mask policy
  → exact frozen preprocessing contract
  → exact frozen L2
  → 15-depth reconstruction
  → reference / observational comparison
```

This is the **primary evidence** for actual operational-mode skill. **Do not
treat the Phase 6C-D single-product substitution sensitivity numbers as full
observational NRT accuracy.** The hindcast must preserve: complete-stack
interaction; source masks; coverage; product-family shifts; input age; SSS
operating mode; temporal-alignment policy. If historical archives do not support
a defensible hindcast of the claimed operational configuration, **do not certify
that configuration.**

### 8B.5 Temperature qualification

Run the frozen L2 only for pre-registered COMPLETE operational modes. Report all
15 depths. At minimum report where reference data allow: RMSE, bias,
correlation, anomaly correlation, valid sample count, coverage. Report
separately where valid: whole NIO, Arabian Sea, Bay of Bengal. Compare against
appropriate existing references including where scientifically supported: frozen
historical L2 performance, L0 climatology, collocated **2022–2023** Argo
profiles, historical/reanalysis reference fields. **Do not access 2024 Argo.**
Deep-ocean disclosure remains mandatory: 500–1000 m daily anomaly skill is
weaker / more climatology-dominant; a low deep RMSE alone must not be
interpreted as strong deep anomaly skill.

### 8B.6 D26 / TCHP operational-mode qualification

Only after an operational temperature mode survives the temperature gate,
evaluate D26 and TCHP using the **same** frozen Phase 7C definitions. Do not
change D26 interpolation, `rho`, `Cp`, TCHP integration, or invalid-case
behaviour to improve NRT results. Where possible repeat the application-error
decomposition under the operational driving mode. If temperature reconstruction
is not qualified, do not promote latest D26/TCHP as qualified.

### 8B.7 Latest Ocean Hazard Indicator qualification

Historical Ocean Hazard Indicators remain unchanged; do not modify the frozen
Phase 7D `outputs/phase7/HAZARD_INDICATOR_PROTOCOL.md`. If the operational
15-depth reconstruction and required D26/TCHP inputs are qualified, test whether
the **same** historical hazard-indicator logic transfers to the operational
mode. **Do not retune** `LOW/MODERATE/ELEVATED/HIGH` thresholds based on NRT
examples. If transfer is supported, the latest hazard mode may display: *Ocean
Thermal Support for Cyclone Intensification*, D26, TCHP, thermocline / upper-ocean
anomaly, *Subsurface Thermal Anomaly*, *Upper-Ocean Heat Reservoir*. The UI must
still state: *"This indicator describes the oceanic thermal environment relevant
to cyclone intensification. It does not predict cyclone genesis, track, landfall,
category, or exact future intensity."* Do not display a numeric cyclone
probability. If transfer is not supported, keep Ocean Hazard Indicators
historical-only.

### 8B.8 Authoritative latest-state inference

**Only if** the qualification gate passes, implement an authoritative latest
field path, conceptually `latest_qualified_field()`. It must: (1) fetch/resolve
the complete qualified seven-channel stack; (2) evaluate source validity,
coverage, age, operating policy; (3) **refuse inference if required qualification
conditions are not met**; (4) execute the **same** frozen whole-field L2
scientific inference path; (5) return the 101×241×15 reconstruction; (6) return
L0 climatology for the effective date; (7) return `anomaly = L2 − L0`; (8) return
D26/TCHP only if those operational diagnostics are qualified; (9) return hazard
indicators only if their operational transfer is qualified; (10) return complete
per-source provenance and age metadata. A point/latest profile must sample from
the authoritative latest field — **no second point-only network implementation.**
If the complete stack is not qualified at request time, **no latest 15-depth
inference is produced.**

### 8B.9 UI — success and failure states

**If and only if** Phase 8B passes the qualification gate, the NRT-facing tab
may be renamed **`Latest Qualified Ocean State`**. Preferred UI:
`[ Historical Replay ] [ Ocean Hazard Indicators ] [ Latest Qualified Ocean State ]`.

The latest tab should show: effective latest reconstruction date/time; per-source
valid time; per-source age; persisted-input status/age where applicable; oldest
input age; spatial coverage; operating-mode name; qualification status; frozen L2
hash; depth selector; latest qualified 15-depth temperature map; **the 3D Depth
View of the latest qualified field**; clicked vertical profile; L0
climatology; anomaly; D26/TCHP if operationally qualified; latest Ocean Hazard
Indicators if operationally qualified; deep-ocean skill disclosure. Follow §5 and
§6 throughout — every displayed value traces to `latest_qualified_field()` or a
labelled snapshot.

**The 3D view here MUST be the shared Phase-7B renderer (§7.0).** Do **not**
build a second NRT/latest-state 3D implementation. The only new work permitted
is: (a) an **adapter** normalizing `latest_qualified_field()` into the canonical
field-view contract, and (b) **provenance/status display** additions — effective
reconstruction time, per-source ages, qualification state, persisted-input
status, `LAST SUCCESSFUL QUALIFIED SNAPSHOT` labelling. Duplicating the
visualization engine, shaders, camera/controller logic, depth controls, colour
logic, profile interaction, or scientific field handling is a Phase 8B failure,
not an optimization.

If Phase 8B does **not** pass, keep the tab named `Latest Inputs` and do not
expose a latest subsurface temperature map as qualified.

### 8B.10 One application — offline/online behaviour

The same offline-first rule from Phase 8A remains mandatory. There is still one
OceanEmbed application. Historical Replay and historical Ocean Hazard Indicators
never require venue internet.

If the latest qualified mode has been certified and a latest qualified
reconstruction was previously produced, the app may persist that exact
provenance-valid output as `LAST SUCCESSFUL QUALIFIED SNAPSHOT`. When
internet/source access fails: Historical Replay and historical Ocean Hazard
Indicators remain fully usable; `Latest Qualified Ocean State` **must not
fabricate a new current reconstruction** — instead show
`LAST SUCCESSFUL QUALIFIED SNAPSHOT — NOT CURRENT` (with its effective
reconstruction time, per-source valid times, age when generated, current elapsed
staleness where computable, model hash, operating-policy name) or
`LATEST QUALIFIED OCEAN STATE CURRENTLY UNAVAILABLE`. **Never silently run L2
using whichever subset of NRT inputs happened to remain reachable.**

Connectivity state is driven by actual source/fetch qualification, not only by
Wi-Fi. On recovery: `Retry / Refresh` → fetch the complete candidate stack →
re-evaluate qualification → if the complete stack passes, run frozen L2, replace
the stale snapshot, update D26/TCHP and latest hazard indicators if qualified;
else remain unavailable/partial and do not run latest subsurface inference. This
happens in the same running app — no restart, no interruption of Historical
Replay.

### 8B.11 Demo-day resilience test

If Phase 8B reaches an implemented qualified latest mode, perform an end-to-end
rehearsal: online → produce/load a provenance-valid qualified latest state →
force network/source failure → verify historical modes still work → verify latest
state becomes clearly stale/unavailable → restore access → `Retry / Refresh` →
verify the complete stack is re-qualified → verify new latest inference occurs
only after the stack passes → verify no app restart was required.

Record `outputs/phase8b/operational_resilience_test.json` with: `tested_at`,
`initial_latest_state_available`, `failure_method`,
`historical_replay_available_during_failure`,
`historical_hazard_indicators_available_during_failure`,
`stale_snapshot_displayed`, `stale_snapshot_label_visible`,
`unavailable_state_rendered`, `recovery_without_restart`,
`complete_stack_requalified_after_recovery`, `new_l2_inference_after_recovery`,
`partial_stack_inference_blocked`, `result`. **Required for an implemented latest
mode: `result = PASS`.**

### 8B.12 Cache / snapshot discipline

A latest qualified snapshot may contain **only** output previously generated by
`complete qualified operational stack → exact frozen preprocessing → exact frozen
L2`. Never cache or display as qualified: fabricated outputs; manually authored
values; incomplete-stack predictions; outputs from a rejected operating mode;
outputs generated before the mode passed qualification. Cache identity must
include at minimum: model hash; processing/scaler version; grid version;
operating-policy version; source product families; source-valid times; source
ages / persisted status; inference/effective date.

### 8B.13 Tests

Frozen L2 / encoder / L0 / scalers hashes unchanged; 2024 Argo untouched;
complete seven-channel contract enforced; no unapproved zero/mean/climatological
SSS fallback; SSS persistence only under the pre-registered policy/age envelope;
source valid time and retrieval time remain separate; temporal-alignment policy
implemented exactly; incomplete/failed source stack blocks latest L2 inference;
full-field latest path uses exact frozen L2; latest point/profile samples the
authoritative latest field; exact 15-depth ordering preserved; anomaly
arithmetic correct; deep-skill disclosure visible; D26/TCHP latest layers only
appear if operationally qualified; latest hazard indicators only appear if
transfer is qualified; no numeric cyclone probability fabricated; app launched
offline still supports historical modes; latest stale snapshot clearly labelled
`NOT CURRENT`; no-cache latest failure state informative; online → offline →
online recovery without restart; partial source recovery does not trigger
incomplete-stack inference; reconnect triggers new latest inference only after
the complete stack passes; **§6 no-fabrication and §7 3D tests pass for the
latest tab**; full test suite remains passing.

**Shared-renderer reuse (§7.0) — mandatory:**

- **every Phase 7B 3D regression test still passes**, unchanged;
- no second 3D renderer module exists — the latest tab imports the same renderer
  component as Historical Replay;
- the `latest_qualified_field()` adapter produces an object that validates
  against the **same** canonical field-view contract as the `replay_field()`
  adapter;
- the shared renderer displays `latest_qualified_field()` values **without
  changing their scientific meaning** — a depth-slice and a clicked profile from
  the latest field equal the backend's latest values within the documented
  tolerance, exactly as they do for historical replay.

### 8B.14 Qualification decision

Use one of: `QUALIFIED`; `QUALIFIED WITH LIMITATIONS`; `NOT QUALIFIED`;
`BLOCKED — INSUFFICIENT EVIDENCE`. A failed or blocked Phase 8B is an acceptable
scientific result. Do not respond by silently changing the model or acceptance
rule.

### 8B.15 Report / final gate

Create `PHASE8B_NRT_SUBSURFACE_QUALIFICATION_REPORT.md` and
`outputs/phase8b/FINAL_NRT_OPERATING_MANIFEST.json`. The report must answer:
which seven operational product/channel policies were evaluated; how were source
times aligned; what SSS mode was evaluated; what maximum persistence age was
allowed; what historical overlap supported hindcast-the-NRT; what temperature
skill at all 15 depths; what coverage; how did Arabian Sea and Bay of Bengal
differ; did the operational mode retain useful skill over L0 where claimed; what
happened at 500–1000 m; were D26/TCHP operationally qualified; did the historical
hazard indicator transfer; was a latest 15-depth map actually certified; was the
offline → online recovery path rehearsed; did incomplete-stack inference remain
blocked; was 2024 Argo untouched; are all frozen hashes unchanged; **was the
shared Phase-7B 3D renderer reused rather than reimplemented (§7.0), and do all
Phase 7B 3D regression tests still pass**.

**Status printout:**

```
Frozen L2 preserved: YES / NO
Complete NRT seven-channel contract: QUALIFIED / QUALIFIED WITH LIMITATIONS / NOT QUALIFIED / BLOCKED
SSS operating mode: <mode or NONE>
Hindcast-the-NRT: COMPLETED / BLOCKED
Latest 15-depth subsurface reconstruction: QUALIFIED / QUALIFIED WITH LIMITATIONS / NOT QUALIFIED / BLOCKED
Latest D26: QUALIFIED / NOT QUALIFIED / BLOCKED
Latest TCHP: QUALIFIED / NOT QUALIFIED / BLOCKED
Latest Ocean Hazard Indicators: QUALIFIED / HISTORICAL ONLY / BLOCKED
Latest tab name: LATEST QUALIFIED OCEAN STATE / LATEST INPUTS
Shared Phase-7B 3D renderer reused (no second implementation): YES / NO / N/A
Phase 7B 3D regression tests still passing: YES / NO
Offline historical demo: WORKING / BLOCKED
Offline latest-state behavior: SAFE / FAIL / N/A
Connection recovery without app restart: PASS / FAIL / N/A
2024 Argo: PROTECTED / COMPROMISED
Full test suite: <N> passed
```

Then print exactly:

> PHASE 8B COMPLETE — AWAITING REVIEW.
> Do not begin any post-8B research, production-hardening phase, new cyclone-probability model, architecture change, or protected 2024 Argo evaluation without separate explicit approval.

**STOP.**

---

## POST-8B — Not Authorized by This Document

Possible future work (none authorized merely by completing Phase 8B): protected
2024 Argo final holdout evaluation under its own approval; production hardening /
deployment; calibrated uncertainty; a separately trained and validated cyclone
rapid-intensification probability model using atmospheric + storm-state
predictors in addition to OceanEmbed thermal diagnostics; further NRT
product/calibration research if Phase 8B is blocked; new model research only if
explicitly reopened.

---

## Appendix A — Executed metrics available to the Validation page (real, do not fabricate)

Frozen L2 on the locked 2022–2024 grid test set
(`outputs/tables/phase6b_l2_metrics_by_depth_test.csv`):

| depth (m) | L2 RMSE (°C) | correlation | skill vs L0 |
|---|---|---|---|
| 0 | 0.48 | 0.96 | +30.1 % |
| 50 | 0.87 | 0.90 | +22.4 % |
| 100 | 1.19 | 0.87 | +33.5 % |
| 150 | 1.03 | 0.89 | +26.3 % |
| 300 | 0.52 | 0.95 | +5.4 % |
| 500 | 0.37 | 0.96 | −4.1 % |
| 1000 | 0.39 | 0.93 | −1.3 % |

External Argo observational check (2022–2023,
`outputs/tables/phase6c_argo_metrics_by_depth.csv`): L2 at ~100 m ≈ 1.3 °C RMSE
vs L0 ≈ 1.8 °C; anomaly correlation ≈ 0.73; float-clustered bootstrap CIs
available. GLORYS is shown for context, not as truth.

Experiment D (`outputs/tables/architecture_closure/channel_ablation_depth_groups.csv`):
run-to-run noise floor ≈ 0.64 % mean / 1.66 % max RMSE; removing **SLA** costs
≈ +29 % through the thermocline; removing **SST** costs ≈ +13 % at the surface;
removing **SSS / currents / winds** stays within the noise floor.

These are the numbers the Validation / Model-Comparison / Ablation pages must
display — pulled live from `outputs/tables/`, never hardcoded, and re-generated
by the existing `scripts/baselines/evaluate_l2.py` / `scripts/validate/` scripts
when requested.

---

## Appendix B — New dependencies by phase (add incrementally, do not pre-install)

**Backend (`requirements.txt`, add when the phase begins):**

- Phase 7A: `fastapi`, `uvicorn[standard]` — the replay API. (`sqlite3` is stdlib;
  add nothing for the cache unless indexed queries are genuinely needed.)
- Phase 7C: nothing expected (`gsw`, `numpy`, `scipy`, `xarray` already present).
- Phase 7D: `geopandas`, `shapely` — coastline / cyclone-track / basin-outline
  overlays for the UI **only**; the frozen basin evaluation boxes do not change.
- Phase 8A / 8B: nothing new — `copernicusmarine`, `earthaccess`, `requests`,
  `certifi` are already present from Phase 6C-D.
- **Not added:** `xesmf` (§5.6.2 note 1), `redis` (note 2), `psycopg2` /
  PostgreSQL (note 3), `scikit-learn` (note 5).

**Frontend (`web/package.json` or similar, created in Phase 7B):**

`react`, `react-dom`, `typescript`, `vite`, `tailwindcss`, `@radix-ui/*` +
`shadcn/ui` components, `cesium` + `vite-plugin-cesium` (or `resium`),
`plotly.js` + `react-plotly.js`, `vitest` + `@testing-library/react`. Bundle a
small offline base-imagery asset for Cesium (no Ion token). Lazy-load Cesium and
Plotly.

Pin versions and record them in each phase report. Keep the frontend in a single
new directory (e.g. `web/`) served in development by Vite and in the demo either
by Vite preview or as static files behind the FastAPI app.
