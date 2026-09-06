# OceanEmbed — Architecture Closure Study: Pre-registration

Written **before** Experiment C or D was trained and **before** the Experiment B
PCA was computed. Every threshold, gate, seed, date range and sampling rule
below is fixed from this point. None will be changed after a result is seen.

Frozen at: 2026-09-05, after repository inspection and pipeline verification,
before any closure model existed.

---

## 0. Verified starting state

Confirmed from the repository itself, not from prose, before writing this
document:

| claim | verified how | result |
|---|---|---|
| L2 is the frozen reference core | `outputs/models/phase6b_l2_final.pt`, state-dict sha256 | `b715bb2bff32d5e4…` ✓ |
| L2 encoder frozen | encoder sub-state-dict sha256 | `30cfd2db9e8b6b96…` ✓ |
| L1 exists and is frozen | state-dict sha256 | `29419ad1dc2c4a1d…` ✓ |
| L3 tested, not adopted | `PHASE6B_L3_REPORT.md` gate | **INVESTIGATE**, "keep L2 as the production model" ✓ |
| 2022–2023 Argo already inspected | `outputs/argo/matched_profiles.parquet` | 5,176 profiles, 2022-01-01→2023-12-31 ✓ |
| 2024 Argo never fetched | `outputs/argo/download_manifest.json` | `heldout_period_not_fetched: [2024-01-01, 2024-12-15]` ✓ |
| Phase 6C-D NRT complete | `PHASE6C_NRT_COMPATIBILITY_REPORT.md` | verdict `NRT_STACK_NOT_VIABLE_RAW` ✓ |
| fallbacks evaluated | `PHASE6C_FALLBACK_ARGO_REPORT.md`, `PHASE6C_INPUT_AVAILABILITY_BASELINE_REPORT.md` | present ✓ |

No discrepancy was found. The repository is not under git (`fatal: not a git
repository`), so the git precautions in the brief do not apply; every change in
this study is additive under new paths.

### Frozen hashes recorded before any work

```
l1_checkpoint_file        fefebd216536b9a1b8383ae41b5d35057b8b46ed1b4b77a9642a514bc9c92b5b
l2_checkpoint_file        81979a6541927ff5c6b0a13c5ce7cdbcd486040d16a304dcdc10b2962a586e35
feature_scaler_file       49671ce760b0dca5c1c82cb184dae91908cc064abfdea8cc7eb2f5bc3c320467
target_scaler_file        5b6f359db0d228dd7d3acf775ab8a6eea76dd521e7b4568ff1873c832e89e93b
climatology_file          748af4d79bc704cc2f742e1c208bacebe781131c5ff142cddc7c334963903cd5
surface_climatology_file  58f0c5812ebcb6d4394a4f18e5b133d0a69657960e0e4c98d74184e91f6e8932
l1_state_dict             29419ad1dc2c4a1d6943e524e852c934fd125ccc8f8e28c339214a3dfdce01b6
l2_state_dict             b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d
l2_encoder_state_dict     30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808
```

These must be identical at the end of the study.

---

## 1. Data contract

| role | dates | may be used for |
|---|---|---|
| TRAIN | 2015-01-01 → 2020-12-31 | gradients, every fitted statistic |
| VALIDATION | 2021-01-01 → 2021-12-31 | model selection, early stopping, the C and D gates |
| OBSERVATIONAL DEVELOPMENT CONFIRMATION | existing 2022–2023 Argo collocation | **one** pre-registered confirmation of C, if and only if it passes the validation gate |
| PROTECTED FINAL HOLDOUT | 2024 Argo | **nothing** |
| old grid test benchmark (2022-01-01 → 2024-12-15) | — | **not used to select B, C or D** |

The old grid test benchmark has already been inspected in Phases 6B/6C, so it
is not a pristine holdout and is deliberately **not** consulted for any decision
in this study. The 2022–2023 Argo set has also already been inspected; it is
therefore *development confirmation*, used at most once, with no tuning
afterwards.

**2024 Argo:** not downloaded, not opened, not collocated, not inspected, not
used for selection. A code-level guard (`closure.holdout.assert_no_2024_argo`)
raises on any attempt, and a test asserts it.

