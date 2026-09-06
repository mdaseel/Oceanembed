# OceanEmbed — Phase 6B-A Baseline Report
**SIH26066 · INCOIS · L0 climatology + L1 pointwise MLP**
Completed 2026-09-05 · baseline version 6B.1 · every number was produced by executing the code.

**The question this phase answers:** do current surface observations carry information about
subsurface temperature beyond location and the seasonal cycle?
**Answer: yes — strongly in the upper 300 m, peaking at the thermocline, and not at all below 500 m.**

---

## 1. Dataset and split confirmation

Read-only from the frozen Phase 6A.5 stores. Nothing in the raw pipeline, preprocessing, Zarr
stores, canonical grid, splits or GLORYS interpolation was modified.

| Split | Range | Days | Samples used |
|---|---|---|---|
| Train | 2015-01-01 → 2020-12-31 | 2,192 | 24,258,864 |
| Validation | 2021-01-01 → 2021-12-31 | 365 | 4,064,640 |
| **Test (LOCKED)** | 2022-01-01 → 2024-12-15 | 1,080 | 12,022,398 |

Grid 101 × 241 at 0.25°, 11,067 surface-valid cells per day (validity masks are time-invariant in
this dataset, verified). Inputs: `sst, sss, sla, current_u, current_v, wind_u, wind_v, lat, lon,
doy_sin, doy_cos`. Targets: the 15 mandated depths.

**The 0 m target is GLORYS's shallowest level (0.494 m), clamped per the Phase 6A.5 provenance.
It is not a native 0.0 m GLORYS observation.**

## 2. Climatology method (L0)

Truncated Fourier (harmonic) regression in day-of-year, fit independently for every
(lat, lon, depth) on the **training years only**.

`T(d) = a₀ + Σ_{k=1..3} [a_k cos(2πkd/365.25) + b_k sin(2πkd/365.25)]` — 7 coefficients per series,
fit against 2,192 training days, so the system is strongly over-determined (`cond(A'A) = 2.0`).

Chosen over a raw day-of-year mean because six training years give only ~6 samples per calendar
day, which is noisy and produces an artificial 31 Dec → 1 Jan discontinuity. Harmonics are smooth
and exactly periodic by construction, defined for any day including 29 Feb, and three harmonics
resolve the annual cycle plus the semiannual monsoon signal that dominates this basin.
Smoothing was **not** tuned against validation or test.

Verified: recovers a known annual+semiannual signal to < 1e-6; no year-boundary jump; predicts
unseen dates. Cells fitted per depth: 11,855 at 0 m down to 8,974 at 1000 m.
Saved to `outputs/baselines/phase6b_climatology.nc` (20.5 MB).

## 3. MLP architecture (L1)

`11 → Dense256 → ReLU → Dense256 → ReLU → Dense128 → ReLU → 15` — **103,695 parameters**.

