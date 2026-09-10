# PHASE 7C — D26 / TCHP Diagnostics

Run 2026-09-09 · Full suites **499 pytest · 83 Vitest · 16 Playwright**
(baseline entering the phase: 490 · 83 · 13)
Scope: derived thermal diagnostics and their map layers. **No model change, no
NRT, no event replay, no Argo, no 2024 Argo.**

Frozen core unchanged and re-verified at every engine start:
L2 state-dict `b715bb2b…e728d`, encoder `30cfd2db…db4808`.

---

## 1. Which convention was used, and what supports it

### 1.1 The repository had none

`D26`, `TCHP`, `isotherm` and `heat content` appear in this repository only
inside prior phase reports, and always in a "not started" sentence
(`PHASE6A_REPORT.md`, `PHASE6B_L2_REPORT.md`, `PHASE6B_L3_REPORT.md`,
`PHASE6C_FALLBACK_ARGO_REPORT.md`, `PHASE7_HISTORICAL_REPLAY_REPORT.md`). There
was no existing OceanEmbed or INCOIS convention to inherit, so step (2) of
§7C.1 applied: identify a named published/operational convention and verify its
constants from a primary source.

### 1.2 The equation form is agreed; the constants are not

Every source consulted agrees on the form:

```
D26  = depth of the 26 °C isotherm
TCHP = ρ · Cp · ∫₀^D26 ( T(z) − 26 °C ) dz      [kJ cm⁻²]
```

after Leipper & Volgenau (1972) "hurricane heat potential", implemented
operationally by NOAA/AOML (Shay et al. 2000; Goni et al. 1996).

The **constants** are a different story. What the sources actually say:

| Source consulted | ρ (kg m⁻³) | Cp (J kg⁻¹ K⁻¹) | ρ·Cp (J m⁻³ K⁻¹) | vs adopted |
|---|---|---|---|---|
| Rutgers course note / common secondary text | 1000 | 4186 | 4 186 000 | +2.50 % |
| Frequently-quoted "operational" pair | 1026 | 4178 | 4 286 628 | +4.97 % |
| Another secondary summary | 1025 | 3850 | 3 946 250 | −3.37 % |
| **NOAA/AOML method page** (`aoml.noaa.gov/phod/cyclone/method.php`) | **no constants published** | — | — | — |

AOML's own methodology page describes the altimetry-based synthetic-profile
method (Version 2.1, October 2008 onward) and cites Shay et al. 2000 and Goni
et al. 1996, but **publishes no numerical constants**. The secondary sources
disagree by ≈8 %, and several quote **fresh-water** values (1000 kg m⁻³ with
4186 J kg⁻¹ K⁻¹ is water, not seawater).

That spread is larger than several of the errors this phase set out to measure,
so a convention had to be frozen — and it had to be one that could be verified
rather than inherited.

### 1.3 What was adopted, and how it was verified

Constants come from **TEOS-10** (IOC/SCOR/IAPSO 2010, the international
thermodynamic standard for seawater), through the `gsw` 3.6.23 package already
in `requirements.txt`.

| Constant | Value | Verification |
|---|---|---|
| `cp₀` | **3991.86795711963 J kg⁻¹ K⁻¹** | Not read from a table. TEOS-10 *defines* Conservative Temperature by `h⁰ = cp₀ · Θ`, so `gsw.enthalpy(SA, CT, 0) / CT` must return cp₀ for **every** SA and CT. Evaluated at SA ∈ {33, 35.16504, 36.5} g kg⁻¹ × CT ∈ {5, 26, 30} °C it returns `3991.867957120` in all nine cases. Pinned by `test_cp0_identity_holds_across_salinity_and_temperature`. |
| `ρ₀` | **1023.035344728 kg m⁻³** | `gsw.rho(SA = SSO, CT = 26 °C, p = 0 dbar)`, where `SSO = 35.16504 g kg⁻¹` is the TEOS-10 Standard Ocean Reference Salinity and 26 °C is the threshold that defines the diagnostic itself. Both inputs are fixed by the standard and by D26's own definition; neither is tuned. |
| `ρ₀·cp₀` | **4 083 822.01 J m⁻³ K⁻¹** | product |
| unit factor | `J m⁻² → kJ cm⁻²` = **1 × 10⁻⁷** | 1 J m⁻² = 10⁻³ kJ / 10⁴ cm² |

**Why cp₀ and not an in-situ heat capacity.** GLORYS `thetao` and the OceanEmbed
target are *potential* temperature, and cp₀ is exactly the constant TEOS-10
defines for turning a potential/conservative temperature into heat content.
An in-situ `cp_t_exact` would additionally require subsurface salinity, which
OceanEmbed does not reconstruct — SSS is an input, not an output.

