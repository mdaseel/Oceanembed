# OceanEmbed — Architecture Closure Study

**SIH26066** · Experiments A (literature) · B (vertical EOF diagnostic) ·
C (climatology-residual) · D (controlled channel ablation)

Run 2026-09-05 → 2026-09-06 · Full test suite **384 passed**
Pre-registration: [`outputs/architecture_closure/PREREGISTRATION.md`](outputs/architecture_closure/PREREGISTRATION.md),
written before C and D were trained and before the B PCA was computed.

---

## 1. Frozen starting state

Verified from the repository itself before anything was written. No discrepancy
was found against the expected state.

| claim | evidence | result |
|---|---|---|
| L2 is the frozen reference core | state-dict sha256 | `b715bb2bff32d5e4…` ✅ |
| L2 encoder frozen | encoder sub-state-dict sha256 | `30cfd2db9e8b6b96…` ✅ |
| L1 frozen | state-dict sha256 | `29419ad1dc2c4a1d…` ✅ |
| L3 tested, not adopted | `PHASE6B_L3_REPORT.md` | **INVESTIGATE** — "keep L2 as the production model" ✅ |
| 2022–2023 Argo already inspected | `outputs/argo/matched_profiles.parquet` | 5,176 profiles, 2022-01-01→2023-12-31 ✅ |
| 2024 Argo never fetched | `outputs/argo/download_manifest.json` | `heldout_period_not_fetched: [2024-01-01, 2024-12-15]` ✅ |
| Phase 6C-D NRT complete | `PHASE6C_NRT_COMPATIBILITY_REPORT.md` | `NRT_STACK_NOT_VIABLE_RAW` ✅ |
| fallbacks evaluated | 6C-B / 6C-C reports | present ✅ |

The repository is **not** under git, so the git precautions in the brief did not
apply; every change here is additive under new paths.

**All nine frozen hashes are byte-identical at the end of the study**, asserted
by six parametrised tests plus a state-dict/encoder hash test. Every training
run additionally re-hashed the frozen artefacts at start and end and recorded
both in its metadata (`frozen_sha256_start == frozen_sha256_end` for all seven
models trained).

### One declared efficiency change, with its proof

Targets were read from the existing memory-mapped cache rather than from Zarr
each epoch. Verified **before** training: inputs, context and target mask are
**bitwise identical** to the sampler that trained L2; target values differ by at
most **9.5 × 10⁻⁷ °C** (float32 cache vs float64 Zarr); and running the frozen
L2 through the new sampler reproduces its recorded best validation loss
`0.15351675395687966` to an absolute difference of **3.7 × 10⁻¹⁰**. Measured
throughput 188 ms/train-day. (`outputs/architecture_closure/pipeline_equivalence.json`)

---

## 2. A — Literature and architecture audit

Full detail: [`ARCHITECTURE_REVIEW.md`](ARCHITECTURE_REVIEW.md) ·
matrix: `outputs/tables/architecture_closure/architecture_review_matrix.csv`

**No model was trained for this section.** Search run 2026-09-05, prioritising
2022–2026, peer-reviewed publisher pages and DOI records. Scope limits stated in
the review itself: this is a targeted audit, not a systematic review; several
publisher pages returned 403, and those rows are built from abstracts and
metadata only and are marked as such. Where a field could not be verified it is
recorded as `?`, never guessed. One entry (DERN-EOF) is cited by title, journal
and PII because its author list was not retrievable — a guessed author list
would have been worse than an incomplete one.

### What the closest work does

| study | domain | family | climatology prior | uncertainty | validation |
|---|---|---|---|---|---|
| Qi et al. 2023 (CBAM-CNN) | tropical Indian Ocean | CNN + attention, 3×3 kernels | no | no | RG-Argo **gridded climatology** |
| Feng et al. 2025 (DSVIT) | tropical Indian Ocean | Vision Transformer | **yes, as input** | ? | independent test set |
| Chae et al. 2026 (TS-Cast) | NW Pacific | U-Net + FiLM, 31-day window | **yes, as input** | **yes** | 23,631 Argo/CTD + moorings + PIES |
| Garcia-Espriu et al. 2025 | global | RF vs LSTM | no | no | simulated water column |

Two structural ideas recur in the strongest work: **a climatological prior the
network adjusts**, and **a low-rank vertical basis**. Those are exactly what
Experiments C and B test. That is where the evidence pointed and where the
compute went.

