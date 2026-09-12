# Phase 8B — Corrective Operational Addendum, 2026-09-12

Appended to `PHASE8B_NRT_SUBSURFACE_QUALIFICATION_REPORT.md`, which is preserved
unchanged. This addendum covers two operational corrections requested after the
Phase 8B scientific review:

- **Problem A** — the Latest Qualified Ocean State resolved to a valid date
  ~8.7 days old.
- **Problem B** — only one date was reachable; a 7-day recent-states selector
  was required.

**Nothing scientific changed.** No retraining, fine-tuning, bias correction or
quantile mapping; no change to the gates, the qualified products, the SSS
operating mode, the D26/TCHP equations or the hazard thresholds; the frozen L2
hashes are unchanged; 2024 Argo was not opened. The Phase 8B statuses stand:
temperature QUALIFIED WITH LIMITATIONS, D26 NOT QUALIFIED and withheld, TCHP
QUALIFIED, hazard qualified by transfer.

---

## 1. Root cause of the ~9-day lag

**Genuine provider latency in the qualified currents product — not an
OceanEmbed bug, not a stale cache, and not a portal/endpoint discrepancy.**

Evidence, gathered before any code was changed:

| check | result |
|---|---|
| CMR granule search, `OSCAR_L4_OC_NRT_V2.0`, sorted `-start_date`, no date window (2,071 granules) | newest granule `oscar_currents_nrt_20260903`, valid 2026-09-03, **ingested 2026-09-05 06:12 UTC**; nothing newer exists |
| Same collection, 25-day window | continuous daily granules up to 2026-09-03, then nothing |
| `OSCAR_L4_OC_FINAL_V2.0` (the retrospective product) | ends 2026-01-16 — not a substitute |
| CMEMS SST `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2` — service time axis | 2026-09-11 |
| CMEMS SLA `cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D` | 2026-09-12 |
| CMEMS SSS `cmems_obs-mob_glo_phy-sss_nrt_multi_P1D` | 2026-09-06 |
| CMEMS wind `cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H` | 2026-09-11 23:00 (day complete) |

So on 2026-09-12 the newest date **every** channel can supply is **2026-09-03**,
set by OSCAR. The date OceanEmbed selected was correct; what was missing was the
evidence that it was correct, and the ability to see the operational record.

Catalogue metadata and the data services agreed for all four Copernicus
datasets, so the old catalogue-based discovery was not returning a stale answer
here. It could have, which is why discovery now reads the services' own time
axes (§3).

### The newer alternative, reported and NOT adopted

`cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m` (CMEMS MULTIOBS NRT total surface
currents, 0.25°, daily — the GlobCurrent-lineage geostrophic + Ekman product)
had data to **2026-09-10** at the time of this check, seven days fresher than
OSCAR.

It has **not** been swapped in. It is a different product: a different
formulation (altimetric geostrophy plus a modelled Ekman component) from a
different provider, whereas the qualified channel is OSCAR NRT, whose
substitution sensitivity was measured in Phase 6C-D and whose behaviour inside
the complete stack was qualified in the Phase 8B hindcast. **Changing it
requires a fresh, pre-registered qualification** — a new channel cannot enter
the frozen L2 merely because it is newer. The decision is yours.

---

## 2. What was actually wrong in the implementation

Three weaknesses, all fixed, none of which changed the answer on this date:

1. **`min` of the per-product newest dates, not a true intersection.** If a
   product were missing an *interior* day, that day would still have been
   offered. Now the newest common date is `max(intersection of every channel's
   usable dates)`.
2. **Discovery read catalogue metadata, not the data.** Catalogue values can lag
   what is retrievable. Discovery now reads each dataset's own time axis, and
   builds a *set*, so a descending time axis cannot make the newest date look
   like the oldest.
3. **Nothing was refreshable, and nothing was reusable.** There was no
   separation between "has a newer date appeared?" and "what was the field for
   2026-09-03?".

---

## 3. The fix

**Date resolution** (`src/oceanembed/nrt/latest.py`):

- `channel_dates()` — per-product sets of usable valid dates, read from the
  Copernicus services' own time coordinates and from the OSCAR granule
  catalogue.
- Wind keeps its completeness rule: a day counts only once its **23:00** field
  exists, because the frozen contract uses a daily U/V mean.