**Reasonableness cross-check** (performed for disclosure, not for tuning):
TEOS-10 in-situ values across representative North Indian Ocean upper-ocean
conditions (SA 33–36 g kg⁻¹, 26–29 °C, 0–100 dbar) give ρ 1020.5–1024.0 and
cp 3993.8–4011.2 → ρ·cp ≈ 4 091 480, which is **0.19 %** from the adopted pair —
closer than any published convention in the table above.

**Consequence to state plainly:** an OceanEmbed TCHP is ≈5 % lower than the same
profile scored with the frequently-quoted 1026 × 4178 pair. That is a
**convention difference, not a skill difference**, and the UI says so on the
diagnostic layer itself.

### 1.4 D26 interpolation and TCHP integration

**D26** — the depth of the **shallowest** downward 26 °C crossing, linearly
interpolated between the two bracketing levels:

```
D26 = z_k + (T(z_k) − 26) · (z_{k+1} − z_k) / (T(z_k) − T(z_{k+1}))
```

Both bracketing levels must be valid and **adjacent**. "Shallowest" is stated
explicitly because the Bay of Bengal supports temperature inversions and barrier
layers, so a profile can cross 26 °C more than once. **No extrapolation ever**:
if no bracketing pair exists inside the valid support, D26 is undefined and a
status is returned instead of a number.

**TCHP** — trapezoidal integration of `(T(z) − 26)` from the top of the profile
down to D26, terminating at D26. The final partial segment `z_k → D26`
contributes `½ · (T(z_k) − 26) · (D26 − z_k)`, which is *exact*, because the
integrand falls linearly to zero at D26 by construction of the interpolation
above. Water above the shallowest available level is treated as isothermal at
that level's value — 0 m thick for the 15-depth stages, 0.494 m for the native
profile, which makes the stage A and stage B integrals start identically.

Every invalid case is a named status, never a silent number:

| Status | D26 | TCHP |
|---|---|---|
| `OK` | value | value |
| `SURFACE_BELOW_26` | undefined | **exactly 0** — no water above 26 °C |
| `NO_CROSSING_IN_SUPPORT` | undefined | undefined |
| `INSUFFICIENT_SUPPORT` | undefined | undefined |
| `NO_VALID_LEVELS` | undefined | undefined |

The `SURFACE_BELOW_26` asymmetry is deliberate: D26 genuinely does not exist
there, but the heat content above the 26 °C isotherm is genuinely zero. It is
verified end to end in the live app (§5).

---

## 2. Pre-registered evaluation population

`outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md` was written and frozen
**before any D26 or TCHP value existed anywhere in this project**. It fixes the
dates, cells, regions, stages, convention, constants, interpolation,
integration, invalid handling and metrics.

| Item | Value |
|---|---|
| Window | the **frozen** `config/data_splits.yaml` test split, `2022-01-01 … 2024-12-15`, `locked: true` — not a new window |
| Rule | every 5th day from the first day of that split |
| Dates | **216**, evaluated **216**, **0 failed** |
| Cells | `ocean_mask ∧ surface_input_valid` on that date, per stage |
| Regions | whole NIO; Arabian Sea and Bay of Bengal from the **frozen** `ml/metrics.py::BASINS` boxes, unchanged |
| Paired samples | ≈2.0 M (D26) and ≈2.2 M (TCHP) |

The stride is a fixed arithmetic rule on a pre-existing frozen split. It is not
conditioned on season, basin, cyclone activity, data quality or any OceanEmbed
output, and it cannot be re-drawn. Feasibility (≈0.73 s/date measured) was
checked before fixing the number, so the stride could not later be relaxed to
fit the compute budget.

This is **historical application validation**, not a pristine never-inspected
test set: the locked split has already been opened for the Phase 6B grid
metrics and the Phase 6C Argo check.

---

## 3. The three-stage experiment

All three stages use the **same dates, the same canonical cells and the same
horizontal treatment**, so horizontal regridding cancels out of every comparison.

| Stage | Vertical support | Source |
|---|---|---|
| **A — native reference** | **36 native GLORYS levels**, 0.494 – 1062.44 m | `data/raw/glorys/<year>/*.nc` via `load_glorys`, then `regrid_horizontal(linear)` retaining all 36 levels |
| **B — 15-depth reference** | the same GLORYS field on the 15 mandated depths | the frozen `temp_<d>m` variables in `model_ready/oceanembed_<year>.zarr` |
| **C — OceanEmbed** | the 15 mandated depths | `replay_field(date).temperature` — the frozen L2, no second inference path |