An independent controlled study (Garcia-Espriu et al. 2025) reports that
temperature reconstruction **degrades significantly below 200 m** and that
upper-layer variability is **underestimated** — the same walls OceanEmbed has
hit in every phase since 6B-A. DERN-EOF attributes the high uncertainty to the
subsurface field being weakly related to the surface field. These limits are not
specific to our model.

### Decision matrix outcome

| family | decision |
|---|---|
| MLP (pointwise) | **TESTED-ADOPTED** (L1, as baseline) |
| CNN (compact dilated spatial) | **TESTED-ADOPTED** — current core |
| CNN + temporal | **TESTED-REJECTED** (L3) |
| ViT / Transformer / attention | **DEFER** |
| GNN | **DEFER** |
| Autoencoder / self-supervised | **DEFER** |
| EOF / low-rank decoder | **DIAGNOSTIC-ONLY** (Experiment B) |
| Climatology-residual | **TESTED** (Experiment C) |
| Uncertainty head | **DEFER — highest-value follow-up** |

The ViT deferral is a judgement about **attribution, not superiority**: in both
Indian Ocean papers the attention model also changed the loss, the prior or the
target resolution, so nothing isolates attention as the cause. Training a ViT on
six years of daily 101×241 fields to find out is a poor use of the remaining
budget. GNNs solve irregular observation geometry, which we do not have — our
inputs are gridded L4 on a fixed 101×241 grid.

**The clearest gap versus the literature is uncertainty, not architecture.**

---

## 3. B — Train-only vertical PCA / EOF diagnostic

Basis: **train dates only** (2015-01-01→2020-12-31), 314 days at stride 7,
2,000 cells/day, `rng(20260905 + day_index)` — all declared before the PCA ran.
**628,000 complete profiles** per analysis. No validation, test or Argo value
enters the covariance (asserted by test).

### The sampling bias, measured rather than assumed away

Complete-case profiles over-represent deep water:

| analysis | eligible cells | fraction of surface-valid domain | mean lat (all → eligible) |
|---|---|---|---|
| B1-FULL15 (15 depths) | 8,935 / 11,067 | **0.807** | 12.75° → 12.26° |
| B2-UPPER300 (12 depths) | 9,407 / 11,067 | **0.850** | 12.75° → 12.28° |

Roughly a fifth of the domain is excluded from the 15-depth analysis. The Bay of
Bengal share falls slightly (0.342 → 0.333) and the Arabian Sea share rises
(0.455 → 0.493). Every number below describes **that** population, not the whole
domain.

### Spectra

| | EVR₁ | k for 90% | k for 95% | k for 99% |
|---|---|---|---|---|
| FULL15 raw | 0.421 | 3 | 4 | 7 |
| **FULL15 residual** | **0.692** | **3** | **5** | **9** |
| UPPER300 raw | 0.458 | 3 | 3 | 5 |
| UPPER300 residual | 0.703 | 3 | 4 | 7 |

A point worth making to a jury: the **raw** profiles are *more* compressible
than the residuals (k95 = 4 vs 5). That is not evidence of physical low-rank
structure — raw compressibility is dominated by the mean vertical profile shape,
which is trivially one mode. The residual spectrum is the meaningful quantity.

### What a truncated basis would actually cost (k = 5, residual, FULL15)

| depth | reconstruction RMSE | ÷ frozen L2 validation RMSE |
|---|---|---|
| 0 m | 0.124 °C | **0.276** ✗ |
| 20 m | 0.149 °C | **0.292** ✗ |
| 30 m | 0.219 °C | **0.370** ✗ |
| 75 m | 0.181 °C | 0.165 ✓ |
| **100 m** | **0.154 °C** | **0.126** ✓ |
| 125 m | 0.144 °C | 0.122 ✓ |
| 150 m | 0.140 °C | 0.132 ✓ |
| 200 m | 0.196 °C | **0.251** ✗ |
| 300 m | 0.211 °C | **0.401** ✗ |

### Verdict — and an honest problem with the rule

The pre-registered rule does not cleanly classify this result, and I am
reporting that rather than retro-fitting a threshold.

- **STRONG** required ≤5 components for ≥95 % **and** k=5 reconstruction ≤25 %
  of frozen L2 RMSE at every 0–300 m depth. The first condition holds (k95 = 5);
  the second fails at **5 of 12** depths.
- **WEAK** required >8 components for 95 %, or k=5 damage >50 % at 75/100/125/150 m.
  **Neither trigger fired** — thermocline ratios are 0.12–0.17.
