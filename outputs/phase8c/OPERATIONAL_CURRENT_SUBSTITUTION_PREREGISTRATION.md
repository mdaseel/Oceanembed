# Operational Current-Source Substitution — PRE-REGISTRATION

Frozen: 2026-09-12, **before** any candidate current field was scored against
the frozen L2, against GLORYS, or against Argo. Committed on its own; the commit
is the freeze timestamp. Nothing below is changed afterwards. Any deviation is
reported as a deviation, with its reason, in the final report.

**One model, two data regimes.** This qualifies an operational *input product*
substitution. It is not architecture research and it authorises no training.

---

## 0. Inspection summary (Phase 0)

| item | finding |
|---|---|
| **A. Historical OSCAR source** | `OSCAR_L4_OC_FINAL_V2.0` (NASA PO.DAAC), variables `u`,`v`; it is what the model-ready store holds (`source_currents: OSCAR L4_OC_FINAL v2.0 u,v (10.5067/OSCAR-25F20)`) and therefore what the frozen L2 was trained on |
| **B. Operational OSCAR source** | `OSCAR_L4_OC_NRT_V2.0`, same formulation, NRT inputs; the qualified Phase 8B currents channel |
| **C. Variables expected by frozen L2** | `current_u`, `current_v` — channels 4 and 5 of the seven, in the frozen feature-scaler order `[sst, sss, sla, current_u, current_v, wind_u, wind_v]` |
| **D. Units expected** | m s⁻¹, unconverted (`target_units: m s-1`, `conversion: none`); frozen train statistics `current_u` mean +0.0120 std 0.2241, `current_v` mean +0.0105 std 0.2081 |
| **E. Grid expected** | canonical 101 × 241 at 0.25°, 5–30 °N / 45–105 °E, latitude ascending, longitude [-180, 180) |
| **F. Temporal semantics** | daily; one field per calendar day; all seven channels on the SAME valid date (COMMON_VALID_DATE, Phase 8B) |
| **G. Current bottleneck** | OSCAR NRT stopped publishing: newest granule 2026-09-03 (ingested 2026-09-05); OSCAR INTERIM 2026-08-31; OSCAR FINAL ends 2026-01-16. Other channels reach 09-06 (SSS) to 09-12 (SLA), so the latest qualified state is pinned at 2026-09-03 |
| **H. Candidate** | `MULTIOBS_GLO_PHY_MYNRT_015_003` → dataset `cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m`, version 202411 (§1) |
| **I. Frozen hashes** | L2 state dict `b715bb2b…e728d`, encoder `30cfd2db…db4808`, feature scaler `49671ce7…`, target scaler `5b6f359d…`, L0 climatology `748af4d7…` — verified at every engine start |
| **J. 2024 Argo** | PROTECTED. Not opened by this work. The observational check reuses the executed 2022–2023 collocation artifact only |

Prior evidence carried in (Phase 6C-D, executed): OSCAR NRT vs OSCAR Final was
`INCOMPATIBLE_RAW` at channel level (ρ ≈ 0.906–0.911, RMSD/σ 0.516–0.561, near-zero
bias, σ-ratio ≈ 1.0 — a *pattern* difference, not an offset), yet
`SUBSTITUTE_WITH_MONITORING` overall because the frozen model's response was only
MINOR (s = 0.202 at 100 m). That is the precedent this candidate is measured
against.

## 1. Candidate product, verified from the provider catalogue

| field | value |
|---|---|
| product | `MULTIOBS_GLO_PHY_MYNRT_015_003` — "Global Total (COPERNICUS-GLOBCURRENT), Ekman and Geostrophic currents at the Surface and 15m" |
| dataset (operational) | `cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m`, version 202411 |
| dataset (multi-year twin, context only) | `cmems_obs-mob_glo_phy-cur_my_0.25deg_P1D-m`, 1993-01-01 → 2026-03-31 |
| provider | Copernicus Marine |
| temporal coverage (NRT) | **2022-05-01 → 2026-09-10** (at verification), daily (86 400 000 ms step) |
| spatial resolution | 0.25°, native centres at x.125 (offset from the canonical grid, so regridding is required exactly as for every other product) |
| depth coordinate | two levels: **0 m and 15 m** |
| variables | `uo`,`vo` (total = geostrophic + Ekman + **tide**), `ugos`,`vgos` (geostrophic, no depth axis), `ue`,`ve` (Ekman, 0/15 m), `utide`,`vtide` (tidal), plus per-variable `err_*` |
| units | m s⁻¹ (`m/s`), `standard_name` eastward/northward_sea_water_velocity |
| retrievability | confirmed: 2024-07-01 over the padded NIO box returned 108 × 248 cells, 222.7 KB, values within ±2 m s⁻¹ |
| access | `copernicusmarine.subset`, same client and credentials handling as every other Copernicus channel |

