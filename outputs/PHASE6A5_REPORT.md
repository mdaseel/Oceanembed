# OceanEmbed — Phase 6A.5 Final Report
**SIH26066 · INCOIS · Model-ready multi-year dataset**
Completed: 2026-09-05 · Pipeline version 6A.1 · Every number below was produced by executing the pipeline.

---

## 1. Exact products used

All dataset IDs were verified against the live provider catalogues before download. Nothing is quoted from memory or from the prompt without checking.

| Channel | Product | Dataset ID | DOI | Var | Native res | Coverage |
|---|---|---|---|---|---|---|
| `sst` | OSTIA L4 REP | `METOFFICE-GLO-SST-L4-REP-OBS-SST` | 10.48670/moi-00168 | `analysed_sst` | 0.05°, daily | 1981-10-01 → 2026-03-31 |
| `sss` | **MULTIOBS Global Ocean SSS** | `cmems_obs-mob_glo_phy-sss_my_multi_P1D` | 10.48670/moi-00051 | `sos` | 0.125°, daily | 1993-01-01 → **2024-12-15** |
| `sla` | DUACS L4 (C3S two-sat) | `c3s_obs-sl_glo_phy-ssh_my_twosat-l4-duacs-0.25deg_P1D` | 10.48670/moi-00145 | `sla` | 0.25°, daily | 1993-01-01 → 2026-01-16 |
| `current_u/v` | OSCAR L4_OC_FINAL v2.0 | `OSCAR_L4_OC_FINAL_V2.0` | 10.5067/OSCAR-25F20 | `u`, `v` | 0.25°, daily | → 2025 |
| `wind_u/v` | CCMP v3.1 | `CCMP_WINDS_10M6HR_L4_V3.1` | 10.5067/CCMP-6HW10M-L4V31 | `uwnd`, `vwnd` | 0.25°, 6-hourly | → 2025 |
| target | GLORYS12V1 | `cmems_mod_glo_phy_my_0.083deg_P1D-m` | 10.48670/moi-00021 | `thetao`, 36 levels 0.494–1062 m | 1/12°, daily | 1993-01-01 → 2026-06-23 |

**Two corrections to the prompt's assumptions**, both verified against the catalogue:
- The SSS variable is **`sos`**, not `sss`. The product also carries `dos` (density), which was deliberately **not** requested.
- The product ID is `MULTIOBS_GLO_PHY_S_SURFACE_MYNRT_015_013`, not the one guessed in the prompt. The **DOI matches the PS exactly**.

## 2. Final common window

**`DATASET_START = 2015-01-01`, `DATASET_END = 2024-12-15` → 3,637 days.**

`DATASET_END` is **not a preference — it is a hard product limit.** The official multi-year SSS reanalysis stops at 2024-12-15; every other product extends well beyond it (OSTIA to 2026-03, DUACS to 2026-01, GLORYS to 2026-06, OSCAR/CCMP into 2025). Your target date and the binding constraint coincide exactly. This attribution is recorded in `config/data_splits.yaml` under `end_determined_by` and locked by a test, so no later phase can "extend" the window by guessing.

## 3. Data splits — `config/data_splits.yaml`

| Split | Range | Days |
|---|---|---|
| Train | 2015-01-01 → 2020-12-31 | 2,192 |
| Validation | 2021-01-01 → 2021-12-31 | 365 |
| **Test (LOCKED)** | 2022-01-01 → 2024-12-15 | 1,080 |
| **Total** | | **3,637** |

No boundary change was needed. Tests assert non-overlap, contiguity, correct day counts, coverage of the full window, and `locked: true`. The file also carries explicit no-leak rules (fit all statistics on train only; test opened once, at the end).

## 4. Download and storage

| Product | Years | Raw size |
|---|---|---|
| GLORYS | 10/10 | 60,501 MB |
| OSTIA | 10/10 | 4,648 MB |
| CCMP | 10/10 | 2,731 MB |
| SSS MULTIOBS | 10/10 | 1,487 MB |
| OSCAR | 10/10 | 681 MB |
| DUACS | 10/10 | 373 MB |
| **Raw total** | | **70 GB** |
| **Processed** | 10 stores | **4.7 GB** |