- **MODERATE** allowed the 25 % test to fail at "one or two" depths. It failed at five.

**Recorded verdict: MODERATE, at the weak edge — a boundary case the rule did
not anticipate.** The gap between MODERATE's "one or two depths" and WEAK's
explicit triggers is a **defect in the pre-registration**, logged here under the
bug-correction policy. No threshold was moved.

The physics behind the awkwardness is clear and more useful than the label: a
k=5 EOF basis costs only **0.12–0.16 °C at the thermocline (12–13 % of L2's
error there)** but **0.20–0.22 °C at 30 m and 300 m (34–40 %)**. An EOF decoder
would buy thermocline efficiency by spending near-surface and
intermediate-depth fidelity.

**No EOF decoder was trained, as pre-registered.** Recorded as worth future
investigation only if a future design is thermocline-focused and can tolerate
near-surface representation error.

*Figures:* `pca_cumulative_variance.png`, `pca_eof_shapes.png`,
`pca_reconstruction_error.png`

---

## 4. C — Climatology-residual reconstruction

**Candidate `L2_RESIDUAL`:** identical architecture (patch 33, latent 32,
136,335 parameters, same 7 inputs, same mask semantics, same optimisation
protocol, same dates). The **only** change is the target:

```
delta_T = T_GLORYS − T_L0(date, cell, depth)      T_pred = T_L0 + delta_T_pred
```

L0 was loaded read-only and never refitted (file hash unchanged). A **new**
train-only residual scaler was fitted and written to a new path; the frozen
target scaler was neither overwritten nor reused. Residual σ peaks at the
thermocline (1.50 °C at 100 m) and is smallest at depth (0.29 °C at 1000 m).

Canonical seed 20260905, 8 epochs, best epoch 4, 76 min.

### Result on 2021 validation, in physical temperature space

| depth | L0 | frozen L2 | **L2-RESIDUAL** | ΔRMSE | Δ anomaly corr |
|---|---|---|---|---|---|
| 0 m | 0.589 | 0.449 | 0.512 | **+14.1 %** | −0.167 |
| 10 m | 0.585 | 0.457 | 0.513 | +12.3 % | −0.157 |
| 50 m | 1.015 | 0.805 | 0.853 | +5.9 % | −0.114 |
| 75 m | 1.533 | 1.095 | 1.185 | +8.2 % | −0.102 |
| **100 m** | 1.871 | **1.224** | 1.379 | **+12.7 %** | −0.100 |
| 125 m | 1.783 | 1.182 | 1.313 | +11.1 % | −0.083 |
| 150 m | 1.500 | 1.059 | 1.149 | +8.5 % | −0.082 |
| 200 m | 0.986 | 0.779 | 0.816 | +4.7 % | −0.077 |
| 300 m | 0.575 | 0.526 | 0.540 | +2.6 % | −0.074 |
| 500 m | 0.391 | 0.379 | 0.384 | +1.2 % | −0.097 |
| 700 m | 0.378 | 0.391 | 0.376 | −3.7 % | −0.036 |
| 1000 m | 0.401 | 0.410 | 0.400 | −2.5 % | −0.037 |

### Pre-registered gate — 3 of 4 criteria failed

| criterion | threshold | result |
|---|---|---|
| 1 · upper 300 m RMSE or coherent anomaly gain | ≥1.0 % better, or ≥8/11 depths improved | **FAIL** — RMSE worse; anomaly correlation improved at **0 of 11** depths |
| 2 · key thermocline (75–200 m) | no depth worse by >1.0 % | **FAIL** — all five worse by 4.7–12.7 % |
| 3 · deep (500–1000 m) | not worse by >1.0 % | **PASS** |
| 4 · no major new bias | no |bias| growth >0.10 °C | **FAIL** — 100 m −0.283→−0.385 °C; 150 m −0.075→−0.280 °C |

### Decision: `RESIDUAL_REJECTED`

Per the pre-registration, a clear canonical-seed failure means the candidate is
rejected and **no further seeds are run** — seeds 20260906/20260907 were not
trained, and the 2022–2023 Argo confirmation gate was **not opened**. That saved
roughly 2.5 h of compute and, more importantly, one of the two remaining uses of
an already-exposed observational set.

**The deep "improvement" is not a win.** At 700 and 1000 m, L0 climatology
already beats frozen L2 (0.378 vs 0.391; 0.401 vs 0.410). Getting closer to
climatology there is the residual model regressing toward its prior, not
learning more. The decisive number is that anomaly correlation fell at **every
single depth** — the hypothesis was that residuals would sharpen anomaly skill,
and the measurement says the opposite.