### 1.1 Which variable is the OSCAR analogue — decided now

OSCAR v2.0 is documented in this repository as *"DIAGNOSTIC: derived from SSH
gradients, wind and SST"*, with `depth: 15m` and *"velocities are an average
over the top 30 m of the mixed layer"*. It carries **no tidal term**.

The candidate's `uo`/`vo` explicitly add a tidal component, which the frozen
model has never seen in this channel.

- **PRIMARY (decision-bearing):** `u = ugos + ue(depth = 15 m)`,
  `v = vgos + ve(depth = 15 m)` — geostrophic + Ekman at 15 m, **tide excluded**.
  This matches OSCAR's physical definition and its nominal 15 m depth.
- **SECONDARY (reported, never decision-bearing):** `uo`/`vo` at 15 m, i.e. the
  product's own total including tide. Declared here so that reporting it later
  cannot be mistaken for choosing the better of the two after the fact.

Known, disclosed approximation: OSCAR is a 0–30 m average while the candidate is
a 15 m level. Both are labelled 15 m; they are not identical quantities.

## 2. Hypothesis and design

> Can the SAME frozen L2 accept the candidate operational current product in
> place of OSCAR `current_u`/`current_v`, without materially degrading
> reconstruction skill, while improving operational recency?

- **Control:** frozen L2 with OSCAR currents.
- **Candidate:** frozen L2 with candidate currents.
- **Every other channel is identical** between control and candidate, per date.
- **No retraining, fine-tuning, adapter, bias correction or quantile mapping.**
  This holds even if the candidate scores *better* than OSCAR.

## 3. Dates — fixed now, no cherry-picking

- **D1 — substitution and target-based evaluation:** the **56 dates already
  pre-registered in Phase 6C-D** (2024-07-01 → 2024-12-13, every 3rd day), all
  inside candidate coverage. No new selection.
- **D2 — observational check:** the **existing executed 2022–2023 Argo
  collocations**, restricted by one rule fixed now — *on or after the candidate's
  coverage start, 2022-05-01*. That yields **4,347 profiles, 87 floats, 610
  dates** (2022-05-01 → 2023-12-31). Positions, times, QC and collocation method
  are reused unchanged from Phase 6C-A; no profile is re-selected and nothing is
  re-tuned.
- **No other dates are scored.** If a date cannot be assembled it is reported as
  skipped, with its count.

## 4. Metrics

**Direct product compatibility (Phase 3)** — candidate vs the training-lineage
OSCAR Final field held in the model-ready store, on D1, using the executed 6C-D
machinery (`nrt.compatibility.channel_stats / classify`): n, coverage, bias,
RMSD, MAE, Pearson ρ (daily median), σ-ratio, RMSD/σ_train, gradient ratio, for
whole NIO, Arabian Sea and Bay of Bengal. Candidate vs OSCAR **NRT** is reported
alongside as context.

**Frozen-L2 substitution (Phase 4)** — identical inputs except currents;
`s = RMSD(pred_candidate, pred_control) / RMSE_L2_test(depth)` at all 15 depths,
on cells alive in both runs. Reported with attention to 0–50 m, 75/100/125 m,
150 m and 200–300 m, and with 500/700/1000 m and the existing deep-skill caveat
retained.

**Target-based hindcast (Phase 5)** — control and candidate against the SAME
GLORYS reference on D1: RMSE, bias, correlation and anomaly correlation at all
15 depths, plus L0, for whole NIO / Arabian Sea / Bay of Bengal.

**Observational check (Phase 6)** — L0, control (OSCAR) and candidate against the
SAME Argo values at the SAME collocations: RMSE and bias by depth, correlation,
anomaly correlation, at the six key depths 50/75/100/125/150/200 m, with the
existing **float-clustered** paired bootstrap (1,000 replicates, seed 20260912).

**Operational recency (Phase 7)** — for OSCAR NRT and for the candidate: newest
provider valid time, retrieval time, effective daily date, input age,
availability across recent days, and the resulting newest complete
seven-channel date, before and after.

