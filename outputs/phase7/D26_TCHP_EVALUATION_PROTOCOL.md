# D26 / TCHP — Pre-registered Application Evaluation Protocol

**Phase:** 7C · **Status:** FROZEN before any D26 or TCHP value was computed.

At the time this file was written, no D26 value, no TCHP value and no error
metric of any kind had been produced by this project. The repository contained
no D26/TCHP implementation at all (verified: the strings `D26`, `TCHP`,
`isotherm` and `heat content` appear only in prior phase reports, always in the
form "not started"). Every number in `PHASE7C_D26_TCHP_REPORT.md` is produced
by running the procedure fixed below, unchanged.

This is **historical application validation** — an application benchmark over a
pre-registered population. It is **not** a pristine never-inspected test set:
the locked 2022–2024 test split has already been opened once for the Phase 6B
grid metrics and the Phase 6C Argo check.

---

## 1. Evaluation population

### 1.1 Dates

| Item | Value |
|---|---|
| Source of the window | the frozen `config/data_splits.yaml` **test** split — not a new window |
| Test split | `2022-01-01` … `2024-12-15`, `locked: true`, 1080 days |
| Selection rule | **every 5th day, stride-sampled from the first day of the locked test split** |
| Resulting dates | `2022-01-01`, `2022-01-06`, `2022-01-11`, … → **216 dates** |
| Feasibility basis | measured ≈1.5 s per date end-to-end, so the full 216 dates run in ≈5 min; the stride is fixed here so it cannot be relaxed later |

The stride is a fixed arithmetic rule applied to a pre-existing frozen split. It
is not conditioned on season, basin, cyclone activity, data quality, or any
OceanEmbed output. It covers all three test years and all twelve months
approximately uniformly, which is why a stride was chosen over a random sample:
it is reproducible without a seed and cannot be re-drawn.

**Dates are not excluded after the fact.** If a date fails to load it is
reported as a failed date with its reason, not silently dropped.

### 1.2 Grid-cell population

The canonical 0.25° grid, 101 × 241, domain 5–30 °N, 45–105 °E.

A cell enters the population for a given date when **all** of:

1. `ocean_mask` is true for that date (the frozen mask in the model-ready store);
2. `surface_input_valid` is true for that date (the joint seven-channel surface
   validity mask — the same mask that decides where the frozen L2 produces
   output at all);
3. the stage under evaluation returns a **defined** D26 for that cell
   (see §3.4 for what "defined" means and how undefined cases are reported).

Condition 3 is applied **per stage**, and the paired comparisons in §5 use only
cells where **both** stages of that pair are defined. The count of cells lost to
each disagreement class is reported rather than hidden — a cell where one stage
finds a crossing and the other does not is itself a result.

### 1.3 Regions

| Region | Definition |
|---|---|
| **Whole NIO** | every cell satisfying §1.2 |
| **Arabian Sea** | `lat 8.0–25.0 °N, lon 50.0–77.0 °E` |
| **Bay of Bengal** | `lat 5.0–22.0 °N, lon 80.0–100.0 °E` |

The two basin boxes are the **frozen** boxes already defined in
`src/oceanembed/ml/metrics.py::BASINS`, used unchanged by Phase 6B and Phase 6C.
They are not redrawn for Phase 7C. They do not tile the domain and they overlap
neither each other nor the whole-NIO total; whole-NIO is not the sum of the two.

---

## 2. The three stages (§7C.3)

All three stages are evaluated at the **same dates and the same canonical
cells**. The horizontal treatment is identical in all three, so it cancels out
of every comparison; only the vertical treatment differs between A and B, and
only the data source differs between B and C.

| Stage | Vertical support | Source |
|---|---|---|
| **A — native reference** | **36 native GLORYS levels**, 0.494 m … 1062.44 m | `data/raw/glorys/<year>/*.nc` via `oceanembed.data.loaders.load_glorys`, then `regrid_horizontal(..., method="linear")` onto the canonical grid, **retaining all 36 native levels** |
| **B — 15-depth reference** | the **same** GLORYS field reduced to the 15 mandated depths | the existing `temp_<d>m` variables in `data/processed/model_ready/oceanembed_<year>.zarr` |
| **C — OceanEmbed** | the 15 mandated depths | `oceanembed.replay.replay_field(date).temperature` — the authoritative frozen-L2 output, no second inference path |

### 2.1 Why B is read from the model-ready store rather than recomputed

The frozen Phase 6A.5 pipeline produced `temp_<d>m` by exactly the operation
stage B is defined to be: `interp_depths` (linear between bracketing native
levels) applied on the native grid **first**, then `regrid_horizontal` onto the
canonical grid. Recomputing it here would either reproduce those arrays bit for
bit or silently diverge from the frozen contract. Reading the frozen store is
therefore both cheaper and stricter.

Stage A applies `regrid_horizontal` with the identical method and settings, and
skips only the `interp_depths` step. **A and B therefore differ in exactly one
operation: the vertical reduction to 15 levels.** That is the quantity A vs B is
supposed to isolate.

### 2.2 The top of the profile