**A mechanism, offered as hypothesis and not part of the verdict:** subtracting
L0 strips the large, easily-learned signal and leaves a lower-SNR target, while
per-depth residual standardisation (σ 0.29 °C deep vs 1.50 °C at 100 m)
reweights the masked loss *toward* the deep, pulling capacity away from the
thermocline where L2 earns its skill. This was not tested.

**This contradicts what TS-Cast and DSVIT do — and the distinction matters.**
Both feed climatology in as an **input** to a network predicting absolute
fields. Experiment C reformulated the **target**. Those are different
interventions, and only the second was tested here. A climatology-as-input
variant remains untested and is not refuted by this result.

*Figures:* `residual_vs_l2_depth_profile.png`, `residual_anomaly_corr.png`

---

## 5. D — Controlled channel ablation

Six models, identical protocol, seed and sample population: a full-input control
plus five leave-one-group-out variants. The ablated group's planes are set to
**0 in standardised space** (the training mean) for both training and
validation; validity still comes from the **original complete seven-channel
field**, so the sample population, architecture, input width and parameter count
(136,335) are unchanged. Only information content changes.

### The matched control, and the noise floor it gives us

`D_CONTROL_ALL` reached validation loss 0.15394 against frozen L2's 0.15352 —
the same configuration trained twice. The per-depth RMSE difference between them
is a **run-to-run noise floor of 0.64 % mean, 1.66 % maximum**
(`ablation_noise_floor.csv`). Any ablation effect inside ±1.7 % is
indistinguishable from training-run variation. Without this control the small
effects below would have been unreadable.

### Impact by depth band (% RMSE change vs control; positive = worse without it)

| group | 0–50 m | 75–150 m | 200–300 m | 500–1000 m |
|---|---|---|---|---|
| **SLA** | **+6.40** | **+29.21** | **+11.63** | +1.97 |
| **SST** | **+13.20** | −1.29 | −0.08 | +3.78 |
| SSS | −0.47 | −1.42 | −1.24 | −0.12 |
| CURRENTS | −0.31 | −0.66 | −0.28 | −0.59 |
| WINDS | −0.36 | −0.32 | −0.69 | −0.79 |

Per depth, the two that clear the noise floor:

- **SLA at the thermocline** — +21.2 % at 75 m, **+32.7 % at 100 m**, +34.0 % at
  125 m, +26.7 % at 150 m; anomaly correlation −0.111 at 100 m.
- **SST at the surface** — **+30.1 % at 0 m**, +27.2 % at 5 m, +25.6 % at 10 m,
  +16.6 % at 20 m; anomaly correlation −0.347 at 0 m.

### Basin split at 100 m (% change vs control)

| ablation | Arabian Sea | Bay of Bengal |
|---|---|---|
| −SLA | +7.5 % | **+66.7 %** |
| −SST | −2.7 % | −0.3 % |
| −SSS | −0.3 % | −1.8 % |
| −CURRENTS | −1.2 % | −4.9 % |
| −WINDS | −1.3 % | −2.3 % |
| *(L0 for scale)* | *+21.2 %* | *+96.7 %* |

Removing SLA costs the Bay of Bengal roughly nine times what it costs the
Arabian Sea. Reported as a basin difference, **not** as a cross-basin
generalisation claim.

### Interpretation — carefully worded

The correct statement is: *removing this information group during training
changed predictive skill by X on this validation year, under this architecture
and dataset.*

- **SLA and SST carry essentially all the incremental information** the L2
  architecture extracts, and they split cleanly by depth: SST owns the surface
  mixed layer, SLA owns the thermocline.
- **SSS, currents and winds show no detectable incremental contribution.** Every
  effect is within ±1.5 %, i.e. inside the noise floor. Several are slightly
  negative; **that is not evidence that removing them helps** — it is what a
  zero effect looks like when measured with 0.64 % run-to-run scatter.
- This measures **incremental predictive value, not physical causation, and not
  channel independence.** OSCAR currents are diagnostically derived from SSH,
  wind and SST (Phase 6C-D registry), so a currents contribution would be
  largely redundant with SLA by construction. A null result for currents is the
  expected outcome, not a surprise.

**Nothing in D may be used to change the operational NRT policy**, and nothing
here does. A controlled ablation zeroes a channel while keeping the cell alive;
an operational outage collapses the joint mask and deletes the cell entirely
(Phase 6C-B/6C-C). They are different experiments.

