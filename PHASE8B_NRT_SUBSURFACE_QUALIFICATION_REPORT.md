# PHASE 8B — NRT Subsurface Qualification

Run 2026-09-11 · protocol frozen at commit `5b69dda` **before** the candidate SSS
product was downloaded and before any statistic was computed · hindcast executed
at `705aa80` · latest path, UI and rehearsal at `db4a7c4`.

Frozen core untouched and re-verified before and after every run: L2 state dict
`b715bb2b…e728d`, encoder `30cfd2db…db4808`, feature/target scalers and L0
climatology file hashes as recorded in `replay/engine.py`. **No model was
trained, fine-tuned, adapted, bias-corrected or quantile-mapped. No Argo file of
any year was opened; 2024 Argo remains PROTECTED.**

---

## 0. The answer

> Can the COMPLETE frozen-L2 seven-channel operational input contract support a
> scientifically qualified latest available 15-depth subsurface reconstruction?

**Yes — QUALIFIED WITH LIMITATIONS.** All five pre-registered gates passed on all
56 pre-registered hindcast dates. Plain `QUALIFIED` was declared unreachable in
the protocol before any result existed: no permitted data can observationally
validate an NRT stack (the products begin in 2024, 2022–2023 Argo predates them,
2024 Argo is protected).

| quantity | operational category |
|---|---|
| 15-depth temperature | **QUALIFIED WITH LIMITATIONS** |
| D26 | **NOT QUALIFIED** — withheld from the latest mode |
| TCHP | **QUALIFIED** |
| Ocean Hazard Indicators | **QUALIFIED** (transfer follows TCHP, per protocol §9) |

A genuine latest qualified reconstruction was produced from the live providers:
**valid 2026-09-03**, retrieved 2026-09-11 17:17 UTC — **8.7 days** before
retrieval, because OSCAR NRT currents set the common date.

---

## 1. Which seven operational product/channel policies were evaluated?

Exactly one stack, `NRT_STACK_V1`. No other was scored.

| channel | product (dataset id) | 6C-D prior decision |
|---|---|---|
| SST | OSTIA NRT `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2` | SUBSTITUTE_APPROVED |
| **SSS** | **MULTIOBS NRT `cmems_obs-mob_glo_phy-sss_nrt_multi_P1D`** | *new — evaluated here* |
| SLA | DUACS NRT all-sat 0.125° | SUBSTITUTE_WITH_MONITORING |
| current U/V | OSCAR NRT v2.0 | SUBSTITUTE_WITH_MONITORING |
| wind U/V | CMEMS NRT wind L4, hourly → daily U/V mean | SUBSTITUTE_APPROVED |

**The SSS finding that made this phase possible.** Phase 6C-D tested only SMOS
L3 and SMAP L2C and rejected both (`NRT_STACK_NOT_VIABLE_RAW`). Inspecting the
model-ready store's own `source_sss` attribute showed the training SSS is CMEMS
MULTIOBS L4, and the live catalogue shows the **same product** publishes a daily
NRT dataset from 2024-01-01. It had never been audited. It is harmonised exactly
like the training SSS (`sos` → PSU, no conversion, same regrid).

## 2. How were source times aligned?

`COMMON_VALID_DATE`: every channel is used at the **same** valid date `D`, as in
training. `D = min over products of the newest complete day` (wind counts a day
only once its 23:00 field exists). Nothing is carried forward from an older day.

Recorded per latest state: requested and retrieval time, per-product newest
available time, per-product valid time used, per-product age, oldest/newest
input age, effective date, reconstruction lag, persisted inputs (always none),
operating-policy name. Product valid time and local retrieval time are separate
fields everywhere.

## 3. What SSS mode, and what maximum persistence age?

