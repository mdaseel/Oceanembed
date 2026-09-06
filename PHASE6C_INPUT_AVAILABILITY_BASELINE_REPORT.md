# OceanEmbed — Phase 6C-B Report
**Input availability & latency stress baseline for the frozen L2**
Completed 2026-09-05 · no model was trained · L2 hash verified unchanged.

**Question:** under realistic missing and stale surface-input conditions, how much skill is lost,
which channels matter most, and when does climatology become safer than the current learned model?

**Answer, and it is not the expected one.** Latency is essentially free — two-day-old currents cost
**0.02 %** at 100 m. A total SSS outage costs 11–20 % *if* naively zero-filled, but a trivial
train-only fallback recovers **all** of it. The only catastrophic failure found is a **code-path
defect in the validity mask**, not a modelling deficiency. On this evidence a learned
availability-aware model is **not** justified.

---

## Step 0 — the existing input contract, and its one real flaw

Baseline before any change: **238 tests passing.** L2 hash verified before and after:
`b715bb2bff32d5e4a1e696b5350e29c3` (encoder `30cfd2db9e8b6b96473c1e205280c009`).

L2 consumes an **8-channel** padded field from `patches.day_field`: the 7 surface channels
standardised with the frozen train scaler, plus **one** validity channel. Missing cells are set to 0
(the train mean in standardised space) and the domain edge is zero-padded with mask 0.

**The critical line is `valid = np.isfinite(raw).all(axis=0)` — a single JOINT mask over all seven
channels.** There is no per-channel validity. The consequence, verified empirically:

| Input state | Valid cells (of 24,341) | Non-zero data cells |
|---|---|---|
| All seven channels present | 11,136 | 11,136 |
| **SSS unavailable everywhere** | **0** | **0** |

One missing channel zeroes **all seven channels and the mask, everywhere**. The CNN receives a blank
field. The mask cannot express "SSS is out but the other six are fine", and L2 was never trained on
whole-channel outages.

Two mask policies were therefore evaluated:

- **`joint`** — the literal frozen behaviour, kept so the failure is measured rather than assumed
  (mode J).
- **`available`** — validity computed from the channels that *are* present, which is what an operator
  would do. All other modes use this. It is still outside L2's training distribution.

## Step 1 — evaluation cohort

**Development data only: the 2021 validation year.** The frozen 2022–2024 benchmark was not used to
choose anything, and the **2024 Argo holdout was never opened** (asserted by a test).

| | |
|---|---|
| Targets | 2021-01-04 → 2021-12-31 (**362 days**) |
| Cells | 11,136 per day |
| **Samples per mode** | **4,031,232** |
| Truth | GLORYS `thetao` at the 15 depths |

The first three days are dropped so that every mode — including the 3-day-stale one — shares an
**identical population**. A test asserts all modes report the same sample count at every depth.

## Steps 2–4 — pre-registered modes and time semantics

Ten modes, fixed before any result was seen (`src/oceanembed/ml/stress.py`):
A complete · B SSS missing · C SSS coherent gaps · D/E/F currents at t-1/t-2/t-3 · G wind t-1 ·
H SLA t-1 · I SSS missing + currents t-2 · J SSS missing through the **unmodified joint-mask path**.

**Issue-time logic.** A channel of age *k* reads index `t-k` and nothing else — there is no
nearest-time search, so a future value cannot be selected. Asserted in code and by tests that decode
the source day from a traceable per-day constant and check `day <= t` for every channel in every
mode. U and V of a vector are always the same age (tested).

**Mode C gaps are explicitly synthetic and labelled as such** — no historical SMAP coverage masks are
held locally for 2021. Gaps are a few large blobs (~40 % of the grid, 3 contiguous regions, rotating
by day), because independent random pixels would be trivially easy for a 33×33 convolution to
interpolate around and would understate the damage.

## Step 5 — degradation vs complete inputs (% RMSE increase)

