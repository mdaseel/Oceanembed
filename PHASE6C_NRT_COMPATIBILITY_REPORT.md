# Phase 6C-D — Real NRT Product Compatibility and Prospective Latency Audit

**OceanEmbed (SIH26066)** · frozen L2 satellite embedding engine
`sha256 b715bb2bff32d5e4…` · patch 33 · latent 32
Run date 2026-09-05 · full test suite **347 passed** (baseline before this phase: 324)

---

## 0. What this phase did, and what it deliberately did not do

This phase asked one question: **can OceanEmbed actually be fed by products that
exist in near-real time, and what happens to the frozen model's output when it
is?**

It is a compatibility and sensitivity audit. It is **not** an accuracy
evaluation, and it makes no skill claim.

Nothing was trained. Nothing was fitted. No adapter, bias correction or quantile
mapping was built. No Argo data was opened, including the 2024 holdout. **No
GLORYS target variable was read on any date** — a constraint enforced in code
(`assert_no_target_access`) and pinned by a test, for the reason set out in §1.

A pre-registration was written **before any NRT file was downloaded and before
any statistic was computed**: [`outputs/nrt/PREREGISTRATION_6CD.md`](outputs/nrt/PREREGISTRATION_6CD.md).
Every interpretation threshold in this report comes from that document. None was
adjusted afterwards.

---

## 1. A declared deviation you should know about before reading any number

**The overlap window falls entirely inside the locked test split.**

The locked test split is 2022-01-01 → 2024-12-15. Step 6 discovered each
reference/NRT overlap independently (no universal window was assumed):

| pair | overlap | days | lower bound set by | upper bound set by |
|---|---|---|---|---|
| OSTIA REP ↔ OSTIA NRT | 2024-01-17 → 2024-12-15 | 334 | NRT product start | local archive end |
| MULTIOBS ↔ SMOS L3 | 2015-01-01 → 2024-12-15 | 3637 | local archive start | local archive end |
| MULTIOBS ↔ SMAP | 2024-01-01 → 2024-12-15 | 350 | NRT product start | local archive end |
| DUACS REP ↔ DUACS NRT | 2024-07-01 → 2024-12-15 | 168 | NRT product start | local archive end |
| OSCAR Final ↔ OSCAR NRT | 2024-01-01 → 2024-12-15 | 350 | NRT product start | local archive end |
| CCMP ↔ Copernicus NRT wind | 2024-06-13 → 2024-12-15 | 186 | NRT product start | local archive end |

All-pair intersection: **2024-07-01 → 2024-12-15, 168 days.**

There is **no date on which a reference product and its NRT counterpart both
exist that lies outside the locked test window** — the NRT products did not
exist earlier. This is a property of the world, not a choice, and the phase
could not be done at all without accepting it.

The deviation is contained by four hard constraints, declared in advance:

1. **No target is read.** Only the seven surface input channels are opened.
   The locked test *labels* remain unopened. Enforced in code and by test.
2. **Nothing is fitted.** All scalers, climatologies and weights are loaded
   frozen and hash-verified before and after every run.
3. **No selection.** No architecture, hyperparameter, threshold or reported
   experiment was chosen using these dates.
4. **Sensitivity, not accuracy.** Model outputs are compared to *other model
   outputs*. No number here is an error against truth.

Under these constraints the single locked test evaluation reported in Phases
6B-A/6B-B is neither re-run nor spent.

---

## 2. Prospective availability latency (Step 4)

Historical latency **cannot** be reconstructed from today's archive: a file
pulled today from a revised archive says nothing about what an operator could
have obtained on the original date. The only honest measurement is prospective,
so a poll log was started on 2026-09-05 and is append-only;
`first_seen_by_oceanembed` is never overwritten once a valid time has been seen.

| product | role | newest valid time | snapshot latency (days) |
|---|---|---|---|
| `SMAP_RSS_L2_SSS_NRT_V6` | NRT | 2026-09-05 | **0.37** |
| DUACS NRT SLA | NRT | 2026-09-05 | **0.50** |
| Copernicus NRT wind | NRT | 2026-09-04 | **0.54** |
| OSTIA NRT SST | NRT | 2026-09-04 | **1.50** |
| SMOS L3 SSS (CMEMS) | NRT | 2026-09-03 | **2.50** |
| OSCAR NRT currents | NRT | 2026-09-03 | **2.50** ← NRT bottleneck |
| OSTIA REP SST | reference | 2026-03-31 | 158.5 |
| DUACS REP SLA (C3S) | reference | 2026-01-16 | 232.5 |
| OSCAR Final currents | reference | 2025-04-22 | 501.5 |
| CCMP v3.1 wind | reference | 2025-04-22 | 501.5 |

