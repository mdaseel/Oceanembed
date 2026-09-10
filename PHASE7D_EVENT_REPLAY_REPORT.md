# PHASE 7D — Historical Event Replay + Ocean Hazard Indicators

Run 2026-09-10 · Suites **575 pytest · 102 Vitest · 23 Playwright**
(entering the phase: 541 · 102 · 19)
Scope: one historical event, and a historical decision-support indicator built
on the Phase 7C diagnostics. **No NRT, no live data, no model change, no Argo,
no 2024 Argo.**

Frozen core unchanged and re-verified at every engine start:
L2 state-dict `b715bb2b…e728d`, encoder `30cfd2db…db4808`.

---

## 1. The event, and how it was chosen

`outputs/phase7/EVENT_SELECTION.md` was written **before any event-specific
OceanEmbed output existed**. The only repository query made beforehand was a
data-availability check — which dates exist, and how many cells carry valid
surface input — never a prediction or an error.

**Rule, fixed first:**

> The single most intense tropical cyclone over the Bay of Bengal or Arabian
> Sea whose full window lies inside the **locked test split**
> (`2022-01-01` … `2024-12-15`), ranked by IMD best-track peak 3-minute
> sustained wind, tie-broken on minimum central pressure, requiring a complete
> surface-input record for every day of the window.

Every clause is external. The test-split restriction is a deliberate
strengthening beyond the master prompt (which permits any 2015–2024 date): it
makes the reconstruction shown here **out of sample** — no day of it was seen in
training, scaler fitting or climatology fitting.

**The ranking left no discretion:**

| Season | Strongest NIO system | IMD peak wind | Min. pressure |
|---|---|---|---|
| 2022 | Asani | 100 km/h | 982 hPa |
| **2023** | **MOCHA** | **215 km/h** | **938 hPa** |
| 2024 | Remal | 110 km/h | 978 hPa |

**Selected: Extremely Severe Cyclonic Storm Mocha, May 2023, Bay of Bengal** —
roughly double the peak wind of either neighbouring season's strongest system,
and 40 hPa deeper. Landfall just north of Sittwe, Myanmar on 14 May 2023.

**Independent confirmation after the fact:** the bundled IBTrACS track carries
IMD peak wind **115 kt** and minimum pressure **938.0 hPa** — the pressure
matches the externally published figure exactly, and 115 kt ≈ 213 km/h against
the quoted 215 km/h. The selection research and the data agree without tuning.

**On wind-averaging conventions.** Intensity is reported here on **one** scale
at a time, with the averaging period named. IMD/RSMC New Delhi, the WMO agency
of record for this basin, uses **3-minute** sustained winds: 115 kt / ~215 km/h.
The same IBTrACS record separately carries the JTWC **1-minute** value, which
peaks at 145 kt. Those are different conventions for the same storm and are not
interchangeable, so no Saffir–Simpson category label is applied anywhere in this
phase. An earlier draft of this report described Mocha as "Category-5
equivalent" beside the IMD figure; although the 1-minute value in the bundled
track would support that label on its own scale, mixing the two conventions in
one sentence invites an argument that adds nothing. The pressure and the two
clearly-labelled wind figures communicate the intensity without it.

**Window: `2023-05-05` … `2023-05-22`, 18 consecutive days**, segmented
pre-event → approach → event → wake → recovery. All 18 days verified present in
the frozen store with a stable 11,268-cell input record.

**Every day is an independent `replay_field(date)` call.** No temporal model, no
sequence input, no state carried between days. L3 remains rejected and unused,
and a test asserts that repeating a date reproduces it bit-for-bit while
different dates genuinely differ.

## 2. Track data — external, bundled, and kept out of the science

`scripts/poc/build_event_track.py` fetches **IBTrACS v04r01** (North Indian
basin, NOAA NCEI) once at build time, subsets it to this one storm, records the
27.9 MB source's SHA-256, and writes an 11 KB local asset. 51 track points,
2023-05-08 18:00 → 2023-05-15 00:00.

- Citation: Knapp et al. (2010), *BAMS* 91, 363–376; data doi:10.25921/82ty-9e16
- Agency of record: IMD / RSMC New Delhi, carried through IBTrACS
- Licence: US Government work, public domain; attribution shown in the UI

The running application performs **no network access** — a test asserts the API
module contains no HTTP client at all. The track is **static geographic
context**: it is not a model input, not an OceanEmbed output, and it never
enters inference, the diagnostics, or any mask. Tests pin that labelling and
that every point lies inside the domain.

---

## 3. The hazard indicator, and where its numbers come from