| Depth (m) | B SSS missing | C SSS gaps | D cur t-1 | E cur t-2 | F cur t-3 | G wind t-1 | H SLA t-1 | I combined | **J joint-mask** |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 20.77 | 7.31 | 0.10 | 0.22 | 0.35 | −0.02 | 0.07 | 20.85 | **223.09** |
| 10 | 18.98 | 6.44 | 0.05 | 0.12 | 0.21 | 0.02 | 0.05 | 19.02 | **229.26** |
| 30 | 20.20 | 7.32 | 0.04 | 0.11 | 0.20 | 0.01 | 0.01 | 20.21 | **201.95** |
| 50 | 20.28 | 8.25 | −0.01 | 0.02 | 0.10 | 0.04 | −0.03 | 20.25 | **165.13** |
| 75 | 15.28 | 6.11 | −0.02 | 0.04 | 0.20 | 0.04 | −0.12 | 15.32 | **108.62** |
| **100** | **11.21** | **4.55** | **−0.07** | **0.02** | **0.25** | **0.02** | **−0.11** | 11.29 | **90.38** |
| 125 | 11.22 | 4.70 | −0.10 | −0.02 | 0.20 | 0.02 | −0.07 | 11.25 | 84.09 |
| 200 | 8.17 | 3.45 | −0.06 | −0.05 | 0.02 | 0.01 | −0.06 | 8.06 | 78.84 |
| 500 | 6.88 | 2.75 | 0.03 | 0.07 | 0.10 | 0.02 | −0.12 | 6.98 | 119.73 |
| 1000 | 3.12 | 1.30 | 0.04 | 0.07 | 0.10 | 0.00 | −0.03 | 3.23 | 40.45 |

Depth groups (RMSE °C):

| Group | Complete | SSS missing | SSS gaps | Currents t-2 | Joint-mask | L0 |
|---|---|---|---|---|---|---|
| Surface / mixed | 0.4527 | 0.5419 | 0.4835 | 0.4534 | 1.4549 | 0.5861 |
| Upper thermocline | 0.6453 | 0.7742 | 0.6942 | 0.6457 | 1.8534 | 0.7979 |
| Thermocline | 1.1691 | 1.3146 | 1.2284 | 1.1693 | 2.2674 | 1.7351 |
| Intermediate | 0.8201 | 0.8970 | 0.8524 | 0.8200 | 1.4767 | 1.0914 |
| Deep | 0.3939 | 0.4147 | 0.4023 | 0.3942 | 0.7159 | **0.3905** |

## Step 6 — answers to the failure-map questions

**1. Which input failure hurts most?** By a wide margin, the **joint-mask code path** (+90 % at 100 m,
+229 % at 10 m). Among genuine data failures, a **total SSS outage** with naive zero-filling: +11 % at
100 m, +21 % at the surface.

**2. How harmful is missing SSS?** Naively, substantial: +19–20 % through 0–50 m, +11 % at 100 m,
+3 % at 1000 m. Damage is **largest in the surface and mixed layer, not the thermocline** — the
opposite of where L2's skill peaks. Coherent spatial gaps over ~40 % of the grid cost roughly a third
as much (+4.6 % at 100 m), so the 33×33 receptive field does substantial spatial in-filling on its own.
**But see Step 7 — this is fully recoverable.**

**3–5. Staleness.** Effectively free at every depth:

| Current age | 50 m | 75 m | 100 m | 125 m | 150 m | 200 m |
|---|---|---|---|---|---|---|
| t-1 | −0.013 % | −0.022 % | −0.069 % | −0.100 % | −0.066 % | −0.065 % |
| t-2 | +0.016 % | +0.037 % | **+0.017 %** | −0.023 % | +0.014 % | −0.050 % |
| t-3 | +0.103 % | +0.198 % | +0.255 % | +0.199 % | +0.202 % | +0.023 % |

**A ~2-day OSCAR delay does not destroy thermocline skill — it costs 0.02 % at 100 m.** Even 3-day-old
currents cost ≤0.26 %. Several 1-day entries are *negative*, i.e. within noise. **Stale wind is
immaterial** (≤0.04 % everywhere) and **stale SLA likewise** (≤0.12 %). This is a strong operational
result: OSCAR's ~1-year "Final"-tier latency is a product-selection problem, not a skill problem, and
day-to-day currency of currents, winds and SLA is close to irrelevant to this model.

**6. Where does climatology become safer?**

| Mode | Depths where L0 wins |
|---|---|
| Complete inputs | 700, 1000 m |
| Currents/wind/SLA stale (any) | 700, 1000 m — **unchanged** |
| SSS coherent gaps | 700, 1000 m — **unchanged** |
| SSS missing (zero-fill) | 500, 700, 1000 m — one depth worse |
| SSS missing + persistence **or** channel climatology | 700, 1000 m — **back to baseline** |
| **Joint-mask path** | **all 15 depths** |

The 700/1000 m boundary is the same one every previous phase found, and **no realistic degradation
moves it** once a sensible fallback is used.

## Step 7 — simple fallbacks under a total SSS outage

All three policies use train-only information. RMSE (°C):