Copernicus: `ok=39 skipped=1 failed=0`. PO.DAAC: `ok=19 skipped=1 failed=0`. **Zero failed downloads.** 104 GB free afterwards.

**The OPeNDAP decision was the difference between feasible and not.** CCMP and OSCAR are published only as global daily files (~32 MB/day each); our domain is 2.6 % of the globe. Measured against real granules before committing:

| | Full global | DAP4 server-side subset | Transferred |
|---|---|---|---|
| CCMP | 32.0 MB/day | 0.84 MB/day | 2.6 % |
| OSCAR | 31.7 MB/day | 0.24 MB/day | 0.8 % |

**3.4 GB moved instead of ~233 GB — a 68× reduction.** Per your instruction the fetcher has **no fallback** to whole-granule download; it aborts and reports instead. Index ranges are discovered from each product's own coordinate axes, which mattered: OSCAR's variables are `(time, longitude, latitude)` while CCMP's are `(time, latitude, longitude)`, so a fixed slice order would have silently transposed one product.

**Retried / recovered:** one interruption killed both downloaders mid-run; all completed years were skipped on resume and only the in-flight year re-fetched. One orphaned 6.4 GB temp file was left locked by Windows and later released. No corrupt file was ever promoted — only a file that opens with the expected day count is atomically renamed to its final name.

## 5. SSS migration

**Old (retired):** SMAP JPL L3 CAP v5.0, 8-day running mean, supplied in the archive.
**New (in use):** `cmems_obs-mob_glo_phy-sss_my_multi_P1D` (`sos`), DOI 10.48670/moi-00051, genuinely daily.

Comparison on the overlapping smoke-test dates (`outputs/tables/sss_product_comparison.csv`, figure `08_sss_product_comparison_2020-01-01.png`):

| Metric | 2020-01-01 | 2020-01-02 |
|---|---|---|
| Correlation | 0.9637 | 0.9637 |
| RMSE (PSU) | 0.577 | 0.572 |
| Mean difference (new − old) | −0.189 | −0.179 |
| Spatial std, old → new | 2.036 → 2.099 | 2.032 → 2.093 |
| Mean spatial gradient, old → new | 0.142 → 0.100 | 0.142 → 0.103 |
| % missing, old → new | 55.9 → **51.7** | 55.9 → **51.7** |

The replacement resolves slightly *more* large-scale variance while being *smoother* at the pixel scale, and covers 4.2 percentage points more of the domain. That pattern is consistent with the L4 analysis suppressing SMAP retrieval noise — plausible, but two days cannot prove noise-vs-signal, so it is reported as an observation, not a conclusion.

**Confirmed in use:** every model-ready store records `source_sss = cmems_obs-mob_glo_phy-sss_my_multi_P1D … 10.48670/moi-00051`, and a test asserts the string `SMAP` cannot appear there.

**A hidden trap:** the new product carries a singleton `depth` axis at 0.0 m. It is squeezed with an assertion that the axis really is size-1 — a blind squeeze would have silently mangled a future multi-level product.

## 6. All 15 GLORYS depths — `outputs/tables/glorys_depth_interpolation_15.csv`

36 native levels available (0.494 → 1062.44 m).

| Requested (m) | Native below | Native above | Method |
|---|---|---|---|
| 0 | 0.494 | 0.494 | **CLAMPED** |
| 5 | 3.819 | 5.078 | linear |
| 10 | 9.573 | 11.405 | linear |
| 20 | 18.496 | 21.599 | linear |
| 30 | 29.445 | 34.434 | linear |
| 50 | 47.374 | 55.764 | linear |
| 75 | 65.807 | 77.854 | linear |
| 100 | 92.326 | 109.729 | linear |
| 125 | 109.729 | 130.666 | linear |
| 150 | 130.666 | 155.851 | linear |
| 200 | 186.126 | 222.475 | linear |
| 300 | 266.040 | 318.127 | linear |
| 500 | 453.938 | 541.089 | linear |
| 700 | 643.567 | 763.333 | linear |
| 1000 | 902.339 | 1062.440 | linear |

