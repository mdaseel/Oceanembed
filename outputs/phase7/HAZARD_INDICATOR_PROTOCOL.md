# Phase 7D — Ocean Hazard Indicator Protocol

**Status:** FROZEN before any threshold value was computed and before any
event label was inspected.

At the time this file was written, no reference percentile had been calculated,
no category boundary existed as a number, and no cell anywhere had been assigned
a hazard level. The rule below was fixed first; the numbers it produces were
generated afterwards by executing it unchanged.

---

## 1. Indicator

**Exact name:** *Ocean Thermal Support for Cyclone Intensification*

**What it is:** a transparent, historically-derived description of how much
upper-ocean heat the reconstructed ocean state offers to a tropical cyclone at a
given place and date.

**What it is not, stated in the UI verbatim:**

> This indicator describes the oceanic thermal environment relevant to cyclone
> intensification. It does not predict cyclone genesis, track, landfall,
> category, or exact future intensity.

**No numeric cyclone probability is displayed, in any form.** No percentage, no
odds, no "chance of". Not authorised in any phase of this document.

## 2. Input quantities

**The category is a function of exactly one quantity: TCHP.**

| Role | Quantity | Why |
|---|---|---|
| **Categorising** | **TCHP** (kJ cm⁻²) | The standard operational measure of the heat available to a cyclone, validated in Phase 7C. It already integrates both the depth of the 26 °C isotherm and the thermal structure above it, so it captures D26 rather than needing to be combined with it. |
| Supporting (displayed, not categorising) | D26 (m) | Shown so the user can see what the integral was taken over. |
| Supporting (displayed, not categorising) | Temperature anomaly at 100 m (°C) | The mandated depth with the strongest measured L2 skill (Phase 6B: +33.5 % over L0). Named *Subsurface Thermal Anomaly* in the UI. |
| Supporting (displayed, not categorising) | Local water depth (m), physical-support status | So a reader can see the diagnostic stands on a real water column. |

**Why a single-variable rule.** Combining D26, TCHP and an anomaly into a
multi-variable score would require weights, and no published source gives
weights for this basin. Inventing them would be exactly the kind of
unfalsifiable tuning this protocol exists to prevent. TCHP alone is the quantity
the operational literature actually uses for this purpose, so the category rests
on it and the other quantities are shown for explanation only.

## 3. Threshold basis — a pre-specified distributional rule

The category boundaries are **percentiles of OceanEmbed's own TCHP distribution
over a reference period fixed in advance**, not numbers chosen by hand.

| Element | Value |
|---|---|
| Reference period | the **TRAIN** split only, `2015-01-01` … `2020-12-31` |
| Sampling | every 5th day of that period (≈439 dates), the same stride rule Phase 7C used |
| Region | the PoC domain, 5–30 °N / 45–105 °E — one distribution, not per basin |
| Season | all days; no seasonal restriction |
| Population | cells where TCHP is defined **and** physically supported (Phase 7C corrective pass), i.e. exactly the cells where a category will ever be shown |
| Source of values | `replay_field(date)` → frozen Phase 7C `d26_tchp` — the model's own output, not GLORYS |
| Boundaries | **p50 → MODERATE, p75 → ELEVATED, p90 → HIGH** |

```
TCHP <  p50   ->  LOW
p50  <= TCHP <  p75   ->  MODERATE
p75  <= TCHP <  p90   ->  ELEVATED
TCHP >= p90   ->  HIGH
```

**Why the train split.** The event is in the locked test split. Deriving
thresholds from the train period keeps test information out of the category
definition entirely, so the labels shown for Mocha cannot have been influenced by
Mocha.

**Why the model's own distribution, not GLORYS.** Phase 7C measured a real
positive TCHP bias in the reconstruction (whole-NIO B vs C bias
+5.80 kJ cm⁻²). Percentiles taken from the model's own history cancel that
offset out of the category assignment; percentiles taken from GLORYS would push
every OceanEmbed label systematically upward. This is a deliberate choice to
avoid importing a known bias into a hazard label.

