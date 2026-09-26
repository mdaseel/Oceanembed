# Historical Cyclone Event Library — Selection and Phase Rule

**Status:** FROZEN before any OceanEmbed reconstruction was produced for a newly
added event. Written 2026-09-14.

Before this file was written, the only queries run for the new candidates were
**external chronology** (IBTrACS v04r01 North Indian basin) and **data
availability** (which dates exist in the frozen model-ready store and how many
cells carry valid surface input). No `replay_field`, D26, TCHP, anomaly, hazard
category or reference comparison was computed for Biparjoy, Tauktae, Yaas,
Amphan or Fani.

Mocha's frozen evidence (`outputs/phase7/EVENT_SELECTION.md`, the bundled
`web/public/assets/event/track.json`, the `EVENT` dict in `poc/app.py`) is
**not modified** by this phase.

---

## 1. Candidate set

Named by the phase request, not chosen here: **Mocha 2023, Biparjoy 2023,
Tauktae 2021, Yaas 2021, Amphan 2020, Fani 2019.** No storm was added or removed
after looking at any OceanEmbed output.

## 2. Source

IBTrACS v04r01, `ibtracs.NI.list.v04r01.csv`, NOAA NCEI. Local copy
`data/raw/ibtracs/ibtracs.NI.list.v04r01.csv`, SHA-256
`1e892624f97f5481cddf6b8e9e65be2925fa0a3336f399f5b9fd87fbb463fb78` — **identical**
to the checksum frozen with the Mocha track in Phase 7D, so every event is drawn
from the same release. Intensity values are the IMD / RSMC New Delhi agency
columns (`NEWDELHI_WIND`, 3-minute; `NEWDELHI_PRES`) carried by IBTrACS.

## 3. Chronology rule (external only)

For each storm, from its IBTrACS rows sorted by `ISO_TIME`:

| Quantity | Definition |
|---|---|
| formation date | UTC date of the first fix carrying an IMD agency wind value |
| peak date | UTC date of the fix with the highest IMD wind; ties → lower IMD pressure, then the earliest fix |
| landfall date | UTC date of the first fix with `DIST2LAND == 0` |
| replay window | formation − 4 days … landfall + 8 days |

Segments:

| Segment | Dates |
|---|---|
| Pre-event | window start … formation − 1 |
| Approach / intensification | formation … peak − 1 (empty when peak = formation) |
| Event | peak … landfall |
| Wake | landfall + 1 … landfall + 4 |
| Recovery | landfall + 5 … window end |

**Check against the frozen event.** Applied to Mocha, this rule yields
2023-05-05 … 2023-05-22 with Pre-event 05–08, Approach 09–12, Event 13–14,
Wake 15–18, Recovery 19–22 — exactly the pre-registered Phase 7D window and
segments. The rule is therefore a restatement of the existing frozen design, not
a new choice. For Mocha the frozen values remain authoritative regardless.

A storm without any `DIST2LAND == 0` fix, or whose peak falls after its landfall
date, is excluded rather than given an improvised window.

## 4. Eligibility (data availability, never output quality)

An event is enabled only if **all** hold:

1. every window date lies inside the processed record 2015-01-01 … 2024-12-15;
2. every window date is present in the frozen model-ready store;
3. every window date has a non-zero surface-input-valid count (all seven
   channels jointly valid somewhere) — counts are reported;
4. the peak-intensity fix lies inside the reconstruction domain
   5–30 °N, 45–105 °E;
5. the storm has at least two fixes inside the domain.

The fraction of track fixes inside the domain is reported; fixes outside it are
drawn but never sampled.

## 5. Split disclosure (not a filter)

Each event is labelled with the data split of its window:
**train** 2015–2020, **validation** 2021, **test** 2022–2024. A training-period
reconstruction is **in-sample** — those dates were seen when the frozen L2 was
fitted — and the UI must say so on the event card and in every brief. Validation
dates were used for model selection. Only test-split events are out-of-sample.

## 6. What this rule does not do

- It never inspects OceanEmbed output, error or agreement with any reference.
- It does not rank events by severity; OceanEmbed assigns no cyclone severity.
- It does not shift, shorten or re-centre a window after results exist.
- Every day is an independent `replay_field(date)`; nothing is interpolated.