Stage B is **read** from the frozen store rather than recomputed, because the
Phase 6A.5 pipeline produced `temp_<d>m` by exactly the operation stage B is
defined to be (`interp_depths` on the native grid, *then* `regrid_horizontal`).
Recomputing it could only reproduce those arrays or silently diverge from the
frozen contract. Stage A applies the identical horizontal step and omits only
the vertical reduction — so **A and B differ in exactly one operation**, which
is what makes A vs B a clean measurement of vertical discretization.

---

## 4. Results

### 4.1 D26 (metres)

| Pair | Region | N | MAE | RMSE | bias | r |
|---|---|---|---|---|---|---|
| **A vs B** — discretization | whole NIO | 2 004 939 | **1.26** | 1.98 | +0.76 | 0.997 |
| | Arabian Sea | 918 613 | 1.42 | 2.20 | +0.60 | 0.997 |
| | Bay of Bengal | 729 169 | 0.99 | 1.60 | +0.80 | 0.997 |
| **B vs C** — reconstruction | whole NIO | 1 964 277 | **9.24** | 13.11 | +2.70 | 0.847 |
| | Arabian Sea | 889 884 | 10.66 | 15.22 | +2.71 | 0.822 |
| | Bay of Bengal | 722 868 | 7.51 | 9.70 | +2.93 | 0.857 |
| **A vs C** — total | whole NIO | 1 984 155 | **9.69** | 13.64 | +3.39 | 0.842 |
| | Arabian Sea | 897 757 | 11.05 | 15.73 | +3.19 | 0.816 |
| | Bay of Bengal | 729 937 | 8.02 | 10.29 | +3.70 | 0.850 |

### 4.2 TCHP (kJ cm⁻²)

| Pair | Region | N | MAE | RMSE | bias | r |
|---|---|---|---|---|---|---|
| **A vs B** — discretization | whole NIO | 2 170 505 | **1.70** | 2.19 | +1.61 | 0.9995 |
| | Arabian Sea | 1 039 889 | 1.14 | 1.57 | +0.98 | 0.9996 |
| | Bay of Bengal | 743 605 | 2.37 | 2.73 | +2.34 | 0.9991 |
| **B vs C** — reconstruction | whole NIO | 2 170 505 | **11.47** | 15.83 | +5.80 | 0.925 |
| | Arabian Sea | 1 039 889 | 10.52 | 15.17 | +4.49 | 0.925 |
| | Bay of Bengal | 743 605 | 12.27 | 15.85 | +7.22 | 0.883 |
| **A vs C** — total | whole NIO | 2 190 691 | **12.40** | 16.98 | +7.39 | 0.923 |
| | Arabian Sea | 1 047 886 | 10.99 | 15.82 | +5.43 | 0.923 |
| | Bay of Bengal | 750 763 | 13.75 | 17.55 | +9.56 | 0.876 |

Sources: `outputs/tables/phase7c_d26_tchp_metrics.csv`,
`phase7c_d26_tchp_status_counts.csv`, `phase7c_d26_crossing_disagreement.csv`,
`outputs/phase7c/evaluation_run.json`.

### 4.3 Reading the decomposition

**The mandated 15-depth vertical sampling is cheap; the reconstruction is what
costs.** Discretization contributes MAE 1.26 m of the 9.69 m total D26 error
(13 %) and 1.70 of the 12.40 kJ cm⁻² total TCHP error (14 %). Correlation for
A vs B is 0.997 (D26) and 0.9995 (TCHP) — the 15 mandated depths reproduce the
native-resolution diagnostic almost exactly.

**These are not collapsed into one number and must not be quoted as one.**
Reporting only A vs C would attribute the full 9.69 m to OceanEmbed; reporting
only B vs C would hide the ≈1.3 m the problem statement's own depth list costs.

**Both discretization terms are positive biases** (+0.76 m, +1.61 kJ cm⁻²):
reducing to 15 levels systematically shallows D26 and lowers TCHP slightly,
because linear interpolation across widening level gaps under-resolves the
curvature of the upper thermocline.

**Basin contrast.** D26 reconstruction error is clearly larger in the Arabian
Sea (10.66 m) than the Bay of Bengal (7.51 m), while TCHP error runs the other
way (10.52 vs 12.27 kJ cm⁻², bias +4.49 vs +7.22). The Bay of Bengal's fresher,
more strongly stratified column concentrates more heat above a shallower
isotherm, so a given D26 error converts into a larger TCHP error there. TCHP
error is also the more asymmetric of the two: the whole-NIO bias is +5.80
kJ cm⁻² against an 11.47 MAE, i.e. OceanEmbed reads systematically **warmer /
deeper** than the reference rather than scattering evenly around it.

