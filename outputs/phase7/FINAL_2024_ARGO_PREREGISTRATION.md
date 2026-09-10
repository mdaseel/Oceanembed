# Final 2024 Argo Holdout — Pre-Registration

**Status:** FROZEN. **The 2024 Argo holdout has NOT been opened.** No 2024
profile has been downloaded for analysis, collocated, scored, plotted, or
compared against any OceanEmbed output, and none was inspected while writing
this file.

**This document does not authorise the evaluation.** It records, in advance,
exactly how the evaluation will be run *if and when* a separate explicit
approval is given. Approval to begin Phase 8A is **not** approval to open this
holdout, and vice versa.

---

## 1. What is protected, stated precisely

The loose claim is "2024 Argo was never downloaded". The precise claim, which is
what matters and what can be defended, is:

**No 2024 Argo profile has ever been collocated, scored, compared to a model
output, or allowed to influence any decision in this project.**

That is enforced in code, not by convention:

| Guard | Where |
|---|---|
| Fetch refuses an index selection containing 2024 profiles | `scripts/validate/fetch_argo_profiles.py:41` |
| `assert df.date.max() < 2024-01-01, "HOLDOUT LEAK"` | `argo_validate.py:252`, `argo_analyse.py:37`, `argo_fallback_analyse.py:88`, `argo_fallback_replay.py:75` |
| Test asserts no matched row carries a 2024 date | `tests/test_phase6c_argo.py::test_holdout_2024_never_appears` |
| Manifests record the window | `heldout_untouched: [2024-01-01, 2024-12-15]` |

**One nuance is recorded here deliberately, so it cannot be raised later as a
surprise.** Argo distributes **one file per float** (`<wmo>_prof.nc`), and that
file holds *every cycle* the float ever made — the fetch script says so in its
own docstring. Floats were selected for their 2022–2023 in-domain profiles, and
the guard prevents a float from ever being selected *because of* 2024 data. But
a selected float that remained active will carry later cycles inside the file
that was fetched.

The QC pass therefore reads each profile's timestamp in order to **exclude**
anything outside 2022-01-01…2023-12-31; `outputs/argo/qc_summary.json` records
**16,699** profiles rejected as `outside_window`, a count that spans both
pre-2022 and post-2023 cycles.

So the accurate position is:

- 2024 temperature and salinity values have **never been read into any
  analysis**, never collocated, never scored, never seen by a human or a metric.
- Some 2024 cycles are **likely physically present on disk** inside whole-float
  files fetched for the 2022–2023 audit, touched only by a date comparison that
  threw them away.
- **This was not verified by opening those files**, because that inspection
  would itself be the thing this holdout forbids. The statement above is derived
  from the fetch code and the recorded manifests only.

The holdout is intact in the sense that matters: nothing about 2024 has informed
the model, the scalers, the climatology, the architecture, the diagnostics, the
thresholds, or the event selection.

## 2. What is frozen before 2024 is opened

Fixed now, and not revisable after any 2024 number is seen:

- **The final model is the existing frozen L2.** State-dict
  `b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d`, encoder
  `30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808`.
- **No architecture change after viewing 2024.** No retraining, fine-tuning,
  layer change, latent-width change, patch change, temporal memory, or L3.
- **No scaler change after viewing 2024.** `phase6b_feature_scaler.json` and
  `phase6b_target_scaler.json` stay byte-identical.
- **No climatology change after viewing 2024.** `phase6b_climatology.nc` stays
  byte-identical.
- **No threshold movement.** The Phase 7C D26/TCHP convention and constants
  (ρ₀ 1023.035344728, cp₀ 3991.86795711963) and the Phase 7D hazard boundaries
  (p50 55.70, p75 79.10, p90 96.94 kJ cm⁻²) are frozen and will not be re-derived
  against 2024.
- **No event-selection change.** Cyclone Mocha and the 2023-05-05…2023-05-22
  window stay as pre-registered, whatever 2024 shows.
- **No cherry-picking.** No subsetting of floats, depths, regions, seasons or
  dates chosen after seeing results.

## 3. How the evaluation will be run

Identical in method to Phase 6C-A. Not "the same philosophy" — **the same
code**, reused unchanged:

| Element | Commitment |
|---|---|
| Fetch | `scripts/validate/fetch_argo_profiles.py`, run with the holdout guard explicitly lifted for 2024 only, from the same Argo GDAC index |
| Window | `2024-01-01` … `2024-12-15` (the processed record ends 2024-12-15) |
| Domain | the canonical 5–30 °N / 45–105 °E box; out-of-domain profiles rejected |
| QC | the existing `select_fields` / `accepted_levels` helpers unchanged: `position_qc`/`juld_qc` rejection, adjusted fields preferred, delayed-mode `D` where available, `A` and `R` retained with their data-mode recorded |
| Temperature | `to_potential_temperature(PRES, TEMP, PSAL, lon, lat)` unchanged — TEOS-10 potential temperature, the same physical conversion used for 2022–2023 |
| Vertical | `interp_to_depths` unchanged, onto the same **15 mandated depths** |
| Collocation | `ocean_aware_bilinear_then_nearest_wet_within_1_cell`, temporal offset **0** (same UTC calendar day), unchanged |
| Inference | `replay_field(date)` — the frozen L2, surface inputs only, no target, no Argo at inference |
| Metrics | exactly the existing columns: `n, rmse, mae, bias, correlation, nrmse, obs_std, anomaly_correlation, anomaly_rmse`, for **L0, L1 and L2**, per depth |
| Reporting | **all 15 depths**, no depth omitted for being unflattering; float-clustered bootstrap CIs as in 6C-A; small subgroups suppressed by the same rule |
| Comparison | against the frozen 2022–2023 results, whole-NIO and per-basin using the frozen `ml/metrics.py::BASINS` boxes |

**Argo remains an external observational check, not perfectly independent
truth.** GLORYS assimilates in-situ observations, so the same caveat that
applies to the 2022–2023 result applies here and will be restated.

## 4. Pre-committed interpretation

Written now, so the conclusion cannot be chosen after seeing the number:

- **If 2024 is similar or better than 2022–2023** → report it as evidence of
  temporal robustness. Do not claim more than one additional year supports.
- **If 2024 is moderately worse** → report the degradation quantitatively, per
  depth and per basin. Investigate possible interannual or domain shift as an
  *explanation offered*, not a defence. **Do not tune to 2024.**
- **If 2024 is substantially worse** → report the limitation plainly and
  prominently, including in the PoC's own validation page. A frozen model that
  degrades on a new year is a real finding about the model, and it will be
  published as one. **Do not tune to 2024.**

In every branch, the frozen L2 stays frozen. There is no outcome of this
evaluation that results in a model change within Phase 7.

**Implementation bugs** may be corrected only if: the bug is documented; a
regression test is added; the corrected run is reported in full; and the
correction does not amount to selecting between two computed outcomes. A bug fix
that happens to improve the result must be reported with both numbers.

## 5. What would count as a leak

Recorded so it is unambiguous. The holdout is compromised if any of these
happens before the separate approval:

- a 2024 profile is collocated, scored, plotted or tabulated;
- a 2024 date appears in any matched-profile artifact;
- a 2024 result influences the model, scalers, climatology, diagnostics,
  thresholds, event selection or any reported decision;
- the evaluation is run and then re-run with different settings, and only one is
  reported.

## 6. Status at freeze

```
2024 Argo:                    PROTECTED - not opened
Final holdout preregistration: READY
Authorisation to execute:      NOT GRANTED
```

---

*Written before the holdout was opened. No 2024 Argo value informed any part of
this document.*