**14 of 15 are true interpolations between bracketing levels. Only 0 m is clamped**, to the shallowest native level 0.494 m, because GLORYS has no shallower data. Every store records this in `depth_0m_policy`, and a test asserts both the word `CLAMPED` and the value `0.494` appear there — so it can never later be described as a native GLORYS 0 m level.

## 7. Canonical grid

Unchanged from Phase 6A and re-derived programmatically, not hard-coded:
**101 latitudes × 241 longitudes = 24,341 cells**, lat 5.0→30.0 °N ascending, lon 45.0→105.0 °E, 0.25° uniform, `[-180,180)` convention.

## 8. Validity masks

Two concepts kept **strictly separate**, because conflating them silently destroys the continental shelf:

- **`ocean_mask`** — is this cell ocean at all? Defined by whether the GLORYS target exists at the **surface** level. Deliberately *not* defined by deep-water validity. **48.7 % of grid cells.**
- **`target_valid_<d>m`** — does a training target exist at *this* depth here? One mask per depth, 15 total.
- **`surface_input_valid`** — all seven surface predictors present. **45.5 %.**

Measured validity as a fraction of ocean cells:

| Depth | Valid | | Depth | Valid |
|---|---|---|---|---|
| 0 m | 100.0 % | | 125 m | 81.9 % |
| 5 m | 100.0 % | | 150 m | 81.5 % |
| 10 m | 96.9 % | | 200 m | 80.8 % |
| 20 m | 94.5 % | | 300 m | 80.1 % |
| 30 m | 91.7 % | | 500 m | 78.7 % |
| 50 m | 87.7 % | | 700 m | 77.7 % |
| 75 m | 84.2 % | | 1000 m | 75.7 % |
| 100 m | 82.4 % | | | |

**A naive "drop any cell missing a depth" rule would have discarded 24 % of all ocean cells — the entire shelf.** Those cells are retained with per-depth masks so future training can mask the loss by depth. Nothing is invented below the seafloor and no vertical extrapolation is performed. A test asserts validity never *increases* with depth, which would be the signature of fabricated sub-seafloor values.

## 9. Multi-year QC — `outputs/tables/multiyear_qc_by_year.csv`

**Calendar: 0 missing days and 0 duplicate timestamps in all ten years.** Day counts 365/366 per year, 350 for 2024 (ends Dec 15) — **3,637 total, exact match** to the configured window.

Missingness is remarkably stable across the decade (min / median / max across years):

| Variable | Missing % | | Variable | Missing % |
|---|---|---|---|---|
| sst | 51.60 / 51.60 / 51.60 | | temp_0m | 51.30 (constant) |
| sla | 51.47 (constant) | | temp_100m | 59.89 (constant) |
| sss | 52.09 / 52.10 / 52.17 | | temp_1000m | 63.13 (constant) |
| wind_u/v | 51.30 (constant) | | current_u/v | 53.54 / 54.23 / 54.53 |

Missingness rises monotonically with depth (51.3 % → 63.1 %) exactly as bathymetry requires.

Value ranges across the full record are physical: `sst` 12.11–36.59 °C, `sss` 24.62–40.03 PSU, `sla` −0.46–0.71 m, winds ±26 m/s, `temp_1000m` 4.11–14.00 °C, and the domain-mean profile decreases monotonically with depth at every level.

**Homogeneity — `outputs/tables/multiyear_homogeneity_flags.csv`:** the detector flagged 10 year-to-year steps at ≥4σ, but **every one is a false positive from an over-sensitive robust scale**, and I am reporting them rather than tuning the threshold to hide them:

| Flag | Step | Absolute meaning |
|---|---|---|
| `current_u` mean | 0.005 m/s (12σ) | trivial interannual variation in a basin-mean current |
| `sss` pct_missing | 0.09 pp (53σ) | nine-hundredths of a percentage point |
| `temp_1000m` mean | 0.09 °C (5σ) | real deep-ocean interannual variability |

The σ values are tiny (0.00066 m/s, 0.0017 pp) precisely *because* the record is so consistent, so ordinary variation trips the test. **No product-version transition, resolution change, variable rename, or unexpected missing period was found.**