`outputs/phase7/HAZARD_INDICATOR_PROTOCOL.md` was frozen **before any threshold
number existed and before any label was seen**.

**Indicator:** *Ocean Thermal Support for Cyclone Intensification*, displayed as
`LOW` / `MODERATE` / `ELEVATED` / `HIGH` / `NOT CATEGORIZED`.

**No numeric cyclone probability exists anywhere** — not in the module, not in
the payload, not in the UI. Two tests enforce this structurally: one walks the
whole JSON response asserting no key or value carries one, the other asserts the
word appears in the source only inside the sentence that forbids it.

### 3.1 One quantity categorises

The category is a function of **TCHP alone**. D26, the 100 m anomaly and the
local water depth are displayed for explanation but do not categorise.

Combining several quantities would need weights, and no published source gives
weights for this basin; inventing them is exactly the unfalsifiable tuning the
protocol exists to prevent. TCHP is the quantity the operational literature
actually uses for this purpose, and it already integrates D26 and the thermal
structure above it.

### 3.2 Thresholds from a pre-specified distributional rule

| Element | Value |
|---|---|
| Reference period | **TRAIN split only**, 2015-01-01 … 2020-12-31 |
| Sampling | every 5th day → **439 dates, 0 failures** |
| Population | TCHP defined **and** physically supported — exactly the cells that can ever carry a category |
| Samples | **4,552,444** |
| Source | OceanEmbed's own TCHP, not GLORYS |

**Frozen boundaries** (`outputs/phase7/HAZARD_THRESHOLDS.json`):

```
LOW       TCHP <  55.70 kJ/cm²
MODERATE  TCHP >= 55.70
ELEVATED  TCHP >= 79.10
HIGH      TCHP >= 96.94
```

Two choices were made in advance and are worth stating precisely.

**The train split** keeps test-period information out of the category definition
entirely, so the labels shown for Mocha cannot have been influenced by Mocha.

**The model's own distribution** rather than GLORYS makes the percentile
categories *internally consistent with the model's output distribution*. It does
**not** correct the Phase 7C TCHP bias at individual cells — that +5.80 kJ/cm²
offset is still present in every value shown. What the choice avoids is applying
percentile thresholds derived from a reference distribution to a systematically
shifted prediction distribution, which would have pushed every OceanEmbed label
upward relative to the population the thresholds were meant to describe. The
bias is disclosed, not removed.

### 3.3 Literature cross-check — the pre-registered disclosure

The protocol required reporting where the classical operational anchor of
**≈50 kJ/cm²** (Shay et al. 2000; Mainelli et al. 2008; AOML practice) falls in
the derived distribution, and required specific honest wording if it fell below
p50.

**It falls at the 44.3rd percentile** — in the lower-middle of the distribution,
somewhat below the MODERATE boundary of 55.70. So `LOW` corresponds roughly to
"below the classical sufficiency threshold" and `MODERATE` and above to "at or
above it". The anchor was **not** used to set any boundary.

**This is an approximate consistency cross-check, not a numerical calibration**,
and the reason matters: Phase 7C established that a TCHP number depends on the
adopted ρ·Cp convention, and that published conventions span ≈8 %. OceanEmbed's
TCHP uses TEOS-10 constants and runs ≈5 % below the same profile scored with the
frequently-quoted 1026 × 4178 pair. The published ~50 kJ/cm² anchor does not
always state which constants produced it. Comparing our 55.70 against it is
therefore a sanity check on the order of magnitude and rough position, and the
44.3rd percentile should not be read as a precise agreement between two
independently-derived thresholds.

Distribution context: min 0.0, p25 25.3, mean 53.3, p95 106.6, max 227.8
kJ/cm². 44.3 % of samples fall below 50 kJ/cm².

### 3.4 Uncertainty travels with the label

Phase 7C measured TCHP reconstruction error of **MAE 11.47, RMSE 15.83, bias
+5.80 kJ/cm²**. The MODERATE→ELEVATED gap is 23.4 and ELEVATED→HIGH is 17.8, so
the error is roughly half a category. The UI therefore displays the measured
error beside every category and states that **adjacent categories are not
distinguishable at a single cell**. The category is a decision-support summary
of a reconstruction, not a measurement.

Deep-ocean skill is not a limiting factor: TCHP integrates 0 → D26, typically
20–130 m, in the range where L2 has its strongest measured skill. The 500–1000 m
disclosure does not apply and is not implied.

### 3.5 A category never appears without support beneath it

