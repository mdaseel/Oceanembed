# OceanEmbed — Phase 6B-C Report
**L3 Temporal Memory Ablation, frozen L2 spatial satellite encoder**
Completed 2026-09-05 · every number was produced by executing the code.

**Question:** does recent, causal surface history add information beyond the current-day spatial
embedding?

**Answer: not reproducibly.** A 3-day window beat the same-capacity 1-day control on validation in
3/3 seeds, but that benefit **did not survive the frozen test benchmark** — it reversed in the very
depth band where it was strongest. L2 remains the model to keep.

---

## 1. Does temporal history add information beyond L2?

Partly, but almost all of the gain over L2 comes from the temporal *module*, not from history.

Validation primary metric (masked standardised MSE, common target dates):

| Model | Val loss |
|---|---|
| L2 spatial (reference) | 0.15352 |
| L3 control, 1 day | 0.15171 |
| **L3, 3 days** | **0.14724** |
| L3, 7 days | 0.14893 |

The 1-day control already improves on L2 (0.15352 → 0.15171) **with no history at all**. That gain
is GRU capacity plus a retrained decoder. Only the remainder is attributable to history — which is
exactly why the control was mandatory.

## 2. Does it beat the same-capacity 1-day control?

**On validation: yes. On the frozen test benchmark: no.**

| | Depths where 3-day beats control | Mean Δ |
|---|---|---|
| Validation (359 days) | **10 / 15** | **+1.57 %** |
| Frozen test (1,074 days) | 7 / 15 | **−0.43 %** |

Broken down by band — this is the result that decides the phase:

| Band | Validation | Frozen test |
|---|---|---|
| **0–150 m** | **+3.20 %, 10/10 depths** | **−0.52 %, 4/10 depths** |
| 200–1000 m | −1.69 %, 0/5 depths | −0.24 %, 3/5 depths |

The upper-ocean benefit was the strongest and most coherent validation signal — positive at *every*
depth from 0 to 150 m. On test it **reverses**. Depth by depth:

| Depth (m) | Val Δ vs control | Test Δ vs control |
|---|---|---|
| 0 | +4.68 % | +0.17 % |
| 5 | +5.13 % | **−2.06 %** |
| 10 | +5.16 % | **−1.81 %** |
| 20 | +2.23 % | **−2.45 %** |
| 30 | +0.81 % | **−1.58 %** |
| 50 | +6.46 % | +1.71 % |
| 75 | +1.76 % | −0.26 % |
| 100 | +3.06 % | +0.45 % |
| 125 | +2.04 % | +0.63 % |
| 150 | +0.66 % | −0.02 % |
| 200 | −2.56 % | −1.34 % |
| 300 | −0.32 % | +0.38 % |
| 500 | −1.96 % | −2.77 % |
| 700 | −3.08 % | +0.75 % |
| 1000 | −0.52 % | +1.76 % |

## 3. Which window won on validation?

**3 days**, on the pre-registered primary metric (lowest validation masked standardised MSE among
the pre-registered set {1, 3, 7}).

**3 days was the best of the pre-registered windows under the fixed validation protocol.** It is not
established as an optimal memory length. Note 7 days was *worse* than 3, so the ordering is not
monotonic in history length.

## 4. Is the improvement reproducible across seeds?

**On validation, yes — 3/3 pre-declared seeds** (20260905, 20260906, 20260907, declared in
`config/phase6c_l3.yaml` before any run).

| Seed | 3-day | 1-day control | Δ |
|---|---|---|---|
| 20260905 | 0.14724 | 0.15171 | +2.95 % |
| 20260906 | 0.14837 | 0.14910 | +0.49 % |
| 20260907 | 0.14998 | 0.15103 | +0.69 % |
| **Mean ± std** | **0.14853 ± 0.00138** | **0.15061 ± 0.00135** | — |