`SSS_MULTIOBS_NRT_SAME_DATE` — the MULTIOBS NRT field valid on `D`.
**Persistence envelope: 0 days, every channel.** The only persistence evidence
in the repository (6C-C `SSS_ABSENT_PERSIST`) was produced at **one day** — the
`max_persist_days = 7` in `policy.py` is a code default, not evidence — and the
alignment rule makes persistence unnecessary. Not used: SMOS/SMAP (6C-D
REJECT_RAW), channel climatology (6C-C: worse against Argo), zero/mean fill.

## 4. What historical overlap supported hindcast-the-NRT?

The 56 Phase 6C-D pre-registered dates, 2024-07-01 → 2024-12-13 (every 3rd
day), fixed before any 6C-D result. **56/56 assembled** with the complete stack.
For each date the frozen L2 was run on all seven NRT channels (N), compared with
the reference-input historical replay (R), L0 climatology, and GLORYS12V1 on the
15 depths (the reference). The assembled-field reference path was asserted
**bitwise identical to `replay_field`** on every date, so every difference below
is a product difference, not a pipeline difference.

Declared in advance: the dates lie inside the locked test split (targets read
for evaluation only, as Phase 7C already had); GLORYS assimilates observations
and is not independent truth; downloads are retrospective.

## 5. Temperature skill at all 15 depths (whole NIO, RMSE °C vs GLORYS)

| depth | L0 | **N (operational)** | R (historical) | N skill vs L0 | N vs R |
|---|---|---|---|---|---|
| 0 | 0.694 | **0.515** | 0.512 | +25.7 % | +0.7 % |
| 5 | 0.691 | **0.516** | 0.514 | +25.4 % | +0.4 % |
| 10 | 0.704 | **0.522** | 0.520 | +25.8 % | +0.4 % |
| 20 | 0.772 | **0.598** | 0.597 | +22.6 % | +0.1 % |
| 30 | 0.873 | **0.681** | 0.680 | +22.0 % | +0.2 % |
| 50 | 1.176 | **0.887** | 0.902 | +24.6 % | −1.8 % |
| 75 | 1.524 | **1.129** | 1.134 | +25.9 % | −0.4 % |
| 100 | 1.649 | **1.296** | 1.247 | +21.4 % | **+3.9 %** |
| 125 | 1.565 | **1.309** | 1.252 | +16.4 % | **+4.5 %** |
| 150 | 1.347 | **1.189** | 1.144 | +11.7 % | +3.9 % |
| 200 | 0.913 | **0.872** | 0.853 | +4.5 % | +2.2 % |
| 300 | 0.552 | **0.537** | 0.536 | +2.7 % | +0.2 % |
| 500 | 0.365 | **0.360** | 0.365 | +1.3 % | −1.3 % |
| 700 | 0.369 | **0.366** | 0.369 | +0.7 % | −0.9 % |
| 1000 | 0.424 | **0.413** | 0.418 | +2.7 % | −1.2 % |

Correlation with GLORYS 0.889–0.954 (N) against 0.761–0.953 (L0); anomaly
correlation 0.72–0.73 at 100–125 m, identical to R. Full tables:
`outputs/tables/phase8b_hindcast_*.csv`.

**Gates** (all copied from executed phases, none invented):

| gate | rule | result |
|---|---|---|
| G1 | 6C-D per-channel rule for the new SSS | **SUBSTITUTE_APPROVED** — band USABLE_WITH_CAVEAT (r 0.189, b 0.018, ρ 0.992, q 1.010), s 0.21 MINOR at 100 m, coverage loss 0.3 % |
| G2 | 6C-D whole-stack rule | **NRT_STACK_VIABLE_WITH_MONITORING** — s 0.43 MATERIAL at 100 m, worst MATERIAL, coverage loss 0.5 % |
| G3 | 6C-A gate A: beat L0 at ≥ 6 of 11 depths 0–200 m | **11 / 11** |
| G4 | 6C-A gate C: beat L0 at 75/100/125 m, 95 % CI < 0 | 75 m [−0.415, −0.372] · 100 m [−0.394, −0.312] · 125 m [−0.311, −0.203] °C |
| G5 | 6C-C criterion 4: beat L0 at 100 m in both basins | AS 1.193 < 1.408 · BoB 1.375 < 1.936 |

