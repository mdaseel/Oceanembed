# OceanEmbed — Phase 6A Final Report
**SIH26066 · INCOIS · Real-data pipeline smoke test**
Run date: 2026-09-04 · Pipeline version 6A.1 · All numbers below were produced by executing the pipeline.

---

## 1. Supplied data inventory

### `Ocean embed datas.zip` (369.8 MB)
| Folder | What it actually contained | Dates | Verdict |
|---|---|---|---|
| `sst/` | NOAA/NCEI OISST v2.1 (**AVHRR-OI, not OSTIA**), 0.25°, K | 2019-12-31, 2020-01-01 | superseded by downloaded OSTIA |
| `sss/` | SMAP JPL L3 CAP v5.0, **8-day running mean**, 0.25° | 2019-12-28 → 2020-01-05 (9 files) | **used** |
| `ssh/` | **Misnamed — contains SMOS CATDS L2Q *salinity*, not sea level.** One file stamped 2026-09-02 (corrupt). 86–98 % missing | 2020-01-01/02 | not used |
| `OSCAR/` | OSCAR L4_OC_FINAL v2.0, `u`,`v`,`ug`,`vg`, 0–360° lon, cftime-Julian | 2020-01-01 → 01-08 | **used** |
| `ccmp/` | CCMP v3.1 6-hourly L4 winds | 2020-01-01, 01-02 | **used** |
| `ascat/` | MetOp-C ASCAT-L2-Coastal swaths (L2, ungridded) | 2020-01-01 (7 swaths) | inventoried, not used |
| `Glorys.nc` | GLORYS12V1 `thetao` — **1 depth level only (0.494 m)** | 2020-01-01 → 01-31 | superseded by download |
| `Argo gridded.nc` | INCOIS gridded ARGO, 1°, 19 levels | monthly: 2020-01-15, 02-15 | inventory only |

### `Agro data.zip` (21.9 MB)
31 daily raw Argo GDAC profile files, 2020-01-01 → 2020-01-31, **global** (not domain-subset): 2,841 profiles / 858 floats.

**The archive is January 2020 — Cyclone Fani (April–May 2019) is not in it.**

---

## 2. Files created

**Config & library**
`config/phase6a.yaml` · `src/oceanembed/config.py` · `src/oceanembed/grid.py` · `src/oceanembed/data/loaders.py` · `src/oceanembed/preprocessing/standardize.py` · `src/oceanembed/preprocessing/regrid.py` · `src/oceanembed/validation/sanity.py` · `.gitignore`

**Scripts**
`scripts/inspect/inspect_all.py` · `scripts/inspect/argo_inventory.py` · `scripts/download/fetch_cmems_phase6a.py` · `scripts/preprocess/build_phase6a.py`

**Tests** `tests/test_preprocessing.py` — **28 passed**

**Outputs**
`outputs/data_inventory.md` · `outputs/PHASE6A_REPORT.md` · `outputs/logs/build_phase6a.log` · `outputs/logs/build_phase6a_meta.json` · `outputs/logs/argo_inventory.log`
Tables: `single_cell_proof.csv`, `merged_variable_stats.csv`, `regridding_report.csv`, `glorys_depth_interpolation.csv`, `argo_profile_inventory.csv`, `argo_profile_inventory_in_domain.csv`
Figures: `01_sst`, `02_sss`, `03_sla`, `04_currents`, `05_winds`, `06_glorys_temp100m`, `07_mean_profile` (all `_2020-01-01.png`)

**Data** `data/processed/oceanembed_smoketest_2020_01_dev.zarr` (1.4 MB) + `.nc` (4.3 MB)

---

## 3. Datasets successfully used

| Channel | Product | ID / DOI | Source |
|---|---|---|---|
| `sst` | OSTIA L4 REP | `METOFFICE-GLO-SST-L4-REP-OBS-SST` · 10.48670/moi-00168 | **downloaded** |
| `sss` | SMAP JPL L3 CAP v5.0 8-day | 10.5067/SMP50-3TPCS | supplied archive |
| `sla` | DUACS C3S 0.25° daily | `c3s_obs-sl_glo_phy-ssh_my_twosat-l4-duacs-0.25deg_P1D` · 10.48670/moi-00145 | **downloaded** |
| `current_u/v` | OSCAR L4_OC_FINAL v2.0 (`u`,`v` total) | 10.5067/OSCAR-25F20 | supplied archive |
| `wind_u/v` | CCMP v3.1 6-hourly → daily | 10.5067/CCMP-6HW10M-L4V31 | supplied archive |
| `temp_*m` | GLORYS12V1 `thetao`, 36 levels 0.494–1062 m | `cmems_mod_glo_phy_my_0.083deg_P1D-m` · 10.48670/moi-00021 | **downloaded** |