The sign is consistent, but the effect is small relative to seed noise: the mean gap (0.00208) is
only ~1.5× the across-seed standard deviation (0.00138), and the canonical seed happened to produce
the **largest** of the three margins. The pre-registered stability rule (≥2/3) was met on
validation — and then the benefit failed to transfer to test anyway.

## 5. At which depths does temporal memory help?

On validation, 0–150 m uniformly. **On the frozen test only 50, 100, 125, 300, 700 and 1000 m
improve, and 5–30 m — where validation was strongest — degrade by 1.6–2.5 %.** There is no
depth band where the benefit is consistent across both splits.

## 6. Does it improve thermocline reconstruction?

Marginally, and it is the only band that survives. Test depth-group RMSE (°C):

| Group | L0 | L2 | L3 control | L3 selected |
|---|---|---|---|---|
| Surface / mixed (0,5,10) | 0.6807 | **0.4787** | 0.4805 | 0.4864 |
| Upper thermocline (20,30,50) | 0.9019 | 0.6977 | **0.6826** | 0.6840 |
| Thermocline (75,100,125) | 1.6758 | 1.1438 | 1.1067 | **1.1034** |
| Intermediate (150,200,300) | 1.0173 | 0.7942 | **0.7845** | 0.7872 |
| Deep (500,700,1000) | **0.3660** (L0) | 0.3757 | **0.3730** | 0.3731 |

The 3-day model is best only in the thermocline group, by 0.3 % over the 1-day control. In the
surface group it is **worse than both L2 and the control**.

## 7. Does it help below 300 m?

No. At 500 m the 3-day model is 2.8 % worse than the control on test. At 700 m and 1000 m it is
slightly better (+0.75 %, +1.76 %), but those depths sit in a band where **climatology still beats
every learned model**, so the comparison is between models that are all worse than L0.

## 8. Does it help at 500–1000 m?

**No — climatology remains the best predictor there**, unchanged from Phase 6B-A and 6B-B.
Test deep-group RMSE: L0 **0.3660** vs L2 0.3757, L3-control 0.3730, L3-selected 0.3731. Temporal
memory did not recover deep skill. Outcome **C** of the four pre-registered possibilities
("temporal history does essentially nothing") is the closest match at depth.

## 9. Does the Bay of Bengal respond differently from the Arabian Sea?

Weakly and inconsistently. Frozen test, 3-day vs 1-day control:

| Depth (m) | Arabian Sea | Bay of Bengal |
|---|---|---|
| 0 | −0.35 % | +1.30 % |
| 10 | −0.92 % | −2.28 % |
| 50 | +2.68 % | −0.76 % |
| 100 | +0.06 % | +1.31 % |
| 125 | −0.72 % | +3.49 % |
| 150 | −1.71 % | +2.94 % |
| 500 | −3.62 % | −1.57 % |
| 1000 | +1.64 % | +2.47 % |

The Bay of Bengal is positive slightly more often at thermocline depths (125–150 m), which is where
spatial context helped it most in Phase 6B-B — but the signs flip across adjacent depths in both
basins, so this is not a coherent pattern. **No cross-basin claim is made**; latitude and longitude
remain inputs and Experiment A is a separate phase.

## 10. Incremental parameter count

| | Parameters |
|---|---|
| Frozen L2 encoder | **113,152** (0 trainable) |
| L3 GRU | 6,336 |
| L3 decoder | 23,183 |
| **L3 trainable total** | **29,519** |
| L2 total for reference | 136,335 |

**Identical trainable count (29,519) for the 1-day, 3-day and 7-day models** — the GRU is one shared
cell whose parameters do not depend on sequence length. That is what makes the control a true
capacity control, and it is asserted by a test.

## 11. Incremental runtime

| Stage | Cost |
|---|---|
| Embedding cache — train (2,192 days) | 587 s |
| Embedding cache — validation | 83 s |
| Embedding cache — test (post-freeze) | 272 s |
| Target cache — train / validation / test | 323 s / 52 s / 171 s |
| L3 training, 1-day | 9.4–12.0 min |
| L3 training, 3-day | 13.5–17.9 min |
| L3 training, 7-day | 25.1 min |
| **L2 training for reference** | **94.5 min** |

