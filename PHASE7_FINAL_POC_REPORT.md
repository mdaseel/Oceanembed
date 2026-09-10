# PHASE 7 — Final PoC Freeze

**Project:** SIH26066 — OceanEmbed · INCOIS / Ministry of Earth Sciences
Run 2026-09-11 · Full suites **603 pytest · 102 Vitest · 23 Playwright**
(baseline before Phase 7: 384 pytest, no frontend)

Machine-readable freeze: **`outputs/phase7/FINAL_POC_MANIFEST.json`**, generated
by `scripts/poc/build_final_manifest.py`, which reads every value from the
artifact it describes. A test re-hashes all 17 referenced artifacts and fails if
any has moved since the freeze.

---

## 1. What Phase 7 was for, and what it delivers

The problem statement's items 1–5 — preprocessing, embeddings, the
reconstruction model, the 15 depths, and independent validation — were complete
before this phase. Item 6, *"demonstration of a working Proof-of-Concept over
the Bay of Bengal / Arabian Sea"*, is what Phases 7A–7E built.

What exists now is an offline application that a stranger can open, pick a
historical date and depth, click an ocean point, and read a 15-depth
reconstructed temperature profile against climatology — with every number
traceable to one frozen model run, and every limitation stated on the screen it
affects.

| Phase | Delivered |
|---|---|
| **7A** | `replay_field(date)` / `replay_point(date, lat, lon)` over the frozen L2; provenance-keyed cache; local API. Point replay *samples* the field, so map, profile and 3D can never disagree. |
| **7B** | The historical PoC: map, depth selector, layers, click-profile, surface-input panel, provenance & validation page, 3D depth view, exports, settings. Offline, no Ion token, three.js chosen over Cesium and documented. |
| **7C** | D26 and TCHP, with a verified convention, a pre-registered population, and the three-stage discretization experiment. Plus a corrective pass that extended physical water-column support to the 2D map and the diagnostics. |
| **7D** | One historical event (Cyclone Mocha, May 2023) and the historical Ocean Hazard Indicators tab, with pre-registered thresholds and an explainability panel. |
| **7E** | This freeze, and the pre-registered — **unexecuted** — 2024 Argo holdout evaluation. |

---

## 2. The frozen scientific core

Unchanged since Phase 6B, re-verified against its recorded hashes at every
engine start; a mismatch is a hard failure, not a warning.

| Artifact | SHA-256 |
|---|---|
| L2 state-dict | `b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d` |
| L2 encoder | `30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808` |
| Checkpoint file | `81979a6541927ff5c6b0a13c5ce7cdbcd486040d16a304dcdc10b2962a586e35` |
| Feature scaler | `49671ce760b0dca5c1c82cb184dae91908cc064abfdea8cc7eb2f5bc3c320467` |
| Target scaler | `5b6f359db0d228dd7d3acf775ab8a6eea76dd521e7b4568ff1873c832e89e93b` |
| L0 climatology | `748af4d79bc704cc2f742e1c208bacebe781131c5ff142cddc7c334963903cd5` |

L2 Spatial Satellite Embedding Engine · 136,335 parameters · 32-dim latent ·
33-cell receptive field · 7 surface inputs → 15 depths on a 101 × 241 grid at
0.25°, 5–30 °N / 45–105 °E.

**Nothing in Phase 7 retrained, fine-tuned, or modified it.** No architecture
search was reopened; L3 remains tested and rejected.

## 3. Versions frozen

| Component | Version |
|---|---|
| Replay API | `7A` · `replay_field` / `replay_point` · field shape 101 × 241 × 15 |
| Processing | `6B.1` |
| Grid | `5.0-30.0N_45.0-105.0E_0.25deg` |
| Transport schema | `oceanembed.field-view.v1` |
| Cache format | `1` — provenance-keyed on date + model + scaler + climatology hashes + processing and grid version; only real frozen-L2 output is ever stored, and a mismatch is a miss rather than a silent reuse |
| Diagnostics | `7C.1` — D26 / TCHP |
| Hazard indicator | `7D.1` — Ocean Thermal Support for Cyclone Intensification |
| Frontend | React + TypeScript + Vite, three.js, Plotly; routes `replay`, `depth`, `hazard`, `validation`, `exports`, `settings` |