**A cross-phase observation worth recording, not acting on:** Phase 6C-D found
raw NRT SSS substitution catastrophic under the joint-mask contract, while D
finds the SSS *channel* contributes no measurable skill. Both can be true — the
6C-D failure was driven by mask collapse and coverage loss, not by the SSS
values themselves. Whether SSS could be dropped from the input set is a
different question that D was not designed to answer and that would need its own
pre-registered experiment.

*Figures:* `channel_ablation_heatmap.png`, `channel_ablation_depth_groups.png`

---

## 6. What each experiment proved

- **A** — the compact CNN is a defensible choice arrived at by elimination, not
  assumption; the two ideas the strongest literature agrees on are the two this
  study tested; the real capability gap is uncertainty.
- **B** — the training residual-profile distribution is empirically low-rank to
  k≈5 for 95 % of variance under this representation and sampling protocol, and
  a k=5 basis would cost 12–13 % of L2's thermocline error but 34–40 % of its
  near-surface and 300 m error.
- **C** — reformulating the target as a climatology residual **degrades** this
  architecture at every depth above 500 m and reduces anomaly correlation
  everywhere. A clean negative result on the one new formulation this study was
  permitted to train.
- **D** — SLA and SST carry the extractable information, split by depth
  (SST surface, SLA thermocline); SSS, currents and winds contribute nothing
  measurable above a 0.64 % noise floor.

## 7. What none of it proved

- Not that a CNN is optimal, nor that 33×33 is the right receptive field.
- Not that attention would fail if isolated properly — the published wins are
  confounded, which is a reason to defer, not a refutation.
- **Not that climatology priors are useless.** C tested a *target*
  reformulation; TS-Cast and DSVIT use climatology as an *input*. Untested here.
- Not that ocean profiles are intrinsically 5-dimensional — B describes one
  distribution, one representation and one biased complete-case population.
- Not that SSS, currents or winds are physically unimportant — only that they add
  no *incremental* predictive value given the other channels, in a model where
  currents are themselves derived from SSH, wind and SST.
- Not that any of this transfers to the untouched 2024 Argo year.
- D used one seed per variant, as pre-registered for compute discipline; effects
  near the noise floor would need seed replication to bound properly.

## 8. Final architecture recommendation

### `FINAL CORE = existing frozen L2` — unchanged, unmodified, `b715bb2b…`

No candidate displaced it. L2-RESIDUAL was rejected at its own pre-registered
gate; no EOF decoder was built; no new architecture family was justified.

The frozen L2 is byte-identical to what entered this study. Every closure model
is stored separately under `outputs/models/architecture_closure/` and none is a
deployment candidate.

**Recommended next step, for your decision and not taken here:** an uncertainty
head. It is the clearest gap versus the literature, it matters more for a
disaster-management product than for a research one, and it is a capability
addition rather than an architecture change — so it does not reopen anything
this study closed.

## 9. Remaining protected data

| asset | status |
|---|---|
| **2024 Argo** | **PROTECTED** — never downloaded, opened, collocated or inspected. Code guard `closure.holdout.assert_no_2024_argo` + 4 tests. |
| 2022–2023 Argo | development confirmation; **not consumed by this study** — C never reached the Argo gate |
| Old grid test benchmark | not used to select B, C or D; not opened during this study |
| 2021 validation | used for C and D selection, as declared |

## 10. Jury-ready model-selection story

> We did not pick a CNN by assumption; we arrived at it by elimination, and we
> kept the failures.
>
> **L0** established what season and location alone can predict. **L1** showed
> the local surface state carries additional subsurface information beyond that
> baseline. **L2** showed spatial context adds reproducible skill — +33.5 % over
> climatology at 100 m on the grid benchmark, +28.1 % against independent Argo
> profiles. **L3** tested whether recent temporal history helps; it did not
> survive out of sample, so we rejected it rather than reporting the validation
> number.
>
> We then closed the remaining architecture questions. A literature audit of
> 2022–2026 work confirmed the two ideas the strongest studies share — a
> climatology prior and a low-rank vertical basis — and we tested both. The
> vertical profile turned out to be compressible to about five modes, but a
> truncated basis would cost a third of our near-surface accuracy, so we
> diagnosed it and did not build it. Predicting departures from climatology made
> the model **worse at every depth above 500 m**, so we rejected it at a gate we
> had written down beforehand. A controlled ablation showed sea level anomaly
> and sea surface temperature carry the extractable information — SST at the
> surface, SLA at the thermocline — while salinity, currents and winds
> contributed nothing above a measured 0.64 % run-to-run noise floor.
>
> The final architecture was selected from these controlled experiments rather
> than from an indiscriminate model sweep, and the untouched 2024 Argo year is
> still available for one honest final evaluation.