| Condition | Displayed |
|---|---|
| TCHP defined and physically supported | the category |
| `SURFACE_BELOW_26` (TCHP = 0 exactly) | `LOW` — a real zero-heat answer |
| below local seafloor | `NOT CATEGORIZED — no water column` |
| diagnostic invalid | `NOT CATEGORIZED — diagnostic unavailable` |
| bathymetry unverified | `NOT CATEGORIZED — physical support unverified` |
| thresholds missing | no indicator at all, with an explanation |

The reasons stay distinct — "no water column" is never merged with "no 26 °C
crossing", and neither is ever merged with a real `LOW`. A browser test asserts
the central invariant directly: across all 24,341 cells on the peak day,
**zero** cells carry a category without `PhysicalSupport.SUPPORTED` beneath
them. This is the Phase 7C corrective work carrying straight through.

---

## 4. What the event shows

### 4.1 Thermal support on peak-intensity day

On **2023-05-13**, over the 11,268 input-valid cells:

| Category | Cells |
|---|---|
| LOW | 1,861 |
| MODERATE | 3,701 |
| ELEVATED | 2,093 |
| **HIGH** | **2,847** |
| NOT CATEGORIZED | 766 |

`outputs/phase7d/hazard-map.png` shows the observed IBTrACS track running
**through and along the eastern edge of the large HIGH region in the central
Bay of Bengal**, with the shelf correctly uncategorised. Stated carefully: this
is the thermal state the storm encountered, reconstructed from surface
observations only. It is not a claim that OceanEmbed predicted the track, and
the co-location of an intense cyclone with high upper-ocean heat content is
consistent with — not evidence for — a causal claim this system does not make.

### 4.2 Cold wake and thermal recovery

Averaged over the 1,521 cells within 1.5° of the observed track, from 18
independent daily reconstructions:

| | pre-event (05 May) | peak (13 May) | minimum | 22 May |
|---|---|---|---|---|
| Nominal 0 m | 30.73 °C | 30.39 | **29.52** (15 May) | 30.00 |
| D26 | 71.3 m | 66.7 | **66.1** (14 May) | 69.0 |
| TCHP | 88.9 kJ/cm² | 79.2 | **67.5** (15 May) | 78.7 |

The reconstructed sequence shows a cooling, D26-shoaling and TCHP-reduction
pattern **consistent with a cyclone cold-wake response**, followed by partial
thermal recovery. Stated at that strength deliberately: these are 18 independent
daily reconstructions averaged over 1,521 cells, differenced afterwards. They
describe what the reconstruction shows, not a dynamical attribution of the
cooling to the storm.

It is equally **honest about what did not happen**: the surface cools ~1.2 °C
into landfall and recovers only ~0.5 °C; TCHP falls ~21 kJ/cm² and is still
~10 kJ/cm² below its pre-event value eight days later. The upper ocean does not
return to its pre-storm state within the window. Nothing is smoothed or
extrapolated to make the recovery look complete.

**This is a difference between independent reconstructions, never a modelled
evolution.** The UI says so, and a test asserts the wording.

**Marine-heatwave terminology is not used.** No recognised duration/percentile
definition is implemented in this phase, so a warm anomaly is not given that
name — the UI states this explicitly.

---

## 5. The application

A third route, **Ocean Hazard Indicators**, sits beside Historical Replay and
the 3D Depth View. It is **historical only** — not connected to live or NRT
data, and no NRT/live-fetch code was introduced (tests assert the absence of
`copernicusmarine`, `earthaccess`, `nrt` and any HTTP client in the served
modules).

It shows, for the selected cell and date: the category; *Upper-Ocean Heat
Reservoir* (TCHP); D26; *Subsurface Thermal Anomaly* (100 m); a **Why this
level?** panel; the categorical map with the observed track; and the cold-wake
series.

**"Why this level?"** exposes the actual supporting numbers — the TCHP value and
the exact boundary it crossed, the frozen boundaries and where they came from,
D26 within the local water depth, the 100 m anomaly, the measured
reconstruction error, and the model hash — plus the verbatim statement:

> This indicator describes the oceanic thermal environment relevant to cyclone
> intensification. It does not predict cyclone genesis, track, landfall,
> category, or exact future intensity.

Everything derives from the same `replay_field()` and Phase 7C diagnostics used
by the map and profile. **No second inference path**, and no categorisation or
threshold anywhere in the frontend — a test asserts the served categories equal
the backend module's output exactly.

---

## 6. Tests

`tests/test_phase7d_hazard.py` (34) and `web/e2e/hazard.spec.ts` (4).

