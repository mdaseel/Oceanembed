# Phase 8B — NRT Subsurface Qualification Protocol (PRE-REGISTRATION)

Frozen: 2026-09-11, **before** the candidate SSS product was downloaded, before
any Phase 8B statistic was computed, and before any hindcast was run. This file
is committed to git on its own; the commit is the freeze timestamp. Nothing
below is changed afterwards. Any deviation is reported in the Phase 8B report
as a deviation, with its reason, and a correction is **appended** under a
"Post-freeze corrections" heading — never edited in place.

---

## 0. The one question

> Can the COMPLETE frozen-L2 seven-channel operational input contract support a
> scientifically qualified latest available 15-depth subsurface temperature
> reconstruction?

Nothing is trained, fine-tuned, re-fitted, adapted, bias-corrected or
quantile-mapped. The frozen L2 (`b715bb2b…e728d`, encoder `30cfd2db…db4808`),
the frozen feature/target scalers, the frozen L0 climatology, the frozen D26 /
TCHP definitions (Phase 7C) and the frozen hazard thresholds (Phase 7D) are
used exactly as they are, and their hashes are verified before and after every
run. **2024 Argo is not opened, downloaded, collocated or scored.**

## 1. Evidence inspected before freezing (and prior knowledge declared)

Inspected: `PHASE6C_NRT_COMPATIBILITY_REPORT.md`, `PHASE6C_FALLBACK_ARGO_REPORT.md`,
`PHASE6C_ARGO_VALIDATION_REPORT.md`, `PHASE8A_NRT_LITE_REPORT.md`,
`outputs/phase8a/demo_resilience_test.json`, `outputs/phase7/FINAL_POC_MANIFEST.json`,
`outputs/nrt/PREREGISTRATION_6CD.md`, `src/oceanembed/nrt/*`,
`src/oceanembed/operational/*`, the model-ready 2024 store metadata, and the
live Copernicus Marine catalogue entry for `MULTIOBS_GLO_PHY_S_SURFACE_MYNRT_015_013`
(metadata only).

**Declared prior knowledge.** The author of this protocol has already seen the
Phase 6C-D results on the same 56 dates used below: SST and wind substitution
APPROVED, SLA and currents WITH_MONITORING, SMOS and SMAP SSS REJECT_RAW,
`ALL_NRT_RAW` = NRT_STACK_NOT_VIABLE_RAW, and the post-hoc diagnostic
`ALL_NRT_EXCEPT_SSS` at s = 0.362 (MATERIAL) at 100 m. The decision rules below
are copied from executed phases, not tuned to those numbers, and they are the
rules that would have been written without them.

Facts established by inspection that shape the design:

1. The training SSS is **CMEMS MULTIOBS L4** `cmems_obs-mob_glo_phy-sss_my_multi_P1D`
   (variable `sos`), confirmed from the model-ready store's own `source_sss`
   attribute. The same product publishes a daily NRT dataset,
   `cmems_obs-mob_glo_phy-sss_nrt_multi_P1D`, catalogue time extent
   2024-01-01 → 2026-09-05. **It was never audited in Phase 6C-D**, which tested
   only SMOS L3 and SMAP L2C.
2. The Phase 6C-C SSS persistence evidence (`SSS_ABSENT_PERSIST`, OBS_SUPPORTED)
   was produced with the **previous day's** field only
   (`scripts/validate/argo_fallback_replay.py`: `store.push("sss", times[t - 1], …)`).
   The `max_persist_days = 7` value in `policy.py` is a store default, **not
   evidence**. The evidenced persistence envelope is therefore **1 day**.
3. The NRT products exist only from 2024 onward. The all-product intersection
   with the reference archive is 2024-07-01 → 2024-12-15 (Phase 6C-D). 2022–2023
   Argo predates every NRT product; 2024 Argo is protected. **No observational
   (in-situ) hindcast of any operational NRT stack is possible in this phase.**

## 2. Candidate operational stack — `NRT_STACK_V1`

Exactly one candidate stack is evaluated. No other is scored.

