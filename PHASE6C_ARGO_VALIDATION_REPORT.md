# OceanEmbed — Phase 6C-A Report
**Argo observational validation of the frozen L2 model**
Completed 2026-09-05 · every number was produced by executing the code · no model was trained.

**Question:** does the frozen OceanEmbed reconstruction agree with actual Argo observations, and
does L2 retain its advantage over L0/L1 in the real observed upper ocean?

**Answer: yes, and more strongly than the GLORYS benchmark suggested.** Against 5,176 independent
Argo profiles, L2 beats climatology at 14 of 15 depths and beats L1 at 11 of 15, with every tested
thermocline improvement statistically significant under a float-clustered bootstrap.

---

## Provenance (Step 0)

Baseline before any change: **182 tests passing.** Nothing was retrained; the audit scripts contain
no optimiser, no `.backward()`, and this is asserted by a test.

| Artifact | Verified value |
|---|---|
| L0 | harmonic climatology, 3 harmonics, `fitted_on=train`, 2015-01-01→2020-12-31 (2,192 days) |
| L1 | `11→[256,256,128]→15`, epoch 7, SHA256 `29419ad1dc2c4a1d…` |
| L2 | patch 33, latent 32, RF 33, dilations [1,2,4,8,1], 136,335 params, epoch 3 |
| L2 full SHA256 | `b715bb2bff32d5e4a1e696b5350e29c3` |
| L2 encoder SHA256 | `30cfd2db9e8b6b96473c1e205280c009` |
| Scalers | feature and target, both `fitted_on=train` |
| Splits | train 2015-01-01→2020-12-31 · val 2021 · test 2022-01-01→2024-12-15 |
| Target semantics | GLORYS `thetao`, `standard_name = sea_water_potential_temperature`, °C |
| 0 m policy | clamped to the shallowest native GLORYS level, **0.494025 m** |

Checkpoint hashes are re-asserted after collocation and by dedicated tests, so a silent weight change
cannot pass.

## 1. How many Argo profiles were found, accepted and rejected?

Source: Argo GDAC (Ifremer), `ar_index_global_prof.txt.gz` (3,401,230 rows), then one
`<wmo>_prof.nc` per float — 108 files, 697 MB, 0 download failures.

| | Count |
|---|---|
| Index rows in the domain (all time) | 114,823 |
| **Index rows in 2022–2023 in domain** | **6,598** across 108 floats |
| Profiles examined in the float files | 23,907 |
| Outside the audit window | 16,699 |
| Outside the domain | 597 |
| Rejected on profile QC | 55 (`position_qc=8`: 52, `juld_qc=8`: 2, `position_qc=4`: 1) |
| Rejected — too few accepted levels | 1,206 |
| Rejected — flagged A/D but ADJUSTED never populated | 174 |
| **Accepted and collocated** | **5,176 profiles, 92 floats** |
| Individual accepted measurements | 2,883,017 |

`DATA_MODE` distribution over profiles reaching that stage: **D 5,886 · A 304 · R 366** —
overwhelmingly delayed-mode, the best-calibrated tier.

**2024 is a declared observational holdout.** Its 3,171 in-domain profiles were identified in the
index but never downloaded, never collocated, and never scored. The fetch script refuses them, and a
test asserts no matched row carries a 2024 date.

## 2. What QC and DATA_MODE rules were used?

- **Profile gates:** `POSITION_QC` and `JULD_QC` must be 1 or 2. Flag **8 (interpolated position) is
  rejected** — an interpolated location is not good enough to collocate against a 0.25° grid.
- **DATA_MODE:** for `D` and `A` the `*_ADJUSTED` fields and `*_ADJUSTED_QC` flags are used; for `R`
  the raw fields. Applied **per profile**, not globally. A profile flagged A/D whose ADJUSTED field
  was never filled is **rejected**, never silently falling back to raw (174 such profiles).