Deliberately spatially and temporally blind: one grid cell, one day, no neighbours, no patches, no
previous or future days, no convolution, attention, recurrence or latent embeddings. A test asserts
the pointwise property directly (a row's prediction is unchanged by the other rows in its batch).

**Masked loss.** For each depth, only cells with `target_valid_<d>m` contribute — no gradient, no
denominator elsewhere. Missing targets are never replaced by zero and no sub-seafloor temperature
is invented. The mean is taken **per depth first, then across depths**: a flat mean over valid
entries would bias training toward shallow depths, which have 24.2 M valid samples versus 19.6 M at
1000 m. A test pins this distinction (50.5 vs ~1.98 on a constructed case).

**Depth weighting rule (train statistics only):** targets are standardised per depth using the
training mean/std, so each depth contributes according to its own variability. Without it the
thermocline would dominate — train target std is 2.34 °C at 100 m versus 1.01 °C at 1000 m.

## 4. Training configuration

| | |
|---|---|
| Seed | 20260905 (numpy, torch, random; deterministic algorithms enabled) |
| Optimizer | Adam, lr 1e-3, ReduceLROnPlateau (×0.5, patience 2) |
| Batch size | 8,192 |
| Max epochs / run | 40 / **12** |
| Early stopping | patience 5, **best epoch 7** |
| Best validation loss | 0.16519 (masked MSE, standardised space) |
| Runtime | **21.8 min**, CPU, torch 2.14.0+cpu, 8 threads |
| Gradients | train only | 
| Model selection | validation only |

Loss history is in `outputs/models/phase6b_l1_training.json`. Train loss plateaued at ~0.080 from
epoch 3 while validation sat at 0.165–0.19.

## 5–7. Depth-wise results and skill over climatology — **LOCKED TEST (2022-01-01 → 2024-12-15)**

| Depth (m) | RMSE L0 | RMSE L1 | NRMSE L0 | NRMSE L1 | Corr L0 | Corr L1 | **Improvement** |
|---|---|---|---|---|---|---|---|
| 0 | 0.683 | 0.545 | 0.412 | 0.324 | 0.923 | 0.957 | **+20.3 %** |
| 5 | 0.675 | 0.544 | 0.407 | 0.328 | 0.924 | 0.955 | **+19.5 %** |
| 10 | 0.681 | 0.553 | 0.416 | 0.338 | 0.920 | 0.951 | **+18.8 %** |
| 20 | 0.727 | 0.620 | 0.448 | 0.383 | 0.905 | 0.934 | **+14.7 %** |
| 30 | 0.823 | 0.707 | 0.499 | 0.428 | 0.880 | 0.912 | **+14.1 %** |
| 50 | 1.118 | 0.915 | 0.602 | 0.493 | 0.817 | 0.874 | **+18.2 %** |
| 75 | 1.583 | 1.203 | 0.730 | 0.555 | 0.710 | 0.835 | **+24.0 %** |
| **100** | **1.788** | **1.293** | 0.780 | 0.564 | 0.654 | 0.829 | **+27.7 %** ← peak |
| 125 | 1.654 | 1.234 | 0.717 | 0.535 | 0.708 | 0.846 | **+25.4 %** |
| 150 | 1.397 | 1.121 | 0.620 | 0.497 | 0.787 | 0.869 | **+19.7 %** |
| 200 | 0.920 | 0.806 | 0.470 | 0.411 | 0.884 | 0.913 | **+12.4 %** |
| 300 | 0.545 | 0.532 | 0.351 | 0.343 | 0.937 | 0.942 | +2.4 % |
| 500 | 0.358 | 0.374 | 0.295 | 0.308 | 0.956 | 0.956 | **−4.5 %** |
| 700 | 0.359 | 0.364 | 0.293 | 0.297 | 0.956 | 0.955 | **−1.4 %** |
| 1000 | 0.382 | 0.383 | 0.374 | 0.375 | 0.928 | 0.927 | **−0.3 %** |

**L1 beats L0 at 12 of 15 depths. It loses at 500 m, 700 m and 1000 m.**

Depth groups (test):

| Group | Depths | RMSE L0 → L1 | Corr L0 → L1 | NRMSE L0 → L1 |
|---|---|---|---|---|
| Surface / mixed layer | 0, 5, 10 | 0.680 → **0.547** | 0.923 → 0.955 | 0.410 → 0.330 |
| Upper thermocline | 20, 30, 50 | 0.901 → **0.754** | 0.869 → 0.907 | 0.515 → 0.433 |
| **Thermocline** | 75, 100, 125 | 1.677 → **1.244** | 0.691 → 0.837 | 0.742 → 0.551 |
| Intermediate | 150, 200, 300 | 1.018 → **0.856** | 0.869 → 0.908 | 0.481 → 0.418 |
| **Deep** | 500, 700, 1000 | 0.366 → **0.374 (worse)** | 0.947 → 0.946 | 0.320 → 0.326 |

**Validation (2021) vs locked test agree closely** — 100 m improvement 31.0 % → 27.7 %, anomaly
correlation 0.701 → 0.685. No sign of the model having been over-fitted to validation.

## 8. Anomaly skill

Anomalies are defined against the **same train-only climatology** for both truth and prediction.
This is the test that separates "reproduces the seasonal cycle" from "predicts departures from it".

| Depth (m) | 0 | 5 | 10 | 20 | 30 | 50 | 75 | **100** | 125 | 150 | 200 | 300 | 500 | 700 | 1000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Anomaly corr (test) | 0.650 | 0.635 | 0.620 | 0.547 | 0.518 | 0.560 | 0.641 | **0.685** | 0.668 | 0.628 | 0.557 | 0.355 | 0.249 | 0.250 | 0.230 |

This is the central scientific result. Surface observations carry **genuine day-to-day information**
about the upper ocean — anomaly correlation ~0.65–0.69 through the thermocline — and **very little**
below 300 m, where it collapses to ~0.23–0.25.

## 9. Arabian Sea vs Bay of Bengal (diagnostic only)

RMSE improvement of L1 over L0 on the locked test:

| Depth (m) | Arabian Sea | Bay of Bengal |
|---|---|---|
| 0 | +26.4 % | +7.2 % |
| 10 | +25.6 % | +5.5 % |
| 30 | +19.0 % | +7.0 % |
| 50 | +18.2 % | +20.3 % |
| 75 | +19.6 % | **+30.3 %** |
| 100 | +20.4 % | **+35.0 %** |
| 125 | +18.8 % | **+32.9 %** |
| 150 | +16.4 % | +24.7 % |
| 300 | +3.0 % | +2.4 % |
| 500 | −5.2 % | −8.0 % |
| 700 | +0.5 % | −12.1 % |
| 1000 | +0.6 % | −5.6 % |

A clear and reproducible asymmetry (same pattern in validation):

- **At the surface the Arabian Sea gains far more** (+26 % vs +7 %). The Bay of Bengal's surface
  climatology is already very good (RMSE 0.50–0.53 °C vs 0.75–0.76 in the Arabian Sea) — consistent
  with the freshwater-capped barrier layer holding BoB surface temperature close to its seasonal
  mean, leaving little for surface observations to add.
- **At the thermocline the Bay of Bengal gains far more** (+35 % vs +20 % at 100 m). BoB
  climatology is much worse there (RMSE 2.21 vs 1.45 °C), i.e. more thermocline variability that
  the seasonal cycle misses and that surface fields evidently do see.

This is a diagnostic observation, not Experiment A. It does not test cross-basin transfer, and the
lat/lon inputs mean basin identity is directly available to the model — the confound that Phase 5.1
flagged. Nothing here should be read as evidence about generalisation.

## 10. Representative profiles

`outputs/figures/profiles_truth_clim_mlp.png` and `..._test.png` — GLORYS truth vs L0 vs L1 at four
locations (Arabian Sea, Bay of Bengal, Equatorial Indian Ocean, N. Arabian Sea). All three curves
follow the same physical shape; L1 tracks truth more closely through the thermocline, and the three
converge below ~500 m, which is the same story the metrics tell.

## 11. Failures and unexpected findings

**1. A real evaluation bug, caught by the locked test.** `_read_block` drops rows whose features
are not all finite, but the evaluator indexed the climatology as if `n_times × n_cells` rows always
survived. Validation dropped **0** rows so it passed silently; the test split dropped **12** and the
run crashed on a shape mismatch. Fixed by returning row-level time/cell indices and indexing the
climatology by the surviving rows. Validation results were re-run and are **numerically identical**,
confirming the bug never affected them. A regression test now constructs a block with a dropped row
and asserts the alignment. Had the assumption held on both splits by luck, this would have produced
silently wrong L0 numbers.

**2. Train/validation loss gap.** Train loss plateaued at ~0.080 while validation sat at ~0.165 — a
2× gap. Because train loss stopped falling, this looks more like a genuine year-to-year distribution
difference than memorisation, and the close validation↔test agreement supports that. Not resolved
here; worth watching when spatial context is added.

**3. L1 is worse than climatology in the deep ocean.** −4.5 % at 500 m, −1.4 % at 700 m, −0.3 % at
1000 m. Reported as found: at those depths the model should not be used in place of climatology.

**4. Basin asymmetry** (§9) — unexpected in its size and direction-flip between surface and
thermocline.

**5. The deep-ocean low-RMSE trap — stated explicitly, as required.**
Deep RMSE is the **lowest of any depth** (0.358–0.382 °C at 500–1000 m versus 1.29 °C at 100 m).
Taken alone that looks like the model's best performance. It is not:

| | 100 m | 500 m | 1000 m |
|---|---|---|---|
| RMSE (°C) | 1.293 | **0.374** | 0.383 |
| NRMSE | 0.564 | 0.308 | **0.375** |
| Improvement over climatology | **+27.7 %** | **−4.5 %** | **−0.3 %** |
| **Anomaly correlation** | **0.685** | **0.249** | **0.230** |

Low deep RMSE is a **low-variance artifact**, exactly as Phase 3 predicted. The deep ocean barely
changes, so the seasonal climatology is already almost right and the small absolute error reflects
weak natural variability rather than skill. On the three measures that matter — normalised error,
improvement over climatology, and anomaly correlation — the deep ocean is where L1 performs
**worst**, not best.

## 12. Leakage audit

| Check | Status |
|---|---|
| Climatology fitted on train only | ✅ metadata `fitted_on=train`, `fit_start/end` = 2015-01-01/2020-12-31, asserted at fit time and in tests |
| Feature scaler fitted on train only | ✅ `fitted_on=train`, meta start/end = train bounds, tested |
| Target scaler fitted on train only | ✅ same, and masked so absent depths never contribute |
| Gradient updates | ✅ train split only |
| Model selection / early stopping / LR | ✅ validation only |
| Test set during development | ✅ never opened — `open_split("test")` raises `PermissionError` without `allow_test=True` |
| Test evaluated once, after freezing | ✅ single run, after architecture, normalisation, climatology, training and metrics were fixed |
| Target among the inputs | ✅ no `temp_*` in `FEATURE_NAMES`, tested |
| Future-day leakage | ✅ each row carries only its own day's surface values, tested against the source array |
| Cross-sample leakage | ✅ pointwise property tested directly |
| Split boundaries | ✅ non-overlap and strict ordering tested; boundary dates (2021-12-31 vs 2022-01-01) tested |

Two independent guards ran inside the fit scripts themselves: `contains_test_dates()` assertions on
the climatology and scaler fits, and an assertion that train strictly precedes validation.

## 13. Test results

**95 passed** — 28 Phase 6A + 23 Phase 6A.5 + **44 new Phase 6B**. No regression in any earlier test.

New coverage: split separation and ordering, test-lock enforcement, leakage detection at split
boundaries, cyclic day-of-year continuity/unit-circle/periodicity, climatology recovery of a known
signal, climatology periodicity and extrapolation to unseen dates, train-only provenance of
climatology and both scalers, streaming-moment correctness and mask respect, zero-variance channel
handling, model output width, pointwise (no cross-sample) property, masked-loss hand-computation,
fully-masked depth, NaN-safety, zero gradient on masked entries, the shallow-vs-deep weighting
property, dataset shapes, `surface_input_valid` handling, retention of shallow cells lacking deep
targets, no NaN features or unmasked NaN targets, lat/lon feature correctness, no-future-leakage,
target-not-in-features, metric correctness against numpy, NRMSE definition, masked metrics, skill
sign in both directions, anomaly definition, basin disjointness, checkpoint round-trip equality,
deterministic inference, seeded reproducibility, and the row-alignment regression from §11.

## 14. Recommendation

# GO

Against the stated gate:

| Criterion | Result |
|---|---|
| Implementation leakage-free | ✅ §12, enforced in code and tests, not just by convention |
| Training stable | ✅ smooth convergence, early stopping at epoch 7; validation and locked test agree closely |
| Meaningful skill beyond climatology over a useful portion of the profile | ✅ **+12 % to +28 % RMSE over 0–200 m**, peaking at the thermocline; anomaly correlation 0.55–0.69 through the same range |
| Results justify testing spatial context | ✅ see below |

**Why spatial context is the right next step, specifically.** The skill peak sits exactly at
75–125 m, where thermocline depth is set by mesoscale eddies and wave dynamics — processes that are
*spatially structured* and only partially visible in a single cell's SSH and SST. A pointwise model
already extracts anomaly correlation ~0.69 there; the residual is plausibly where spatial context
helps most. Conversely the deep ocean (≥ 500 m) shows no pointwise skill at all, and there is no
evidence here that spatial context would change that — it should not be assumed.

**The bar the Satellite Embedding Engine must clear** is now concrete, not rhetorical: beat
+27.7 % RMSE improvement and 0.685 anomaly correlation at 100 m on the locked test, without
degrading the 0–50 m range where L1 already achieves +14 % to +20 %.

**Carry forward as open items:** the train/validation gap (§11.2), L1's deep-ocean deficit (§11.3),
and the basin asymmetry (§9) — which should be revisited with the coordinate-free anomaly design
from Phase 5.1 before any cross-basin claim is made.

---

**Phase 6B-A is complete. L0 vs L1 results are ready. GO/INVESTIGATE: GO.**
**Do you want me to proceed to the Satellite Embedding Engine phase?**

STOP — L2 spatial encoder, L3 temporal encoder, EOF decoder, uncertainty, D26, TCHP, cyclone
evaluation, Argo validation, NRT experiments and frontend are all not started.
