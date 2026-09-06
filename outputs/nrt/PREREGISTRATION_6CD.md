# Phase 6C-D — Pre-registration

Written **before** any NRT product was downloaded, before any compatibility
statistic was computed, and before the substitution table was opened.
Everything below is fixed from this point on. Any deviation is reported as a
deviation, with its reason, in the final report.

Frozen at: 2026-09-05, immediately after Step 6 (overlap discovery) and before
Step 7 (download).

---

## 0. What this phase is and is not

This phase measures **whether real NRT products can be fed into the frozen
OceanEmbed input contract**, and **how much the frozen L2 model's output moves**
when they are. It is a compatibility and sensitivity audit.

It is **not** an accuracy evaluation. No skill claim is made or updated here.

Not done in this phase, at all:
- no training, fine-tuning, or re-fitting of any model
- no re-fitting of the feature scaler, target scaler, or climatology
- no adapter, bias correction, quantile mapping, or learned correction
- no Argo data is opened, including the 2024 holdout
- no GLORYS **target** variable is read on any date

---

## 1. Declared deviation: the overlap window lies inside the locked test period

The locked test split is **2022-01-01 -> 2024-12-15**.

Step 6 discovered the per-pair overlap windows. Every reference/NRT pair's
overlap is bounded below by the NRT product's own start date, and the earliest
of those is 2024-01-01 (OSCAR NRT, SMAP NRT); the all-pair intersection is
**2024-07-01 -> 2024-12-15** (168 days), bounded below by DUACS NRT.

There is therefore **no date on which a reference product and its NRT
counterpart both exist that is outside the locked test window**. The products
did not exist earlier. This is a property of the world, not a choice.

The deviation is contained as follows, and these are hard constraints, not
intentions:

1. **No target is read.** This phase opens the surface input channels only.
   The GLORYS `thetao` target is never loaded on any date. The locked test
   *labels* remain unopened.
2. **Nothing is fitted.** No statistic computed on these dates enters any
   artefact. All scalers, climatologies and weights are loaded frozen and
   verified by hash.
3. **No selection.** No architecture, hyperparameter, threshold, or reported
   experiment is chosen on the basis of these dates. The interpretation bands
   in section 4 are fixed in this document before results exist.
4. **Sensitivity, not accuracy.** Model outputs are compared to *other model
   outputs* (reference-input prediction vs NRT-input prediction). No number in
   this phase is an error against truth.

Under these constraints the locked test *evaluation* remains unspent: the
single final test-set accuracy evaluation reported in Phase 6B-A/6B-B is not
re-run, re-tuned, or invalidated by this phase.

A behavioural test enforces constraint 1: the compatibility and substitution
code paths must not open any target store.

---

## 2. Frozen input contract that NRT data must satisfy

Taken from the code, not from prose (`src/oceanembed/ml/patches.py`,
`src/oceanembed/grid.py`, Phase 6A.5 acquisition):

- domain 5-30 N, 45-105 E; grid exactly **101 lat x 241 lon** at 0.25 deg
- acquisition uses a **1 deg download pad**, then regrids to the canonical grid
- latitude ascending; longitude in [-180, 180)
- channels, in order: `sst, sss, sla, current_u, current_v, wind_u, wind_v`
- units: degC, PSU, m, m/s, m/s, m/s, m/s
- daily; wind aggregated as the **daily mean of U and V independently**
- validity is a **single joint mask**: `isfinite(all 7 channels).all(axis=0)`
- edge handling: **internal zero-pad by `patch//2` with mask = 0**, no external
  halo
- the frozen feature scaler is applied unchanged and is never refitted

Any NRT product that cannot be placed on this contract without changing it is
recorded as incompatible; the contract is not bent to accommodate a product.

---

## 3. Experiment design, fixed now

### 3.1 Sampling
- Per-pair channel comparison: every day in that pair's own overlap window that
  is present in both sources.
- Substitution experiments: the all-pair intersection **2024-07-01 ->
  2024-12-15**, sampled every **3rd day** -> **56 dates**. The stride is a
  compute budget decision made now, before any result is seen.

### 3.2 Substitution runs (Step 11)
Each run swaps **exactly one** channel's product and holds the other six at
their reference values:

`NRT_SST_ONLY`, `NRT_SSS_SMOS_ONLY`, `NRT_SSS_SMAP_ONLY`, `NRT_SLA_ONLY`,
`NRT_CURRENTS_ONLY`, `NRT_WIND_ONLY`.

`ALL_NRT_RAW` (every channel swapped simultaneously) is run **only if** at
least four of the six single-channel runs qualify as SUBSTITUTE_APPROVED or
SUBSTITUTE_WITH_MONITORING under section 4.3. If it is not run, that is
reported as a result, not as an omission.

### 3.3 OSCAR age vs product decomposition (Step 14)
The measured OSCAR NRT availability latency is 2.47 d, so the operational age
is pre-registered as **k = 3 days**. Four fields are built:

| run | product | valid time |
|---|---|---|
| A | OSCAR Final | t |
| B | OSCAR Final | t - 3 |
| C | OSCAR NRT | t |
| D | OSCAR NRT | t - 3 |

- age effect = B - A
- product effect = C - A
- interaction = (D - A) - (B - A) - (C - A)

### 3.4 SSS special handling (Step 8)
SMOS L3 and SMAP are **gappy by construction**. Their gaps are real
missingness and **must not be filled** - no interpolation, no smoothing, no
persistence, no climatology substitution inside this phase. Coverage fraction
is itself a reported result. Distribution statistics are computed on the
**common valid support only**, and the coverage loss is reported separately so
the two effects are never conflated.