- **Level gates:** `PRES_QC`, `TEMP_QC`, `PSAL_QC` each in {1, 2}, plus plausibility envelopes
  (pressure 0–2100 dbar, temperature −2.5–40 °C, salinity 2–42). Bad-QC measurements are dropped, not
  repaired or interpolated over.

## 3. Are Argo and OceanEmbed evaluating the same temperature quantity?

**They are now — they would not have been without an explicit conversion.**

GLORYS `thetao` carries `standard_name = sea_water_potential_temperature`. Argo `TEMP` is **in-situ**
temperature. Comparing them directly would inject a depth-dependent bias of ~0.08 °C at 1000 dbar —
the same order as the model differences being measured (deep RMSE ≈ 0.28–0.42 °C).

Observations are therefore converted with **TEOS-10 via `gsw` 3.6.23**:
`SA = gsw.SA_from_SP(PSAL, PRES, lon, lat)` → `pt0 = gsw.pt0_from_t(SA, TEMP, PRES)`,
i.e. potential temperature referenced to **0 dbar**, matching GLORYS.

Salinity is required for this. Where PSAL is absent or fails QC, the level is dropped — **salinity is
never invented**. Tests confirm the conversion is a no-op at the surface and a real correction at
depth.

## 4. How were pressure/depth and vertical interpolation handled?

Depth comes from `gsw.z_from_p(PRES, lat)`, which is latitude-dependent, rather than the 1 dbar ≈ 1 m
approximation (a test asserts the latitude dependence is actually present).

Interpolation onto the 15 target depths is linear and **strictly non-extrapolating**: a depth is
produced only when it lies between two accepted samples separated by ≤ 100 m. Nothing is extended
above the shallowest sample, below the deepest, or below the seafloor.

**The nominal 0 m level is essentially unobservable by Argo**: only **91** profiles support it, versus
~5,000 at every depth from 5 to 700 m. This is a direct consequence of refusing to extrapolate, and
is reported rather than papered over. Recall also that OceanEmbed's "0 m" is GLORYS's 0.494 m level.

## 5–8. Does L2 beat climatology and L1 observationally? What happens 0–300 m?

**RMSE against Argo potential temperature, 2022–2023, identical matched samples:**

| Depth (m) | L0 | L1 | **L2** | GLORYS | n | **L2 vs L0** | **L2 vs L1** |
|---|---|---|---|---|---|---|---|
| 0 | 0.488 | 0.383 | 0.401 | 0.257 | 91 | +17.8 % | −4.7 % |
| 5 | 0.805 | 0.615 | **0.588** | 0.470 | 4,557 | **+27.0 %** | +4.4 % |
| 10 | 0.863 | 0.710 | **0.696** | 0.567 | 4,821 | **+19.3 %** | +1.9 % |
| 20 | 1.158 | **1.031** | 1.097 | 0.828 | 4,831 | +5.3 % | **−6.5 %** |
| 30 | 1.318 | **1.185** | 1.273 | 0.992 | 4,985 | +3.4 % | **−7.4 %** |
| 50 | 1.312 | 1.264 | **1.158** | 0.990 | 4,997 | +11.8 % | +8.4 % |
| 75 | 1.552 | 1.359 | **1.181** | 1.099 | 5,016 | **+23.9 %** | **+13.1 %** |
| **100** | 1.703 | 1.342 | **1.224** | 1.149 | 5,014 | **+28.1 %** | **+8.8 %** |
| 125 | 1.578 | 1.239 | **1.162** | 1.046 | 5,013 | **+26.4 %** | +6.2 % |
| 150 | 1.328 | 1.083 | **0.993** | 0.867 | 5,011 | **+25.2 %** | +8.3 % |
| 200 | 0.958 | 0.888 | **0.773** | 0.677 | 4,994 | **+19.3 %** | **+12.9 %** |
| 300 | 0.765 | 0.715 | **0.674** | 0.586 | 4,962 | +11.9 % | +5.7 % |
| 500 | 0.418 | 0.438 | **0.408** | 0.366 | 4,882 | +2.4 % | +6.7 % |
| 700 | 0.376 | 0.355 | **0.348** | 0.349 | 4,832 | +7.4 % | +2.0 % |
| 1000 | **0.277** | 0.282 | 0.279 | 0.285 | 3,219 | **−0.8 %** | +1.1 % |