Covered: the event was pre-registered with an external rule and no performance
language; the protocol fixes the rule; **the protocol contains none of the
derived boundary numbers**, proving it was not written backwards from results;
thresholds came from the train split with no test date contributing; the
literature anchor is disclosure-only; boundary inclusivity at each cut;
below-seafloor, unverified-bathymetry and invalid-diagnostic cells are never
categorised; `SURFACE_BELOW_26` is categorised `LOW` rather than withheld;
missing thresholds yield no labels at all; the not-categorised reasons stay
distinct; the explanation quotes the real boundary; no probability is produced
or served; the bundled track matches the pre-registered event and the external
intensity record; the track is labelled as context; all points lie in-domain;
categories on a real field are a pure function of TCHP where usable; the 18
window dates are independent and reproducible; the served categories equal the
backend module; the event endpoints report the pre-registered window; no NRT or
network code; no Argo; frozen Phase 7C metrics and hashes unchanged.

**Two initial failures were my own test being too crude**, not code faults: it
banned the substring "probability", which legitimately appears in the sentence
*forbidding* one. Replaced with precise assertions — no key or value may carry a
probability, and every textual mention must be a negation.

**Three flaws were caught by looking at the running application**, not by
tests — worth recording, because the assertions were green throughout:

1. **The legend counted land.** `NOT CATEGORIZED` was summed over the whole
   array, so it read 13,839 when only 766 ocean cells genuinely lack support.
   Counts are now taken over the input-valid population and sum exactly to it.
2. **An error message blamed the wrong cause.** When the served payload carried
   no hazard block at all — an older backend still running — the tab claimed
   "the frozen hazard thresholds are not present", which was false and sent the
   reader to rebuild a file that was fine. The two causes are now separated: a
   missing hazard block reports a stale backend, and only a genuine load failure
   mentions the thresholds.
3. **The track was drawn over dates it never crossed.** The Mocha track was
   rendered on whatever date was selected, so a 2023 storm appeared over a 2021
   ocean state, implying a relationship that does not exist. The track is now
   drawn **only** inside the event window; outside it the map says why and
   offers to jump to peak intensity. Pinned by a browser test.

---

## 7. Discipline

- The event was selected by an external rule before any event-specific output
  existed; the window was not shifted afterwards.
- The thresholds were derived once, from the train split, by executing a rule
  frozen beforehand. They were not tuned to Mocha, and the protocol was not
  edited after the numbers appeared.
- Every date is an independent reconstruction. No temporal model, no forecast.
- No numeric cyclone probability, anywhere.
- Historical only — no NRT, no live fetch, no Phase 8A scaffolding.
- L2, its checkpoint, the scalers, the L0 climatology, the Phase 7C D26/TCHP
  equations and constants, and every frozen Phase 7C artifact are unchanged.
- **2024 Argo remains PROTECTED.** This phase reads no Argo data at all.
- Phase 7B evidence images restored byte-identical after each regression run.

**Known limitations, stated rather than smoothed:** the categories are relative
to this basin's own history, so a `LOW` in a persistently warm basin does not
mean "insufficient heat for a cyclone"; the single-variable rule ignores
salinity stratification and barrier layers, which matter in the Bay of Bengal
and which OceanEmbed cannot see because it does not reconstruct salinity; the
one-degree-of-freedom threshold set is a defensible starting point, not a
validated hazard model; and the reconstruction error is about half a category
wide.

---

## 8. Freeze-review hardening pass (2026-09-10)

A freeze review raised six presentation and claims issues. All were accepted.
**No scientific value changed**: the event, window, 439 threshold dates, TCHP
distribution, p50/p75/p90, Phase 7C artifacts, L2 and the Argo protection are
all exactly as before. These were corrections to what the work *claims*, not to
what it computed.

**H1 — the cold-wake chart had a genuine unit error (the blocker).** Three
quantities in three units were plotted on two axes: nominal 0 m on a °C axis,
and **both** D26 (metres) and TCHP (kJ/cm²) on a single right-hand axis I had
labelled with the composite `kJ/cm² · m`. That is not a unit. It passed
unnoticed because the two ranges overlap numerically in this window — D26
66–71 m against TCHP 67–89 kJ/cm² — so the lines looked plausible while sharing
a meaningless axis. Replaced with **three vertically stacked panels sharing one
date axis**, each carrying its own unit, with the peak-intensity marker spanning
all three. An e2e test now asserts the three axis titles are exactly
`Nominal 0 m (°C)`, `D26 (m)`, `TCHP (kJ/cm²)` and that no axis title contains a
composite unit. Underlying values are untouched.

