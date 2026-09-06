# OceanEmbed — Phase 6C-C Report
**Evidence-gated fallback contract + Argo observational replay**
Completed 2026-09-05 · no model trained · L2 hash verified unchanged · 2024 Argo untouched.

**Question:** do the fallback policies that development evidence supports actually preserve L2's
*observational* skill against real Argo profiles?

**Answer: seven of eight do; one does not — and it is the one development preferred.** SSS
persistence is statistically indistinguishable from complete inputs against 5,160 Argo matches.
SSS *channel climatology*, which looked marginally **better** than complete inputs on 2021 GLORYS,
is significantly **worse** against Argo at every key depth and worsens the known thermocline warm
bias. It stays development-only.

---

## Step 0 — pinned legacy behaviour and provenance

Baseline before any change: **274 tests passing** — matching the previous report's observation.

| Artefact | SHA256 (pinned in tests) |
|---|---|
| L2 full state dict | `b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d` |
| L2 encoder | `30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808` |
| feature scaler | `49671ce760b0dca5c1c82cb184dae919…` (`fitted_on=train`) |
| target scaler | `5b6f359db0d228dd7d3acf775ab8a6ee…` (`fitted_on=train`) |
| target climatology | `748af4d79bc704cc2f742e1c208baceb…` (train 2015-01-01→2020-12-31) |
| surface climatology | `58f0c5812ebcb6d4394a4f18e5b133d0…` (train 2015-01-01→2020-12-31) |

**Legacy contract, unchanged.** `day_field` standardises the seven channels in `SURFACE` order with
the frozen train scaler, computes **one joint validity mask** `isfinite(all seven).all(axis=0)`,
zeroes masked cells, and zero-pads the domain edge with mask 0. Ordinary per-cell NaNs blank only
their own cell; land behaves as land.

**The whole-channel failure is preserved, not redefined.** A dedicated test
(`test_legacy_blank_field_failure_is_preserved_as_a_documented_regression`) still asserts that
feeding `day_field` an all-NaN SSS channel yields **0 valid cells and all seven channels zeroed**.
The wrapper prevents *reaching* that path; it does not change it.

## Steps 1–4 — the operational contract

`src/oceanembed/operational/` — `policy.py`, `availability.py`, `assemble.py`, `provenance.py`.

**Two paths, deliberately separate.** `reference_complete_field` calls the unmodified legacy
`day_field`. `assemble_field` repairs only *declared* channels and then calls **the same unmodified
`day_field`**. Because the assembled field has no whole-channel gap, the joint mask behaves exactly
as in normal operation.

**Explicit allow-list, no generic fallback.** Nine registered policies and nothing else. A test
asserts `p.absent ⊆ {"sss"}` for every policy — there is no repair path for any channel whose
sensitivity was never measured. Eleven untested situations are parametrised and must raise:
SST / SLA / wind / current outages, `sss`+`sla` together, stale SST, stale SSS, 4-day currents,
2-day winds, 2-day SLA, and SSS-absent combined with stale wind.

**Age follows the original observation.** `PersistenceStore.carry_forward` moves a field to a new
store date **without touching its original observation time**. The worked example manifest shows a
field stored on t-1 but originally observed t-2 correctly reporting **age = 2.0 days, not 1.0**.
Age beyond the configured range, and any request that would serve a future field, are refused.

**Climatology is not an observation**: `source_valid_time = null`, `original_observation_time = null`,
`age_days = null`, plus `training_period = 2015-01-01/2020-12-31`. `max_age_days` ignores those nulls.

**Replay mode = RETROSPECTIVE** throughout. Historical archive availability is not treated as
operational availability on the date; `source_available_time` is honoured when supplied
(a source available after the declared issue time is refused) but was not reconstructible here.

## Step 9 — complete-input invariance