**L2 beats L0 at 14 of 15 depths** and **beats L1 at 11 of 15**.

Depth groups:

| Group | L0 | L1 | **L2** | GLORYS | n |
|---|---|---|---|---|---|
| Surface / mixed (0,5,10) | 0.833 | 0.664 | **0.644** | 0.520 | 9,469 |
| Upper thermocline (20,30,50) | 1.266 | **1.165** | 1.179 | 0.941 | 14,813 |
| **Thermocline (75,100,125)** | 1.612 | 1.314 | **1.189** | 1.099 | 15,043 |
| Intermediate (150,200,300) | 1.044 | 0.909 | **0.825** | 0.720 | 14,967 |
| Deep (500,700,1000) | 0.371 | 0.373 | **0.357** | 0.341 | 12,933 |

**0–300 m:** L2 wins over L0 at every depth, by 3–28 %, and over L1 everywhere except the narrow
20–30 m band. This is the band the PS cares about most and it holds up observationally.

**One clean negative: L1 beats L2 at 20 m (−6.5 %) and 30 m (−7.4 %).** This did not appear against
the GLORYS benchmark and is a genuine observational finding. It sits exactly where the seasonal
thermocline top and mixed-layer base live; the spatial embedding appears to over-smooth that sharp
transition relative to a purely local model. It is reported, not explained away.

## 7. Does the strongest previous result near 75–125 m survive?

**Yes — it is the strongest part of the observational result.** At 75/100/125 m, L2 improves on
climatology by **+23.9 % / +28.1 % / +26.4 %** and on L1 by **+13.1 % / +8.8 % / +6.2 %**, with
anomaly correlation **0.684 / 0.734 / 0.737**.

For orientation, the GLORYS-benchmark figures in Phase 6B-B were +33.5 % over L0 and +8.0 % over L1
at 100 m. The Argo numbers are of the same magnitude and the same sign. The thermocline advantage is
not an artifact of scoring against the training target.

## 9. What happens at 500/700/1000 m?

Mixed, and materially better than the GLORYS benchmark suggested:

- **500 m:** L2 +2.4 % over L0 and +6.7 % over L1 — L2 is the best of the three learned/climatological
  options here, whereas against GLORYS it had been −4.1 %.
- **700 m:** L2 +7.4 % over L0.
- **1000 m:** L2 **−0.8 %** — climatology remains marginally best, consistent with every previous
  phase.

The deep band remains the weakest, and the low absolute deep RMSE (0.28–0.42 °C) is **not** evidence
of strong skill: deep anomaly correlation is only **0.40–0.46** for L2 versus **0.73** at 100 m. Small
deep error reflects small deep variability.

## 10. How does OceanEmbed error compare with GLORYS against the same observations?

**GLORYS has the lowest RMSE at 14 of 15 depths** — but this is the least independent comparison in
the report, for two compounding reasons (see §14). The informative statement is the size of the gap:

| Depth | L2 RMSE | GLORYS RMSE | L2 excess |
|---|---|---|---|
| 100 m | 1.224 | 1.149 | +6.5 % |
| 125 m | 1.162 | 1.046 | +11.1 % |
| 150 m | 0.993 | 0.867 | +14.6 % |
| 200 m | 0.773 | 0.677 | +14.2 % |
| 700 m | 0.348 | 0.349 | **−0.3 % (L2 marginally better)** |
| 1000 m | 0.279 | 0.285 | **−2.1 % (L2 marginally better)** |

At the thermocline, a 136k-parameter model driven only by same-day surface fields lands within
**6–15 %** of a full data-assimilating ocean reanalysis measured against the same profiles — and
matches or slightly beats it below 700 m. That is the most useful single framing of this phase.

## 11. Are there large systematic biases?

No large ones, but a **coherent warm bias in the 50–150 m band** shared by all three learned systems
*and by GLORYS*:

| Depth (m) | L0 | L1 | L2 | GLORYS |
|---|---|---|---|---|
| 5 | −0.226 | −0.222 | −0.056 | −0.065 |
| 20 | +0.008 | −0.001 | +0.185 | +0.140 |
| 50 | +0.330 | +0.493 | +0.382 | +0.381 |
| 75 | +0.397 | +0.643 | +0.432 | +0.504 |
| **100** | +0.400 | +0.612 | **+0.478** | +0.553 |
| 125 | +0.330 | +0.539 | +0.497 | +0.498 |
| 200 | +0.041 | +0.170 | +0.190 | +0.209 |
| 1000 | +0.106 | +0.103 | +0.138 | +0.074 |

L2's peak bias is **+0.48 °C at 100 m** — smaller than L1's +0.61 °C and comparable to GLORYS's
+0.55 °C. Because the reanalysis shows the same signed structure, this looks like a property largely
**inherited from the training target** rather than introduced by the embedding. Two caveats: this
phase cannot separate an inherited bias from an independently-arrived-at one, and part of it may
reflect representativeness (a point profile versus a 0.25° cell mean). It was not visible when scoring
against GLORYS, because GLORYS was then the reference.

## 12. Does Bay of Bengal differ from Arabian Sea?

Yes, and consistently with Phase 6B-B. Sample counts are given for every row; nothing below 30
matched observations is reported.

| Depth (m) | AS n | AS L2 vs L0 | BoB n | BoB L2 vs L0 |
|---|---|---|---|---|
| 10 | 3,206 | +18.8 % | 1,090 | +25.7 % |
| 30 | 3,337 | +1.3 % | 1,101 | +14.9 % |
| 50 | 3,336 | +6.6 % | 1,114 | **+27.5 %** |
| 75 | 3,339 | +18.8 % | 1,130 | **+34.0 %** |
| **100** | 3,335 | +25.9 % | 1,132 | **+36.4 %** |
| 125 | 3,333 | +25.3 % | 1,133 | **+33.5 %** |
| 150 | 3,331 | +24.2 % | 1,133 | +30.6 % |
| 500 | 3,275 | +5.6 % | 1,121 | −11.9 % |
| 1000 | 1,801 | −2.9 % | 1,094 | −6.9 % |

**The Bay of Bengal gains more from the spatial embedding at thermocline depths** (+34 % vs +19 % at
75 m), exactly the pattern the GLORYS benchmark showed. Its climatology is worse there to begin with,
and spatial context recovers a large part of that.

**No cross-basin generalisation claim is made.** Latitude and longitude remain model inputs, so basin
identity is directly visible; Experiment A remains a separate phase. The 0 m row is suppressed for the
Arabian Sea (n=6).

## 13. How many observations support each depth result?

Between **4,557 and 5,016** matched observations at every depth from 5 m to 700 m; **3,219** at
1000 m; and only **91** at 0 m. Sample counts appear in every table and in
`argo_sample_count_vs_depth.png`. The 0 m row should be treated as indicative only.

## Statistical significance

Paired bootstrap, **1,000 replicates, resampling whole floats** (91 clusters) rather than individual
observations — profiles from one float on nearby cycles are strongly correlated, and resampling
measurements would give spuriously tight intervals.

| Depth | L2 − L0 RMSE [95 % CI] | L2 − L1 RMSE [95 % CI] |
|---|---|---|
| 50 m | −0.154 [−0.256, −0.050] ✓ | −0.106 [−0.190, −0.012] ✓ |
| 75 m | −0.371 [−0.508, −0.236] ✓ | −0.178 [−0.294, −0.053] ✓ |
| 100 m | −0.479 [−0.633, −0.320] ✓ | −0.118 [−0.197, −0.036] ✓ |
| 125 m | −0.416 [−0.549, −0.268] ✓ | −0.077 [−0.142, −0.012] ✓ |
| 150 m | −0.334 [−0.448, −0.208] ✓ | −0.090 [−0.154, −0.030] ✓ |
| 200 m | −0.185 [−0.274, −0.102] ✓ | −0.115 [−0.154, −0.080] ✓ |