All three dataset IDs were verified against the live Copernicus catalogue before use; DOIs match the official PS exactly.

**Correction to the research dossier:** §5 listed DOI `10.48670/moi-00145` as DUACS at 0.25° daily. That DOI resolves to `SEALEVEL_GLO_PHY_CLIMATE_L4_MY_008_057` (C3S), whose daily 0.25° dataset is the one above. The other DUACS product (`SEALEVEL_GLO_PHY_L4_MY_008_047`, DOI `moi-00148`) is **0.125°, not 0.25°**. The PDF's DOI was right; the dossier's product/resolution pairing was ambiguous.

## 4. Datasets missing or blocked
**None remaining.** Three gaps existed in the supplied archive and all were closed by targeted download after you authenticated (2 days × one 27°×62° box × one variable each; 2.7 MB + 0.2 MB + 34.9 MB):
1. GLORYS supplied with 1 depth level → downloaded 36 levels (0–1200 m)
2. No sea-level product at all → downloaded DUACS SLA
3. SST was AVHRR-OI not OSTIA → downloaded OSTIA

ASCAT and SMOS remain inventoried but unused (documented, not deleted).

## 5. Common time window
| Product | Dates available |
|---|---|
| sst | 2 (2020-01-01 → 01-02) |
| sss | 9 (2019-12-28 → 2020-01-05) |
| sla | 2 (2020-01-01 → 01-02) |
| currents | 8 (2020-01-01 → 01-08) |
| winds | 2 (2020-01-01 → 01-02) |
| glorys | 2 (2020-01-01 → 01-02) |

**Intersection = 2 days: 2020-01-01, 2020-01-02.** Missing from intersection: none. Requested Fani window 2019-04-25→05-10: **0 days available** — no synthetic data created.

## 6. Canonical grid
Derived programmatically, not hard-coded: **101 latitudes × 241 longitudes = 24,341 cells**
lat 5.0→30.0 °N ascending · lon 45.0→105.0 °E · 0.25° uniform · `[-180,180)` convention.
Ocean cells (GLORYS-defined): **11,855 / 24,341 (48.7 %)**.

## 7. Preprocessing per variable

| Variable | Native → target | Handling |
|---|---|---|
| `sst` | 0.05° → 0.25° | K → °C (−273.15, recorded); linear interp; NaN 51.7 → 50.9 % |
| `sss` | 0.25° → 0.25° | lat **flipped** (source descending); units 1e-3 ≡ PSU; NaN 54.9 → 55.9 % |
| `sla` | 0.25° → 0.25° | no conversion (m); NaN 50.0 → 50.5 % |
| `current_u/v` | 0.25° → 0.25° | lon **0-360 → [-180,180)** + re-sorted; **cftime Julian → datetime64**; dim/coord name mismatch (`latitude` dim vs `lat` coord) repaired; `u`,`v` used **not** `ug`,`vg`; NaN 53.8 → 54.1 % |
| `wind_u/v` | 0.25° → 0.25° | lon **0-360 → [-180,180)**; **4 × 6-hourly → daily mean of U and V independently** — magnitude never substituted; NaN 0 → 0 % |
| `temp_*m` | 1/12° → 0.25° | vertical interp first (below), then linear horizontal |