The frozen preprocessing **clamps** nominal 0 m to the shallowest native GLORYS
level (≈0.494 m); it is not a native 0 m level. Consequently stage B's 0 m value
*is* stage A's 0.494 m value.

To keep the integral consistent between stages, the water above the shallowest
available level is treated as **isothermal at that level's value** in every
stage. For A that is the 0–0.494 m layer; for B and C the nominal 0 m level is
already the top, so nothing is added. This makes A and B start their integrals
identically, so no part of the A-vs-B difference is an artefact of the surface
convention.

---

## 3. D26 — depth of the 26 °C isotherm

### 3.1 Convention

D26 is the depth of the **shallowest** downward crossing of the 26 °C isotherm,
obtained by **linear interpolation between the two bracketing depth levels**.

"Shallowest crossing" is stated explicitly because the Bay of Bengal supports
temperature inversions and barrier layers, so a profile may cross 26 °C more
than once. Taking the shallowest crossing is the operational convention (D26 as
the top of the sub-26 °C water) and makes the result deterministic.

### 3.2 Interpolation

For the first adjacent, both-valid level pair `(z_k, z_{k+1})` with
`T(z_k) ≥ 26 > T(z_{k+1})`:

```
D26 = z_k + (T(z_k) − 26) · (z_{k+1} − z_k) / (T(z_k) − T(z_{k+1}))
```

- Both bracketing levels must be **valid** and **adjacent** in the level list.
- If `T(z_0) == 26` exactly, `D26 = z_0`.
- **No extrapolation, ever.** If no bracketing pair exists within the valid
  support, D26 is undefined and a status is returned (§3.4).

### 3.3 Vertical validity

A level is valid when its temperature is finite. Interpolation uses only
adjacent valid levels. A NaN encountered above the first crossing **ends the
usable support** — the algorithm does not bridge a gap to reach a deeper
crossing, because bridging would be extrapolation through unmeasured water.

### 3.4 Statuses — every invalid case is named, never silently a number

| Status | Meaning | D26 | TCHP |
|---|---|---|---|
| `OK` | a bracketing crossing was found | value (m) | value |
| `SURFACE_BELOW_26` | shallowest valid level is already < 26 °C | undefined | **0.0** by definition (no water above 26 °C) |
| `NO_CROSSING_IN_SUPPORT` | profile stays ≥ 26 °C through the deepest valid level | undefined | undefined |
| `INSUFFICIENT_SUPPORT` | shallowest level invalid, or a gap ends support before a crossing | undefined | undefined |
| `NO_VALID_LEVELS` | no finite temperature anywhere in the column | undefined | undefined |

`SURFACE_BELOW_26` is the one case where an undefined D26 still yields a
**defined and physically meaningful TCHP of exactly zero**: there is no water
warmer than 26 °C, so the heat content above the 26 °C isotherm is zero. It is
reported as its own class and is included in TCHP statistics; it is excluded
from D26 statistics because D26 genuinely does not exist there. This asymmetry
is deliberate and is stated in the report.

Cells below the seafloor, and cells where the reanalysis has no target, appear
as invalid levels and therefore resolve to `INSUFFICIENT_SUPPORT` or
`NO_VALID_LEVELS`. **No status is inferred from `climatology_defined`**, which
records L0 coefficient availability and is not a bathymetry product.

---

## 4. TCHP — tropical cyclone heat potential

### 4.1 Formulation

```
TCHP = ρ₀ · cp₀ · ∫₀^D26 ( T(z) − 26 °C ) dz          [J m⁻²] → [kJ cm⁻²]
```

This is the standard hurricane-heat-potential formulation of Leipper &
Volgenau (1972), as used operationally by NOAA/AOML (Shay et al. 2000; Goni et
al. 1996). Every source consulted agrees on this **form**.

TCHP is defined **only** where D26 is defined (`OK`), plus the
`SURFACE_BELOW_26` case where it is exactly 0. It is never computed to a
non-existent or extrapolated D26.

### 4.2 Constants — verified, not copied

The published sources do **not** agree on the constants, and several quote
fresh-water values. Consulted:

| Source | ρ (kg m⁻³) | cp (J kg⁻¹ K⁻¹) | ρ·cp (J m⁻³ K⁻¹) | vs adopted |
|---|---|---|---|---|
| Rutgers course note / common secondary text | 1000 | 4186 | 4 186 000 | +2.50 % |
| Frequently-quoted "operational" pair | 1026 | 4178 | 4 286 628 | +4.97 % |
| Another secondary summary | 1025 | 3850 | 3 946 250 | −3.37 % |
| NOAA/AOML method page | **publishes no constants** | — | — | — |

The spread across published conventions is ≈8 % — larger than several of the
errors this phase sets out to measure. A convention therefore had to be
**chosen and frozen**, and it had to be one that can be verified from a primary
source rather than inherited from a secondary summary.

**Adopted:** the constants are taken from **TEOS-10**
(IOC/SCOR/IAPSO 2010, the international thermodynamic standard for seawater),
via the `gsw` 3.6.23 package already present in `requirements.txt`.