### 4.4 A limitation this phase discovered — where the isotherm does not exist

Status counts over the full population (2 025 125 / 2 004 939 / 2 245 004 OK for
A / B / C):

| Stage | OK | SURFACE_BELOW_26 | NO_CROSSING_IN_SUPPORT | INSUFFICIENT_SUPPORT |
|---|---|---|---|---|
| A — native | 2 025 125 | 165 566 | 0 | 237 387 |
| B — 15-depth | 2 004 939 | 165 566 | 0 | 257 573 |
| **C — OceanEmbed** | 2 245 004 | 183 074 | 0 | **0** |

**OceanEmbed never returns `INSUFFICIENT_SUPPORT`, because the frozen L2 emits a
finite temperature at all 15 depths wherever the surface inputs are valid — it
has no concept of the seafloor.** The GLORYS references have 237 k–258 k cells
where the water column ends before the isotherm; OceanEmbed reports a D26 in
those same cells anyway. The B vs C disagreement table records **280 727** cells
where C resolved a crossing and B could not.

This is visible at a glance in `outputs/figures/phase7c/01_d26_three_stages.png`:
the shelf regions are hatched in stages A and B and almost fully coloured in C.

Consequences, stated rather than patched:

- Those cells are **excluded from every paired metric above** (a pair needs both
  stages defined), so the reported errors are not contaminated by them — but the
  cells still render on the map.
- A TCHP over 30 m of shelf water has no physical column behind it. The
  diagnostic map says so in text, and the app already carries a real ETOPO
  bathymetry source used by the 3D view and the profile panel.
- **No bathymetric qualification rule was applied.** Masking or flagging the
  diagnostic by ETOPO depth would be new scientific logic that the protocol did
  not pre-register, and applying it now would change the very metrics this
  phase was run to produce. It is recorded here as the first candidate for a
  separately pre-registered rule in Phase 7D, where these diagnostics feed a
  hazard indicator and the distinction starts to matter operationally.

`NO_CROSSING_IN_SUPPORT` is zero everywhere, which is the expected physical
result: no North Indian Ocean column stays above 26 °C to 1000 m.

---

## 5. Diagnostics in the application

D26 and TCHP are now two layers of the existing **Historical Replay** map,
selected from the **existing** Display Layer control — no new dropdown was
added, and the depth selector was not duplicated.

- **Computed once, in the backend**, by `field_diagnostics(view)` from the same
  authoritative `replay_field` result that drives the map, the profile and the
  3D view. The frontend performs **no** diagnostic arithmetic: a second D26
  implementation in TypeScript could drift from the Python one, and then a map
  and a profile could disagree about the same cell. `test_served_values_equal_
  the_diagnostics_module` asserts byte-equality (`atol=0, rtol=0`) between the
  served arrays and the module output.
- **Switching to a diagnostic layer runs no inference** — the values arrive with
  the field already fetched. Pinned by an e2e request counter.
- **Undefined cells are drawn in their own colour *and* hatched**, labelled
  on the map as `no 26 °C crossing — not a value (N cells)`. The double encoding
  is deliberate: colour alone would be ambiguous to a colour-vision-deficient
  reader, and a dark ramp colour could be misread as a low value.
- **Same cartography as the temperature map.** The diagnostic layers use the
  shared ETOPO shaded-land relief, the same land labels, and the same bilinear
  display resampling with coverage feathering, so switching layers changes the
  quantity and not the map. Display resampling never changes a reported value —
  the stat tiles, the profile and the exports read the unmodified array — and
  the no-crossing hatch is deliberately **not** feathered, because a smoothed
  edge would imply a value where there is none.
- **Colorbars report the actual displayed span** (e.g. `4.1 to 131.4 m`,
  `0.0 to 181.0 kJ/cm²`), never a fixed invented range.
- **The convention and its constants are shown on the layer**, including the
  ≈8 % spread across published conventions.
- **D26 and TCHP use distinct ramps** from each other and from the temperature
  ramp, so one map cannot be read as another.
- **The 3D view says why it has no diagnostic stack** instead of faking one:
  these are depth-integrated surfaces, so the volume keeps showing a real
  depth-resolved layer and a note points back to the map.
- **Exports carry the real diagnostics** — `d26`, `tchp` and `d26_status` are in
  the NetCDF with units, flag meanings, and the convention in their attributes.