**What the stack costs.** Operational inputs move the reconstruction by 43 % of
the model's own error at 100 m (6C-D band MATERIAL, as the 6C-D post-hoc
`ALL_NRT_EXCEPT_SSS` diagnostic foreshadowed at 0.36). In accuracy terms it is
**detectably worse than historical replay at 100 and 125 m** (N−R 95 % CI
[+0.033, +0.062] and [+0.042, +0.070] °C) and within noise at 75 m — while still
beating climatology by a wide, significant margin.

**One mechanism is visible in the bias.** The 100–150 m warm bias against GLORYS
grows from +0.36 to **+0.48 °C** at 100 m and from +0.54 to **+0.65 °C** at 125 m.
Phase 6C-A found a thermocline warm bias of the same sign; the operational
inputs add roughly +0.1 °C to it.

## 6. What coverage?

Joint-mask coverage of the reference cells: 99.45 % mean over the hindcast
(loss 0.55 %); **99.66 %** in the live run. The pre-registered request-time floor
(L4) is 95 %.

## 7. How did the Arabian Sea and the Bay of Bengal differ?

| 100 m RMSE °C | L0 | N | R | N vs R |
|---|---|---|---|---|
| Arabian Sea | 1.408 | 1.193 | 1.174 | +1.6 % |
| Bay of Bengal | 1.936 | 1.375 | 1.302 | **+5.6 %** |

The Bay of Bengal gains most from the model (+29 % over L0) and also loses most
to the operational inputs. **Depth-dependent limitations:** in the Arabian Sea
the operational mode did not beat climatology at **300 and 500 m**; in the Bay of
Bengal at **700 m**. The whole-NIO mode beats L0 at every depth. The SSS channel
is MARGINAL in the Arabian Sea alone (q 0.850, on the boundary); the 6C-D
convention decides on the full NIO and reports the basin as a caveat, which is
what is done here.

## 8. Useful skill over L0, and 500–1000 m

Useful skill is retained where claimed: +16 to +26 % over L0 from 0 to 125 m,
+12 % at 150 m. **Below 300 m the margin is 0.7–2.7 %** and deep daily anomaly
correlation is only **0.21–0.26** (N) — the deep band is climatology-dominant. A
low deep RMSE is small variability, **not** strong deep anomaly skill. The deep
disclosure is shown in the latest tab exactly as in Historical Replay.

## 9. Were D26 / TCHP operationally qualified?

Evaluated only because temperature qualified (protocol §8), with the frozen
Phase 7C definitions, under non-inferiority to historical replay (no margin
invented): the paired date-bootstrap CI of `MAE(N) − MAE(R)` against GLORYS must
contain zero or lie below it, in the whole NIO and each basin.

| | whole NIO | Arabian Sea | Bay of Bengal | category |
|---|---|---|---|---|
| D26 MAE diff (m) | +0.16 [+0.02, +0.31] | +0.04 [−0.11, +0.19] | **+0.37 [+0.25, +0.50]** | **NOT QUALIFIED** |
| TCHP MAE diff (kJ/cm²) | −0.26 [−0.48, −0.03] | −0.05 [−0.26, +0.21] | −0.28 [−0.45, −0.08] | **QUALIFIED** |

D26 is detectably worse — consistent with the extra thermocline warm bias
deepening the 26 °C isotherm. It is **withheld**: the transport carries no D26
value at all, the frontend contract rejects a withheld diagnostic that carries
one, and no layer, tile or export offers it. TCHP is at least as good as
historical replay.

## 10. Did the historical hazard indicator transfer?