**Bitwise identical, both ways:**
- `reference_complete_field` ≡ `day_field` — `np.array_equal` (test).
- `assemble_field` with nothing declared wrong ≡ `day_field` — `np.array_equal` (test).
- An ordinary per-cell NaN in an otherwise available product produces a field **bitwise identical**
  to legacy, with that cell still masked. The wrapper does not repair it.

No tolerance was required.

## Step 5 — Argo replay

Same accepted Phase 6C-A population, same collocation protocol (`ocean_aware_bilinear_then_nearest
_wet_within_1_cell`), same day matching.

| | |
|---|---|
| Argo population | 5,176 profiles, 92 floats, 730 dates, 2022-01-01→2023-12-31 |
| **Replayed** | **5,160 matches over 727 dates** |
| Dates skipped | 3 (2022-01-01/02/03 lack the 3 days of history the stale modes need) |
| Runtime | 11.0 min · L2 hash unchanged |

## Step 6 — results

RMSE against Argo potential temperature (°C):

| Depth (m) | L0 | **COMPLETE** | SSS persist | SSS clim | cur t-2 | cur t-3 | SSS persist + cur t-2 |
|---|---|---|---|---|---|---|---|
| 10 | 0.8640 | 0.6973 | **0.6962** | 0.6925 | 0.6965 | 0.6964 | 0.6955 |
| 30 | 1.3193 | 1.2744 | 1.2747 | 1.2748 | 1.2748 | 1.2756 | 1.2751 |
| 50 | 1.3134 | 1.1591 | **1.1581** | 1.1708 | 1.1601 | 1.1620 | 1.1590 |
| 75 | 1.5521 | 1.1813 | **1.1810** | 1.2101 | 1.1839 | 1.1887 | 1.1835 |
| **100** | 1.7041 | 1.2241 | **1.2234** | **1.2787** | 1.2287 | 1.2324 | 1.2279 |
| 125 | 1.5787 | 1.1621 | **1.1613** | 1.2195 | 1.1677 | 1.1707 | 1.1669 |
| 150 | 1.3280 | 0.9933 | **0.9928** | 1.0352 | 1.0007 | 1.0034 | 1.0004 |
| 200 | 0.9578 | 0.7730 | 0.7731 | 0.7899 | 0.7759 | 0.7764 | 0.7760 |
| 1000 | **0.2768** | 0.2793 | 0.2795 | 0.2811 | 0.2805 | 0.2809 | 0.2806 |

Degradation vs COMPLETE (%):

| Depth (m) | SSS persist | **SSS clim** | cur t-1 | cur t-2 | cur t-3 | wind t-1 | SLA t-1 | combined |
|---|---|---|---|---|---|---|---|---|
| 50 | −0.09 | +1.00 | +0.02 | +0.09 | +0.24 | +0.03 | −0.28 | −0.02 |
| 75 | −0.02 | **+2.44** | +0.08 | +0.22 | +0.63 | +0.03 | −0.27 | +0.19 |
| **100** | **−0.06** | **+4.46** | +0.19 | +0.37 | +0.68 | −0.04 | −0.23 | +0.31 |
| 125 | −0.07 | **+4.94** | +0.26 | +0.48 | +0.74 | −0.07 | −0.19 | +0.41 |
| 150 | −0.05 | **+4.21** | +0.36 | +0.74 | +1.01 | −0.08 | −0.16 | +0.71 |
| 200 | +0.01 | **+2.20** | +0.19 | +0.38 | +0.45 | −0.05 | +0.02 | +0.39 |

Depth groups (RMSE °C):

| Group | L0 | COMPLETE | SSS persist | SSS clim | cur t-2 | cur t-3 |
|---|---|---|---|---|---|---|
| Surface / mixed | 0.8337 | 0.6449 | 0.6442 | 0.6402 | 0.6443 | 0.6442 |
| Upper thermocline | 1.2675 | 1.1805 | 1.1803 | 1.1836 | 1.1807 | 1.1816 |
| **Thermocline** | 1.6130 | 1.1894 | **1.1889** | **1.2365** | 1.1937 | 1.1976 |
| Intermediate | 1.0444 | 0.8250 | 0.8249 | 0.8490 | 0.8293 | 0.8306 |
| Deep | 0.3715 | 0.3574 | 0.3579 | 0.3596 | 0.3583 | 0.3587 |