Verified in a live browser against a real frozen replay, not only in tests. At
15.25 °N 87.75 °E on 2021-06-15 the backend returns D26 = 71.17591719900622 m
and TCHP = 77.6361771728517 kJ cm⁻²; the UI tiles read **71.2 m** and
**77.6 kJ/cm²**.

The `SURFACE_BELOW_26` asymmetry was confirmed on a real cell: at 5 °N 48.75 °E
— the Somali upwelling, in June — the surface is 25.64 °C, so the transport
sends `d26 = null` and `tchp = 0`, the tile reads "No 26 °C crossing", and the
map hatches the region. That hatched patch in
`outputs/phase7c/ui-d26.png` is the June Somali upwelling, which is the correct
physical answer rather than a rendering artefact.

---

## 6. Figures

`outputs/figures/phase7c/` — date and cell chosen **positionally**, never by how
the result looks: the date is the median of the pre-registered population
(index 108 of 216 → 2023-06-25) and the cell is the Phase 7B default demo
location, itself selected by geography in Phase 7B.

| File | Content |
|---|---|
| `01_d26_three_stages.png` | D26 for A / B / C, invalid and no-crossing cells in their own colour |
| `02_tchp_three_stages.png` | TCHP for the same three |
| `03_error_attribution.png` | discretization vs reconstruction vs total, per region |
| `04_representative_profile.png` | the three profiles with the interpolated D26 marked, full column and upper 200 m |

Nothing is hidden: the no-crossing class is drawn, labelled and counted in every
map figure.

---

## 7. Tests

`tests/test_phase7c_diagnostics.py` (40) and `web/src/test/diagnostics.test.ts`
(20) and `web/e2e/diagnostics.spec.ts` (3).

Analytic cases are exact by construction, so a failure is a real behaviour
change and never a tolerance artefact: a linear profile `T = 30 − 0.1 z` must
give D26 = 40 m and a triangular excess integral of exactly 80 °C·m.

Covered: interpolation between bracketing levels; a crossing that lands between
levels rather than snapping to one; exactly-26 at a level and at the surface;
the shallowest of two crossings under an inversion; surface-below-26; no
crossing in support; no valid levels; an invalid top level; **a gap that is
never bridged to reach a deeper crossing**; a gap below the crossing being
harmless; D26 never exceeding the deepest valid level; the analytic TCHP; an
exact isothermal-slab integral; **integration terminating at D26** (two profiles
identical above D26 and wildly different below must give identical TCHP); the
`1e-7` unit conversion; operationally plausible magnitudes; TCHP undefined
wherever D26 is except the surface-below case; 36 native levels supported;
malformed inputs rejected; the TEOS-10 identity for cp₀; ρ₀ at the defining
isotherm; **that the constants are not the fresh-water values**; the protocol
file existing and matching the shipped constants; the served payload equalling
the module output exactly; undefined serialising as `null` and never 0; the
convention being disclosed; NetCDF diagnostics being real; frozen hashes
unchanged; and the executed tables covering every pair, region and quantity.

**A rendering gap was found by review, not by the tests, and fixed.** The first
version of `DiagnosticMap` drew the field correctly but omitted the ETOPO relief
overlay, the land labels and the bilinear display resampling that the
temperature map uses, so the diagnostic layers rendered blocky on a bare dark
background and looked like a different application. The tests passed throughout,
because they assert values, statuses and the hatch class rather than cartography
— a reminder that "the assertions are green" is not the same as "it looks
right". Fixed by sharing the relief loader and mirroring the resampling, with
the hatch left unfeathered on purpose.

**One real bug was found by these tests and fixed.** The first implementation
reported a column whose usable support was cut short by a gap or the seafloor as
`NO_CROSSING_IN_SUPPORT`, merging it with a column that genuinely stayed above
26 °C to the bottom. The protocol distinguishes them, so the code was wrong, not
the protocol: `thermal.py` now separates the two on `usable[:, -1]`. Two other
initial failures were errors in the **test expectations**, not the code — 28 °C
at 50 m over 24 °C at 75 m really does interpolate to 62.5 m, and 2.5 °C·m of
excess really is ≈1.02 kJ cm⁻². Both were corrected in the tests, and the 62.5 m
case was kept as its own regression test against a nearest-level snap.

---

## 8. Discipline and limitations

- **No model change.** L2 was not retrained, fine-tuned or touched; the engine's
  hash verification stayed enabled throughout and both hashes are unchanged.