| Depth (m) | Complete | **persistence** | **channel climatology** | zero-standardised | L0 |
|---|---|---|---|---|---|
| 10 | 0.4575 | 0.4576 | 0.4577 | 0.5443 | 0.5866 |
| 30 | 0.5918 | 0.5919 | 0.5928 | 0.7114 | 0.7127 |
| 50 | 0.8070 | **0.8069** | **0.7949** | 0.9707 | 1.0171 |
| 75 | 1.0963 | **1.0959** | **1.0789** | 1.2637 | 1.5342 |
| **100** | 1.2255 | **1.2254** | **1.2243** | 1.3629 | 1.8726 |
| 150 | 1.0608 | 1.0611 | 1.0682 | 1.1758 | 1.5014 |
| 300 | 0.5268 | 0.5268 | 0.5274 | 0.5574 | 0.5752 |

**This is the headline finding. Carrying yesterday's SSS forward, or substituting its train-only
seasonal climatology, recovers essentially 100 % of the loss** — at 100 m, 1.2254 and 1.2243 versus a
complete-input 1.2255. At 50–75 m the channel climatology is marginally *better* than the real field.

The interpretation is that **L2 uses SSS mainly for its slowly-varying, largely seasonal structure,
not its day-to-day anomaly.** That is consistent with the supplied SSS being an 8-day product in
Phase 6A and with the small marginal information a smooth salinity field adds once SST, SLA and winds
are present. It is a statement about this model's sensitivity, **not** a claim about the physical
importance of salinity.

**Strongest simple fallback: channel climatology, with persistence statistically indistinguishable.**
Persistence is preferable operationally — it needs only the previous day's field, degrades gracefully
to older days, and requires no fitted artefact at inference time.

## Step 8 — the target the future L2-NRT model would have to beat

The bar is **not** a deliberately broken frozen L2. It is the best simple policy.

| Failure mode | Strongest simple baseline | Frozen L2 (naive) | **Target for any future L2-NRT** (RMSE at 100 m) |
|---|---|---|---|
| SSS missing | persistence / channel clim. → **1.224** | 1.363 (zero-fill) | must beat **1.224**, i.e. beat complete-input L2 (1.2255) |
| SSS coherent gaps | persistence-style in-fill (not separately run) | 1.281 | must beat ~**1.22–1.28** |
| Currents t-1/t-2/t-3 | use them as-is | 1.225 / 1.226 / 1.229 | must beat **1.225** — essentially no headroom |
| Wind t-1 | use as-is | 1.226 | no headroom |
| SLA t-1 | use as-is | 1.224 | no headroom |
| SSS missing + currents t-2 | persistence on SSS | 1.364 | must beat ~**1.225** |
| **Joint-mask outage** | **fix the mask** (engineering) | 2.333 | not a modelling target |

**In every realistic mode the target is at or below complete-input L2 performance.** A learned
availability-aware model would have to match a model that sees all its inputs — while seeing fewer.
There is essentially no headroom for it to claim.

## Step 8b — basin sensitivity

Degradation under a total SSS outage differs sharply and non-monotonically by basin:

| Depth (m) | Arabian Sea | Bay of Bengal |
|---|---|---|
| 0 | +18.1 % | +8.1 % |
| 50 | **+23.1 %** | **−4.1 %** |
| 75 | +21.4 % | **−7.8 %** |
| 100 | +19.0 % | −2.8 % |
| 200 | +9.2 % | +15.0 % |
| 500 | +6.0 % | **+23.6 %** |
| 1000 | +4.3 % | +14.8 % |

Sample counts exceed 1.0 M in every cell, so these are not small-sample artefacts.
**The Arabian Sea is far more sensitive to SSS in the upper 100 m; the Bay of Bengal is more sensitive
below 200 m** — and in the BoB thermocline, removing SSS slightly *improves* the prediction.

That last point deserves care rather than a physical story. It is consistent with the freshwater-
capped BoB, where a strong halocline decouples surface salinity from thermocline temperature, so SSS
may act partly as a distractor there. But this is a **model-sensitivity observation under an imposed
outage, not causal channel importance**, and lat/lon remain model inputs, so basin identity is
directly visible. It is flagged for a later, properly designed attribution study.

## Step 11 — tests

**274 passed** — 238 pre-existing plus **36 new**. No earlier phase regressed.