**Why one whole-domain distribution and not per-basin.** A given TCHP supports
intensification the same way in the Arabian Sea as in the Bay of Bengal.
Per-basin percentiles would relabel the same physical heat differently on either
side of India and would hide the real basin contrast Phase 7C measured. The
consequence — that the Bay of Bengal will tend to occupy higher categories — is
a genuine physical signal and will be reported, not corrected away.

**Frozen.** These boundaries are fixed by executing the rule above once. They
will not be moved because the selected event looks better under a different cut,
and they will not be re-derived on a different period after the labels are seen.

## 4. Literature cross-check — disclosure, not calibration

The operational literature associates TCHP of roughly **50 kJ cm⁻²** with
conditions supportive of intensification (Shay et al. 2000; Mainelli et al.
2008; AOML operational practice), though published work also shows the threshold
is regionally dependent — approximately 40–60 kJ cm⁻² near 5–10 °N and
80–100 kJ cm⁻² near 15–20 °N in the western North Pacific.

Because no single published value is defensible for this basin, that anchor is
**not** used to set any boundary. It will instead be reported as a cross-check:
the report will state where ~50 kJ cm⁻² falls within the derived distribution.

**If the anchor falls below p50** — that is, if most of the North Indian Ocean
exceeds the classical threshold for most of the year — the report and the UI
must say so plainly, and must describe the categories as *relative thermal
support within this basin*, not as a binary sufficiency test. A `LOW` label in a
basin that is warm nearly everywhere does not mean "not enough heat for a
cyclone"; it means "little relative to this basin's own history".

Also disclosed wherever a TCHP number appears: OceanEmbed's TCHP is ≈5 % below
the same profile scored with the frequently-quoted 1026 × 4178 constants, a
convention difference fixed in Phase 7C and not a skill difference.

## 5. Reconstruction uncertainty must travel with the label

Phase 7C measured, on the locked test split, a whole-NIO TCHP reconstruction
error of **MAE 11.47 kJ cm⁻², RMSE 15.83, bias +5.80** (B vs C, i.e. against the
same-15-depth reference).

If a category is narrower than that error, a single-cell label is uncertain by
of order one category. **The UI must therefore display the measured error
alongside the category, and must state that adjacent categories are not
distinguishable at a single cell.** The category is a decision-support summary
of a reconstruction, not a measurement.

Deep-ocean skill is not a limiting factor here: TCHP integrates from the surface
to D26, typically 20–130 m, which lies in the depth range where L2 has its
strongest measured skill. The 500–1000 m weak-anomaly-skill disclosure does not
apply to this indicator and must not be implied to.

## 6. Invalid and unsupported cases

A hazard category is shown **only** where TCHP is both defined and physically
supported. Everything else is `NOT CATEGORIZED`, with the reason named:

| Condition | Displayed |
|---|---|
| TCHP defined and `PhysicalSupport.SUPPORTED` | the category |
| `SURFACE_BELOW_26` (whole column below 26 °C, TCHP = 0) | `LOW` — a real zero-heat answer, categorised normally |
| `INSUFFICIENT_WATER_COLUMN_SUPPORT` (below local seafloor) | `NOT CATEGORIZED — no water column` |
| `NO_CROSSING_IN_SUPPORT`, `INSUFFICIENT_SUPPORT`, `NO_VALID_LEVELS` | `NOT CATEGORIZED — diagnostic unavailable` |
| bathymetry `UNVERIFIED` | `NOT CATEGORIZED — physical support unverified` |
| land / surface input missing | no cell drawn at all |

**An invalid D26 or TCHP never silently produces a hazard category.** These
reasons are kept distinct from one another — in particular "no water column" is
never merged with "no 26 °C crossing", and neither is ever merged with a real
`LOW`.

`SURFACE_BELOW_26` is categorised rather than withheld because TCHP = 0 exactly
is a genuine measurement of the heat available above 26 °C, and zero heat is
genuinely the lowest support there can be.

