# Operational Current-Source Qualification — Phase 8C

Protocol frozen 2026-09-12 at commit `c01c170`, **before** any candidate current
field was scored. Experiment executed at `988a8cd`. One frozen model throughout:
L2 state dict `b715bb2b…e728d`, encoder `30cfd2db…db4808`, verified before and
after every run.

> **Decision: SUBSTITUTE_REJECTED.** The candidate is the fresher product, and
> the frozen model barely notices the swap — but against real Argo observations
> it is **detectably worse through the thermocline**, which is the band this
> project exists to reconstruct. OSCAR remains the current source in both
> regimes.

---

## 1. What was the original product, and why was it operationally insufficient?

| role | product |
|---|---|
| historical / training lineage | `OSCAR_L4_OC_FINAL_V2.0` — what the model-ready store holds and what the frozen L2 was trained on |
| operational (Phase 8B) | `OSCAR_L4_OC_NRT_V2.0` |

OSCAR production stopped: on 2026-09-12 the newest NRT granule was **2026-09-03**
(ingested 09-05), INTERIM stopped at 08-31, and FINAL ends 2026-01-16 — every
ingest timestamp in the family stops on 2026-09-05. Meanwhile SLA reached 09-12
and SST and wind 09-11, so the Latest Qualified Ocean State was pinned at
**2026-09-03** by currents alone.

## 2. What is the candidate, and is it semantically compatible?

`MULTIOBS_GLO_PHY_MYNRT_015_003` → `cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m`
(version 202411, Copernicus Marine) — the GlobCurrent-lineage total surface
current analysis: daily, 0.25°, m s⁻¹, depth levels 0 m and 15 m, NRT coverage
**2022-05-01 → 2026-09-11**, with a multi-year twin back to 1993. Retrieval over
the NIO box was confirmed (223 KB/day).

**Semantically it is an analogue, not a twin.** OSCAR is documented here as a
diagnostic from SSH gradients, wind and SST, nominal depth 15 m, an average over
the top 30 m, with **no tidal term**. The candidate's `uo`/`vo` explicitly add
tide. The pre-registration therefore fixed:

- **primary (decision-bearing):** `ugos + ue` at 15 m — geostrophic + Ekman,
  **tide excluded**, matching OSCAR's formulation;
- **secondary (reported only):** `uo`/`vo` at 15 m, the product's own total.

Disclosed approximation: OSCAR is a 0–30 m average, the candidate a 15 m level.

## 3. How different is it from OSCAR?

Channel level, whole NIO, on the 56 pre-registered dates, using the unchanged
6C-D machinery and bands:

| comparison | channel | bias (m/s) | RMSD (m/s) | ρ | σ-ratio | RMSD/σ_train | band |
|---|---|---|---|---|---|---|---|
| candidate vs OSCAR **Final** | u | +0.013 | 0.116 | 0.912 | 1.054 | 0.517 | INCOMPATIBLE_RAW |
| candidate vs OSCAR **Final** | v | −0.010 | 0.113 | 0.902 | 1.069 | 0.543 | INCOMPATIBLE_RAW |
| candidate vs OSCAR **NRT** | u | +0.019 | 0.091 | 0.980 | 1.071 | 0.404 | MARGINAL |
| candidate vs OSCAR **NRT** | v | −0.011 | 0.086 | 0.982 | 1.036 | 0.415 | MARGINAL |

Near-zero bias, σ-ratio ≈ 1.05, ρ ≈ 0.90 against the training lineage: a
**pattern** difference, not an offset — exactly the shape 6C-D found for OSCAR
NRT, and not something an affine adapter could fix. Notably the candidate
resembles OSCAR **NRT** (ρ ≈ 0.98) much more than the OSCAR **Final** field the
model was trained on.

## 4. What happens to frozen-L2 predictions?

Identical inputs except currents, same frozen inference:

| quantity | candidate (primary) | secondary (with tide) |
|---|---|---|
| s at 100 m | **0.232 — MINOR** | 0.219 — MINOR |
| worst band (depth) | MINOR (30 m, s = 0.239) | MINOR (30 m) |
| joint-mask coverage loss | 0.09 % | — |
| 6C-D per-channel decision | **SUBSTITUTE_WITH_MONITORING** | — |