| channel | operational product (dataset id) | family relation to training | prior evidence |
|---|---|---|---|
| sst | OSTIA NRT `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2` | same system, NRT stream | 6C-D SUBSTITUTE_APPROVED |
| sss | MULTIOBS NRT `cmems_obs-mob_glo_phy-sss_nrt_multi_P1D` (`sos`) | **same product, NRT dataset** | none — evaluated here |
| sla | DUACS NRT `cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D` | all-sat NRT vs two-sat climate record | 6C-D SUBSTITUTE_WITH_MONITORING |
| current_u/v | OSCAR NRT `OSCAR_L4_OC_NRT_V2.0` | same formulation, NRT inputs | 6C-D SUBSTITUTE_WITH_MONITORING |
| wind_u/v | CMEMS NRT wind `cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H` | different production system | 6C-D SUBSTITUTE_APPROVED |

**SSS operating policy: `SSS_MULTIOBS_NRT_SAME_DATE`.** The SSS channel is the
MULTIOBS NRT field valid on the effective date. Explicitly **not** permitted:
SMOS or SMAP substitution (6C-D REJECT_RAW); training-channel climatology
(6C-C: significantly worse against Argo, worsens the thermocline warm bias);
zero- or mean-filled SSS; persistence of any SSS field older than the evidenced
envelope.

**Persistence rule and maximum age envelope: NONE (0 days) for every channel.**
The persistence envelope evidenced in 6C-C is 1 day and only for SSS; the
alignment rule below makes persistence unnecessary, so none is used.

## 3. Temporal alignment — `COMMON_VALID_DATE`

The frozen contract was trained on seven channels valid on the **same day**.
The operational stack keeps that property:

- **Effective reconstruction date `D`** = the most recent calendar date for
  which **all seven** channels have a field from their operational product
  valid on `D`. Concretely `D = min over products (newest valid date)`, then
  confirmed by retrieving every channel for `D`.
- Every channel is used at valid date `D`. No channel is carried forward and no
  channel is taken from a different day.
- Daily fields: SST, SSS, SLA and OSCAR are daily products; wind is the daily
  mean of the hourly U and V components **independently** over `D`, exactly as in
  training and in 6C-D.
- **"Latest available" ≠ "right now".** `D` is typically several days before the
  retrieval time because the slowest channel sets it. The reconstruction is
  described as the *latest available qualified reconstruction, valid `D`*,
  never as the ocean "now".

Recorded for every latest-state candidate: requested/retrieval time (UTC);
per-product source valid time; per-product newest available valid time;
per-product source age = retrieval time − valid time; oldest and newest input
age; effective date `D`; reconstruction lag = retrieval time − `D`; persisted-input
status (always "none"); operating-policy name `NRT_STACK_V1 / COMMON_VALID_DATE /
SSS_MULTIOBS_NRT_SAME_DATE`.

Product-age computation: `age_hours = (local_retrieval_time_utc − product_valid_time_utc)`
in hours, product valid time taken from the product's own time coordinate
(00:00 UTC for daily products). A provider generation time is recorded only if
the provider states one (Phase 8A rule).

## 4. Hindcast-the-NRT

### 4.1 Dates

The **56 Phase 6C-D pre-registered dates** (2024-07-01 → 2024-12-13, every 3rd
day, `outputs/nrt/fetch_manifest.json`). They were fixed in 6C-D before any
result, and OSCAR NRT is held locally on exactly these dates. A date is used
only if all seven NRT channels are present for it; the number used is reported.

**Evidence sufficiency:** if fewer than **28** of the 56 dates (half of the
pre-registered sample) can be assembled with the complete stack, the phase
returns **`BLOCKED — INSUFFICIENT EVIDENCE`** rather than a qualification
verdict.

### 4.2 Driving path

```
date t
  → NRT_STACK_V1 products valid on t (all seven)
  → harmonised with the SAME functions as 6C-D / training
    (nrt.harmonize.to_canonical → preprocessing.regrid.regrid_horizontal)
  → the UNMODIFIED frozen day_field (single joint validity mask, frozen scaler)
  → the frozen whole-field L2 (embed_field → forward_from_z), decoded at the
    cells alive in that date's joint mask
  → 101×241×15 reconstruction  N(t)
```

Compared on the same date against:

- **R(t)** — the frozen L2 driven by the reference (training) products: the
  authoritative `replay_field(t)` historical path;
- **L0(t)** — the frozen train-only harmonic climatology;
- **G(t)** — the GLORYS12V1 reanalysis on the 15 mandated depths
  (model-ready `temp_<d>m`), the reference field.

The MULTIOBS NRT SSS is harmonised exactly like the training SSS: `sos` →
`sss`, singleton depth dropped, units PSU, no conversion (`data/loaders.py`).

### 4.3 Deviations declared now