- **No tuning on results.** The constants, population, stages, interpolation,
  integration and metrics were frozen in the protocol before any value existed,
  and none was revised afterwards.
- **No Argo of any kind was read**, and **2024 Argo remains PROTECTED** — not
  downloaded, opened, collocated or scored. GLORYS reanalysis is not Argo.
- **No data was mutated.** Stage A reads the raw GLORYS archive read-only;
  stage B reads the frozen model-ready store; nothing was written into
  `data/`.
- The shelf limitation in §4.4 is **disclosed, not patched** — no unregistered
  bathymetric rule was introduced.
- The ≈8 % convention spread means OceanEmbed TCHP is not numerically
  interchangeable with an operational TCHP product; the offset is documented in
  the UI and here.
- Deep-ocean skill disclosure is unaffected: these diagnostics live entirely in
  the upper ocean, above a D26 that is typically 20–130 m.
- `playwright.config.ts` now reads an optional `OCEANEMBED_BASE_URL`, defaulting
  unchanged to `http://127.0.0.1:8000`, so a verification server can run beside
  an app already open on 8000. Phase 7B's evidence images in `outputs/phase7b/`
  were restored after the regression run so they continue to reflect the Phase 7B
  build.

---

# PHASE 7C GATE

```
D26: VALIDATED
TCHP: VALIDATED
Convention source documented: YES (form: Leipper & Volgenau 1972 / AOML;
                                   constants: TEOS-10 via gsw, derived and pinned)
Evaluation protocol preregistered: YES (outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md)
Discretization error quantified: YES (D26 MAE 1.26 m · TCHP MAE 1.70 kJ/cm², whole NIO)
Reconstruction contribution quantified: YES (D26 MAE 9.24 m · TCHP MAE 11.47 kJ/cm²)
Total application error: D26 MAE 9.69 m · TCHP MAE 12.40 kJ/cm²
D26/TCHP visible in Historical Replay: YES (map layers, real values, invalid cells distinct)
Frozen L2 preserved: YES
2024 Argo: PROTECTED
Tests passing: 598 / 598  (499 pytest · 83 Vitest · 16 Playwright)
```

**PHASE 7C COMPLETE — AWAITING REVIEW.**
Do not proceed to the next phase until the user explicitly replies "CONTINUE".

---

# PHASE 7C CORRECTIVE / APPLICATION HARDENING ADDENDUM

Run 2026-09-10 · Suites **541 pytest · 102 Vitest · 19 Playwright**
(entering this pass: 499 · 83 · 16)

Everything above this line is the original Phase 7C report and is unchanged,
including §4.4, the limitation section that motivated this pass. That audit
trail is the point: the experiment found something, said so, and did not
retroactively tidy it away.

## A1. What this pass did and did not touch

**The preregistered A/B/C experiment is untouched and was not rerun.** These
whole-NIO results stand exactly as reported above:

| | A vs B | B vs C | A vs C |
|---|---|---|---|
| D26 MAE | 1.26 m | 9.24 m | 9.69 m |
| TCHP MAE | 1.70 kJ/cm² | 11.47 kJ/cm² | 12.40 kJ/cm² |

`phase7c_d26_tchp_metrics.csv`, `phase7c_d26_tchp_status_counts.csv`,
`phase7c_d26_crossing_disagreement.csv`, `outputs/phase7c/evaluation_run.json`,
the four `outputs/figures/phase7c/` figures and
`outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md` were **not** regenerated,
edited or reinterpreted. `TestFrozenPhase7C` asserts each of those six numbers
and the presence of every artifact, and additionally asserts that the frozen
protocol still contains **no** mention of ETOPO — the bathymetric rule added
here is deliberately *not* backdated into the document that describes how the
experiment was actually run.

This pass changes **application presentation and qualification only**. No model,
checkpoint, decoder, preprocessing, input channel, `replay_field` inference path
or raw prediction was modified.

## A2. The limitation, and where it had already been fixed

§4.4 established that the frozen L2 emits all 15 depths wherever surface inputs
are valid and has no concept of the seafloor, so ~7–8 % of its `D26 = OK` cells
claim a crossing below the local seabed.

The **3D depth view had already been corrected** before this pass, using real
ETOPO bathymetry: `scripts/poc/build_bathymetry.py` regrids the same local
ETOPO 2022 source used for the 3D terrain onto the canonical 101×241 grid with
the frozen `regrid_horizontal`, producing
`web/public/assets/bathymetry/depth.bin`; `displayDepthValid` in
`web/src/field/bathymetry.ts` gates the rendered depth footprints and the
profile chart.