**H2 — "cancels out the +5.80 bias" overstated the method.** Corrected in §3.2:
using the model's own train-period distribution makes the percentile categories
internally consistent with the model's output distribution; it does **not**
correct the bias at individual cells. The offset is present in every displayed
value and is disclosed, not removed.

**H3 — the ~50 kJ/cm² anchor needed its convention caveat.** Corrected in §3.3:
because published TCHP conventions differ by ≈8 % and OceanEmbed's TEOS-10
constants run ≈5 % below the frequently-quoted pair, the comparison is an
approximate consistency cross-check on order of magnitude and rough position,
not a numerical calibration. The 44.3rd percentile is not precise agreement
between independently derived thresholds.

**H4 — "textbook" was doing causal work.** Corrected in §4.2 to a pattern
"consistent with a cyclone cold-wake response", with an explicit reminder that
these are independent daily reconstructions differenced afterwards, not a
dynamical attribution.

**H5 — "Category-5 equivalent" mixed wind-averaging conventions.** Removed. The
label comes from a **1-minute** scale while every ranking figure here is IMD's
**3-minute** value. Checked before removing: the bundled IBTrACS record *does*
carry JTWC 1-minute winds peaking at 145 kt, which would support the label on
its own scale — so this was not a false claim, it was a conflated one. Intensity
is now reported one scale at a time with the averaging period named, and no
Saffir–Simpson category label appears anywhere in Phase 7D.

**H6 — "VALIDATED" was ambiguous against the limitations section.** The gate now
reads *Ocean thermal-support categorization: VALIDATED* and lists explicitly
what is **not** validated and not claimed.

**H7 (added) — `HIGH` could be misread as "high cyclone risk".** The map legend
is now headed `THERMAL SUPPORT (ocean heat available, not cyclone risk)` and the
selected-cell tile reads e.g. `HIGH THERMAL SUPPORT` rather than a bare `HIGH`.

**One pre-existing flaky test was fixed, outside the hardening scope.**
`web/src/test/terrain.test.ts` — untouched by me and unchanged from HEAD — has
two heavy DEM tests that sat on the default 5 s budget, so the suite passed or
failed with machine load and "regression green" was not reliably verifiable. One
made ~950,000 individual `expect()` calls over 317,826 vertices; that loop now
accumulates violations and asserts once, which is exactly as strict and about
100x cheaper. The other genuinely builds two 620k-triangle geometries and was
given an explicit 30 s timeout. No assertion was weakened and no terrain
behaviour changed. Verified stable across three consecutive full runs. Flagged
because it is the user's file and revertable independently of this pass.

**Frozen pre-registrations were not rewritten.** Both `EVENT_SELECTION.md` and
`HAZARD_INDICATOR_PROTOCOL.md` keep their original text intact; the corrections
are appended as dated, clearly-labelled post-freeze notes that state the rule is
unchanged. Two tests pin this: the no-derived-numbers check is now scoped to the
text *above* any correction section, and a new test asserts a correction note
never moves a boundary — the served thresholds must still equal the originally
derived ones.

---

# PHASE 7D GATE

```
Historical event replay: WORKING
Ocean Hazard Indicators: WORKING

Ocean thermal-support categorization: VALIDATED
  (a pre-registered categorical summary of reconstructed upper-ocean heat,
   single-quantity, thresholds derived from the train split before any label)
NOT validated, and not claimed:
  cyclone outcome prediction      NOT CLAIMED
  cyclone probability             NOT PRODUCED (no numeric probability exists)
  cyclone intensity forecast      NOT CLAIMED
  the threshold set as a hazard model — it is a defensible starting point
Hazard indicator protocol frozen: YES (outputs/phase7/HAZARD_INDICATOR_PROTOCOL.md)
Numeric cyclone probability shown: NO
Event selected before error inspection: YES (outputs/phase7/EVENT_SELECTION.md)
Tsunami / Sea-Level-Rise tiles removed: YES (never present)
Event: Cyclone Mocha, 2023-05-05 .. 2023-05-22, Bay of Bengal, locked test split
Track source: IBTrACS v04r01 / IMD RSMC New Delhi, bundled offline, cited
Thresholds: p50 55.70 · p75 79.10 · p90 96.94 kJ/cm² (TRAIN split, 4,552,444 samples)
Literature 50 kJ/cm² anchor: 44.3rd percentile (disclosure only)
Category without physical support: 0 cells
Frozen L2 preserved: YES
2024 Argo: PROTECTED
Tests passing: 700 / 700  (575 pytest · 102 Vitest · 23 Playwright)
```

**PHASE 7D COMPLETE — AWAITING REVIEW.**
Do not proceed to the next phase until the user explicitly replies "CONTINUE".