**Every mode still beats climatology at 14 of 15 depths, losing only at 1000 m — exactly where
COMPLETE also loses.** No fallback moves the climatology crossover.

## Step 7 — paired float-clustered bootstrap (1,000 replicates, 91 floats)

RMSE difference vs COMPLETE across the six key depths (negative = fallback better):

| Policy | Within noise | Significant | Mean difference |
|---|---|---|---|
| **SSS_ABSENT_PERSIST** | **6/6** | 0/6 | **−0.0005 °C** |
| WIND_STALE_1D | 6/6 | 0/6 | −0.0003 °C |
| CURRENT_STALE_1D | 6/6 | 0/6 | +0.0020 °C |
| CURRENT_STALE_2D | 6/6 | 0/6 | +0.0040 °C |
| SSS_PERSIST + CUR_2D | 6/6 | 0/6 | +0.0034 °C |
| SLA_STALE_1D | 4/6 | 2/6 (both **negative**) | −0.0021 °C |
| CURRENT_STALE_3D | 4/6 | 2/6 | +0.0068 °C |
| **SSS_ABSENT_CLIM** | **0/6** | **6/6** | **+0.0352 °C** |

## The result that did not transfer

| | 6C-B (GLORYS, 2021 dev) | **6C-C (Argo, 2022-23)** |
|---|---|---|
| SSS persistence @100 m | 1.2254 vs 1.2255 → −0.01 % | **−0.06 %, CI spans zero 6/6** |
| SSS channel climatology @100 m | 1.2243 vs 1.2255 → **−0.10 % (better)** | **+4.46 %, significant 6/6** |

Development said channel climatology was *marginally better than complete inputs*. Against real
observations it is clearly worse, and the mechanism is visible in the bias:

| Depth (m) | COMPLETE bias | SSS persist Δbias | **SSS clim Δbias** |
|---|---|---|---|
| 75 | +0.433 | −0.0006 | **+0.042** |
| **100** | +0.477 | −0.0008 | **+0.060** |
| 125 | +0.497 | −0.0007 | **+0.062** |
| 150 | +0.390 | −0.0005 | **+0.054** |

Phase 6C-A found a pre-existing **+0.48 °C thermocline warm bias**. Substituting a seasonal-mean SSS
field **worsens it by a further +0.060 °C** and lowers anomaly correlation from 0.734 to 0.716 at
100 m. Persistence leaves both untouched (Δbias ≤0.0008 °C, anomaly correlation 0.7346 vs 0.7344).

The likely reason: a climatological SSS removes the day's real salinity structure, and the model
compensates with a warmer thermocline. GLORYS could not reveal this because it shares the same bias
structure the models were trained on; Argo can. **This is precisely why the phase existed.**

## Steps 5–8 — policy states after the replay