**That implementation was treated as the existing tested reference and was not
modified, redesigned or reimplemented.** `web/src/components/DepthRenderer.tsx`,
`LocationProbe.ts`, `geometry.ts`, `bathymetry.ts` and `terrain.ts` carry no
change from this pass. Both pre-existing 3D bathymetry specs
(`e2e/bathymetry.spec.ts`) pass unchanged, as do the probe, prism, terrain and
volume specs.

What was still wrong was everything **outside** the 3D view: the 2D
selected-depth map painted temperature over shelf water at 1000 m, and the D26
and TCHP layers presented below-seafloor results as ordinary values.

## A3. One physical truth, two readers

There is exactly one authoritative physical-depth representation: `depth.bin`.
This pass added a **backend reader** of that same artifact rather than a second
bathymetry system:

- `src/oceanembed/diagnostics/bathymetry.py` loads the identical bytes and
  **verifies them against the `depthSha256` the build script recorded**, so a
  drift fails closed instead of diverging silently.
- Two rules, stated once and kept **orthogonal**:

  ```
  depth_physically_valid = ocean cell AND local_water_depth_m >= requested_depth_m
  display_valid          = surface_input_valid AND depth_physically_valid
  ```

  Physical support is bathymetric existence *alone*. Whether a satellite
  observed the surface on a given day cannot change where the seabed is, so a
  deep cell with a missing input is **still deep water**: its reason for not
  being drawn is MISSING INPUT, never BELOW SEAFLOOR. `display_valid` is the
  composition, and matches the frontend `displayDepthValid` the 3D view, the
  profile and the 2D map all share.
- `test_served_bathymetry_equals_the_frontend_asset` asserts the array the API
  serves is byte-identical to the file the browser loads.

The 2D map does **not** re-derive the seafloor: it calls the same
`displayDepthValid` utility the 3D renderer and the profile panel call. No
scientific equation was reimplemented in React.

**`climatology_defined` is not used anywhere in this path.** It records L0
coefficient availability, not seafloor depth, and the backend module contains no
reference to it.

## A4. Physical support as a separate axis

The frozen `D26Status` enum gains no members and changes no values
(`test_phase7c_statuses_are_untouched`). Physical support is a **second,
independent** status:

| `PhysicalSupport` | Meaning |
|---|---|
| `SUPPORTED` | the required interval fits inside the local water column |
| `INSUFFICIENT_WATER_COLUMN_SUPPORT` | the diagnostic resolved, but below the local seafloor |
| `NOT_APPLICABLE` | the diagnostic does not exist for a non-bathymetric reason |
| `UNVERIFIED` | bathymetry unreadable — fails closed, never assumed supported |

**D26** is qualified, never altered: no clamping to the seabed, no zeroing, no
fabricated crossing. A cell with `D26 = 82 m` over 45 m of water keeps the value
82 m and is labelled `INSUFFICIENT_WATER_COLUMN_SUPPORT`.

**TCHP** integrates from the surface to D26, so its interval is contained in
D26's; it **inherits D26's verdict** rather than getting a second independently
tunable threshold. The integration is never truncated at the seafloor and the
result never relabelled as the same diagnostic.

**`SURFACE_BELOW_26` is preserved exactly** and is never collapsed into a
support failure: D26 stays undefined, TCHP stays exactly 0, and that zero is a
real answer at any water depth, so TCHP there is `SUPPORTED`.

## A5. What changed in the application

**2D selected-depth map.** Cells without a water column at the selected depth
are drawn in a neutral charcoal `UNSUPPORTED_DEPTH_RGB = rgb(48, 52, 58)`
(`#30343a`), chosen to be unlike the cold end of every temperature ramp
(thermal 48,18,59 · viridis 68,1,84 · cividis 0,34,78) and lighter than the
missing-data colour. Land, missing surface input, missing climatology, no
isotherm and no water column remain five distinguishable states. Unsupported
cells are excluded from colour normalisation, so a below-seafloor value cannot
stretch the scale the real cells share, and they are never smoothed into or out
of — a feathered edge would imply a measurement in rock. Measured footprint:

| Depth | Unsupported ocean cells |
|---|---|
| 0 m | 0 |
| 100 m | 1,351 |
| 500 m | 1,747 |
| 1000 m | 2,925 |

**Legend.** The map states `depth not physically available — below local
seafloor (N cells)` with its own swatch, plus a panel note distinguishing it
from land, missing input and missing climatology.