## 10. GLORYS suspicious values — the Phase 6A shelf-break issue, resolved

Phase 6A found a handful of negative temperatures near the Gulf of Aden and I guessed they were "isolated boundary artifacts." **That guess was wrong**, and the full record settles it.

**Finding A — the defect is persistent, not episodic.** `outputs/tables/glorys_native_persistent_defect.csv`

In **native** GLORYS, 2 cells (15.0 °N, 50.583/50.667 °E) at 3 depths (318, 380, 454 m) are corrupted on **every single day of all ten years**:

| Cell | Depth | Days affected | Pinned at 0.0001 | Min °C |
|---|---|---|---|---|
| 50.583 °E | 318 m | 3,525 / 3,637 | 13 | −2.36 |
| 50.583 °E | 380 m | **3,637 / 3,637** | 3,483 | −3.00 |
| 50.583 °E | 454 m | **3,637 / 3,637** | 3,606 | −3.00 |
| 50.667 °E | 318 m | 3,548 / 3,637 | 24 | −2.37 |
| 50.667 °E | 380 m | **3,637 / 3,637** | 3,479 | −3.00 |
| 50.667 °E | 454 m | **3,637 / 3,637** | 3,596 | −3.00 |

21,621 native values below 3 °C in total, ~14,200 pinned at exactly `0.0001`. **Classification: provider fill leakage at a steep bathymetric boundary — a permanent defect in GLORYS12V1, not a processing error of ours.**

**Finding B — it does not reach the model-ready dataset.** The two bad cells lie between canonical grid points and are surrounded by NaN, so linear regridding to 0.25° yields NaN rather than blending them in. Verified directly: **0 finite values at that location, and 0 values below 3 °C at 200–1000 m across all 3,637 days.** It is quarantined by NaN propagation, not by clipping — nothing was clipped.

**Finding C — every flag in the model-ready product is real.** `outputs/tables/glorys_suspicious_classified.csv` contains **zero** below-plausible and **zero** near-zero values. All flags are shallow warm extremes (>36 °C at 0/5/10 m), concentrated in the Persian Gulf and Gulf of Oman (24–30 °N, 48–56 °E) — among the hottest sea surfaces on Earth, where such values are genuine. **My 36 °C ceiling is simply too tight for that basin; I left it in place rather than widen it to make flags disappear.**

## 11. Phase 6A regression test — `outputs/tables/phase6a_regression_check.csv`

The scaled pipeline reproduces the Phase 6A smoke-test output on 2020-01-01/02 **exactly**:

| Channel | Mean abs diff | Max abs diff | Coverage mismatch | Verdict |
|---|---|---|---|---|
| sst, sla, current_u, current_v, wind_u, wind_v | **0.000000** | **0.000000** | **0** | PASS |
| temp_0m, temp_50m, temp_100m, temp_500m, temp_1000m | **0.000000** | **0.000000** | **0** | PASS |
| sss | 0.353 | 14.17 | 1,857 | EXPECTED-DIFF |

**Bit-identical across all 11 unchanged channels** — not merely within tolerance. Grid coordinates match exactly. SSS differs by design, and the 1,857 mismatched cells are places where the new product has coverage the old one lacked.

*(An initial run reported all-NaN. That was my own orchestration error — I waited for the `.zarr` directory to exist, but Zarr creates it at the start of writing, so I read the store mid-write. Waiting on build-log completion instead gave the result above. No data was affected.)*

## 12. Model-ready dataset

**Path:** `data/processed/model_ready/oceanembed_<year>.zarr` — 10 stores, 2015 … 2024.

| | |
|---|---|
| Dimensions | `time × lat × lon` = 3,637 × 101 × 241 |
| Surface variables (7) | `sst, sss, sla, current_u, current_v, wind_u, wind_v` |
| Target variables (15) | `temp_0m … temp_1000m` |
| Masks (17) | `ocean_mask`, `surface_input_valid`, `target_valid_<d>m` × 15 |
| Chunking | `time=32, lat=101, lon=241` |
| Total size | **4,979 MB** (~479–502 MB per year) |