- `common_dates()` — the intersection across all five products.
- `resolve_common_date()` — `max(common_dates)`, or `None`.
- `available_window(days=7)` — the seven calendar days ending at the newest
  qualified date, each decided independently, each unavailable day naming the
  channel that is missing.

**Cache lifetimes, separated:**

| cache | lifetime | why |
|---|---|---|
| discovery (time axes, granule lists) | `DISCOVERY_TTL_SECONDS = 900`, and `refresh_discovery()` clears it; the UI's Retry/Refresh passes `refresh=true` | whether a newer date exists must never be pinned by an old answer |
| per-date qualified field (`outputs/phase8b/daily_cache/<date>/`) | immutable | a qualified field for a past date cannot change; identity includes the valid date, product ids, source valid times, model/scaler/climatology hashes, grid and policy version, and the decision SHA |

A cached field is only ever served as the date it was produced for: `load_daily`
passes the expected date into the identity check.

**API:**

- `GET /api/latest/available-dates?days=7&refresh=false` — the window, per-product
  newest dates, per-day status and reason. Runs no inference.
- `GET /api/latest/qualified?date=YYYY-MM-DD` — one date through the **same**
  seven-channel qualification → harmonisation → frozen L2 → field-view adapter →
  existing map/3D/profile. Without `date` it serves the newest qualified date.
- A requested date the stack cannot supply returns `DATE_NOT_QUALIFIED` with the
  missing channels and **no inference**.
- The "last successful" snapshot (the offline fallback) is only ever written for
  the newest state; older dates go to the per-date cache.

**UI:** a `RECENT QUALIFIED STATES` strip of seven day-chips under the title.
Unavailable days stay visible, disabled, and say which channel is missing. The
newest is marked. Selecting a day re-renders the map, 3D view, profile, point
values, TCHP and hazard from that day's field. `SELECTED OCEAN STATE · VALID`
and `NEWEST QUALIFIED STATE` are shown side by side, with the lag for the
selected day. D26 remains withheld in every latest state.

---

## 4. Live verification

One controlled live pass, 2026-09-12 11:30 UTC
(`outputs/phase8b/latest_date_verification.json`).

**What each provider actually holds** (read from the services' own time axes and
the granule catalogue, 30-day discovery window):

| channel | dataset | newest available | usable dates in window |
|---|---|---|---|
| SST | `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2` | 2026-09-11 | 30 |
| SSS | `cmems_obs-mob_glo_phy-sss_nrt_multi_P1D` | 2026-09-06 | 25 |
| SLA | `cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D` | 2026-09-12 | 31 |
| currents | `OSCAR_L4_OC_NRT_V2.0` | **2026-09-03** | 22 |
| wind | `cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H` | 2026-09-11 (23:00, day complete) | 30 |

**Newest common qualified date: 2026-09-03**, set by OSCAR. SLA is nine days
fresher, and it makes no difference: the stack moves at the pace of its slowest
mandatory channel.

**Seven-day window** (all seven days ending at the newest qualified date):

| date | status |
|---|---|
| 2026-08-28 | AVAILABLE |
| 2026-08-29 | AVAILABLE |
| 2026-08-30 | AVAILABLE |
| 2026-08-31 | AVAILABLE |
| 2026-09-01 | AVAILABLE |
| 2026-09-02 | AVAILABLE |
| 2026-09-03 | AVAILABLE — newest |

**Two qualified states produced through the same frozen path:**

| valid date | coverage | reconstruction lag | per-source state |
|---|---|---|---|
| 2026-09-03 | 99.66 % | 227.5 h (9.5 d) | all five OK, each valid 2026-09-03 |
| 2026-09-02 | 99.66 % | 251.5 h (10.5 d) | all five OK, each valid 2026-09-02 |

They are genuinely different fields: **max |Δ| 2.10 °C, mean |Δ| 0.117 °C**.

**Through the UI**, at the same cell and depth (15.25 °N, 87.75 °E, 100 m):

| selected date | L2 temperature | TCHP | state tile |
|---|---|---|---|
| 2026-09-02 | 22.944 °C | 57.2 kJ/cm² | Qualified state for this date |
| 2026-09-03 | 22.299 °C | 54.2 kJ/cm² | Newest qualified state |

Re-selecting a date returns the same field, served from the immutable per-date
cache without contacting the providers again (the verification's second pass
reports `served_from: immutable per-date cache` for both dates).

