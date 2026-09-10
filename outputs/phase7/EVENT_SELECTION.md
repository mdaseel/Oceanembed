# Phase 7D — Event Selection

**Status:** FROZEN before any event-specific OceanEmbed output or model-reference
error was inspected.

At the time this file was written, no `replay_field` call had been made for any
date in the selected window during Phase 7D, and no D26, TCHP, anomaly or
hazard label had been computed for the event. The only repository queries run
before writing this were **data availability** checks (which dates exist in the
frozen store, and how many cells carry valid surface input) — never a
prediction, a reference comparison, or an error.

---

## 1. Selection rule, fixed before looking

> **Select the single most intense tropical cyclone over the Bay of Bengal or
> Arabian Sea whose full event window lies inside the LOCKED TEST SPLIT
> (`2022-01-01` … `2024-12-15`), ranked by IMD best-track peak 3-minute
> sustained wind, with minimum central pressure as the tie-break, and requiring
> a complete surface-input record for every day of the window in the frozen
> model-ready store.**

Every clause is external to OceanEmbed:

- **Intensity ranking** comes from the IMD/RSMC New Delhi best-track record as
  reported in the public season summaries — not from anything this project
  computed.
- **The test-split restriction** is a deliberate strengthening beyond the
  master prompt, which only requires a date inside the 2015–2024 window. Using
  the locked test split means the reconstruction shown for this event is
  **out of sample**: no day of it was seen during training, scaler fitting or
  climatology fitting.
- **The data-availability clause** is a precondition, not a filter on quality.
  It asks whether the inputs exist, never whether the output is good.

**The rule contains no reference to OceanEmbed error, skill, bias, D26, TCHP or
agreement with GLORYS.** No candidate was scored before selection.

---

## 2. Candidate shortlist and the ranking that decided it

Strongest system per season inside the locked test split:

| Season | Strongest NIO system | IMD peak 3-min wind | Min. pressure | IMD class |
|---|---|---|---|---|
| 2022 | Cyclone **Asani** | 100 km/h | 982 hPa | Severe Cyclonic Storm |
| **2023** | **Cyclone MOCHA** | **215 km/h** | **938 hPa** | **Extremely Severe Cyclonic Storm** |
| 2024 | Cyclone **Remal** | 110 km/h | 978 hPa | Severe Cyclonic Storm |

2023 also produced Biparjoy (165 km/h, 958 hPa, ESCS, Arabian Sea) and Tej
(ESCS), both weaker than Mocha on both ranking variables.

**Selected event: Cyclone MOCHA, May 2023, Bay of Bengal.**

The margin is not marginal: Mocha's peak wind is roughly double the strongest
system of either neighbouring season, and its central pressure is 40 hPa lower.
The ranking is unambiguous, so the rule required no discretionary judgement.

## 3. Why this event qualifies as a disaster-management demonstration

Mocha was the most intense North Indian Ocean cyclone of 2023, reached
Category-5-equivalent intensity, made landfall just north of Sittwe in Rakhine
State, Myanmar, and caused severe loss of life and damage across Myanmar and
Bangladesh. It underwent rapid intensification over the central Bay of Bengal —
precisely the regime in which upper-ocean thermal structure is physically
implicated, and therefore the regime where a subsurface reconstruction has
something real to say.

**What OceanEmbed does and does not claim about it** is fixed here, before any
figure is produced: OceanEmbed **reconstructs the subsurface ocean thermal state
that the cyclone encountered**. It did not predict, and is not claimed to have
predicted, the storm's genesis, track, landfall, category or intensity.

---

## 4. Event chronology and replay window

IMD chronology (all times UTC):

| Stage | Date |
|---|---|
| Depression over the southeast Bay of Bengal | 9 May 2023 |
| Deep Depression | 10 May 2023 |
| Cyclonic Storm | 11 May 2023 |
| Severe Cyclonic Storm | 11 May 2023, 12:00 |
| Very Severe Cyclonic Storm | 12 May 2023 |
| Extremely Severe Cyclonic Storm | 12 May 2023, 18:00 |
| **Peak intensity** — 215 km/h, 938 hPa | **13 May 2023, 18:00** |
| Landfall north of Sittwe, Myanmar | 14 May 2023, 07:00 |
| Weakened to Depression / low-pressure area | 15 May 2023 |

**Replay window: `2023-05-05` … `2023-05-22` (18 consecutive days).**