**Chunk rationale:** every planned downstream access — temporal windows, spatial patches, regime masks, per-depth loss masking — reads whole maps over a short time span. Keeping lat/lon whole avoids cross-chunk stitching for spatial patches; `time=32` gives ~3 MB float32 chunks, inside Zarr's efficient range. One year is ~11 time-chunks, so no read pulls a year into RAM. Data stays multidimensional — **nothing was flattened to rows**.

Each store embeds source products with DOIs, the time window, domain, target grid, regridding method, vertical method, the 0 m clamp policy, ocean-mask definition, `created_at` and `pipeline_version`.

**Tests: 51 passing** — the original 28 Phase 6A tests still green, plus 23 new ones covering split integrity, the ocean-vs-per-depth mask separation, depth-validity monotonicity, the 0 m clamp record, chunking, and the assertion that the retired SMAP product cannot appear in model-ready metadata.

## 13. Warnings

1. **A permanent GLORYS defect exists** (§10) at 15.0 °N / 50.58–50.67 °E, 318–454 m, on every day of the record. It does not enter the model-ready data, but anyone using **native** GLORYS in a later phase must handle it.
2. **0 m is 0.494 m.** Honest, recorded, tested — but not literally the surface.
3. **OSCAR is not an independent observation.** It is diagnosed from SSH + winds + SST, so `current_u/v` partially duplicates `sla` and `wind_u/v`. Relevant to interpreting feature importance later, not to dataset correctness.
4. **SSS spatial-smoothness change is uncharacterised over the full record.** The old/new comparison covers two days only; the gradient reduction is plausibly denoising but unproven.
5. **The 36 °C suspicious-value ceiling is too tight for the Persian Gulf**, producing real-but-flagged values. Deliberately left unadjusted.
6. **Homogeneity flags are false positives** (§9) — reported rather than suppressed.
7. **Three supplied products could not have supported this window** and were correctly replaced: AVHRR-OI v2.1 starts 2016-01-01, SMAP 8-day starts 2015-04-30, ASCAT MetOp-C starts 2019-10-22. Had the supplied stack been scaled as-is, 2015 would have lacked SST, SSS *and* winds.
8. **Argo remains inventory-only**, per instruction. Raw Argo is trivially scriptable via `argopy`; **INCOIS LAS scriptability is unverified** and may require manual export — the one open question for the validation phase.

## 14. GO / NO-GO for Phase 6B

Checking each of your stated conditions:

| Condition | Result |
|---|---|
| Full surface stack present | ✅ all 7 channels, 3,637 days, no gaps |
| Official SSS used | ✅ `cmems_obs-mob_glo_phy-sss_my_multi_P1D`, DOI 10.48670/moi-00051, SMAP retired and test-blocked |
| All 15 targets produced | ✅ 14 interpolated + 0 m clamped, provenance recorded |
| Date splits explicit | ✅ `config/data_splits.yaml`, test locked |
| Preprocessing passes QC | ✅ 0 missing days, 0 duplicates, 0 real discontinuities |
| Phase 6A regression passes | ✅ **bit-identical** on all 11 unchanged channels |
| No unresolved alignment corruption | ✅ grid identical; the one known defect is characterised and provably quarantined |

# GO — Phase 6A.5 is ready for Phase 6B.

**Reasons.** All seven conditions are met. The regression result is the strongest available evidence that scaling changed nothing: not "within tolerance" but exactly zero difference across every unchanged channel, with zero coverage mismatch. The dataset is real files only — nothing synthesised, no product substituted without being declared and justified. The one genuine data defect in the record was found, characterised across all 3,637 days, classified as provider fill leakage, and *proven* not to propagate. The masks preserve 24 % of ocean cells that a careless pipeline would have deleted. And every judgement call that could have been hidden — the 0 m clamp, the too-tight Persian Gulf threshold, the false-positive homogeneity flags, my own mid-write read error — is reported rather than smoothed over.

**Carried into Phase 6B as known limitations, not blockers:** items 2, 3 and 4 in §13.

---

**STOP.** Phase 6B not started. No model trained, no climatology, no embeddings, no event masks, no D26/TCHP, no Argo collocation, no frontend — awaiting your review.