For comparison, OSCAR NRT itself scored s = 0.202 at 100 m in 6C-D and earned
the same category. On model-response grounds alone the candidate looks fine.

## 5. What happens at 75 / 100 / 125 m, and in the two basins?

Against the GLORYS reference on the same dates (whole NIO, RMSE °C):

| depth | L0 | control (OSCAR) | candidate | candidate vs control |
|---|---|---|---|---|
| 0 | 0.697 | 0.515 | 0.524 | +1.85 % |
| 50 | 1.176 | 0.903 | 0.906 | +0.30 % |
| **75** | 1.523 | 1.134 | 1.143 | **+0.78 %** |
| **100** | 1.649 | 1.247 | 1.267 | **+1.58 %** |
| **125** | 1.564 | 1.252 | 1.274 | **+1.73 %** |
| 150 | 1.346 | 1.144 | 1.165 | +1.88 % |
| 200 | 0.913 | 0.853 | 0.869 | +1.85 % |
| 500 | 0.365 | 0.365 | 0.360 | −1.31 % |
| 1000 | 0.425 | 0.418 | 0.414 | −1.14 % |

Gates: **C5** candidate beats L0 at **11 of 11** depths 0–200 m; **C6** it beats
L0 at 75/100/125 m with the bootstrap interval entirely below zero; **C7** it
beats L0 at 100 m in both the Arabian Sea and the Bay of Bengal. All pass — they
ask whether the candidate beats *climatology*, and it does. They do not ask
whether it matches OSCAR, and the table already shows it does not, by ~1.6–1.9 %
through 100–200 m.

## 6. Does it preserve observational Argo skill? — **No**