---

## 2. Non-destructive contract

Nothing under `outputs/models/phase6b_*`, `outputs/baselines/phase6b_*`,
`outputs/baselines/phase6cb_*`, `outputs/argo/*`, `outputs/nrt/*`,
`outputs/operational/*`, `data/processed/*` or `config/*` is written, moved or
refitted. All new artefacts live under:

```
outputs/architecture_closure/
outputs/models/architecture_closure/
outputs/tables/architecture_closure/
outputs/figures/architecture_closure/
```

No filename from a prior phase is reused.

---

## 3. Shared training protocol (C and D)

Identical to the protocol that produced the frozen L2, so that a difference in
result is a difference in formulation or information, not in budget:

- architecture `L2EmbeddingModel`, patch **33**, latent **32**, dilations
  [1,2,4,8,1], receptive field 33, 136,335 parameters
- 7 surface channels + 1 validity-mask channel, frozen feature scaler, frozen
  `day_field` (internal zero-pad by `patch//2`, mask 0, single joint mask)
- context = lat, lon, doy_sin, doy_cos, standardised with the frozen scaler
- optimiser Adam, lr 1e-3, `ReduceLROnPlateau(factor 0.5, patience 2)`
- **max_epochs 15, early-stopping patience 4, train-day stride 1**
- loss: per-depth masked MSE in standardised target space
- gradients on TRAIN only; checkpoint selection on VALIDATION only
- canonical seed **20260905**; additional pre-declared seeds **20260906**,
  **20260907** (used only where this document says so)

**One declared efficiency change, with its equivalence proof.** Targets are read
from the existing memory-mapped target cache instead of from Zarr each epoch.
Verified before training: inputs, context and target mask are **bitwise
identical** to the sampler that trained L2, target values differ by at most
**9.5e-07 °C** (float32 cache vs float64 Zarr), and running the frozen L2
through the new sampler reproduces its recorded best validation loss
**0.15351675395687966** to an absolute difference of **3.7e-10**. Measured
throughput 188 ms/train-day, ≈7.2 min per epoch
(`outputs/architecture_closure/pipeline_equivalence.json`).

Two closure trainings may run concurrently on this 16-core machine. Concurrency
affects wall-clock only; results are seed-deterministic per process.

---

## 4. Experiment B — train-only vertical PCA / EOF diagnostic

**Question.** Is the 15-depth temperature profile sufficiently low-rank that an
EOF/profile decoder would be scientifically justified?

This is a **diagnostic only**. No EOF neural decoder will be trained in this
study regardless of the outcome.

### 4.1 Basis population — declared before the PCA is computed

Train dates only (2015-01-01 → 2020-12-31). No validation, test or Argo value
may enter the covariance.

- **Days:** every 7th train day → 314 days. Stride 7 is chosen so the sample is
  not aliased to a weekday-free calendar artefact and covers all seasons of all
  six training years.
- **Cells:** 2,000 per day, drawn without replacement from that analysis's
  eligible cell set, with `numpy.random.default_rng(20260905 + day_index)`.
  Deterministic and reproducible.
- **Two analyses, two eligible sets:**
  - **B1-FULL15** — cells valid at all 15 depths;
  - **B2-UPPER300** — cells valid at all depths ≤ 300 m (11 depths).
- **Two representations, both analysed:**
  - **raw** absolute temperature profiles;
  - **residual** profiles = target − frozen train-only L0 climatology.

Because target validity follows bathymetry, the complete-case population is
**not** the whole domain. The geographic and depth-distribution bias of each
eligible set will be quantified and reported (fraction of domain cells retained,
and the shift in the bathymetric/latitudinal distribution), not assumed away.

### 4.2 Reported quantities
Eigenvalues; explained variance per component; cumulative explained variance;
components needed for 90 %, 95 %, 99 %; reconstruction RMSE for
k ∈ {1, 2, 3, 5, 8, 10, 15}; reconstruction error per depth; the leading EOF
shapes.

### 4.3 Interpretation rule — frozen now