**All 12 intervals exclude zero and favour L2.** Negative = L2 has the lower RMSE.

## 14. The GLORYS assimilation caveat

**Argo is used here as an external observational check with an assimilation-dependence caveat — it is
not statistically independent of GLORYS.**

GLORYS12V1 assimilates in-situ temperature and salinity profiles, including Argo. Two consequences:

1. **GLORYS's apparent advantage is partly circular.** Many of these very profiles, or profiles from
   the same floats, plausibly informed the reanalysis. Its lowest-RMSE status should not be read as a
   fair contest.
2. **L0/L1/L2 inherit that dependence indirectly**, since all three were trained on GLORYS. So Argo is
   not fully independent of OceanEmbed either — it is one step removed, which is weaker than true
   independence but considerably stronger than scoring against the training target itself.

What the comparison **does** support: L2 improves on climatology and on a pointwise model when both
are measured against real instruments, and the ranking obtained against GLORYS survives the change of
reference. What it **cannot** establish: an unbiased absolute error, or a fair L2-versus-GLORYS
ranking.

## Method fixed in advance

- **Collocation:** one predeclared method — ocean-aware bilinear over the four surrounding cells using
  only wet cells with renormalised weights; if fewer than two are wet, nearest wet cell within one
  grid step; otherwise unmatched. **Never interpolates through land.** Identical for all four systems.
- **Temporal matching:** same UTC calendar day, offset 0 for every profile.
- **Identical populations:** at each depth the accepted set is the intersection of Argo support with
  finite values from all four systems, so no system is scored on a more convenient subset. Tested.
- **Anomalies** are taken about the same train-only L0 climatology used in Phases 6B-A/B.
- **Example profiles** were chosen by a fixed rule declared before plotting — seeded RNG 20260905,
  uniform among the 2,760 profiles matched at every depth 5–1000 m — not selected because L2 looked
  good.

## Incident: a NumPy view-aliasing bug found and fixed

While generating figures, the count of fully-matched profiles came back as 0 where a standalone check
gave 2,760. Diagnosis: for a boolean column, `df[col].to_numpy(dtype=bool)` returns a **view** into
the DataFrame, so the in-place `&=` inside `accepted_mask` rewrote the stored `argo_sup_<d>m` column.
`metrics_by_depth(subset=...)` then wrote the basin-restricted mask back into that column, so after
the Arabian Sea pass the column meant "accepted AND Arabian Sea", and the Bay of Bengal pass
intersected two **disjoint** boxes to nothing.

- **Impact:** the by-depth metrics, depth groups and bootstrap CIs were unaffected — the intersection
  is idempotent, and all of them ran before the basin pass. Verified by re-running: those tables are
  numerically identical before and after the fix. **The basin summary was wrong** and has been
  regenerated.
- **Fix:** a defensive `.copy()` in `accepted_mask`, and `m = m & subset` instead of `m &= subset`.
- **Regression tests:** `test_accepted_mask_does_not_mutate_the_dataframe`,
  `test_subset_evaluation_does_not_mutate_the_dataframe`, and
  `test_disjoint_basins_both_retain_samples`.

## Tests

**238 passed** — 182 pre-existing (28 Phase 6A + 23 6A.5 + 44 6B-A + 38 6B-B + 49 6B-C) plus
**56 new**. No earlier phase regressed.