Each L3 epoch is 40–80 s versus L2's 810 s. Two engineering decisions made this possible:

1. **The frozen encoder is evaluated once per date, not once per sample per timestep.** A naive
   implementation would have multiplied L2's spatial cost by the window length.
2. **Targets were cached separately.** Profiling showed re-reading 15 depth variables from Zarr cost
   132 ms/day — **68 % of epoch time** — because a one-day read decompresses a whole 32-day chunk
   fifteen times. Caching cut that to **0.8 ms/day**, a 165× reduction. The target store lives in a
   different directory so the embedding cache remains provably free of temperature.

## 12. Was the frozen L2 encoder unchanged?

**Yes, in all seven training runs.** Enforced three independent ways:

- `requires_grad=False` on every encoder parameter, encoder in eval mode;
- training consumes **cached** z, so encoder gradients are structurally impossible;
- a SHA256 of the encoder weights is asserted equal before and after each run
  (`30cfd2db9e8b6b96 == 30cfd2db9e8b6b96` in every run log).

The cache additionally refuses to load against a different encoder, and cached z was verified
**bitwise identical** (max abs diff 0.000e+00) to a fresh encoder pass on random dates in both
splits.

## 13. Does the validation/test discrepancy from L1/L2 recur?

**Not cleanly — it is mixed this time.** Mean RMSE across all 15 depths:

| Model | Validation | Test | Direction |
|---|---|---|---|
| L2 spatial | 0.6891 | 0.6902 | test slightly worse |
| L3 control (1d) | 0.6840 | 0.6780 | test better |
| L3 selected (3d) | 0.6720 | 0.6797 | test worse |

In Phase 6B-A and 6B-B, test outperformed validation consistently. Here only the 1-day control
follows that pattern; L2 and the 3-day model do the opposite. Note these are **common-date**
numbers over a slightly different sample population than the 6B-B figures, so they are not directly
comparable to the earlier report.

**The recurring pattern is consistent with interannual distribution differences and now appears
across L1/L2/L3, but the cause has not been isolated.** It is not proven that 2021 is anomalous, and
this phase provides no new evidence either way.

## 14. Do the ordering diagnostics suggest genuine temporal ordering matters?

**Barely.** Using the frozen selected model with no retraining:

| Diagnostic | Validation | Frozen test |
|---|---|---|
| Repeated current day `[z_t, z_t, z_t]` vs correct history | +0.434 % worse (14/15 depths) | +0.277 % worse (14/15 depths) |
| Reversed history vs correct order | +0.147 % worse (12/15 depths) | +0.215 % worse (15/15 depths) |

Two readings, both worth stating:

- The degradations are **systematic** — repeated-current is worse at 14/15 depths on both splits, and
  reversed is worse at 15/15 on test. So the model does use the actual historical *values* to a
  small degree; this is not pure noise.
- But the magnitudes are **tiny**. Destroying the real history costs only ~0.3–0.4 %, while the
  3-day-vs-control gap on validation was +1.57 %. Roughly three-quarters of the apparent validation
  benefit is therefore **not** attributable to historical information. And reversing time costs
  almost as little as deleting history entirely, so the GRU has not learned a directional dynamic.

Per the interpretation rules, this does **not** support a claim that ocean memory is important.

## 15. Is temporal memory scientifically worth its added complexity?

**On this evidence, no.** It adds a recurrent module, a two-cache pipeline and a window
hyperparameter, and returns no benefit that survives out of sample. L2 plus (at most) the 1-day
temporal head is the defensible model.

One finding *is* worth carrying forward: **the 1-day control beat L2 on both splits**
(validation 0.15171 vs 0.15352; test thermocline 1.1067 vs 1.1438). That is decoder retraining and a
small extra module, not memory — a cheap, history-free improvement that could be revisited
deliberately in a later phase.