New coverage: L2 checkpoint hash unchanged; stress code contains no optimiser, `.backward()` or
`requires_grad_(True)`; surface climatology and both scalers train-only; 2024 Argo holdout
inaccessible; split lock intact; modes pre-registered and unique; **U/V ages paired for currents and
winds**; declared ages correct; **a channel of age k reads exactly t-k** (parametrised 0–3);
**no future day can be read in any mode**; negative index refused; persistence carries forward and
never looks forward; persistence walks further back when intermediate days are missing;
**A_COMPLETE is bit-identical to the frozen `day_field`**; the joint-mask blanking pinned so it cannot
regress silently; available-mask keeps other channels alive; zero-standardised maps the train mean to
exactly 0; land masking unchanged under degradation; **no NaN reaches the CNN in any mode**; field
shape matches the frozen contract; **degradation does not mutate the source dataset**; degradation
deterministic; gap masks coherent (≤12 blobs), reproducible and day-dependent; gaps touch only SSS;
identical populations across modes; complete-mode degradation exactly zero; all 15 depths present;
recorded hashes equal; cohort is development data only; age sensitivity covers 0–3 days.

One test initially failed and was **correct to fail**: it asserted that persistence would fill an
*undeclared* NaN channel and keep the cell alive. In the frozen semantics an undeclared NaN still
participates in the joint mask, so the cell is blanked regardless of imputation. The test was wrong,
not the code; it was corrected and a second test now pins the undeclared-NaN behaviour explicitly.

## Artifacts

`outputs/tables/` — `phase6cb_input_stress_by_depth.csv`, `phase6cb_input_stress_depth_groups.csv`,
`phase6cb_skill_vs_climatology.csv`, `phase6cb_current_age_sensitivity.csv`,
`phase6cb_simple_fallbacks.csv`, `phase6cb_basin_sensitivity.csv`,
`phase6cb_basin_degradation.csv`, `phase6cb_stress_meta.json`
`outputs/baselines/phase6cb_surface_climatology.nc` (train-only, 2015–2020)
`outputs/figures/` — `input_stress_rmse_vs_depth.png`, `input_stress_skill_vs_depth.png`,
`input_stress_heatmap.png`, `current_age_sensitivity.png`, `input_stress_100m_summary.png`,
`input_stress_fallbacks.png`, `input_stress_basin.png`

---

## Verdict

Against the pre-registered gate:

| Criterion | Evidence |
|---|---|
| At least one realistic mode causes meaningful degradation | ⚠️ Only SSS outage, and **only when naively zero-filled** |
| The operating problem is measurable and reproducible | ✅ 4.03 M samples/mode, identical populations, deterministic |
| Simple fallback behaviour can be clearly defined | ✅ persistence — and it **recovers essentially all the loss** |
| Frozen L2 + simple policies retain essentially all useful skill across realistic modes | ✅ **yes, in every mode tested** |

# ALREADY ROBUST — RECONSIDER COMPLEXITY

**A learned availability-aware L2-NRT model is not justified by this evidence.** In every realistic
operating mode, the frozen L2 combined with a one-line fallback policy performs at or within noise of
complete-input L2:

- Stale currents (1–3 d), stale wind, stale SLA: **≤0.26 % cost**, no change to where climatology wins.
- Total SSS outage: **fully recovered** by persistence or train-only channel climatology.
- Coherent SSS gaps over 40 % of the domain: +4.6 % at 100 m, still comfortably beating climatology.

**What this phase does justify is two pieces of engineering, not a new network:**

1. **Fix the joint validity mask** (the only catastrophic failure). Expressing per-channel validity —
   or simply computing the mask from available channels and imputing the absent one — converts a
   +90 % blow-up at 100 m into a +11 % one, and with persistence into ~0 %. This is a small, testable
   change to `day_field`, not a retraining exercise. **It is out of scope here and is not implemented.**
2. **Adopt a documented fallback policy**: carry forward the last available field per channel; fall
   back to the train-only channel climatology if nothing recent exists.

**Honest caveats.** Mode C's gaps are synthetic, so the spatial-gap number is indicative rather than
calibrated against real SMAP coverage. Staleness was simulated by substituting an older field, which
tests sensitivity to currency but not to a genuine forecast/NRT product having different error
characteristics from the reanalysis-grade inputs used here. Both would be worth revisiting with real
NRT products before an operational deployment claim — but neither is likely to overturn a result this
one-sided.

**I am explicitly not manufacturing a robustness problem.** The pre-registered instruction was not to,
and the measurements do not support one.

---

**Phase 6C-B input-availability and latency stress baseline is complete.**
**Result: ALREADY ROBUST — RECONSIDER COMPLEXITY.**

STOP — no L2-NRT training, no channel-specific trainable masks, no source-age inputs, no residual
prediction, no alpha blending, no uncertainty model, no NRT ingestion, no 2024 Argo use, no
D26/TCHP/OHC, no cyclone or marine-heatwave analysis, no frontend. Awaiting your review.