---

## 11. Final decision table

| Question | Experiment | Result | Decision |
|---|---|---|---|
| Does climatology matter? | L0 | existing | keep as baseline |
| Does local surface state help? | L1 | existing | **yes** |
| Does spatial context help? | L2 | existing | **yes — adopted** |
| Does short temporal history help? | L3 | existing | **no reproducible gain — rejected** |
| Is vertical structure strongly low-rank? | **B** | k95 = 5 for residual profiles, but k=5 costs 34–40 % of L2 error near surface and at 300 m | **MODERATE (boundary case) — diagnostic only, no decoder built** |
| Does residual prediction improve L2? | **C** | worse at every depth 0–500 m; anomaly correlation down at all 15; 3 of 4 gate criteria failed | **RESIDUAL_REJECTED** |
| Which channels contribute most? | **D** | SLA +29 % thermocline, SST +13 % surface; SSS/currents/winds within a 0.64 % noise floor | **diagnostic — SLA and SST carry the information** |
| Is another architecture family justified? | **A** | ViT wins confounded; GNN solves a problem we don't have; uncertainty is the real gap | **no new family — DEFER** |

---

## 12. Artefacts

**Code** — `src/oceanembed/closure/`: `sampling.py`, `residual.py`,
`ablation.py`, `holdout.py`.
**Scripts** — `scripts/closure/`: `verify_pipeline.py`, `pca_diagnostic.py`,
`train_closure.py`, `run_ablations.sh`, `evaluate_closure.py`,
`closure_analysis.py`, `make_figures_closure.py`.

**Tables** (`outputs/tables/architecture_closure/`) —
`architecture_review_matrix.csv`, `pca_sample_population.csv`,
`pca_explained_variance_raw.csv`, `pca_explained_variance_residual.csv`,
`pca_reconstruction_error.csv`, `residual_metrics_validation.csv`,
`residual_metrics_validation_metrics_by_depth.csv`,
`channel_ablation_metrics.csv`, `channel_ablation_by_depth.csv`,
`channel_ablation_depth_groups.csv`, `channel_ablation_basin_metrics.csv`,
`ablation_noise_floor.csv`, plus depth-group and basin tables for both runs.

**Provenance** (`outputs/architecture_closure/`) — `PREREGISTRATION.md`,
`pipeline_equivalence.json`, `pca_diagnostic.json`, `residual_gate.json`,
`closure_residual_target_scaler.json`, eval metadata for both runs.

**Models** (`outputs/models/architecture_closure/`) — 7 checkpoints, all
prefixed `closure_`, none colliding with a phase artefact:
`L2_RESIDUAL_s20260905`, `D_CONTROL_ALL`, `D_MINUS_{SST,SSS,SLA,CURRENTS,WINDS}`.

**Figures** (`outputs/figures/architecture_closure/`) — 7 PNGs.

**Tests** — `tests/test_architecture_closure.py`, 37 tests. Full suite **384
passed**. They pin: six frozen files byte-identical; L2 state-dict and encoder
hashes; no closure artefact in a frozen directory; 2024 Argo refused by code and
absent from the collocation; PCA basis train-only, deterministic, monotone
cumulative variance, exact at k=15, error decreasing in k, population bias
reported; residual target exactly `target − frozen L0`; `L0 + delta` round-trip;
residual scaler train-only and distinct from the frozen one; candidate matches
the frozen input contract and is stored separately; ablation zeroes exactly the
right planes, leaves the mask and other channels untouched, preserves the valid
population and parameter count, does not mutate its input, and all D runs share
protocol, seed and population.

---

```
OceanEmbed Architecture Closure complete.

Frozen L2 preserved: YES
L3 repeated: NO
2024 Argo holdout: PROTECTED

A Literature review: COMPLETE
B PCA/EOF diagnostic: COMPLETE
C Residual experiment: REJECTED
D Channel ablation: COMPLETE

Recommended final core:
existing frozen L2 (sha256 b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d)

Full test suite:
384 passed

STOP — awaiting review before final model freeze and PoC integration.
```