---

## Methodology

**Frozen state.** L2 architecture was read from the checkpoint, not from prose: patch 33, dilations
[1,2,4,8,1], receptive field 33, latent 32, decoder (128,36)→(128,128)→(15,128). The L3 decoder is
structurally identical and was warm-started from the L2 decoder.

**Pre-registration.** Windows {1, 3, 7} and seeds {20260905, 20260906, 20260907} were written into
`config/phase6c_l3.yaml` before any L3 run, and tests assert their values. One training
configuration (Adam, lr 1e-3, ReduceLROnPlateau, max 30 epochs, patience 5) was used for every
candidate; no per-window tuning.

**Common target dates.** Train 2015-01-07→2020-12-31 (2,186 days), validation 2021-01-07→2021-12-31
(359 days), test 2022-01-07→2024-12-15 (1,074 days). The first 6 days of each split are sacrificed so
history never crosses a split boundary, and target indices start at `max_history-1` **regardless of
the window used** — so 1-day, 3-day and 7-day models are scored on an identical sample population
(3,997,824 validation and 11,960,064 test samples for every candidate).

**Test discipline.** No L3 decision used the test benchmark. `splits.open_split("test")` raises
`PermissionError` without an explicit flag; test embeddings and target caches were built **only
after** `phase6b_l3_selected.pt` was written, and a test asserts they cannot exist before that. The
benchmark was run **once**. Nothing was changed afterwards — including the tempting option of
re-tuning once the negative result appeared.

**Loss** is unchanged from Phase 6B-A/B: per-depth validity masks, NaN-safe, averaged per depth then
across depths. Scalers and climatology are the frozen train-only artefacts; nothing was refitted.

**A measurement caveat:** cached targets are float32 whereas the Phase 6B-A/B evaluations read
float64 from Zarr. The maximum discrepancy measured was 9.5e-7 °C, against RMSE values of
0.35–1.68 °C — negligible, but it means L3 tables are not bit-comparable with 6B-B tables. All
models *within* this report share the identical target path, so the comparisons here are exact.

## Tests

**182 passed** — 28 Phase 6A + 23 Phase 6A.5 + 44 Phase 6B-A + 38 Phase 6B-B + **49 new Phase 6B-C**.
No regression in any earlier phase.

New coverage includes: pre-registered windows and seeds; common-date arithmetic; exact L2 checkpoint
loading; encoder `requires_grad=False` and eval mode; **no gradient reaches the encoder**; encoder
weights bit-identical after optimiser steps; fingerprint detects a 1e-6 weight change; GRU input
width equals latent width; **identical trainable count across 1/3/7-day windows**; single shared GRU
cell; decoder width 15; current day is the last sequence element and influences the output more than
the oldest; decoder warm-start equality; checkpoint round-trip; deterministic inference; sequence
shape per window; contiguity and current-day-last ordering; **no future reads**; identical target
dates across windows; the 1-day control gains no extra dates; cell alignment constant across time;
reversed/repeated diagnostics reorder correctly; block batching equals direct sequences; every target
covered exactly once when shuffled; targets correspond to day *t*; no NaN into the GRU; missing deep
targets masked not fabricated; current-day lat/lon and DOY correctness; **target temperature never
appears in the sequence**; embedding cache declares no targets; target cache is a separate store;
cache provenance matches the frozen encoder and rejects a different one; **cached z equals direct
encoder output**; cache cell indexing matches the sampler; validation history never crosses into
train; no test dates in the L3 caches; test embeddings absent before freeze; split lock; train-only
scaler and climatology provenance; selected-checkpoint records validation-only selection.

## Artifacts