**D26 / TCHP convention.** Form after Leipper & Volgenau (1972), as used
operationally by NOAA/AOML (Shay et al. 2000; Goni et al. 1996). Constants from
**TEOS-10** (IOC/SCOR/IAPSO 2010) via `gsw`, not copied from a table:
ρ₀ = **1023.035344728 kg m⁻³**, cp₀ = **3991.86795711963 J kg⁻¹ K⁻¹**,
ρ₀·cp₀ = 4 083 822.01 J m⁻³ K⁻¹. cp₀ is *derived* from the standard's own
identity `h⁰ = cp₀·Θ` and pinned by a test. Published conventions span ≈8 %, so
OceanEmbed's TCHP is ≈5 % below the frequently-quoted 1026 × 4178 pair — a
convention difference, not a skill difference.

**Pre-registrations, all written before their results existed:**

- `outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md`
- `outputs/phase7/EVENT_SELECTION.md`
- `outputs/phase7/HAZARD_INDICATOR_PROTOCOL.md`
- `outputs/phase7/FINAL_2024_ARGO_PREREGISTRATION.md`

**Hazard thresholds** (`HAZARD_THRESHOLDS.json`): p50 **55.70**, p75 **79.10**,
p90 **96.94** kJ cm⁻², from 4,552,444 samples over 439 train-split dates.
Frontend status: **shipped, historical only**, never connected to live data, no
numeric cyclone probability anywhere.

**Event:** Cyclone Mocha, Bay of Bengal, window 2023-05-05…2023-05-22, selected
by an external IMD-intensity rule inside the **locked test split** before any
event-specific model output was inspected.

**Demonstration default:** 2021-06-15 at 15.25 °N, 87.75 °E — central Bay of
Bengal, chosen by geography in Phase 7B, not by prediction error. Runs offline.

---

## 4. Application metrics — the executed numbers

### 4.1 Reconstruction skill, grid test set 2022–2024

| Depth | L0 RMSE | L2 RMSE | Skill vs L0 |
|---|---|---|---|
| 0 m | 0.683 | **0.477** | **+30.1 %** |
| 50 m | 1.118 | 0.868 | +22.3 % |
| 100 m | 1.788 | **1.189** | **+33.5 %** |
| 150 m | 1.397 | 1.030 | +26.3 % |
| 300 m | 0.544 | 0.515 | +5.4 % |
| 500 m | 0.358 | 0.373 | **−4.1 %** |
| 700 m | 0.359 | 0.369 | −2.7 % |
| 1000 m | 0.382 | 0.387 | −1.3 % |

The shape of this table is the honest headline: **the model earns its keep
through the thermocline and loses to climatology below ~500 m.** That is stated
in the UI at those depths rather than buried here.

### 4.2 External Argo observational check, 2022–2023

5,176 collocated profiles from 92 floats, same-day, ocean-aware collocation.

| Depth | n | L2 RMSE | bias | corr | anomaly corr |
|---|---|---|---|---|---|
| 0 m | 91 | 0.401 | −0.101 | 0.905 | 0.632 |
| 50 m | 4,997 | 1.158 | +0.382 | 0.896 | 0.526 |
| 100 m | 5,014 | 1.224 | +0.478 | 0.876 | **0.734** |
| 300 m | 4,962 | 0.674 | +0.172 | 0.949 | 0.516 |
| 1000 m | 3,219 | 0.279 | +0.138 | 0.977 | 0.395 |

**This is an external observational check, not perfectly independent truth** —
GLORYS assimilates in-situ observations. Stated wherever the numbers appear.