Reusing the executed 2022–2023 collocations (4,347 profiles, 86 floats, 610
dates, from the candidate's coverage start 2022-05-01), same positions, times,
QC and collocation rule; float-clustered paired bootstrap, 1,000 replicates.

**Integrity first:** the control recomputed here reproduces the stored executed
`L2` values **exactly** (max absolute difference 0.0 at every key depth), so this
measures currents and nothing else.

| depth | RMSE control | RMSE candidate | change | 95 % CI (°C) | detectable? |
|---|---|---|---|---|---|
| 50 m | 1.2322 | 1.2349 | +0.22 % | [−0.018, +0.018] | no |
| 75 m | 1.2173 | 1.2266 | +0.77 % | [−0.002, +0.019] | no |
| **100 m** | 1.2527 | 1.2705 | **+1.42 %** | [+0.006, +0.029] | **yes, worse** |
| **125 m** | 1.1922 | 1.2122 | **+1.67 %** | [+0.010, +0.027] | **yes, worse** |
| **150 m** | 1.0138 | 1.0304 | **+1.64 %** | [+0.009, +0.023] | **yes, worse** |
| 200 m | 0.7729 | 0.7754 | +0.33 % | [−0.003, +0.009] | no |

**C8 requires** ≥ 4 of 6 key depths with intervals spanning zero, and worst
degradation ≤ +0.68 % (the 6C-C bar: the weakest policy ever promoted). Measured:
**3 of 6 spanning, worst +1.67 %. C8 FAILS.**

The secondary tide-included variant fails too (+1.17 / +1.44 / +1.59 % at
100/125/150 m), so the result does not hinge on the tide choice.

The GLORYS comparison (§5) and the Argo comparison agree on both sign and
magnitude — two independent references telling the same story.

## 7. Does it improve operational recency?

Yes, and modestly:

| | currents | newest complete seven-channel date |
|---|---|---|
| today, with OSCAR | 2026-09-03 | **2026-09-03** |
| with the candidate | 2026-09-11 | **2026-09-06** |

**Gain: 3 days.** The candidate's own currents reach 09-11, but the stack is then
held by salinity at 09-06 — the next bottleneck. A fresher currents product does
not buy 8 days; it buys 3.

## 8. Why this is a rejection, not a trade-off

The candidate offered **3 days** of recency for a **statistically significant
1.4–1.7 % loss** of observational accuracy exactly at 100–150 m, the thermocline
band that drives D26, TCHP and the hazard indicator. The pre-registered rule
already said what to do with that, before the numbers existed.

This is Phase 6C-C repeating: there, a fallback that looked *better* on
reanalysis was demoted when real Argo profiles disagreed. Here, a substitution
that passed every model-side and reanalysis-side gate is rejected on the
observational check. The cheap evidence agreed with the decision only after the
expensive evidence was consulted.

**An honest limitation:** OSCAR NRT — the incumbent operational product — cannot
itself be tested this way, because it begins in 2024 and the permitted Argo
window ends in 2023. So this phase can say the candidate is measurably worse
than the *training-lineage* OSCAR against observations; it cannot say how the
candidate compares with OSCAR NRT observationally. That asymmetry argues for the
conservative outcome, which is what was pre-registered.

## 9. What was and was not changed

- **L2 retrained?** No. Hashes identical before and after every run.
- **Historical Replay changed?** No. It still reads OSCAR Final over 2015–2024;
  no splicing of products inside the historical record.
- **Latest mode changed?** No. It still uses OSCAR NRT; the rejected candidate
  appears in no operational code path, and is not in the product registry.
- **Scalers, L0, D26/TCHP equations, hazard thresholds?** Untouched.
- **2024 Argo?** PROTECTED and not opened. No artifact contains a 2024 profile.
- **Architecture research?** Not started. The candidate scoring *worse* is
  recorded as substitution evidence only; retraining on any current product
  remains unauthorised new research, and the candidate's 2022-05 start would in
  any case give a far shorter training record.

## 10. Artifacts

`outputs/phase8c/`: `OPERATIONAL_CURRENT_SUBSTITUTION_PREREGISTRATION.md`,
`candidate_product.json`, `current_compatibility.csv`, `substitution_by_depth.csv`,
`target_metrics_by_depth.csv`, `target_bootstrap.csv`, `substitution_result.json`,
`argo_comparison.csv`, `argo_bootstrap.csv`, `argo_result.json`, the `_total`
secondary set, `argo_candidate_replay.parquet`, `recency_comparison.json`,
`decision.json`. Scripts in `scripts/nrt8c/`. Tests in
`tests/test_phase8c_current_substitution.py`.

---

# PHASE 8C GATE

```
Frozen L2 preserved: YES

Historical OSCAR replay preserved: YES

Candidate current product:
    MULTIOBS_GLO_PHY_MYNRT_015_003 / cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m

Candidate current semantics:
    geostrophic + Ekman at 15 m, tide excluded, m/s, daily, 0.25 deg
    (secondary reported: uo/vo total including tide)

Direct current compatibility:
    FAIL at channel level (INCOMPATIBLE_RAW vs OSCAR Final; pattern difference,
    rho 0.90, sigma-ratio 1.07) — as OSCAR NRT also was

Frozen-L2 substitution:
    PASS — s = 0.232 at 100 m (MINOR), worst band MINOR,
    coverage loss 0.09 % -> SUBSTITUTE_WITH_MONITORING

2022-23 Argo observational check:
    FAIL — detectably worse at 100/125/150 m (+1.42 / +1.67 / +1.64 %),
    3 of 6 key depths spanning zero (>= 4 required),
    worst degradation +1.67 % (<= +0.68 % required)

Operational recency improvement:
    2026-09-03 -> 2026-09-06 (+3 days; next bottleneck SSS at 2026-09-06)

Operational current source decision:
    SUBSTITUTE_REJECTED

Number of production reconstruction models:
    ONE

Historical Replay current source:
    OSCAR_L4_OC_FINAL_V2.0

Latest Qualified State current source:
    OSCAR_L4_OC_NRT_V2.0 (unchanged)

2024 Argo:
    PROTECTED

Full regression suite:
    885 passed (745 pytest / 105 Vitest / 35 Playwright), no failures
```

**STOP.** No retraining, no second model, no architecture research, no 2024 Argo
evaluation and no cyclone-probability work follows from this phase. If a fresher
currents source is wanted, the open options are: wait for OSCAR production to
resume; pre-register a different candidate; or pre-register a study of whether
the candidate's thermocline penalty is acceptable against a different operational
objective. Each needs separate explicit approval.