Judged on the **residual** profiles of **B1-FULL15**, with B2-UPPER300 reported
alongside.

| verdict | condition |
|---|---|
| **STRONG EOF JUSTIFICATION** | ≤5 components explain ≥95 % of residual-profile variance **and** the k=5 reconstruction RMSE is ≤25 % of the frozen L2 validation RMSE at **every** depth from 0 to 300 m |
| **MODERATE** | 6–8 components needed for 95 %, or the k=5 reconstruction fails the 25 % test at one or two depths |
| **WEAK** | >8 components needed for 95 %, or low-k reconstruction damages thermocline structure (k=5 reconstruction RMSE >50 % of frozen L2 validation RMSE at any of 75/100/125/150 m) |

Correct language for the write-up: *"the training profile distribution is
empirically low-rank to this degree under this representation and sampling
protocol"* — not a claim about the intrinsic dimensionality of ocean profiles.

---

## 5. Experiment C — climatology-residual L2

**Question.** Does predicting departures from climatology improve
reconstruction, especially anomaly and deep behaviour, without sacrificing L2's
validated upper-ocean skill?

**Reference:** the frozen L2 absolute-temperature model.
**Candidate:** `L2_RESIDUAL`.

### 5.1 What changes and what does not

Changed — and only this:

```
target        delta_T(depth) = T_GLORYS(depth) - T_L0(date, cell, depth)
prediction    T_pred         = T_L0 + delta_T_pred
scaling       a NEW per-depth residual scaler, fitted on TRAIN residuals only
```

Unchanged: 33×33 context, the same 7 physical inputs, the existing validity-mask
semantics, the encoder architecture, latent width 32, the decoder structure, the
coordinate/seasonal context, the train and validation dates, and the
optimisation protocol of §3.

Explicitly **not** done: no temporal history, no patch-size change, no
attention, no physics loss, no mask/age metadata, no channel-set change, no
uncertainty head, no NRT logic change.

**L0 is never refitted.** It is loaded read-only and hash-checked. The frozen
target scaler is neither overwritten nor reused; the new residual scaler is
written to `outputs/architecture_closure/closure_residual_target_scaler.json`.
Reusing the absolute-temperature scaler would silently reweight the per-depth
loss, because residuals have a different per-depth spread.

### 5.2 Metrics
On 2021 validation, in **physical temperature space** (not normalised loss), at
all 15 depths: RMSE, MAE, bias, correlation, anomaly correlation, skill relative
to L0, and Δ versus the frozen L2. Depth groups: 0/5/10, 20/30/50, 75/100/125,
150/200/300, 500/700/1000. Also: thermocline warm bias, deep anomaly
correlation, and Arabian Sea / Bay of Bengal diagnostics.

### 5.3 Development gate — frozen now

`L2_RESIDUAL` may advance to observational confirmation **only if all four hold**
on 2021 validation:

1. mean 0–300 m RMSE improves over frozen L2 by **≥1.0 %**, **or** anomaly
   correlation improves coherently across the upper ocean (defined as: anomaly
   correlation improves at **≥8 of the 11** depths from 0 to 300 m, with no
   depth in that range degrading by more than 0.01 in absolute correlation);
2. **no** key thermocline depth (75, 100, 125, 150, 200 m) degrades by more than
   **1.0 %** RMSE;
3. the deep group (500/700/1000 m) is not worse than frozen L2 by more than
   **1.0 %** mean RMSE;
4. no major new systematic bias appears — defined as: no depth acquires a
   |bias| more than **0.10 °C** larger than the frozen L2's bias at that depth.

If the canonical seed clearly fails, the candidate is **REJECTED** and no
further seeds are run. If it passes, seeds 20260906 and 20260907 are run and the
qualitative result must survive **≥2 of 3** seeds.

### 5.4 Argo confirmation — only if §5.3 passes

The candidate is frozen completely first. Then evaluated **once** on the
existing Phase 6C-A 2022–2023 collocation population, using the existing
protocol unchanged (QC, collocation, interpolation, DATA_MODE, potential-
temperature conversion, sample population). Comparators: L0, L1, frozen L2,
`L2_RESIDUAL`, and GLORYS where already defined.