### 4.3 D26 / TCHP application error, decomposed

216 pre-registered dates, ~2.0 M paired samples, whole NIO:

| | A vs B (discretization) | B vs C (reconstruction) | A vs C (total) |
|---|---|---|---|
| D26 MAE | **1.26 m** | 9.24 m | 9.69 m |
| TCHP MAE | **1.70 kJ/cm²** | 11.47 kJ/cm² | 12.40 kJ/cm² |

The mandated 15-depth sampling costs ~13 % of the total; reconstruction is the
rest. **The problem statement's own depth list is not what limits the
diagnostic** — a directly useful answer to an obvious jury question.

### 4.4 Test counts

| Suite | Count |
|---|---|
| pytest | **603** |
| Vitest | **102** |
| Playwright | **23** |
| **Total** | **728** |

Baseline entering Phase 7: 384 pytest, no frontend suite. Not a target that was
aimed at — the actual current result.

---

## 5. Known limitations, carried into the freeze

Recorded in the manifest and surfaced in the UI where each one bites:

1. **Deep-ocean daily anomaly skill at 500–1000 m is weaker and more
   climatology-dominant.** L2 is *worse than L0* at 500 m (−4.1 %). Disclosed at
   those depths in the profile, the 3D view and the validation page.
2. **The frozen L2 has no concept of the seafloor.** It emits all 15 depths
   wherever surface inputs are valid, so ~7–8 % of D26 results would otherwise
   sit below the local seabed. These are qualified as
   `INSUFFICIENT_WATER_COLUMN_SUPPORT` for display; raw values are preserved and
   exported unchanged.
3. **Bathymetry is point-sampled at cell centres, not cell minima**, so a 0.25°
   cell spanning a shelf edge is represented by its centre depth alone.
4. **TCHP is convention-dependent** and not numerically interchangeable with
   operational products using different constants.
5. **Hazard categories are relative to this basin's own history.** A `LOW` label
   does not mean insufficient heat for a cyclone.
6. **The hazard rule uses one quantity** and cannot see salinity stratification
   or barrier layers — which matter in the Bay of Bengal, precisely because
   OceanEmbed does not reconstruct salinity.
7. **The TCHP reconstruction error is ~half a hazard category wide**, so
   adjacent categories are not distinguishable at a single cell.
8. **Argo is an external check, not independent truth.**
9. **The Phase 7C benchmark used the locked test split**, already opened for the
   6B and 6C results. It is historical application validation, not a pristine
   test set.

---

## 6. The protected 2024 Argo holdout

**NOT OPENED.** No 2024 profile has been downloaded for analysis, collocated,
scored, plotted, or compared against any OceanEmbed output.

`outputs/phase7/FINAL_2024_ARGO_PREREGISTRATION.md` freezes the method in
advance: the same code (not merely the same philosophy) — the existing QC
helpers, TEOS-10 potential-temperature conversion, the same 15 depths, the same
collocation with zero temporal offset, the same metric columns, all 15 depths
reported, float-clustered bootstrap CIs. It pre-commits the interpretation for
every outcome, including "substantially worse", and forbids tuning to 2024 in
all of them.

**One nuance is recorded there deliberately rather than left to be discovered.**
Argo distributes one file per float containing *every* cycle. Floats were
selected for their 2022–2023 profiles and the fetch script refuses an index
selection containing 2024, so no float was ever chosen *because of* 2024 data —
but a selected float that stayed active carries later cycles inside the file
that was fetched. The QC pass reads timestamps only to **exclude** them (16,699
rejected as `outside_window`). This was **not verified by opening those files**,
because that inspection would itself be the thing the holdout forbids.

The claim that matters, and the one that is test-enforced: **nothing about 2024
has informed the model, the scalers, the climatology, the architecture, the
diagnostics, the thresholds, or the event selection.** A test asserts the
maximum date in the collocation output is before 2024-01-01.