### Two defects the live pass exposed, both fixed

1. **The oldest day in the window was blamed on the providers.** With OSCAR
   stalled, the 7-day window reached back before the 14-day discovery lookback,
   so 2026-08-28 was reported as "no usable field for" *all five* channels when
   in truth discovery had never looked that far back. The lookback is now 30
   days, and a day before the window start says so explicitly instead of naming
   channels. An operator must not be told a provider is missing data it has.
2. **A qualified older state displayed as "Unavailable".** The state tile had
   labels only for the newest state and the snapshot, so `QUALIFIED_STATE_FOR_DATE`
   fell through to "Unavailable" while showing a perfectly good field. Both that
   state and `DATE_NOT_QUALIFIED` now have their own labels, and a browser test
   asserts the tile never reads "Unavailable" for a served qualified date.

---

## 5. Confirmations

- **Every displayed day is independently qualified.** Each date runs its own
  seven-channel check, harmonisation and frozen-L2 inference; the tests assert
  that selecting A then B equals B computed alone.
- **No persistence was introduced.** `persistence_envelope_days` is still 0; a
  channel stamped another day is refused (`NOT_ON_COMMON_DATE`); no
  interpolation across dates exists. A syntax-tree test asserts the module uses
  no sequence model, no rolling/`ffill`/`interpolate`/`shift` call, and imports
  no deep-learning framework.
- **The frozen L2 is unchanged** — state-dict and encoder hashes verified before
  and after the live run.
- **2024 Argo remains protected** — nothing in this change reads Argo of any
  year.
- **The shared renderer is reused** — no new 3D module; the latest field still
  travels in `oceanembed.field-view.v1` and is adapted by the same `adaptReplay`.

## 6. Tests

**Backend** — `tests/test_phase8b_latest.py`, 51 tests (was 32), covering every
item requested:

| # | requirement | test |
|---|---|---|
| 1 | newest common date from the real intersection | `test_newest_common_date_is_the_intersection_not_the_min`, `test_one_stalled_channel_holds_the_whole_stack_back` |
| 2 | a stale metadata cache cannot pin the latest date | `test_stale_discovery_cannot_permanently_hold_the_latest_date`, `test_discovery_ttl_is_bounded` |
| 3 | ascending/descending axes agree | `test_time_axis_order_cannot_change_the_newest_date` |
| 4 | incomplete wind day excluded | `test_incomplete_wind_day_is_excluded` |
| 5 | a day missing one current channel is unavailable | `test_unavailable_days_are_visible_and_name_the_missing_channel`, `test_a_date_one_channel_lacks_is_refused` |
| 6 | no persistence or carry-forward | `test_channel_on_a_different_date_is_refused`, `test_no_temporal_model_was_introduced` |
| 7 | no inference for an incomplete day | `test_a_date_no_channel_can_supply_is_refused_without_inference`, `test_an_unqualified_date_runs_no_inference` |
| 8 | seven-day list deterministic and ordered | `test_window_is_ordered_deterministic_and_ends_at_the_newest` |
| 9 | unavailable dates expose a reason | `test_unavailable_days_are_visible_and_name_the_missing_channel`, `test_a_day_before_the_discovery_window_says_so` |
| 10 | different dates produce their own fields | `test_each_date_is_its_own_independent_field`, `test_selecting_an_older_date_serves_that_date_only` |
| 11 | reselecting reproduces the field | `test_reselecting_a_date_reproduces_the_same_field`, `test_no_temporal_state_between_dates` |
| 12 | field/profile/map agree for a day and cell | `test_point_profile_is_a_sample_of_the_field`, `test_latest_equals_the_hindcast_field_for_that_date` |
| 13 | D26 stays absent | `test_live_payload_uses_the_historical_transport`, `test_selecting_an_older_date_serves_that_date_only` |
| 14 | TCHP/hazard from the selected day only | `test_selecting_an_older_date_serves_that_date_only` |
| 15 | frozen hashes unchanged | `test_frozen_hashes_unchanged_after_serving_dates`, `test_field_contract` |
| 16 | 2024 Argo untouched | `test_no_argo_and_no_fallbacks_in_the_latest_path`, plus `tests/test_phase8b_gate.py::TestHoldout` |