Yes, by the pre-registered rule: the Phase 7D indicator is a fixed function of
TCHP with frozen thresholds (55.70 / 79.10 / 96.94 kJ/cm², **not retuned**), so
transfer follows TCHP. Descriptively, N and R agree on the category at **88.1 %**
of 631,008 cell-days. The latest indicator carries the non-prediction statement
and no numeric probability. The Phase 7D protocol file is unchanged.

## 11. Was a latest 15-depth map actually certified?

**Yes, with limitations**, and one was produced from the live providers:

| product | newest available | valid time used | age at retrieval |
|---|---|---|---|
| OSTIA NRT SST | 2026-09-10 | 2026-09-03 | 209.3 h |
| MULTIOBS NRT SSS | 2026-09-05 | 2026-09-03 | 209.3 h |
| DUACS NRT SLA | 2026-09-11 | 2026-09-03 | 209.3 h |
| OSCAR NRT currents | **2026-09-03** | 2026-09-03 | 209.3 h |
| CMEMS NRT wind | 2026-09-10 23:00 | 2026-09-03 | 209.3 h |

**OSCAR sets the date.** Phase 6C-D measured OSCAR's latency at about 2.5 days
from a single-day snapshot, explicitly flagged as an upper bound, not a service
level. Today its newest granule was 8 days old. The reconstruction is therefore
honestly described as *valid 2026-09-03* with an 8.7-day lag, never as the ocean
now. The protocol deliberately does not gate on lag: accuracy was qualified at
each product's own valid date, and lag only affects how recent the result is.

`latest_qualified_field()` (`src/oceanembed/nrt/latest.py`) refuses inference
unless the decision artifact is qualified and every L1–L5 condition holds:
- all seven channels come from exactly the qualified datasets;
- every channel is valid on the common date;
- the same harmonisation is used;
- coverage is within 5 points of the hindcast reference;
- the frozen hashes verify.

It then calls the engine's own `_infer`, the one inference implementation. A
latest field for a hindcast date reproduces that date's hindcast N to within
float32 cache precision, which is tested. The point profile samples the field.

## 12. Was the offline → online recovery path rehearsed?

**Yes — `outputs/phase8b/operational_resilience_test.json`: PASS**, driving the
real app, endpoints, engine and providers in one process, with inference counted
at the engine's single inference method:

| check | result |
|---|---|
| initial latest state available (live) | PASS — valid 2026-09-03 |
| Historical Replay during full outage | PASS |
| historical hazard indicators during outage | PASS |
| stale snapshot displayed, no inference | PASS |
| `LAST SUCCESSFUL QUALIFIED SNAPSHOT — NOT CURRENT` visible | PASS |
| no snapshot → `LATEST QUALIFIED OCEAN STATE CURRENTLY UNAVAILABLE` | PASS |
| **partial outage (NASA only) → no inference** | PASS |
| recovery without restart | PASS |
| complete stack re-qualified after recovery | PASS |
| new frozen-L2 inference after recovery | PASS |

Exactly **2** inferences ran in the whole rehearsal: the initial run and the
recovery run.

## 13. Did incomplete-stack inference remain blocked?

Yes, verified three ways:
- **Live.** The partial outage was refused. It happened at date resolution: OSCAR's catalogue was unreachable, so no common date existed.
- **Fetch-stage refusal**, where some products download and one fails, is pinned by a parametrised test for every single product.
- **Other refusals** are tested too: a wrong valid date, low coverage and an unqualified decision.

Each of these tests replaces inference with an assertion. So "refused" means the model never ran, not merely that a status string said so.

## 14. Shared renderer — reused, not reimplemented

**Yes.** The latest tab adds only the pieces §7.0 permits:
- a status/provenance panel (`LatestQualified.tsx`);
- a withheld-diagnostic field in the contract.

The latest field travels in the identical `oceanembed.field-view.v1` transport (`poc.app.field_payload`) and is adapted by the same `adaptReplay`. It is drawn by the **same** `MapView`, `DepthRenderer`, `Profile` and `DiagnosticMap`, mounted once in `App.tsx`. The same explorer receives either the historical or the latest field.