Observational promotion criteria, frozen now:

1. no broad degradation over 50–200 m — RMSE must not worsen at more than one of
   the depths 50/75/100/125/150/200 m;
2. mean thermocline (75/100/125 m) RMSE not worse than frozen L2;
3. the known ≈+0.5 °C thermocline warm bias must not worsen by more than
   **0.05 °C** at any of 75/100/125 m;
4. anomaly correlation remains coherent — no depth in 0–300 m loses more than
   0.02 absolute anomaly correlation versus frozen L2;
5. any deep improvement must not be purchased by upper-ocean degradation
   (criteria 1–4 already enforce this and are evaluated together).

Outcomes: `RESIDUAL_PROMOTED_AS_FINAL_CORE_CANDIDATE`,
`RESIDUAL_INTERESTING_BUT_NOT_PROMOTED`, `RESIDUAL_REJECTED`.

**No tuning after an Argo result is seen.** Even if promoted, the frozen L2 is
not overwritten; the candidate is stored separately and 2024 Argo stays
untouched.

---

## 6. Experiment D — controlled channel ablation

**Question.** Which surface observation groups actually contribute predictive
information to the L2 architecture?

Five leave-one-group-out variants only — not 2⁵ combinations:
`L2_MINUS_SST`, `L2_MINUS_SSS`, `L2_MINUS_SLA`, `L2_MINUS_CURRENTS`
(u+v together), `L2_MINUS_WINDS` (u+v together).

### 6.1 The control
A **sixth** model, `L2_CONTROL_ALL`, is trained with the full input set under
the identical protocol and seed. Primary comparisons are ablation vs
`L2_CONTROL_ALL`; the frozen L2 is reported alongside as context. Without a
matched control, any difference from the frozen L2 could be a training-run
difference rather than an information difference. `L2_CONTROL_ALL` is a
diagnostic model, never a deployment candidate, and does not replace L2.

### 6.2 The controlled ablation itself
For an ablated group, after the frozen `day_field` has built the standardised,
masked, zero-padded field, that group's data planes are set to **0 in
standardised space** (= the training mean) for **both training and validation**.
Everything else is untouched, and in particular:

- validity comes from the **original complete seven-channel field**, so the
  sample population is unchanged and validity is **not** recomputed;
- input width, architecture and parameter count are unchanged;
- preprocessing and the target population are unchanged.

**This is not an operational missing-channel event.** In an outage the joint
mask collapses and the cell disappears entirely (Phase 6C-B/6C-C). D changes
information content only, and nothing in D may be used to alter the frozen
operational NRT policy.

### 6.3 Protocol and metrics
Same architecture, patch, seed (20260905), train and validation periods, target
scaler, loss, optimiser, hyperparameters, epoch budget and sample population for
all six models. No per-ablation tuning. No test or Argo data is used to train or
select them.

At all 15 depths on 2021 validation: RMSE, ΔRMSE vs `L2_CONTROL_ALL`, anomaly
correlation, Δ anomaly correlation, bias. Plus depth groups, a channel × depth
impact heatmap, and Arabian Sea / Bay of Bengal diagnostics.

### 6.4 Interpretation rule
The reported statement is *"removing this information group during training
changed predictive skill by X"* — an incremental predictive value under this
model and dataset, **not** unique physical causation and **not** channel
independence. OSCAR currents are diagnostically derived from SSH, wind and SST
(Phase 6C-D registry), so contributions overlap by construction. Basin
differences are reported as basin differences, not as generalisation claims.

---

## 7. What will not be done in this study

No ViT, Transformer, GNN, U-Net, ConvLSTM, LSTM, new GRU, autoencoder,
foundation model or diffusion model will be trained. Experiment A is a
literature audit only. L3 will not be repeated. No EOF neural decoder will be
built. No uncertainty head. After the closure report, work stops.

---

## 8. Bug-correction policy

If a protocol bug is found, it will be documented, only the bug fixed, a
regression test added, and it will be stated explicitly whether any previously
reported result was affected. Thresholds above will not move.