`outputs/models/` — `phase6b_l3_selected.pt` (frozen), `phase6b_l3_w{1,3,7}_s20260905.pt`,
`phase6b_l3_w{1,3}_s2026090{6,7}.pt`, plus a training JSON per run recording encoder hashes
before/after.
`outputs/embeddings/{train,validation,test}/` — cached z with encoder provenance; no targets.
`outputs/targets_cache/{train,validation,test}/` — separate target store.
`outputs/tables/` — `phase6b_l3_window_selection.csv`, `phase6b_l3_seed_stability.csv`,
`phase6b_l3_metrics_by_depth{,_test}.csv`, `phase6b_l3_vs_l2{,_test}.csv`,
`phase6b_l3_vs_control{,_test}.csv`, `phase6b_l3_depth_group_summary{,_test}.csv`,
`phase6b_l3_basin_summary{,_test}.csv`.
`outputs/figures/` — `l3_validation_vs_window.png`, `l0_l1_l2_l3_rmse_vs_depth{,_test}.png`,
`l2_vs_l3_anomaly_corr{,_test}.png`, `l3_delta_vs_l2{,_test}.png`,
`l3_delta_vs_control{,_test}.png`, `l3_depth_groups{,_test}.png`, `l3_seed_stability.png`,
`l3_ordering_diagnostic{,_test}.png`.

## Open questions preserved (not resolved by this phase)

1. **Dead latent units.** The L2 embedding is empirically low-rank in this trained instance, but the
   cause of the inactive dimensions remains unresolved. The encoder was frozen here, so this phase
   could not and did not address it. Temporal history did not "fix" them.
2. **Validation/test discrepancy.** Consistent with interannual distribution differences and now
   observed across L1/L2/L3, but the cause has not been isolated.
3. **Patch size.** 33×33 had the lowest validation loss under a fixed budget; not established as the
   globally optimal spatial scale.

---

# GO / INVESTIGATE: **INVESTIGATE**

Against the pre-registered gate:

| Criterion | Result |
|---|---|
| Implementation leakage-free | ✅ causal-only, split-bounded, target-free inputs, all tested |
| L2 encoder truly frozen | ✅ hash-verified identical in all 7 runs |
| Multi-day beats same-capacity 1-day control on primary validation metric | ✅ 0.14724 vs 0.15171 |
| Reproduced in ≥2/3 seeds | ✅ 3/3 on validation |
| Upper ocean not broadly degraded | ✅ on validation (10/10 in 0–150 m) |
| **Final frozen benchmark shows no major generalisation failure** | ❌ **the 0–150 m benefit reverses on test: +3.20 % → −0.52 %** |

Two INVESTIGATE triggers fired:

- **Validation gains largely disappear out of sample.** The benefit is +1.57 % on validation and
  −0.43 % on test, and the strongest, most coherent validation signal (10/10 depths in 0–150 m)
  becomes 4/10 and negative.
- **History ordering appears close to irrelevant.** Reversing time costs 0.215 %; deleting history
  entirely costs 0.277 %. The model is not exploiting temporal direction.

**Recommendation: keep L2 as the production model.** Do not adopt L3 into the architecture. A
no-temporal-benefit result is a legitimate scientific outcome, and forcing L3 in on the strength of
a validation-only gain would be exactly the error the control and the frozen benchmark exist to
prevent.

**What is genuinely worth following up**, using train+validation only and a fresh protocol:
the 1-day control's history-free improvement over L2 (decoder retraining plus a small module), which
held on both splits and costs almost nothing.

---

**Phase 6B-C L3 Temporal Memory Ablation is complete.**
**Temporal history vs L2/control results are ready.**
**GO/INVESTIGATE: INVESTIGATE.**

STOP — no encoder fine-tuning, terminal-ReLU replacement, latent redesign, EOF decoder, uncertainty,
D26/TCHP/OHC, cyclone, marine-heatwave, eddy, barrier-layer, monsoon/IOD, Experiment A/C/E, Argo
validation, NRT or frontend work has been started. Awaiting your review before proceeding.