| Policy | State | Basis |
|---|---|---|
| REFERENCE_COMPLETE | `REFERENCE_COMPLETE` | bitwise-identical legacy path |
| **SSS_ABSENT_PERSIST** | **`OBS_SUPPORTED_FALLBACK`** | −0.06 % @100 m, CI spans zero 6/6, Δbias <0.001 °C |
| **CURRENT_STALE_1D** | **`OBS_SUPPORTED_FALLBACK`** | +0.19 % @100 m, CI spans zero 6/6 |
| **CURRENT_STALE_2D** | **`OBS_SUPPORTED_FALLBACK`** | +0.37 % @100 m, CI spans zero 6/6 |
| **CURRENT_STALE_3D** | **`OBS_SUPPORTED_FALLBACK`** | +0.68 % @100 m, detectable at 2/6 — **weakest promoted** |
| **WIND_STALE_1D** | **`OBS_SUPPORTED_FALLBACK`** | −0.04 % @100 m, CI spans zero 6/6 |
| **SLA_STALE_1D** | **`OBS_SUPPORTED_FALLBACK`** | −0.23 % @100 m, never worse than COMPLETE |
| **SSS_PERSIST + CUR_2D** | **`OBS_SUPPORTED_FALLBACK`** | +0.31 % @100 m, CI spans zero 6/6 |
| **SSS_ABSENT_CLIM** | **`DEV_SUPPORTED_FALLBACK`** (held) | fails gate 2 and 3: +4.46 % @100 m, significant 6/6, bias +0.060 °C |
| everything else | `UNSUPPORTED_INPUT_MODE` | never tested |

Basin check (criterion 4) — the pattern is not basin-driven. At 100 m: persistence AS +0.03 % /
BoB −0.17 %; climatology AS +4.97 % / BoB +2.75 %. Sample counts 3,323 (AS) and 1,130 (BoB).

## Answers to the report questions

1. **Does SSS persistence retain observational skill?** Yes — statistically indistinguishable from
   complete inputs at all six key depths, with no bias change.
2. **Does SSS channel climatology?** **No.** Significantly worse at 6/6 key depths and it worsens the
   thermocline warm bias. Held at development-only.
3. **Do t-1/t-2/t-3 currents remain negligible against Argo?** t-1 and t-2 yes (CI spans zero 6/6).
   t-3 is now *detectable* at 2/6 depths (+0.68 % at 100 m) — still small, but no longer invisible as
   it appeared on GLORYS.
4. **Does SSS + t-2 currents remain safe?** Yes — +0.31 % at 100 m, CI spans zero 6/6.
5. **Which are now OBS_SUPPORTED?** Seven: SSS persistence, currents t-1/t-2/t-3, wind t-1, SLA t-1,
   and the combined SSS-persist + currents-t-2.
6. **Which remain development-only?** SSS channel climatology.
7. **New basin- or depth-specific failure?** Only for climatology, and it is depth-structured
   (peaks at 125 m), not basin-driven.
8. **Is complete-input inference unchanged?** Yes — bitwise identical, both paths, asserted by tests.
9. **Can an unsupported outage still blank the CNN through the operational path?** No — it raises
   `UnsupportedInputMode` before inference. The legacy blank-field behaviour still exists in
   `day_field` and is pinned by a regression test; the wrapper prevents reaching it.
10. **Is the contract ready to receive real NRT products?** Structurally yes — provenance, age,
    issue-time and policy gating are in place. But every number here comes from *reanalysis-grade
    inputs substituted in time*. A genuine NRT product differs in more than age, so the contract is
    ready to be **tested** against real NRT, not yet validated for it.

## Steps 10–12 — scope and testing

**Partial spatial gaps were deliberately not implemented.** Phase 6C-B's gap masks were synthetic;
no gap-filling strategy is registered, and any partial-availability situation therefore falls through
to `UNSUPPORTED_INPUT_MODE`. That belongs to the real-NRT phase when actual SMAP/SMOS sampling masks
can be examined.

**324 tests pass** — 274 pre-existing plus **50 new**. No earlier phase regressed.

The new tests are behavioural rather than source-string checks. The optimiser test, for instance,
runs the assembler and then asserts every model parameter has `grad is None` and the state-dict hash
is unchanged, rather than grepping for the word "optimizer".

