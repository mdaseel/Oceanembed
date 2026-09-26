# OceanEmbed — Scientific & Disaster Intelligence Expansion: Pre-registration

**Frozen 2026-09-14, before any attribution, occlusion, SST-only, physical-QA,
coastal, stress-test, RI or thermal-extreme result existed.** Every method,
threshold, date set and sampling rule below is fixed from this point. If a
result is disappointing it is reported, not re-analysed.

Production model: frozen L2, state-dict `b715bb2b…ae728d`, encoder
`30cfd2db…4808`, checkpoint file `81979a65…6e35`. None of the experiments below
writes to a production artefact, the replay cache, the Phase 7D thresholds, the
scalers or the L0 climatology. New artefacts live under `outputs/science/`,
`outputs/models/science/` and `outputs/tables/science/`.

Protected: **2024 Argo is not opened** by anything here.

Input channels: **seven** surface channels in the frozen order
`sst, sss, sla, current_u, current_v, wind_u, wind_v`, plus the validity-mask
plane the encoder reads (not a physical channel, never attributed or ablated).

---

## 1. Channel attribution (Model Science → Attribution)

- **Method:** Integrated Gradients (Sundararajan, Taly & Yan 2017), implemented
  directly in PyTorch (no third-party attribution library).
- **Input:** the unmodified standardised padded field for the requested date,
  exactly as `day_field` builds it; only the receptive-field patch (patch × patch,
  the frozen receptive field) centred on the requested cell influences that
  cell, so attribution is computed on that patch.
- **Baseline:** the seven data planes set to **0 in standardised space** (the
  training mean — the same neutral value the frozen pipeline already uses for
  missing input). The mask plane and the decoder context (lat, lon, day of year)
  are held at their actual values.
- **Steps:** 64, midpoint Riemann sum. The completeness residual
  `|Σ attributions − (F(x) − F(baseline))|` is reported per depth.
- **Units:** °C per output depth (standardised attribution × frozen target-scaler
  σ for that depth; the inverse transform is affine).
- **Reported per depth × channel:** signed net attribution (sum over the patch),
  gross magnitude (sum of absolute values over the patch), and the normalised
  gross share across the seven channels.
- **Wording:** "model sensitivity / attribution". Never causal.
- **Cache identity:** model hash, date, row, col, method, steps, baseline, analysis
  version.

## 2. Channel occlusion sensitivity (Model Science → Ablation)

- **Inference-time, frozen model.** For each of the seven channels separately,
  that channel's data plane is set to 0 in standardised space (training mean);
  every other plane and the mask are untouched; the frozen whole-field forward
  is run again.
- **Reported:** ΔT(depth) = T_occluded − T_original at the selected cell;
  domain median |ΔT| per depth over display-valid cells (surface input valid AND
  bathymetric support); ΔTCHP at the cell, recomputed with the frozen Phase 7C
  `d26_tchp` from the occluded profile only.
- Never stored as, or served as, a production field.
- **Displayed beside** the already-published retrained leave-one-group-out
  Experiment D (Architecture Closure, validation 2021) with its 1.66 % noise
  floor. The two answer different questions: occlusion measures what the frozen
  model *uses*; retraining measures what information is *recoverable* without a
  group.

## 3. SST-only experimental baseline (optional)

- Same protocol as Experiment D (patch 33, latent 32, 136,335 parameters, Adam
  1e-3, ReduceLROnPlateau 0.5/2, max 15 epochs, patience 4, seed 20260905, TRAIN
  2015–2020 gradients, VALIDATION 2021 selection), same sampler and target cache.
- **Only change:** the six non-SST data planes are set to 0 in standardised space
  for training and validation. Identical architecture and input width, so the
  comparison isolates information content.
- **Evaluation:** 2021 validation, identical population, physical °C, against
  FROZEN_L2 and the matched full-input control D_CONTROL_ALL. RMSE, anomaly
  correlation (vs L0), skill vs L0 per depth; key depths 50, 75, 100, 125, 150 m.
  Differences inside the Experiment D noise floor (1.66 %) are reported as
  indistinguishable.
- Test split not opened; no Argo read; production L2 untouched whatever the
  result.

## 4. Physical plausibility QA (Model Science → Physical QA)

- **Dates:** every 7th day from 2021-01-01 (validation) and from 2023-01-01
  (test-grid benchmark, already inspected in Phase 6B): 53 + 53 dates. 2024
  excluded.
- **Cells:** surface input valid, ocean, and levels used only while
  `local_water_depth ≥ level` (ETOPO artefact) and the GLORYS target is valid at
  that level, contiguously from the top — the same support for reconstruction
  and reference.
- **No mandatory-monotonic rule.** Diagnostics per profile:
  vertical gradient `(T[k+1]−T[k])/(z[k+1]−z[k])` for each supported level pair;
  **inversion** = warming with depth by more than **0.1 °C** between adjacent
  supported levels; **strong inversion** > 0.5 °C; maximum inversion magnitude;
  strongest cooling gradient and its mid-depth.
- **Reference:** GLORYS target at the same cells, levels and dates; and the
  2022–2023 Argo collocation already on disk (observed vs collocated L2, levels
  where both are finite).