New coverage: L1/L2 checkpoint hashes unchanged; train-only climatology and scaler provenance; audit
scripts contain no optimiser or `.backward()`; QC byte decoding across four encodings; only QC 1–2
accepted; interpolated position flag 8 rejected; DATA_MODE selects adjusted vs raw per profile;
delayed mode uses calibrated values; empty-ADJUSTED profiles rejected rather than falling back;
bad-QC and implausible levels dropped; potential temperature differs from in-situ at depth and not at
the surface; depth-from-pressure is latitude dependent; no extrapolation above/below a profile; 0 m
not fabricated; exact-match and linear interpolation correctness; large vertical gaps not bridged;
unsorted/duplicate depths handled; bilinear reproduces a uniform field and is exact at nodes;
**interpolation never mixes land into a value**; nearest-wet fallback; all-land returns NaN;
outside-domain returns NaN; collocation deterministic and method fixed; identical sample populations
across all four systems; RMSE/bias match direct numpy; improvement sign reported both ways; bootstrap
resamples floats and is reproducible; small subgroups suppressed; the 2024 holdout never appears;
domain bounds; collocation offset within one cell; zero temporal offset; **no model column mirrors
the Argo observation**; 0 m support is rare as expected; QC summary and manifest contents.

## Artifacts

`outputs/argo/` — `matched_profiles.parquet` (5,176 rows), `qc_summary.json`,
`collocation_manifest.json`, `download_manifest.json`, `index_audit_2022_2023.csv`,
`analysis_meta.json`
`outputs/tables/` — `phase6c_argo_metrics_by_depth.csv`, `phase6c_argo_depth_groups.csv`,
`phase6c_argo_l2_vs_l0.csv`, `phase6c_argo_l2_vs_l1.csv`, `phase6c_argo_glorys_context.csv`,
`phase6c_argo_basin_summary.csv`, `phase6c_argo_bootstrap_ci.csv`
`outputs/figures/` — `argo_rmse_vs_depth.png`, `argo_bias_vs_depth.png`,
`argo_anomaly_corr_vs_depth.png`, `argo_l2_improvement_vs_depth.png`,
`argo_sample_count_vs_depth.png`, `argo_example_profiles.png`

---

## 15. Verdict

Against the pre-registered gate:

| Check | Result |
|---|---|
| **A.** L2 beats L0 at a majority of depths 0–200 m | ✅ **11 of 11**, by 3.4–28.1 % |
| **B.** L2 beats L1 across a coherent upper-ocean band | ✅ coherent from 50–300 m (+5.7 to +13.1 %); fails only at 20–30 m |
| **C.** L2 retains a coherent advantage at 75/100/125 m | ✅ +23.9 / +28.1 / +26.4 % over L0, all bootstrap-significant |
| **D.** L2 anomaly correlation positive and meaningful in the upper ocean | ✅ 0.53–0.74 from 50–200 m, peaking 0.737 at 125 m |
| **E.** Any broad systematic bias hidden by the GLORYS benchmark | ⚠️ a **+0.48 °C warm bias at 100 m**, but GLORYS shows the same +0.55 °C structure — disclosed, not disqualifying |

# GO

The observational evidence broadly preserves the existing story: **spatial context adds useful
upper-ocean and thermocline skill, and it does so against real instruments, not only against the
training target.** The headline Phase 6B-B claim survives an external check — +28.1 % over climatology
at 100 m against Argo versus +33.5 % against GLORYS, same sign and same magnitude — and every
thermocline improvement is significant under a bootstrap that respects float clustering.

**Carried forward as open items, not blockers:**

1. **L1 beats L2 at 20–30 m** (−6.5 %, −7.4 %) — a new observational finding, invisible against
   GLORYS; the embedding appears to over-smooth the mixed-layer base.
2. **The +0.5 °C thermocline warm bias** appears shared with GLORYS and is plausibly inherited, but
   this phase cannot prove that.
3. **1000 m remains climatology-dominant** (−0.8 %), unchanged across every phase.
4. **The assimilation caveat stands** — Argo is an external check, not an independent one.

---

**Phase 6C-A Argo observational validation is complete. GO.**

STOP — no availability-aware L2-NRT, source-age channels, missing-channel training,
residual/climatology blending, uncertainty model, NRT pipeline, SMAP/SMOS compatibility work,
D26/TCHP/OHC, cyclone or marine-heatwave analysis, RAMA, EOF decoder, temporal model or frontend has
been started. The 2024 Argo holdout remains untouched. Awaiting your review before proceeding.