1. **The hindcast dates lie inside the locked test split** (2022-01-01 → 2024-12-15),
   as in 6C-D. The GLORYS target is read on these dates **for evaluation only**.
   It was already read on the test split by the Phase 6B-A/B locked evaluation
   and by Phase 7C. Nothing is selected, tuned or fitted on it.
2. **The reference G is an assimilating reanalysis, not an observation.** 6C-C
   showed a case (SSS climatology) where GLORYS-based development evidence did
   not transfer to Argo. That limitation applies here in full and is the reason
   `QUALIFIED` (without limitations) is unreachable in this phase (§7).
3. **Downloads are retrospective** (today's archive state). They support
   product-difference and hindcast measurement, not claims about what was
   retrievable on the original date.

## 5. Evaluation population, regions, metrics

- **Population**, per date and depth: cells where N, R, L0 and G are all finite
  (N's and R's joint masks, L0 coefficient support, GLORYS target validity).
  All systems are scored on the identical cell set.
- **Regions**: whole NIO (all canonical cells), Arabian Sea (lat 8–25, lon
  50–77) and Bay of Bengal (lat 5–22, lon 80–100) — the frozen
  `oceanembed.ml.metrics.BASINS`, unchanged.
- **Temperature metrics, all 15 depths, each region, for N, R and L0 against G**:
  RMSE, bias (system − G), Pearson correlation, anomaly correlation (anomalies
  about L0), valid sample count; plus joint-mask coverage of N and R (fraction
  of ocean cells).
- **Skill over L0**: `1 − RMSE_N / RMSE_L0`. **Degradation versus historical
  replay**: `RMSE_N / RMSE_R − 1`.
- **Sensitivity** (6C-D §4.2, unchanged): `s = RMSD(N, R) / RMSE_L2_test(depth)`
  with `RMSE_L2_test` from `outputs/tables/phase6b_l2_metrics_by_depth_test.csv`,
  on cells alive in both runs; bands NEGLIGIBLE < 0.10 ≤ MINOR < 0.25 ≤
  MATERIAL < 0.50 ≤ SEVERE.
- **Uncertainty**: paired bootstrap over **dates** (dates are the independent
  clusters here; cells within a date are strongly correlated), 1,000 replicates,
  seed 20260911, on per-date sums. 95 % percentile intervals.
- **D26 / TCHP** (§8): frozen `oceanembed.diagnostics.d26_tchp` on N, R and G;
  MAE, RMSE, bias against G where both are defined; status counts; same
  population rule as Phase 7C (ocean AND surface-input-valid).

### 5.1 SSS channel compatibility

The MULTIOBS NRT SSS is compared with the MULTIOBS MY reference channel in the
model-ready store over every common day in 2024-07-01 → 2024-12-15, with the
frozen 6C-D machinery (`nrt.compatibility.channel_stats / classify`) and the
frozen 6C-D bands (§4.1 there). Its single-channel substitution run
`NRT_SSS_MULTIOBS_ONLY` uses the 6C-D run protocol (other six channels at
reference values, same 56 dates).

## 6. Decision rules — copied from executed phases

### 6.1 Channel gate (6C-D §4.3, unchanged)
**G1.** The SSS channel decision for `NRT_SSS_MULTIOBS_ONLY` under the 6C-D
per-channel rule (REJECT_RAW overriding, as resolved in 6C-D) is
SUBSTITUTE_APPROVED or SUBSTITUTE_WITH_MONITORING. The other four channel
decisions are the executed 6C-D decisions and are not re-run.

### 6.2 Stack gate (6C-D §4.4, unchanged)
**G2.** The whole-stack verdict for `ALL_NRT_V1` (all seven channels NRT):

| verdict | condition |
|---|---|
| NRT_STACK_VIABLE_RAW | 100 m band NEGLIGIBLE/MINOR, worst depth ≤ MATERIAL, joint-mask coverage loss < 5 % |
| NRT_STACK_VIABLE_WITH_MONITORING | 100 m band ≤ MATERIAL and no depth SEVERE |
| NRT_STACK_NOT_VIABLE_RAW | otherwise |

G2 passes for VIABLE_RAW or VIABLE_WITH_MONITORING.

### 6.3 Skill gates (6C-A gates A and C, applied to the hindcast)
**G3** (6C-A gate A). Whole NIO: RMSE_N < RMSE_L0 at a majority (≥ 6) of the 11
depths 0–200 m.

**G4** (6C-A gate C). Whole NIO: at each of 75, 100 and 125 m, RMSE_N < RMSE_L0
**and** the paired date-bootstrap 95 % interval of `RMSE_N − RMSE_L0` lies
entirely below zero.

**G5** (6C-C criterion 4, basin check). At 100 m, RMSE_N < RMSE_L0 in the
Arabian Sea **and** in the Bay of Bengal.

## 7. Qualification categories

| category | condition |
|---|---|
| **QUALIFIED** | not reachable in Phase 8B: requires an independent observational hindcast of the operational stack, which no permitted data supports (§1.3) |
| **QUALIFIED WITH LIMITATIONS** | G1 and G2 and G3 and G4 and G5 all pass |
| **NOT QUALIFIED** | any of G1–G5 fails |
| **BLOCKED — INSUFFICIENT EVIDENCE** | fewer than 28 dates assemble, or a required NRT product cannot be acquired for the hindcast |

Under QUALIFIED WITH LIMITATIONS the limitations are stated, never softened:
no observational validation of the NRT stack; reference is an assimilating
reanalysis; every depth where N does not beat L0 is listed as a depth-dependent
limitation; the measured degradation versus historical replay is shown; the
500–1000 m disclosure applies (deep anomaly skill weak, climatology-dominant;
low deep RMSE is not strong deep skill); the 6C-D channels decided WITH_MONITORING
are named.

## 8. D26 / TCHP operational qualification

Evaluated **only if** temperature is QUALIFIED WITH LIMITATIONS. Frozen Phase 7C
definitions; nothing about interpolation, ρ₀, c_p, integration or invalid-case
behaviour changes.

No executed phase defines a pass/fail threshold for D26/TCHP error. The
conservative rule that invents no margin is the 6C-C *non-inferiority to the
reference-input mode* logic:

**D26 (resp. TCHP) is QUALIFIED iff**, in the whole NIO **and** in each basin,
the paired date-bootstrap 95 % interval of `MAE(N vs G) − MAE(R vs G)` contains
zero or lies entirely below zero — i.e. the operational mode is not detectably
worse than the historical replay the Phase 7C numbers describe. Otherwise
NOT QUALIFIED. If temperature is not qualified, D26 and TCHP are NOT QUALIFIED
without evaluation of the gate.

## 9. Latest Ocean Hazard Indicator transfer

The Phase 7D indicator is a fixed function of TCHP, D26 status and physical
support with frozen thresholds (55.70 / 79.10 / 96.94 kJ cm⁻²), which are **not
retuned**. Transfer is QUALIFIED iff TCHP is QUALIFIED under §8; otherwise
latest hazard indicators remain **HISTORICAL ONLY**. The category agreement
between N and R on the hindcast dates is reported descriptively. No numeric
cyclone probability exists or is produced.

## 10. Operational (latest-state) conditions — only if qualified

If and only if the category is QUALIFIED WITH LIMITATIONS, `latest_qualified_field()`
may run, and at request time it **refuses inference** unless every condition
holds:

- **L1** all seven channels retrieved from exactly the §2 dataset ids;
- **L2** a common valid date `D` exists and every channel was retrieved for `D`;
- **L3** harmonised by the same functions as the hindcast;
- **L4** joint-mask coverage of the canonical ocean cells is not more than 5
  percentage points below the hindcast REFERENCE mean coverage (the 6C-D < 5 %
  coverage-loss condition);
- **L5** frozen hashes verified.

Any failure → no latest inference, no partial-stack inference, no fallback.

## 11. Wording, fixed now

- Qualified with limitations: tab **Latest Qualified Ocean State**, banner
  `QUALIFIED WITH LIMITATIONS`, reconstruction described as "latest available
  qualified reconstruction, valid <D>".
- Not qualified / blocked: tab stays **Latest Inputs**, banner
  `LATEST SUBSURFACE RECONSTRUCTION NOT QUALIFIED` (or `… BLOCKED — INSUFFICIENT
  EVIDENCE`); no latest subsurface map is exposed as qualified.
- Stale: `LAST SUCCESSFUL QUALIFIED SNAPSHOT — NOT CURRENT`. None: `LATEST
  QUALIFIED OCEAN STATE CURRENTLY UNAVAILABLE`.
- Never: "Live Ocean Right Now", "Corrected Ocean State", "Historical Forecast",
  any numeric cyclone probability.