Tests pin that:
- the set of modules importing three.js is identical to the Phase 7 freeze (`9fb32ba`);
- the latest component imports no renderer;
- a displayed value and a profile value equal the backend value for the same cell and depth.

**All Phase 7B 3D regression tests pass unchanged.**

## 15. 2024 Argo, frozen hashes

**2024 Argo untouched**: no Argo file of any year was opened by any 8B code
(decision records `argo_opened: false`; matched Argo artifacts still end
2023-12-31). **All frozen hashes unchanged**, before and after the hindcast, the
live run and the rehearsal.

---

## 16. Deviations and limitations, stated

1. **No observational validation of the operational stack.** The reference is an
   assimilating reanalysis; 6C-C showed a case where GLORYS-based evidence did
   not transfer to Argo. This is why the ceiling is WITH LIMITATIONS.
2. **The operational mode is measurably worse than historical replay** at
   100–150 m (+3.9 to +4.5 % RMSE, bias +0.1 °C warmer), and D26 does not survive.
3. **Lag is set by OSCAR** and was 8.7 days today, well beyond the 6C-D snapshot.
4. **The live partial-outage refusal happened at date resolution**, not fetch; the
   fetch-stage path is covered by tests, not by the live rehearsal.
5. **SSS compatibility pooled 167 of 168 days** (one day had fewer than 10 common
   cells) and is MARGINAL in the Arabian Sea alone.
6. **Downloads are retrospective** for the hindcast; they support product
   comparison, not claims about original-date availability.
7. **Phase-boundary test changes**, recorded in each file: three 7E/8A reservation
   tests (reserved 8B wording, the `latest_qualified` entry point, app-wide
   latest-inference ban) were narrowed to what stays true after a qualified 8B.
   The durable replacement is stricter in one respect: the qualified tab name is
   never hard-coded in the frontend and can only arrive from the decision
   artifact.
8. **One pre-existing test fails, not caused by 8B:**
   `tests/test_display_bathymetry.py::test_local_bundle_reproducible_and_same_terrain_source`.
   - The ETOPO source and the committed `depth.bin` both still match their recorded SHA-256s.
   - The asset and its builder are untouched since Phase 8A.
   - Regridding today reproduces the NaN pattern exactly, but 4,602 of 24,341 cells differ by at most **1.06 × 10⁻⁵ m**.
   - The test compares raw bytes, so this floating-point-level variation fails it.

   The 3D bathymetry path is frozen by standing instruction, so neither the asset
   nor the test was altered. That decision is left to review.

---

# PHASE 8B GATE

```
Frozen L2 preserved: YES
Complete NRT seven-channel contract: QUALIFIED WITH LIMITATIONS
SSS operating mode: SSS_MULTIOBS_NRT_SAME_DATE (MULTIOBS NRT L4, same valid date, no persistence)
Hindcast-the-NRT: COMPLETED
Latest 15-depth subsurface reconstruction: QUALIFIED WITH LIMITATIONS
Latest D26: NOT QUALIFIED
Latest TCHP: QUALIFIED
Latest Ocean Hazard Indicators: QUALIFIED
Latest tab name: LATEST QUALIFIED OCEAN STATE
Shared Phase-7B 3D renderer reused (no second implementation): YES
Phase 7B 3D regression tests still passing: YES
Offline historical demo: WORKING
Offline latest-state behavior: SAFE
Connection recovery without app restart: PASS
2024 Argo: PROTECTED
Full test suite: 836 passed (698 pytest · 105 Vitest · 33 Playwright); 1 pre-existing failure, not 8B (§16.8)
```

**PHASE 8B COMPLETE — AWAITING REVIEW.**
Do not begin any post-8B research, production-hardening phase, new
cyclone-probability model, architecture change, or protected 2024 Argo
evaluation without separate explicit approval.

**STOP.**