Because the frozen contract uses a single joint mask, a gappy SSS channel
removes every channel at that cell. The resulting joint-mask coverage under
each SSS candidate is reported as a first-class number.

If only an L2 swath NRT SMAP product is available, the date sample for SMAP is
reduced for volume reasons and the reduced sample size is stated wherever a
SMAP number appears.

### 3.5 Statistics
On the common valid support: n, bias (NRT - reference), RMSD, MAE, Pearson r,
std ratio, p01/p50/p99 of both, and spatial-gradient mean and p95 (effective
resolution proxy). Reported for the **full North Indian Ocean domain** and
separately for the **Arabian Sea** and the **Bay of Bengal** boxes already used
in Phase 6B/6C.

---

## 4. Interpretation bands — FROZEN BEFORE RESULTS

These thresholds are set now, with no result visible. They are not adjusted
afterwards. If a result lands awkwardly across a boundary, it is reported as
landing across the boundary.

### 4.1 Channel compatibility band
Normalised by the **frozen training-period standard deviation** of that channel
taken from the frozen feature scaler, since that is the scale on which the
model actually consumes the input.

Let `r = RMSD / sigma_train`, `b = |bias| / sigma_train`, `rho` = Pearson
correlation, `q = sigma_NRT / sigma_reference`.

| band | condition (all must hold) |
|---|---|
| **INTERCHANGEABLE** | r < 0.10, b < 0.05, rho >= 0.98, 0.95 <= q <= 1.05 |
| **USABLE_WITH_CAVEAT** | r < 0.25, b < 0.15, rho >= 0.90, 0.85 <= q <= 1.15 |
| **MARGINAL** | r < 0.50, rho >= 0.75 |
| **INCOMPATIBLE_RAW** | anything else |

Bands are evaluated top-down; the first band whose conditions all hold is
assigned.

### 4.2 Model sensitivity band
Normalised by the frozen L2 model's **own established test RMSE at that depth**
(`outputs/tables/phase6b_l2_metrics_by_depth_test.csv`), because a prediction
shift only matters relative to the error the model already has.

Let `s = RMSD(prediction_NRT, prediction_reference) / RMSE_L2(depth)`.

| band | condition |
|---|---|
| **NEGLIGIBLE** | s < 0.10 |
| **MINOR** | 0.10 <= s < 0.25 |
| **MATERIAL** | 0.25 <= s < 0.50 |
| **SEVERE** | s >= 0.50 |

Primary reporting depth: **100 m** (the depth used throughout Phases 6B-6C).
Also reported: the worst band across all 15 depths, and the full depth profile.

### 4.3 Per-channel decision rule (Step 15)

| decision | condition |
|---|---|
| **SUBSTITUTE_APPROVED** | band in {INTERCHANGEABLE, USABLE_WITH_CAVEAT} **and** sensitivity at 100 m in {NEGLIGIBLE, MINOR} **and** worst-depth sensitivity <= MATERIAL **and** joint-mask coverage loss < 2 % |
| **SUBSTITUTE_WITH_MONITORING** | sensitivity at 100 m <= MATERIAL **and** worst-depth sensitivity != SEVERE, and not approved above |
| **ADAPTER_REQUIRED** | compatibility in {MARGINAL, INCOMPATIBLE_RAW} **but** the discrepancy is dominated by a stable offset or scale term rather than by decorrelation (rho >= 0.90 while b >= 0.15 or q outside [0.85, 1.15]) |
| **REJECT_RAW** | sensitivity SEVERE at 100 m, or rho < 0.75, or joint-mask coverage loss >= 20 % |

No adapter is built in this phase. ADAPTER_REQUIRED is a finding handed to a
later phase, not an action taken here.

### 4.4 Whole-stack decision rule (Step 16)

| verdict | condition |
|---|---|
| **NRT_STACK_VIABLE_RAW** | `ALL_NRT_RAW` ran, its 100 m sensitivity in {NEGLIGIBLE, MINOR}, worst depth <= MATERIAL, joint-mask coverage loss < 5 % |
| **NRT_STACK_VIABLE_WITH_MONITORING** | 100 m sensitivity <= MATERIAL and no depth SEVERE |
| **NRT_STACK_NOT_VIABLE_RAW** | otherwise, or `ALL_NRT_RAW` did not qualify to run |

The term `NRT_QUALIFIED` remains reserved and is not used by this phase.

---

## 5. Pre-declared possible outcomes

All of these are acceptable results and are reported as found:
- every channel substitutes cleanly and the stack is viable raw;
- some channels substitute and others need an adapter;
- the OSCAR discrepancy turns out to be dominated by **age**, not product;
- the OSCAR discrepancy turns out to be dominated by **product**, not age;
- no gappy SSS candidate is usable under the joint-mask contract, in which case
  the finding is that the **contract**, not the product, is the binding
  limitation;
- the whole NRT stack is not viable raw.

Finding that a substitution is unnecessary or that a product is unusable is a
result, not a failure of the phase.

---

## 6. Retrospective-download caveat

Every NRT file downloaded in Step 7 is pulled from **today's** archive state.
It may have been revised since its valid date. Therefore:
- these files support **product-difference** measurement;
- they do **not** support any claim about what an operator could have retrieved
  on the original date;
- that question is answered only by the prospective latency log, which is
  append-only and started on 2026-09-05.

Every downloaded file is recorded with `replay_mode: RETROSPECTIVE`.