Coverage: model/scaler/climatology hashes; reference path bitwise-identical; assembler-with-no-faults
bitwise-identical; ordinary per-cell NaNs unchanged; land unchanged in every supported mode;
eleven untested situations refused (parametrised); registry contains only evidenced policies and
repairs no untested channel; unsupported outage never reaches the CNN; **legacy blank-field failure
preserved**; supported fallback keeps the mask alive; **persistence age follows the original
observation through a carry-forward chain**; age reported in the manifest; persistence beyond range
refused; no prior field refused rather than invented; store never serves a future field; stale
channel reads exactly t−age; age running off the record refused; negative age refused; U/V ages and
absence must be paired; climatology has null valid-time and null age with a training period;
climatology without an artefact refused; manifest `max_age` ignores nulls; source available after the
issue time refused; wrong valid-time refused; malformed dimensions refused; all-NaN replacement
refused; no source mutation; deterministic provenance; every channel once in the manifest; manifest
JSON round-trip; and on the replay outputs — 2024 absent, all modes present, identical L2 coverage,
L0 a strict subset with metrics on the intersection, recorded hashes unchanged.

**One test failed initially and was right to.** It asserted every mode had identical *native*
coverage. In fact **L0 is narrower by 3 rows at 200 m** (24–25.5 °N, 57 °E, Gulf of Oman): the
train-only climatology has no fitted coefficients where no 200 m target existed during training. The
metrics already intersect across all modes, so no number was affected. The test now asserts the two
properties that matter — all L2 modes share COMPLETE's coverage exactly, and L0 is a strict subset
with metrics computed on the intersection.

## Artifacts

`src/oceanembed/operational/` — `policy.py`, `availability.py`, `assemble.py`, `provenance.py`
`outputs/tables/` — `phase6cc_argo_fallback_metrics_by_depth.csv`,
`phase6cc_argo_fallback_depth_groups.csv`, `phase6cc_fallback_vs_complete.csv`,
`phase6cc_fallback_vs_climatology.csv`, `phase6cc_fallback_bootstrap.csv`
`outputs/figures/` — `phase6cc_argo_fallback_rmse.png`, `phase6cc_argo_fallback_degradation.png`,
`phase6cc_100m_fallback_summary.png`, `phase6cc_fallback_skill_vs_depth.png`
`outputs/operational/` — `example_reference_manifest.json`, `example_persistence_manifest.json`,
`example_climatology_manifest.json`, `example_unsupported_manifest.json`
`outputs/argo/` — `fallback_replay.parquet` (5,160 matches), `fallback_replay_meta.json`

---

# GO

| Gate criterion | Result |
|---|---|
| REFERENCE_COMPLETE unchanged | ✅ bitwise identical, both paths |
| Wrapper prevents unsupported blank-field inference | ✅ raises before inference; legacy failure pinned, not redefined |
| Main candidate fallbacks retain meaningful observational skill | ✅ 7 of 8 promoted; all beat L0 at 14/15 depths |
| Registry prevents extrapolation to untested modes | ✅ no generic fallback; 11 untested situations refused |
| Provenance and age semantics correct | ✅ age follows the original observation; climatology carries null age |
| 2024 Argo untouched | ✅ asserted |
| Full suite passes | ✅ 324 |

The contract is **evidence-gated in the strict sense**: a policy is usable only where it was measured,
and the one policy that development preferred was **demoted** on observational evidence rather than
carried forward. That demotion is the most useful outcome of the phase — it is exactly the failure
mode that scoring against the training target cannot expose.

**Carry forward as open items:** currents at t-3 are the weakest promoted policy and should be
re-checked against real NRT; partial spatial gaps remain unsupported by design; and every result here
uses reanalysis-grade fields substituted in time, so genuine NRT products remain untested.

---

**Phase 6C-C is complete. GO.**

STOP — no live/NRT products downloaded or substituted, no SMAP/SMOS operational SSS, no OSCAR or CCMP
NRT swap, no 2024 Argo, no model training of any kind, no residual or uncertainty model, no
D26/TCHP/OHC, no frontend. Awaiting your review before **Phase 6C-D — Real NRT Product Compatibility
& Prospective Latency Audit**.