**Honest limitation, stated rather than hidden:** the log currently holds 24
rows over 4 poll cycles on a single day. Each figure above is a *snapshot* —
the newest valid time minus the first poll that saw it — and is therefore an
**upper bound** on true provider latency, because the field may have appeared
earlier than the first poll. It is not extrapolated and should not be quoted as
a service-level number until the log spans weeks. Log:
`outputs/nrt/latency_log.parquet`; summary `outputs/tables/phase6cd_latency_summary.csv`.

**The finding that matters is the gap, not the precise values.** Every product
OceanEmbed was trained on lags by **158 to 501 days**. Every NRT counterpart is
available within **0.4 to 2.5 days**. The training products are structurally
unusable in an operational setting; the substitution question is not optional.

*Figure:* `outputs/figures/phase6cd_01_latency.png`, `…_02_overlap.png`

---

## 3. Data acquired (Step 7)

2.34 GB across 14 files, all recorded with `replay_mode: RETROSPECTIVE`
(`outputs/nrt/fetch_manifest.json`). Every product was harmonised onto the
frozen contract using **the training regridding function itself**
(`regrid_horizontal`), not a reimplementation — if the two paths diverged, every
number in this report would be measuring that divergence instead of a product
difference.

| product | native | after harmonisation |
|---|---|---|
| OSTIA NRT SST | 0.05°, K | 101×241, °C |
| DUACS NRT SLA | 0.125°, m | 101×241, m |
| SMOS L3 asc SSS | 0.2°, QC-filtered | 101×241, PSU |
| Copernicus NRT wind | 0.125°, hourly | 101×241, daily mean of U and V **independently** |
| OSCAR NRT currents | 0.25°, daily | 101×241, m s⁻¹ (also at *t*−3) |
| SMAP L2C NRT SSS | orbital swath | binned to 101×241, gaps preserved |

**SMAP required a decision.** PO.DAAC publishes no daily gridded NRT SMAP
product — only L2 swath NRT, or an 8-day running-mean science L3. The L2C
granules were therefore binned: a retrieval contributes to the one canonical
cell containing it, a cell's value is the mean of the qualified retrievals that
landed in it, and a cell with no qualified retrieval **stays NaN**. No
interpolation, spreading or smoothing. Volume forced a reduced sample of
**7 dates** (§8), and that reduced *n* is carried with every SMAP number below.

Two acquisition bugs were found and fixed rather than absorbed: a date-only CMR
temporal range silently pulled the *next* day's orbits into each "daily" SMAP
composite (roughly doubling its apparent coverage), and a granule listing capped
at 60 was truncating a day that actually has ~120 sub-orbital segments. Both
were corrected and the SMAP ingest re-run from scratch.

---

## 4. Raw channel compatibility, no calibration (Steps 9–10)

No correction of any kind was applied before these numbers. `σ_train` is the
frozen training-period standard deviation of that channel taken from the frozen
feature scaler — the scale on which the model actually consumes the input.

Full North Indian Ocean:

| channel | NRT product | days used | NRT coverage | bias | RMSD | ρ (daily median) | σ ratio | RMSD/σ | band |
|---|---|---|---|---|---|---|---|---|---|
| sst | OSTIA NRT | 168/168 | 0.994 | −0.069 °C | 0.336 °C | 0.975 | 1.013 | 0.194 | **USABLE_WITH_CAVEAT** |
| sss | SMOS L3 asc | 100/168 | **0.024** | +0.253 PSU | 0.858 PSU | 0.275 | 2.078 | 0.439 | **INCOMPATIBLE_RAW** |
| sss | SMAP L2C | 7/7 | **0.532** | −1.370 PSU | 2.714 PSU | 0.856 | 2.047 | 1.391 | **INCOMPATIBLE_RAW** |
| sla | DUACS NRT | 168/168 | 0.997 | +0.002 m | 0.029 m | 0.959 | 1.032 | 0.303 | **MARGINAL** |
| current_u | OSCAR NRT | 56/56 | 0.952 | −0.005 m/s | 0.116 m/s | 0.911 | 0.987 | 0.516 | **INCOMPATIBLE_RAW** |
| current_v | OSCAR NRT | 56/56 | 0.952 | +0.001 m/s | 0.117 m/s | 0.906 | 1.032 | 0.561 | **INCOMPATIBLE_RAW** |
| wind_u | CMEMS NRT | 168/168 | 1.000 | +0.060 m/s | 0.744 m/s | 0.970 | 1.005 | 0.158 | **USABLE_WITH_CAVEAT** |
| wind_v | CMEMS NRT | 168/168 | 1.000 | +0.099 m/s | 0.753 m/s | 0.972 | 1.013 | 0.173 | **USABLE_WITH_CAVEAT** |

Basin breakdown (bands only; full table in
`outputs/tables/phase6cd_channel_compatibility.csv`):

| channel / product | Arabian Sea | Bay of Bengal |
|---|---|---|
| sst / OSTIA NRT | USABLE_WITH_CAVEAT | **MARGINAL** (ρ 0.830) |
| sss / SMOS | INCOMPATIBLE_RAW (68 usable days) | INCOMPATIBLE_RAW — **0 usable days of 168** |
| sss / SMAP | INCOMPATIBLE_RAW (ρ 0.667) | INCOMPATIBLE_RAW (bias −3.18 PSU) |
| sla / DUACS NRT | MARGINAL | MARGINAL |
| currents / OSCAR NRT | **MARGINAL** | INCOMPATIBLE_RAW |
| wind / CMEMS NRT | USABLE_WITH_CAVEAT | USABLE_WITH_CAVEAT |

Three things in that table are worth stating plainly:

**The currents discrepancy is not an offset.** Bias is essentially zero
(|bias|/σ ≈ 0.02) and the variance ratio is ≈ 1.0, yet RMSD/σ is 0.52–0.56.
OSCAR NRT and OSCAR Final agree on the mean and the spread and disagree on the
*pattern*. No affine adapter can fix that; it is not the kind of error an
adapter addresses.

**The SST discrepancy is basin-structured.** The Arabian Sea shows a −0.117 °C
bias with ρ = 0.972; the Bay of Bengal shows essentially no bias but ρ = 0.830.
The reprocessed and NRT OSTIA streams differ more in *where* they place
structure in the Bay than in their overall level.

**SMOS ascending L3 delivers nothing in the Bay of Bengal.** Not "little" —
across all 168 days there was not a single day with ≥10 co-located qualified
retrievals in the Bay of Bengal box. Domain-wide it averages **2.4 %** of ocean
cells per day.

*Figures:* `…_03_compatibility_bands.png`, `…_04_normalised_discrepancy.png`,
`…_08_gradient_ratio.png`

### Effective resolution

The spatial-gradient ratio (mean |∇| NRT ÷ reference) shows the NRT wind carries
**15–25 % more small-scale structure** than 6-hourly CCMP (0.125° hourly vs
0.25° 6-hourly), NRT SLA about 5 % more, and NRT SST about **8 % less**. The
gappy SSS products show ratios of 4–4.7, which is an artefact of computing
gradients across swath edges, not a resolution statement, and is reported as
such.

---

## 5. SSS: the special case (Step 8)

Both NRT SSS candidates are gappy by construction, and their gaps were **not
filled** — no interpolation, no persistence, no climatology, nothing. Coverage
is itself a result.

| | MULTIOBS L4 (training) | SMOS L3 asc | SMAP L2C binned |
|---|---|---|---|
| mean daily ocean coverage | 98.4 % | **2.4 %** | **53.2 %** |
| days with usable common support | 168/168 | 100/168 | 7/7 |
| Bay of Bengal usable days | 168 | **0** | 7 |
| median p50 (PSU) | 35.96 / 35.57 | 36.21 | 34.66 |
| bias vs reference | — | +0.25 PSU | −1.37 PSU |
| ρ | — | 0.275 | 0.856 |