**NRT status: NOT STARTED.** No live-fetch code, no credentials, no network call
in the application, and no `Latest Inputs` tab — not even a disabled one. Tests
assert the absence of `copernicusmarine`, `earthaccess`, any HTTP client in the
served app, and the reserved wording `Latest Qualified Ocean State` and
`Live Ocean Right Now`.

---

## 7. The repository freeze itself

The freeze is **two commits**, deliberately, because a manifest cannot contain
the hash of the commit that contains it. Rather than paper over that, the two
are named separately and the distinction is recorded in the manifest.

| Commit | Contents |
|---|---|
| **`9fb32ba` — source freeze** | All Phase 7 code, tests, scripts, scientific artifacts, pre-registrations, executed tables and figures, static assets, and the 7A–7D reports. 88 files, +8,701 / −494. |
| *(this one)* — freeze metadata | `FINAL_POC_MANIFEST.json` and this report, which describe the commit above. |

`FINAL_POC_MANIFEST.json` records `source_freeze_commit: 9fb32ba16e30b8670cc…`
and `source_tree_clean_excluding_freeze_metadata: true`. The freeze claim it
makes is precise: **nothing outside the two declared metadata files was
uncommitted when it was generated.** Four tests verify this against git rather
than against the manifest's own assertion — that the recorded commit exists in
history, that no source or artifact file is uncommitted, that the manifest
declares itself as separately committed, and that every one of the 17 hashed
artifacts is tracked by git.

**What was checked before staging.** All 70 changed paths were enumerated and
reviewed. No `__pycache__`, `node_modules`, `.venv`, `test-results` or
`replay_cache` entered the commit — all correctly ignored. A credential-pattern
scan across every new and changed text file returned only this report's own
sentence stating that no credentials exist.

**Evidence images and the regression suite.** Running the e2e suite regenerates
screenshots under `outputs/phase7b`, `phase7c` and `phase7d`. After the final
verification run these were restored to their committed state, so each phase's
evidence still reflects the build that produced it and the freeze is exactly
reproducible.

## 8. Freeze discipline

- Every phase's pre-registration was written **before** the results it governs.
  Where a freeze review later corrected wording, the original text was left
  intact and a dated post-freeze note appended — never a silent rewrite. Two
  tests pin that a correction can never move a boundary.
- Frozen artifacts are byte-identical to Phase 6B. Executed Phase 7C evaluation
  outputs were never regenerated after the fact.
- The three flaws found by *looking at the running application* rather than by
  tests — a legend counting land, an error message blaming the wrong cause, and
  a storm track drawn over dates it never crossed — are recorded in the phase
  reports rather than quietly patched. Green assertions are not the same as a
  correct screen.
- Phase 7B evidence images were restored byte-identical after every regression
  run, so each phase's evidence still reflects the build that produced it.

---

# PHASE 7E GATE

```
OceanEmbed Phase 7 PoC complete.

Final core: existing frozen L2
Frozen L2 preserved: YES

Historical point replay: WORKING
Historical field replay: WORKING

15-depth profile: WORKING
Climatology + anomaly: WORKING

Dashboard: WORKING
3D Depth View: WORKING

D26: VALIDATED
TCHP: VALIDATED

Historical event replay: WORKING
Ocean Hazard Indicators: WORKING

2024 Argo: PROTECTED
Final holdout preregistration: READY

Full test suite: 603 passed
  (plus 102 Vitest and 23 Playwright — 728 total)
```

**PHASE 7E COMPLETE — AWAITING REVIEW.**

Two SEPARATE approvals are possible from here, and granting one does NOT grant
the other:

1. approval to open the protected 2024 Argo holdout
2. approval to begin Phase 8A (NRT-Lite / live input telemetry)

Take no action on either until explicitly told which to proceed with.
Phase 8B full NRT subsurface qualification is specified in the master prompt but
is **NOT** authorized at the end of Phase 7E; Phase 8A must be completed and
reviewed first.