All timestamps floored to 00:00 UTC (a *labelling* change; no resampling except CCMP's declared daily mean). Land never filled; no extrapolation; no NaN auto-fill.

**Grid registration note:** OSCAR and GLORYS sit on whole 0.25° marks; OSTIA/SMAP/DUACS/CCMP sit on half-cell offsets (…125/…375). The canonical grid matches the former exactly, so OSCAR is near-passthrough while the latter four are genuinely interpolated.

## 8. GLORYS vertical interpolation

36 native levels available (0.494 → 1062.44 m).

| Requested | Native below | Native above | Method |
|---|---|---|---|
| 0 m | 0.494 | 0.494 | **CLAMPED** — 0 m is above the shallowest native level |
| 50 m | 47.374 | 55.764 | linear |
| 100 m | 92.326 | 109.729 | linear |
| 500 m | 453.938 | 541.089 | linear |
| 1000 m | 902.339 | 1062.440 | linear |

A real bug was caught here: the first run returned `temp_0m` 100 % NaN because 0 m fell outside the native range and `interp` produced NaN — which then wiped the entire ocean mask. `bracketing_levels` correctly *declared* the clamp but `interp_depths` never *implemented* it. Fixed by clipping the interpolation position and relabelling, with the clamp recorded in provenance and locked by a test.

## 9. Data quality (merged dataset)

| Variable | min | max | mean | std | % missing |
|---|---|---|---|---|---|
| sst | 16.82 | 30.12 | 27.24 | 1.63 | 51.6 |
| sss | 14.64 | 41.60 | 34.65 | 2.03 | 55.9 |
| sla | −0.283 | 0.383 | 0.066 | 0.091 | 51.5 |
| current_u | −0.936 | 0.731 | −0.042 | 0.176 | 54.2 |
| current_v | −0.881 | 0.723 | 0.048 | 0.178 | 54.2 |
| wind_u | −11.65 | 5.22 | −4.34 | 2.60 | 51.3 |
| wind_v | −9.40 | 6.25 | −2.43 | 2.26 | 51.3 |
| temp_0m | 16.47 | 32.28 | 27.22 | 1.64 | 51.3 |
| temp_50m | 20.08 | 31.22 | 27.02 | 1.64 | 57.3 |
| temp_100m | 17.02 | 29.71 | 22.82 | 2.40 | 59.9 |
| temp_500m | 9.31 | 16.66 | 11.22 | 1.26 | 61.7 |
| temp_1000m | 5.91 | 11.89 | 7.66 | 0.97 | 63.1 |

Checked and clear: no K/°C confusion, no cm/s vs m/s confusion, no all-zero or all-NaN field, no duplicate coordinates, no flipped axis, no longitude wrapping error.
Missing fraction rises monotonically with depth (51 → 63 %) exactly as bathymetry requires.
Mean `wind_u` = −4.34 m/s (easterly) is the correct January NE-monsoon signature.

## 10. Single-cell proof
**2020-01-01 · 13.25 °N · 85.75 °E** (central Bay of Bengal; one of 3,841 fully-populated open-ocean cells)

| Variable | Value | Traced to |
|---|---|---|
| sst | 27.3500 °C | OSTIA `analysed_sst`, K→°C |
| sss | 33.1541 PSU | SMAP `smap_sss` 8-day |
| sla | −0.0036 m | DUACS `sla` |
| current_u | 0.0315 m/s | OSCAR `u` |
| current_v | −0.0952 m/s | OSCAR `v` |
| wind_u | −7.0528 m/s | CCMP `uwnd`, daily mean of 4×6 h |
| wind_v | −0.5317 m/s | CCMP `vwnd`, daily mean of 4×6 h |
| temp_0m | 27.1584 °C | GLORYS, clamped to 0.494 m |
| temp_50m | 27.8223 °C | GLORYS, linear 47.374 / 55.764 m |
| temp_100m | 22.1922 °C | GLORYS, linear 92.326 / 109.729 m |
| temp_500m | 9.5227 °C | GLORYS, linear 453.938 / 541.089 m |
| temp_1000m | 6.2824 °C | GLORYS, linear 902.339 / 1062.440 m |

**Independent cross-check:** OSTIA `sst` 27.35 °C vs GLORYS `temp_0m` 27.16 °C — two entirely independent products agreeing to **0.19 °C** at the same cell/day. This is the strongest available evidence that the spatial and temporal alignment is correct.

**Physical note:** `temp_50m` (27.82) exceeds `temp_0m` (27.16). This is a genuine winter Bay of Bengal **temperature inversion** under the freshwater-driven barrier layer (consistent with `sss` = 33.15, fresher than the Arabian Sea), not an interpolation artifact. It is exactly the barrier-layer physics flagged in Phase 4.

## 11. Diagnostic outputs
Figures (`outputs/figures/`, 2020-01-01): SST · SSS · SLA · currents (magnitude + vectors) · winds (magnitude + vectors) · GLORYS 100 m · mean vertical profile.
Visual verification: the Indian subcontinent, Sri Lanka and the Persian Gulf render in the correct places; GLORYS 100 m resolves mesoscale eddies; the Arabian Sea is warmer than the Bay of Bengal at 100 m (shallower BoB thermocline). Georeferencing is confirmed by eye, not assumed.
Tables: as listed in §2.

## 12. Processed dataset
`data/processed/oceanembed_smoketest_2020_01_dev.zarr` (1.4 MB) and `.nc` (4.3 MB)
Dims **time 2 × lat 101 × lon 241**; 12 variables (7 surface + 5 target).
Metadata embedded: source products with DOIs, source files, time period, domain, target grid, regridding method, vertical method, ocean mask, `created_at`, `pipeline_version`.

## 13. Warnings

1. **Period is January 2020, not Cyclone Fani.** No Fani data exists in the archive; the cyclone experiment (Phase 5.1 Experiment C) needs a separate 2019 acquisition.
2. **Only 2 days.** Sufficient to prove the pipeline, **not** sufficient to train anything.
3. **`sss` is an 8-day trailing running mean stamped daily** — not a true daily field. It will over-smooth genuine daily SSS variability and is the weakest channel scientifically.
4. **`temp_0m` is 0.494 m, clamped.** Honest and recorded, but it is not literally the surface.
5. **SSS out-of-envelope values, both real:** 70 cells < 20 PSU at 21.4–21.9 °N / 90.6–91.6 °E (Ganges–Brahmaputra plume — genuine) and 149 cells > 41 PSU at 22.6–29.9 °N / 48.4–59.9 °E (Persian Gulf / Gulf of Oman — genuine, though the narrow Gulf likely carries land-contaminated radiometer footprints). Flagged, not clipped.
6. **12 GLORYS values are physically impossible** (−0.73 to 0.0001 °C) at exactly 2 cells (15.0 °N, 50.58/50.67 °E — Gulf of Aden shelf break) at 318/380/454 m. 0.00016 % of finite values; a near-zero fill leak at a steep bathymetric boundary. Flagged, not silently fixed. Re-check when the window is extended.
7. **Ocean mask is derived from GLORYS.** This was a deliberate decision (documented in the run log), taken because OSTIA analyses inland water: 338 native cells inside the domain box are **Tibetan Plateau lakes** at 0.06–1.61 °C. Masking to "cells where the training target exists" removes them on a principled basis rather than by clipping values.
8. **OSCAR is not an independent observation** — it is diagnosed from SSH + winds + SST, so `current_u/v` partially duplicates `sla` and `wind_u/v`. Relevant to later interpretation, not to pipeline correctness.
9. **INCOIS gridded ARGO is monthly at 1°** and has no 0 m level — it cannot validate a daily 0.25° product without aggregation. Raw Argo profiles are the stronger resource (§14).

## 14. Argo inventory (STEP 14 — inventory only, nothing integrated)
**INCOIS gridded** (`Argo gridded.nc`): 1° grid, 2 monthly timesteps (2020-01-15, 02-15), 19 levels. Contains 14 of the 15 SIH depths — **0 m is absent** (shallowest is 5 m); carries 5 extra levels (250/400/600/800/900 m). No QC fields (it is an analysed field, not observations).
**Raw GDAC profiles**: 2,841 global profiles / 858 floats over January 2020. **In domain: 400 profiles, 110 distinct floats, all 31 days covered, ~12.9 profiles/day**, lat 5.01–20.65 °N, lon 46.21–92.67 °E, median 1,983 dbar max pressure, median 314 levels. Data mode **368 D / 28 A / 4 R** (overwhelmingly delayed-mode, best QC); POSITION_QC = 1 for all 400. Full QC fields present.
**19 profiles fall inside the 2020-01-01/02 smoke window** — a useful early read on eventual validation sample size.

---

## 15. GO / NO-GO

# GO — Phase 6A pipeline is trustworthy enough to begin baseline modelling.

**Reasons.**
- All **seven** mandated surface channels plus a properly depth-interpolated GLORYS target were built from **real files only**; nothing was synthesised or substituted without being declared.
- Coordinate alignment is **asserted programmatically**, not assumed: identical time/lat/lon across all 12 variables, no duplicates, ascending axes, verified 101 × 241 shape.
- Alignment is **independently corroborated**: OSTIA and GLORYS, two unrelated products, agree to 0.19 °C at the proof cell; and the maps render the correct geography.
- Every transformation that could silently corrupt the science is **explicit and tested**: unit conversion, latitude flip, 0-360 longitude wrap, Julian-calendar conversion, 6-hourly→daily vector aggregation, and depth clamping vs interpolation. **28 tests pass.**
- The one genuine bug (0 m → all-NaN) was **caught by the pipeline's own validation, diagnosed, fixed, and locked by a regression test** — which is the actual thing a smoke test is meant to demonstrate.
- Suspicious values were **flagged and explained, never silently repaired**; the single mask applied is documented with its justification.

**Conditions that must be met before Phase 6B training — none of which are pipeline defects:**
1. **Extend the date range.** 2 days cannot train a model. The pipeline is date-agnostic; this is an acquisition task, not a code change.
2. **Decide the SSS strategy** — the 8-day running mean is the weakest channel and may need a true daily product.
3. **Expand 5 debug depths → the full 15** (mechanically ready; `FINAL_DEPTHS` is already in config and tested).
4. **Acquire 2019 data** if Cyclone Fani / Experiment C is to survive as the differentiator.

---

**STOP.** Phase 6B not started. No model trained, no embedding engine, no cyclone work, no frontend, no D26/TCHP, no ML rows — awaiting your review.