| Constant | Value | How it was verified |
|---|---|---|
| `cp₀` | **3991.86795711963 J kg⁻¹ K⁻¹** | The TEOS-10 *defined* reference isobaric heat capacity. **Derived from the installed library, not copied:** TEOS-10 defines Conservative Temperature by `h⁰ = cp₀ · Θ`, so `gsw.enthalpy(SA, CT, p=0) / CT` must return cp₀ for **every** SA and CT. It was evaluated at SA ∈ {33, 35.16504, 36.5} g/kg × CT ∈ {5, 26, 30} °C and returned `3991.867957120` in all nine cases. This identity is pinned as a unit test. |
| `ρ₀` | **1023.035344728 kg m⁻³** | `gsw.rho(SA = SSO, CT = 26 °C, p = 0 dbar)`, where `SSO = 35.16504 g/kg` is the TEOS-10 Standard Ocean Reference Salinity and 26 °C is the threshold that defines the diagnostic itself. Both inputs are fixed by the standard and by D26's own definition — neither is tuned. |
| `ρ₀·cp₀` | **4 083 822.01 J m⁻³ K⁻¹** | product of the above |
| Unit conversion | `J m⁻² → kJ cm⁻²`: divide by **1 × 10⁷** | 1 J m⁻² = 10⁻³ kJ / 10⁴ cm² = 10⁻⁷ kJ cm⁻² |

Why cp₀ rather than an in-situ heat capacity: GLORYS `thetao` and the
OceanEmbed target are **potential** temperature, and cp₀ is precisely the
constant TEOS-10 defines for converting a potential/conservative temperature
into heat content. Using an in-situ `cp_t_exact` would additionally require
subsurface salinity, which OceanEmbed does not reconstruct (SSS is an input,
not an output — §8.3 of the master prompt).

Cross-check for reasonableness, not for tuning: TEOS-10 in-situ values over
representative North Indian Ocean upper-ocean conditions (SA 33–36 g/kg,
26–29 °C, 0–100 dbar) give ρ 1020.5–1024.0 and cp 3993.8–4011.2, i.e.
ρ·cp ≈ 4 091 480, **0.19 %** from the adopted pair — closer than any of the
published conventions in the table above.

**Frozen.** These constants are fixed by this document. They will not be
adjusted to improve agreement between any pair of stages. The report will
restate the ≈8 % convention sensitivity so that a reader comparing OceanEmbed
TCHP against an operational product knows the offset is a convention difference
and not a skill difference.

### 4.3 Integration method

Trapezoidal integration of `(T(z) − 26)` over the discrete valid levels, from
the top of the profile down to D26:

1. the isothermal cap above the shallowest level (§2.2) contributes
   `(T(z₀) − 26) · z₀` — zero for stages B and C;
2. each full level pair `(z_j, z_{j+1})` entirely above D26 contributes
   `½ · [ (T(z_j) − 26) + (T(z_{j+1}) − 26) ] · (z_{j+1} − z_j)`;
3. the final partial segment from `z_k` to D26 contributes
   `½ · (T(z_k) − 26) · (D26 − z_k)`, which is exact, because the integrand
   falls linearly to zero at D26 by construction of the D26 interpolation.

Integration **terminates at D26**. It never continues into sub-26 °C water and
never extrapolates below the deepest valid level.

---

## 5. Metrics

For **D26** (in m) and for **TCHP** (in kJ cm⁻²), each computed over the pooled
population of (date, cell) pairs:

- **MAE**, **RMSE**, **bias** (first minus second of the pair), **Pearson
  correlation**, and **valid sample count N**.

Reported for all three pairs — the decomposition is the point of the phase and
the three numbers are never collapsed into one:

| Pair | What it measures |
|---|---|
| **A vs B** | error from the mandated **15-depth vertical sampling** alone |
| **B vs C** | the **OceanEmbed reconstruction** contribution, under identical 15-depth support |
| **A vs C** | total **end-to-end application** error |

Each pair is reported separately for **whole NIO**, **Arabian Sea** and **Bay of
Bengal**. Status-class counts (§3.4) are reported per stage, and the
disagreement classes (one stage `OK`, the other not) are reported per pair.

No metric is reported for a region/pair with `N = 0`; it is shown as
unavailable rather than as a zero.

---

## 6. Discipline

Fixed by this document and not revisable after results are seen:

- L2 is **not** retrained, fine-tuned or modified; Phase 7C changes no model.
- The frozen checkpoint, encoder, scalers and L0 climatology are untouched, and
  the engine's own hash verification is left enabled.
- D26/TCHP results **must not** be used to tune the model, alter the input
  contract, or re-select any earlier decision.
- **2024 Argo is not downloaded, opened, collocated or scored.** This phase
  reads no Argo data at all. GLORYS reanalysis is not Argo.
- The population, stages, conventions, constants, interpolation, integration and
  metrics above are frozen. If an implementation **bug** is found, it may be
  corrected only with the correction documented in the report, a regression test
  added, and the corrected run reported in full — never as a silent re-run and
  never as a choice between two computed outcomes.

---

*Written before execution. Nothing in this file was informed by a computed D26
or TCHP value, because none existed when it was written.*