**SMAP gaps were not filled from SMOS or from anything else.** The two are
reported independently, as required.

The decisive point is not the retrieval quality, it is the **contract**. The
frozen input contract computes a *single joint validity mask*:
`isfinite(all 7 channels).all(axis=0)`. It cannot express a per-channel outage.
So a cell missing only SSS loses **all seven channels**. Substituting SMOS
therefore destroys **97.7 %** of the model's live cells; substituting SMAP
destroys **44.6 %**.

That is a limitation of the input contract as much as of the products. A
production system needing a single-mission SSS feed would have to change the
mask semantics — which is a Phase 6B-level architectural change, not something
this phase is permitted to do.

*Figures:* `…_05_sss_coverage.png`, `…_06_sss_maps.png`

---

## 6. Frozen-L2 substitution sensitivity (Steps 11–13)

Each run swaps one channel's product, holds the other six at reference values,
and compares the frozen model's prediction against the reference-input
prediction **on cells alive in both runs**, so a coverage change can never be
mistaken for a value change. `s` = shift RMSD ÷ the frozen L2's own test RMSE at
that depth. The L2 state-dict hash was verified identical before and after every
pass.

At **100 m** (the primary reporting depth used throughout Phases 6B–6C):

| run | days | coverage loss | shift RMSD | s | band (100 m) | worst band | decision |
|---|---|---|---|---|---|---|---|
| `NRT_WIND_ONLY` | 56 | 0.000 | 0.041 °C | 0.034 | NEGLIGIBLE | NEGLIGIBLE | **SUBSTITUTE_APPROVED** |
| `NRT_SST_ONLY` | 56 | 0.000 | 0.141 °C | 0.118 | MINOR | MATERIAL (0 m) | **SUBSTITUTE_APPROVED** |
| `NRT_CURRENTS_ONLY` | 56 | 0.003 | 0.240 °C | 0.202 | MINOR | MINOR | **SUBSTITUTE_WITH_MONITORING** |
| `NRT_SLA_ONLY` | 56 | 0.000 | 0.340 °C | 0.286 | MATERIAL | MATERIAL | **SUBSTITUTE_WITH_MONITORING** |
| `NRT_SSS_SMAP_ONLY` | **7** | 0.446 | 0.858 °C | 0.722 | SEVERE | SEVERE | **REJECT_RAW** |
| `NRT_SSS_SMOS_ONLY` | 56 | 0.977 | 1.479 °C | 1.244 | SEVERE | SEVERE | **REJECT_RAW** |

Depth structure worth noting:

- **SST** is worst at the *surface* (s = 0.281 at 0 m) and settles to
  0.06–0.12 below 100 m — the reprocessed/NRT difference is a near-surface
  effect, which is what one would expect.
- **SLA and currents** peak in the **thermocline** (100–125 m) and fall away
  above and below, consistent with those channels informing thermocline depth.
- **Wind** is negligible at every depth (max s = 0.034). The frozen model barely
  uses the distinction between two wind products.

*Figure:* `…_09_sensitivity_profiles.png`, `…_11_decisions.png`

---

## 7. OSCAR: separating the age effect from the product effect (Step 14)

OSCAR NRT arrives with ~2.5 days of latency, so operationally it is both a
*different product* and an *older field*. Four runs separate the two, using the
pre-registered k = 3 days:

| run | product | valid time |
|---|---|---|
| A | OSCAR Final | *t* (the reference) |
| B | OSCAR Final | *t* − 3 → **age effect** |
| C | OSCAR NRT | *t* → **product effect** |
| D | OSCAR NRT | *t* − 3 → the operational case |

RMSDs do not add; variances of independent effects do, so the decomposition is
done on squared shifts.

| depth | age only | product only | both (operational) | quadrature sum | age share | dominant |
|---|---|---|---|---|---|---|
| 30 m | 0.099 | 0.104 | 0.139 | 0.144 | 47.8 % | PRODUCT |
| 100 m | **0.269** | **0.242** | **0.354** | 0.362 | 55.4 % | AGE |
| 150 m | 0.233 | 0.184 | 0.290 | 0.297 | 61.6 % | AGE |
| 200 m | 0.157 | 0.118 | 0.193 | 0.196 | 63.7 % | AGE |
| 1000 m | 0.030 | 0.029 | 0.040 | 0.042 | 51.5 % | AGE |