## 7. Explainability — "Why this level?"

Every categorised cell must expose, on demand, the actual numbers behind it:

- the TCHP value and the boundary it fell on (e.g. `78.4 kJ/cm² — above the
  ELEVATED boundary of 74.1, below HIGH at 96.3`)
- D26 in metres, and the local water depth it sits within
- the 100 m temperature anomaly
- the measured Phase 7C reconstruction error for TCHP
- the frozen model hash and the date
- the verbatim non-prediction statement from §1

The panel must derive from the **same** `replay_field()` and Phase 7C diagnostic
outputs the map and profile use. No second inference path, no recomputation in
the frontend.

## 8. Cold wake and thermal recovery

For the selected event window, before/after change may be shown for SST
(nominal 0 m), subsurface temperature, D26 and TCHP, computed as differences
between **independent daily** `replay_field` results.

This is a difference between two reconstructions, never a modelled evolution.
The wording must not imply the system propagated anything forward in time.

**Marine heatwave terminology is forbidden here.** A single warm anomaly is not
a marine heatwave; no recognised duration/percentile definition (e.g. Hobday et
al.) is implemented in this phase, so the term is not used.

## 9. Discipline

Fixed by this document and not revisable after labels are seen:

- Thresholds come from the rule in §3, executed once on the train split. They
  are not tuned to the event.
- If the derived boundaries turn out not to separate the event usefully, that
  is reported as a result — the rule is not swapped for one that looks better.
- If no defensible category can be assigned to a cell, `NOT CATEGORIZED` is
  displayed rather than a forced label.
- No numeric cyclone probability, ever.
- The indicator is HISTORICAL in Phase 7D. It is not connected to live or NRT
  data, and no NRT/live-fetch code is introduced.
- L2, its checkpoint, the scalers, the L0 climatology, the Phase 7C D26/TCHP
  equations and constants, and the frozen Phase 7C evaluation artifacts are all
  unchanged.
- **2024 Argo remains PROTECTED.** No Argo data is read.

---

*Written before execution. No threshold number and no event label existed when
this file was written.*

---

## Post-freeze corrections (2026-09-10, freeze review)

The original text above is left **unaltered**. These are corrections to
*wording and claims only*. **No rule, population, boundary, quantity or
threshold changed**, and nothing here was informed by an event label — the
frozen boundaries remain p50 55.70, p75 79.10, p90 96.94 kJ cm⁻², derived
exactly as §3 specifies.

**C1 — "cancel that offset out" (§3) overstated what the choice does.**

§3 says percentiles from the model's own history "cancel that offset out of the
category assignment". That is too strong. Using OceanEmbed's own train-period
TCHP distribution makes the percentile categories **internally consistent with
the model's output distribution**. It does **not** correct the Phase 7C TCHP
bias at individual cells; the +5.80 kJ cm⁻² offset is still present in every
value displayed. What the choice avoids is applying thresholds derived from a
reference distribution to a systematically shifted prediction distribution. The
bias is disclosed, not removed. The rule — use the model's own train-period
distribution — is unchanged.

**C2 — the ~50 kJ cm⁻² anchor needs its convention caveat (§4).**

§4 correctly makes the anchor disclosure-only. It should also state that a TCHP
value depends on the adopted ρ·Cp convention, that published conventions span
≈8 %, and that OceanEmbed's TEOS-10 constants run ≈5 % below the frequently
quoted 1026 × 4178 pair. The comparison against the anchor is therefore an
**approximate consistency cross-check on order of magnitude and rough position,
not a numerical calibration**, and the measured 44.3rd percentile must not be
read as precise agreement between two independently derived thresholds.

**C3 — category labelling in the UI.**

Categories are displayed as **THERMAL SUPPORT** levels, so `HIGH` cannot be read
as "high cyclone risk". It means high reconstructed upper-ocean heat under the
frozen TCHP categorisation, and nothing more. The verbatim non-prediction
statement in §1 is unchanged and still shown.