**D26 / TCHP layers.** Three classes, distinguishable by colour *and* by hatch
direction: the value ramp; orange `/` hatch for the existing no-crossing class
(191 cells on 2021-06-15); charcoal `\` hatch for
`INSUFFICIENT_WATER_COLUMN_SUPPORT` (836 cells). The stat tile shows
`Below local seafloor` and still reports the raw value beside it
(`raw 82.3 m — no water column`), so nothing is hidden from the operator.

**Profile.** Already correct — it hid below-seafloor chart points and labelled
the table `Below seafloor — raw output only` using the same utility. Left
untouched, as instructed.

**Bathymetry unavailable** anywhere in this path yields `UNVERIFIED` and no
supported cells, matching the 3D view's existing fail-closed behaviour.

## A6. API and exports (additive only)

No existing field was removed or renamed; `test_existing_fields_are_not_broken`
pins the full prior key set and the `oceanembed.field-view.v1` schema id.

Added to `/api/replay/view`: `diagnostics.d26_physical_status`,
`diagnostics.tchp_physical_status`, `physical_status_labels`,
`physical_status_counts`, and a `bathymetry` block carrying
`local_water_depth_m`, **both** `depth_physically_valid_counts` and
`display_valid_counts` per mandated depth (reported separately, never merged),
the dataset, both checksums, both rules, the sign convention, the separation
note, and the **cell-centre sampling caveat** (a 0.25° cell spanning a shelf
edge is represented by its centre depth alone).

Added to the NetCDF export: `local_water_depth`, `depth_physically_valid`
(101×241×15), `d26_physical_status`, `tchp_physical_status` — all beside the
**unchanged** raw `temperature`, `d26`, `tchp` and `d26_status`, which the tests
assert byte-for-byte against the engine. `depth_physically_valid` carries
bathymetric existence only; `surface_input_valid` is already its own exported
variable, so a consumer composes the two rather than receiving them pre-merged,
and `test_exported_physical_validity_excludes_only_bathymetry` pins that a deep
cell with a missing input stays 1 there.

## A7. Verification

541 pytest · 102 Vitest · 19 Playwright, all passing. New: 42 backend tests
(`tests/test_phase7c_physical_support.py`), 19 frontend
(`web/src/test/physicalSupport.test.ts`), 3 browser
(`web/e2e/physicalSupport.spec.ts`).

Visually confirmed in the running application at 0 / 100 / 300 / 500 / 700 /
1000 m — screenshots `outputs/phase7c/map-*.png`, `ui-d26-qualified.png`,
`ui-tchp-qualified.png`. The footprint contracts progressively with depth in 2D
exactly as it already did in 3D.

Two initial test failures were **my own coordinate assumptions**, not code
faults: latitude ascends in the field and descends down the canvas, so grid cell
(0,0) is the bottom-left pixel, not the top-left. Corrected in the tests.

**A semantic conflation was found at freeze review and corrected.** The first
version of `depth_physically_valid` accepted an optional `surface_input_valid`
argument and ANDed it in, and both call sites passed it — so the exported
variable and the API counts under that name were really *display* validity
wearing a *physical* label. `qualify()` and the 2D map's reason attribution were
already correct, so the fix was narrow: the argument was removed, a separate
`display_valid` composes the two, and the export and counts now report them
independently. `TestPhysicalIsNotDisplay` pins the distinction structurally (the
function cannot accept the argument again), behaviourally (a deep cell with no
surface input stays physically deep, and `qualify` returns `NOT_APPLICABLE`
rather than `INSUFFICIENT_WATER_COLUMN_SUPPORT`), and in the rendered map
(missing input draws the missing colour, not the unsupported one).

## A8. Status

```
Original preregistered A/B/C metrics: FROZEN and unchanged
Phase 7C seafloor-support limitation: disclosed in section 4.4, retained
3D depth validity: ALREADY CORRECT - not modified in this pass
2D selected-depth physical support: WORKING
D26 physical qualification: WORKING (raw value preserved)
TCHP physical qualification: WORKING (inherits D26; never truncated)
SURFACE_BELOW_26 semantics: unchanged (D26 undefined, TCHP = 0)
Profile below-seafloor presentation: already correct, untouched
Raw L2 output: unchanged
Frozen L2 preserved: YES
2024 Argo: PROTECTED
Phase 7D work: NONE
Physical support vs display validity: SEPARATE (missing input never reads as below-seafloor)
Tests passing: 662 / 662  (541 pytest · 102 Vitest · 19 Playwright)
```

**PHASE 7C CORRECTIVE PASS COMPLETE — AWAITING REVIEW.**
Still Phase 7C. Do not proceed to Phase 7D until the user explicitly replies "CONTINUE".