| Segment | Dates | Purpose |
|---|---|---|
| Pre-event | 05–08 May | the undisturbed ocean before the depression forms |
| Approach / intensification | 09–12 May | the thermal state the system moved over while intensifying |
| Event | 13–14 May | peak intensity and landfall |
| Wake | 15–18 May | cold wake and immediate post-storm structure |
| Recovery | 19–22 May | thermal recovery |

The window is symmetric about the event by construction (4 days before
formation, 8 days after landfall) and was chosen to make the sequence readable,
not to make any day look better.

**Every day is an independent `replay_field(date)` call.** There is no temporal
model, no sequence input, and no state carried between days. The before/during/
after presentation is a strip of independent daily reconstructions and must
never be described as a forecast. L3 remains rejected and unused.

**Verified availability** (before selection was finalised, and the only
repository query made): all 18 days are present in
`data/processed/model_ready/oceanembed_2023.zarr`, with 11,855 ocean cells and
11,268 surface-input-valid cells on the first, middle and last day of the
window — a stable input record with no gap.

---

## 5. External track source and attribution

The track overlay uses **IBTrACS v04r01**, the International Best Track Archive
for Climate Stewardship, North Indian basin subset, distributed by
**NOAA National Centers for Environmental Information (NCEI)**.

- Product: `ibtracs.NI.list.v04r01.csv` (North Indian basin)
- Citation: Knapp, K. R., M. C. Kruk, D. H. Levinson, H. J. Diamond, and C. J.
  Neumann (2010), *The International Best Track Archive for Climate Stewardship
  (IBTrACS): Unifying tropical cyclone best track data*, Bulletin of the
  American Meteorological Society, 91, 363–376.
- Data citation: Knapp, K. R., H. J. Diamond, J. P. Kossin, M. C. Kruk, C. J.
  Schreck (2018), *International Best Track Archive for Climate Stewardship
  (IBTrACS) Project, Version 4*, NOAA National Centers for Environmental
  Information. doi:10.25921/82ty-9e16
- Licensing: US Government work, public domain; NOAA/NCEI attribution retained
  in the bundled metadata and shown in the UI.

IBTrACS carries the IMD/RSMC New Delhi agency columns for this basin, so the
displayed intensity remains the official regional-agency value rather than a
re-analysis by this project.

**Offline discipline.** The track is fetched **once at build time**, subset to
this single storm, and bundled as a local static asset with its source checksum
recorded — exactly as the ETOPO terrain and bathymetry already are. The running
application performs no network access. The track is **static geographic
context**: it is not a model input, not an OceanEmbed output, and it never
enters inference, the diagnostics, or any mask.

---

## 6. Discipline

- The event was selected by the rule above and **not** because OceanEmbed
  performs well during it. No event-specific error was computed before this file
  was written.
- The window will not be shortened, shifted or re-centred after seeing the
  results.
- Each date is an independent reconstruction; no temporal model is used or
  implied.
- The frozen L2, its checkpoint, the scalers, the L0 climatology and the Phase
  7C diagnostic conventions are unchanged by this phase.
- **2024 Argo remains PROTECTED** — not downloaded, opened, collocated or
  scored. This phase reads no Argo data at all.
- OceanEmbed makes no claim about cyclone genesis, track, landfall, category or
  intensity evolution.

---

*Written before execution. Nothing in this file was informed by an OceanEmbed
reconstruction of the selected event, because none had been produced.*

---

## Post-freeze correction (2026-09-10, freeze review)

The original text above is left **unaltered**. This corrects a *descriptive
claim only*. **The selection rule, the ranking, the chosen event and the replay
window are unchanged**: Extremely Severe Cyclonic Storm Mocha, 2023-05-05 …
2023-05-22.

**C1 — "Category-5-equivalent intensity" (§3) is removed as a description.**

§3 describes Mocha as having "reached Category-5-equivalent intensity". That
label comes from a **1-minute** sustained-wind scale, while every other
intensity figure in this document — including the 215 km/h used to rank the
candidates — is IMD/RSMC New Delhi's **3-minute** value. Placing the two in one
sentence conflates conventions that are not interchangeable.

For completeness: the bundled IBTrACS record does carry the JTWC 1-minute value,
peaking at **145 kt**, which would support that label on its own scale. The
phrase is dropped anyway, because mixing averaging conventions invites an
argument that adds nothing to the demonstration. Intensity is now reported on
one scale at a time with the averaging period named:

- IMD / RSMC New Delhi, 3-minute sustained: **115 kt ≈ 215 km/h**
- JTWC, 1-minute sustained: **145 kt**
- Minimum central pressure: **938 hPa**

No Saffir–Simpson category label is applied anywhere in Phase 7D.