**Answer: neither dominates.** Age and product contribute 45–64 % of the
variance depending on depth, they are close to independent (the interaction term
is small and slightly negative at every depth), and the operational case is very
close to the quadrature sum of the two.

The practical consequence: OSCAR NRT's product-only sensitivity is **MINOR**
(s = 0.202 at 100 m), but the *operational* combination of a different product
three days old is **s = 0.298, MATERIAL**. Roughly half of that is simply
staleness and would not be repaired by any product change.

*Figure:* `…_10_oscar_age_vs_product.png`

---

## 8. Whole-stack substitution (Steps 15–16)

The pre-registered gate required at least four of six single-channel runs to
qualify before `ALL_NRT_RAW` was permitted to run. Exactly **four** qualified
(SST, wind approved; SLA, currents with monitoring), so the gate opened and the
run went ahead — evaluated in code, not by eye.

| run | kind | days | coverage loss | s (100 m) | band | worst band |
|---|---|---|---|---|---|---|
| `ALL_NRT_RAW` (SSS = SMOS) | **pre-registered** | 56 | 0.977 | 1.188 | SEVERE | SEVERE |
| `ALL_NRT_RAW_SMAP_SSS` | post-hoc | 7 | 0.446 | 0.739 | SEVERE | SEVERE |
| `ALL_NRT_EXCEPT_SSS` | post-hoc | 56 | 0.003 | **0.362** | **MATERIAL** | MATERIAL |

### Verdict, by the pre-registered rule

> **NRT_STACK_NOT_VIABLE_RAW** — 100 m band SEVERE, worst band SEVERE, joint-mask
> coverage loss 0.977.

The reserved term `NRT_QUALIFIED` is **not** used and remains reserved.

The two post-hoc rows are labelled post-hoc because they were added after the
single-channel results were seen. They are diagnostics, they use the same
pre-registered bands, and they did **not** change the verdict, which rests
solely on the pre-registered `ALL_NRT_RAW`.

The `ALL_NRT_EXCEPT_SSS` diagnostic is nonetheless the most operationally
informative line in this report: **with SSS held at its reference product, the
other four channels substitute together to a MATERIAL — not SEVERE — shift**
(s = 0.362 at 100 m) with essentially no coverage loss. The four channels
compose roughly as expected rather than compounding catastrophically. SSS alone
carries the failure.

---

## 9. Answers to the questions this phase was set

**Can OceanEmbed be fed by NRT products today?** Not as a complete raw
substitution. Four of six channels can be substituted (two approved, two with
monitoring). The SSS channel cannot, from either candidate, and under the
current single-joint-mask contract that one channel takes the whole field with
it.

**Which channel is the binding constraint?** SSS, decisively and by a wide
margin. Every other channel's substitution shift is between 0.03 and 0.29 of the
model's existing error; SSS is 0.72–1.24.

**Is that the product's fault or the system's?** Both, and the split matters.
SMOS ascending L3 genuinely delivers almost nothing over this domain (2.4 %
daily coverage; zero usable days in the Bay of Bengal). SMAP is a real product
with 53 % daily coverage that is *rejected by the contract*, not by its
quality — its correlation is 0.856 and it fails principally on coverage and on a
−1.37 PSU offset. A per-channel validity mask, rather than one joint mask, is
the change that would make a gappy SSS feed usable at all. That is a Phase-6B
architectural change and is explicitly **not** made here.

**Is the OSCAR problem the product or the delay?** Neither alone — they are
comparable in size and close to independent, contributing 45–64 % each depending
on depth. Fixing the product would recover at most about half of the operational
sensitivity.

**Does an adapter look warranted?** For no channel does the pre-registered
`ADAPTER_REQUIRED` condition fire. The channels that fail on *pattern*
(currents, ρ ≈ 0.91 with near-zero bias and unit variance ratio) fail in a way
an affine adapter cannot fix. The channels that fail on *offset* (SMAP,
−1.37 PSU) also fail the correlation floor. This is a negative result and is
reported as one: **no adapter is recommended by this evidence**, and none was
built.

---

## 10. Deviations, ambiguities and limitations

Reported because they are real, not because anyone asked:

1. **The overlap window is inside the locked test split.** Unavoidable; contained
   by the four constraints in §1. No target was read; the locked evaluation is
   not spent.
2. **The pre-registered decision table had an ordering ambiguity.** REJECT_RAW's
   conditions can hold simultaneously with SUBSTITUTE_WITH_MONITORING's, and no
   precedence was stated. REJECT_RAW is treated as an overriding disqualifier.
   On these results the choice **changes no verdict**, because every channel it
   could have affected is already SEVERE at 100 m.
3. **The band rule did not name a region.** Decisions are taken on the full-NIO
   band, with basin variation reported as a caveat (§4). For a two-component
   channel the *worse* of the two component bands is used.
4. **SMAP rests on 7 days, not 56.** Its `n` is carried everywhere it appears.
   Its numbers are directionally informative and are not equal-weight evidence
   with the 56-day runs.
5. **Latency is a 1-day, 4-cycle snapshot** and an upper bound. It should be
   re-read once the log spans weeks.
6. **Downloads are retrospective.** They support product-difference measurement
   only. They cannot support any claim about what was retrievable on the
   original date.
7. **Two post-hoc runs were added** after seeing results; both are labelled and
   neither influences the verdict.
8. **The SSS gradient ratios (≈4–4.7) are swath-edge artefacts**, not resolution
   statements.

---

## 11. Artefacts

**Code** — `src/oceanembed/nrt/`: `registry.py`, `discover.py`, `latency.py`,
`log_availability.py`, `harmonize.py`, `compatibility.py`, `substitution.py`.
**Scripts** — `scripts/nrt/`: `discover_overlap.py`, `fetch_nrt.py`,
`fetch_oscar_lag.py`, `fetch_smap.py`, `harmonise_nrt.py`, `compare_channels.py`,
`substitution_run.py`, `make_figures_nrt.py`.

**Tables** (`outputs/tables/`) — `phase6cd_latency_summary.csv`,
`phase6cd_channel_daily.csv`, `phase6cd_channel_compatibility.csv`,
`phase6cd_substitution_sensitivity.csv`, `phase6cd_substitution_summary.csv`,
`phase6cd_oscar_age_vs_product.csv`, `phase6cd_oscar_decomposition_detail.csv`,
`phase6cd_daily_coverage.csv`.

**Provenance** (`outputs/nrt/`) — `PREREGISTRATION_6CD.md`,
`product_registry.json`, `overlap_manifest.json`, `fetch_manifest.json`,
`harmonisation_log.json`, `smap_ingest_log.json`, `compatibility_meta.json`,
`substitution_meta.json`, `latency_log.parquet`,
`source_availability_snapshot.json`.

**Figures** (`outputs/figures/`) — `phase6cd_01…11_*.png` (11 figures).

**Tests** — `tests/test_phase6cd_nrt.py`, 23 tests. Full suite **347 passed**.
They pin: first-seen is never overwritten; a re-poll invents no new first-seen;
the no-op substitution reproduces the frozen field **bitwise**; a NaN in a
substituted channel blanks the whole cell through the joint mask; target
variables are refused; regridding does not fill a gap; hourly wind is averaged
as U and V independently; SMOS QC drops rather than repairs; bands match the
pre-registration text; and overlap was discovered per pair rather than assumed
universal.

---

## 12. Decision gate

### GO — with the scope of the "go" stated precisely

The phase answered its question and the answer is actionable:

- Wind and SST substitution are **approved**.
- SLA and currents substitution are **approved with monitoring**, with the
  caveat that half of the operational currents sensitivity is staleness, not
  product.
- SSS substitution is **rejected** from both candidates, and the binding
  constraint is at least as much the single-joint-mask contract as the products.
- The whole raw NRT stack is **NRT_STACK_NOT_VIABLE_RAW**.

**Recommended next step, for your decision, not taken here:** the highest-value
follow-up is not an adapter — the evidence does not support one — but a decision
about the **joint validity mask**. A per-channel mask would convert SMAP from
"rejected by the contract" into a testable option, and would also make the
Phase 6C-C fallback contract expressible. That is an architectural change to a
frozen component and needs your explicit authorisation before anyone touches it.

**Phase boundary reached. Nothing further will be built until you have
reviewed this.**