## 5. Gates — reused from executed phases, fixed before results

| gate | rule | source |
|---|---|---|
| **C1 channel compatibility band** | INTERCHANGEABLE / USABLE_WITH_CAVEAT / MARGINAL / INCOMPATIBLE_RAW from r = RMSD/σ_train, b = \|bias\|/σ_train, ρ, q = σ_cand/σ_ref | 6C-D §4.1, unchanged |
| **C2 model sensitivity band** | NEGLIGIBLE < 0.10 ≤ MINOR < 0.25 ≤ MATERIAL < 0.50 ≤ SEVERE on s at 100 m, plus worst depth | 6C-D §4.2, unchanged |
| **C3 per-channel decision** | SUBSTITUTE_APPROVED / SUBSTITUTE_WITH_MONITORING / ADAPTER_REQUIRED / REJECT_RAW, REJECT_RAW overriding | 6C-D §4.3, unchanged (same code path) |
| **C4 whole-stack verdict** | NRT_STACK_VIABLE_RAW / …WITH_MONITORING / NOT_VIABLE_RAW for the complete seven-channel operational stack with the candidate | 6C-D §4.4, unchanged |
| **C5 skill vs climatology** | whole NIO: candidate beats L0 at ≥ 6 of the 11 depths 0–200 m | Phase 8B G3 (= 6C-A gate A) |
| **C6 thermocline** | at 75, 100 and 125 m: candidate beats L0 **and** the paired date-bootstrap 95 % CI of (RMSE_cand − RMSE_L0) lies entirely below zero | Phase 8B G4 (= 6C-A gate C) |
| **C7 basins** | at 100 m candidate beats L0 in both the Arabian Sea and the Bay of Bengal | Phase 8B G5 (= 6C-C criterion 4) |
| **C8 observational non-inferiority** | vs the OSCAR control against Argo, at the six key depths: the paired float-clustered 95 % CI of the RMSE difference spans zero at **≥ 4 of 6**, **and** the worst key-depth degradation is ≤ **+0.68 %** | 6C-C promotion precedent: +0.68 % at 100 m with 2/6 detectable was the **weakest policy ever promoted** (`CURRENT_STALE_3D`). Using the weakest previously promoted policy as the bar invents no new threshold |

## 6. Decision

| outcome | condition |
|---|---|
| **SUBSTITUTE_APPROVED** | C3 = SUBSTITUTE_APPROVED **and** C4 viable **and** C5, C6, C7 pass **and** C8 passes |
| **SUBSTITUTE_WITH_MONITORING** | C3 = SUBSTITUTE_WITH_MONITORING **and** C4 viable **and** C5, C6, C7 pass **and** C8 passes |
| **SUBSTITUTE_REJECTED** | anything else — including any C8 failure, C4 NOT_VIABLE, or C3 REJECT_RAW / ADAPTER_REQUIRED |

Integration happens **only** on APPROVED or WITH_MONITORING, and only for the
operational/latest mode.

## 7. What does not change, whatever the result

- Historical Replay keeps OSCAR currents, over its whole 2015–2024 record. No
  splicing of OSCAR and candidate inside the historical record, ever.
- The frozen L2, both scalers, L0 and the Phase 7 benchmark metrics are
  untouched; D26/TCHP equations and hazard thresholds are untouched.
- One production reconstruction model. If the candidate scores better than
  OSCAR, that is recorded as operational-substitution evidence only; retraining
  on the candidate is new research and is **not** authorised here.
- 2024 Argo stays PROTECTED and unopened.
- The UI must state both the operational current source and the historical
  training source, and never hide that they differ.

## 8. Artifacts to be produced

`outputs/phase8c/`: `candidate_product.json`, `current_compatibility.csv`,
`substitution_by_depth.csv`, `target_metrics_by_depth.csv`, `argo_comparison.csv`,
`argo_bootstrap.csv`, `recency_comparison.json`, `decision.json`; report
`OPERATIONAL_CURRENT_SOURCE_QUALIFICATION_REPORT.md`; tests.

## 9. Pre-declared possible outcomes

All are acceptable and will be reported as found: the candidate is
indistinguishable from OSCAR for the frozen model; it is measurably different but
still skilful (WITH_MONITORING); it is better than OSCAR (recorded, **no
retraining**); it fails the observational check and is rejected; or it cannot be
assembled on enough dates and the phase reports insufficient evidence.