- **Metrics:** inversion frequency per level pair and per depth band
  (0–50, 50–150, 150–300, 300–1000 m); strongest-gradient distribution; the
  fraction of reconstructed profiles whose strongest cooling gradient lies inside
  the reference [p1, p99] envelope; the fraction steeper than the reference p99.
  Reported for NIO, Bay of Bengal, Arabian Sea (frozen `BASINS` boxes).
- **No single physics score.**

## 5. Coastal context

- **States / provinces:** Natural Earth 1:10m Admin-1 (public domain), release
  recorded by file hash.
- **Indian districts:** geoBoundaries gbOpen IND ADM2 (ODbL 1.0; source
  lgdirectory.gov.in via Pathways Data), recorded by file hash. District context is
  reported only for Indian coasts.
- **Rule:** for each ocean grid cell, the nearest Admin-1 polygon (its nearest
  point is on that unit's coast), distance to that point in km (haversine), and —
  when that unit is Indian — the nearest district polygon, reported only when its
  nearest point is within 10 km of the state's nearest point. Precision is the
  0.25° cell centre (±~14 km).
- **Wording:** geographic exposure context only. No "at risk", no damage claim.

## 6. Historical-track stress test

- Geometry: the event's IBTrACS fixes exactly as stored in the event asset —
  **not translated, rotated, re-timed or resampled beyond the frozen 10 km
  sampler.**
- Sampled against (a) the historical reconstruction on the event's peak date and
  (b) the latest qualified field (D26 withheld), with the existing track sampler
  and section code. Differences are latest − historical.
- Permanent label: **REPLAYED HISTORICAL GEOMETRY — NOT A FORECAST OR
  PREDICTION.** No intensity, no recurrence claim.

## 7. Retrospective rapid-intensification study

**Exploratory. Not a predictor; no classifier; no probability.**

- **Source:** IBTrACS v04r01 North Indian file (hash recorded).
- **Intensity:** `NEWDELHI_WIND` (IMD 3-min sustained, kt). Sensitivity:
  `USA_WIND` (JTWC 1-min), reported separately.
- **Storms:** seasons 2015–2024 with at least one IMD fix ≥ 34 kt.
- **Eligible 24-h pair:** two fixes exactly 24 h apart, both with IMD wind, both
  over water (`DIST2LAND > 0`), both inside 5–30 °N, 45–105 °E; the sampling date
  (below) inside 2015-01-01…2024-12-15 with surface input available.
- **ΔV24** = V(t+24 h) − V(t). **RI pair:** ΔV24 ≥ 30 kt. **RI storm:** any
  eligible RI pair. Storms with no eligible pair are excluded with that reason.
- **Thermal sampling (per storm):** the eligible pair with the largest ΔV24
  (ties → earliest). Field: the reconstruction valid on **date(t) − 1 day**
  (reduces self-induced cold-wake contamination). Path: the IBTrACS positions from
  t to t+24 h, resampled every 10 km by the frozen sampler. Variables: along-path
  length-weighted mean TCHP (**primary**); D26 (historical, physically
  supported); temperature and anomaly at 50, 75, 100 m (secondary); fraction of
  path length in HIGH thermal support.
- **Statistics:** group medians and IQR; two-sided Mann–Whitney U; Holm
  adjustment across the 8 variables; rank-biserial effect size; bootstrap 95 % CI
  of the difference in medians (2,000 resamples, seed 20260914, resampling
  storms). If either group has fewer than 5 storms, descriptive only (no p).
- **Split disclosure:** 2015–2020 reconstructions are in-sample for L2. A
  sensitivity restricted to 2021–2024 storms is reported.
- Wording: **retrospective association**. A null result is reported as such.

## 8. Subsurface thermal extremes vs. marine heatwaves

**Protocol decision, made before computing anything:** the formal Hobday et al.
(2016) marine-heatwave definition requires a climatological baseline of
preferably ≥ 30 years of daily data. This record holds 6 training years
(2015–2020) of reconstructions, and subsurface MHW definitions are not
standardised. **The feature is therefore named SUBSURFACE THERMAL EXTREME, not
MARINE HEATWAVE.**

- **Baseline:** frozen-L2 reconstructions 2015-01-01…2020-12-31 (OceanEmbed's own
  field, the same philosophy as the frozen TCHP thresholds), depths 0, 50, 75,
  100, 125, 150 m.
- **Threshold:** per cell, depth and day of year, the 90th percentile of all
  baseline values within ±5 days (11-day window, all years), then a 31-day
  circular moving mean (Hobday structure).
- **Event:** ≥ 5 consecutive exceedance days; gaps ≤ 2 days joining two ≥ 5-day
  runs are bridged. Evaluated on a **trailing** window ending on the requested
  date (no future days used); duration reported as "so far".
- **Reported only where computed:** exceedance (°C above threshold), percentile
  of the value within the baseline window samples, duration so far, spatial
  extent (lat-aware km²) per basin.
- Historical dates only; the latest mode does not have enough consecutive
  qualified days and says so.

## 9. Validation context

Display of existing Phase 6C Argo 2022–2023 results by nearest standard depth and
basin: L2, L0, L1, GLORYS RMSE; improvement vs L0; anomaly correlation; n; paired
bootstrap CI where computed. Labelled **expected historical validation error /
validation context**, never a calibrated uncertainty interval.