Plus cache discipline: `test_a_cached_field_is_never_served_as_another_date`,
`test_daily_cache_reuse_is_exact`,
`test_snapshot_is_invalid_once_the_decision_changes`.

**Browser** — `web/e2e/latestQualified.spec.ts`, 8 tests (was 6). The two new
ones cover the selector rendering with its 7 days and newest marker, an
unavailable day being visible, disabled and explained, switching days updating
the valid-date label and the shared map/3D/profile, an unavailable day never
issuing a request (so no inference can run), the lag staying visible, the state
tile label, and the absence of any "ocean now" claim.

**Totals: 869 passing (729 pytest · 105 Vitest · 35 Playwright), no failures.**

---

---

## 7. Second check, after a report that newer data was available (2026-09-12, 13:32 UTC)

Re-verified against the providers, with discovery forced to re-read:

| channel | newest available |
|---|---|
| SLA | 2026-09-12 |
| SST | 2026-09-11 |
| wind | 2026-09-11 (23:00) |
| SSS (MULTIOBS L4 NRT) | 2026-09-06 |
| **currents (OSCAR NRT)** | **2026-09-03** |

CMR, sorted newest-first over all 2,071 granules, still returns
`oscar_currents_nrt_20260903` (ingested 2026-09-05) as the newest. **The newest
common date is still 2026-09-03**, and it is not an OceanEmbed defect.

The two portals in the report were checked and are **not** the binding channel:

- **Argo GDAC** (`data-argo.ifremer.fr/geo/indian_ocean/2026/09/`, daily files to
  20260912) is *in-situ validation* data. It is not one of the seven satellite
  inputs the frozen L2 consumes, so its recency cannot move the reconstruction
  date. The 2024 holdout also remains protected.
- The salinity page showing `Sea_Surface_Salinity_Rain_Corrected` and dates to
  2026-09-10 is the **SMOS L3** product `MULTIOBS_GLO_PHY_SSS_L3_MYNRT_015_014`
  — the candidate Phase 6C-D **rejected** (2.4 % mean daily coverage; zero
  usable days in the Bay of Bengal). The qualified salinity channel is the
  MULTIOBS **L4** NRT product, which is at 2026-09-06 and is not the limiting
  channel either.

The only way to a fresher latest state is a **new qualification of a different
currents product** (§1), not a change to this code.

---

## 8. Recent states are pre-produced, so the tab opens instantly

Previously a date was fetched only when clicked, which meant a full
five-product download and a frozen-L2 run while the user waited.

**Now:**

- **The server warms the window at startup.** `warm_recent_states()` walks the
  7-day window newest-first, skips dates already cached, and produces the rest
  into the immutable per-date cache. It is a normal, fully qualified run per
  date — the warm-up relaxes no check and refuses exactly as an interactive
  request would; refusals are recorded per date and never crash the loop.
- **The page asks for it too.** The tab calls `/api/latest/prewarm` on mount,
  which returns immediately, and each day-chip shows whether it is `ready` or
  still being prepared, refreshing until all are ready.
- **Discovery is single-flighted.** A page load and the warm-up at startup used
  to miss the cache simultaneously and each pay a full provider round-trip; a
  per-key lock now means one read serves both.
- **Discovery is persisted** (`outputs/phase8b/discovery_cache.json`) and served
  stale-while-revalidate for up to 6 hours, with a refresh started behind it.
  It only decides *which* date to ask for; the retrieval still verifies that
  every channel really carries that date before any inference runs, so a stale
  hint cannot produce a wrong field.
- **Historical Replay is never blocked**: downloads happen off the event loop and
  outside the engine lock, and only the inference itself briefly takes it.

Measured on this machine:

| action | before | after |
|---|---|---|
| open the tab (cold server, window listing) | 54.5 s | **0.16–0.32 s** |
| select an already-produced date | 41 s (paid discovery first) | **~0.8–3.5 s** (transfer of the field itself) |
| Historical Replay while the warm-up runs | — | 1.9 s, unaffected |
| dates ready after startup | 0 of 7 | **7 of 7** |

Nothing about the science changed: each date is still an independent frozen-L2
run over its own complete seven-channel stack, D26 stays withheld, and an
unavailable date still produces no inference.

**END OF ADDENDUM.** The Phase 8B scientific result is unchanged. Swapping the
currents product to a fresher one remains an open decision requiring its own
pre-registered qualification.
