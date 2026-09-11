# PHASE 8A — NRT-Lite / Live Input Telemetry

Run 2026-09-11 · Suites **637 pytest · 102 Vitest · 27 Playwright**
(entering the phase: 603 · 102 · 23)
Scope: **live input telemetry only.** No subsurface reconstruction, no latest
temperature map, no latest D26/TCHP, no latest hazard indicator, no 2024 Argo.

Frozen core untouched and re-verified at every engine start:
L2 state-dict `b715bb2b…e728d`, encoder `30cfd2db…db4808`.

---

## 1. Can live SST/SLA telemetry be retrieved? Yes.

Both NRT sources answered, and the region was actually retrieved — not merely
polled. Measured live during verification:

| Channel | Product | Valid time | Retrieved at | Age | NIO coverage |
|---|---|---|---|---|---|
| **SST** | `SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001` · doi:10.48670/moi-00165 | 2026-09-09T00:00:00 | 2026-09-10T19:30:19 | **43.5 h** | **49.9 %** (299,464 / 600,000) |
| **SLA** | `SEALEVEL_GLO_PHY_L4_NRT_008_046` · doi:10.48670/moi-00149 | 2026-09-10T00:00:00 | 2026-09-10T19:30:24 | **19.5 h** | **50.7 %** (48,698 / 96,000) |

State: `ONLINE_CURRENT`. Downloads were 1.16 MB (SST) and 389 KB (SLA) for the
5–30 °N / 45–105 °E box, one day each.

**NIO coverage is the fraction of finite cells in the retrieved native-grid NIO
rectangle**, reported with the raw counts beside it rather than as a bare
percentage. Much of the non-finite area is associated with land, but this is
**not** an inference-readiness or ocean-only coverage metric.

**Products and the catalogue poll are reused from the Phase 6C-D registry**
(`src/oceanembed/nrt/registry.py`, `discover.poll_product`). No NRT download
machinery was duplicated.

**OceanEmbed code does not directly inspect, store, print or log credential
values; authentication is delegated to the configured Copernicus Marine
client.** A missing or rejected login surfaces as an ordinary source failure
with its own state.

## 2. Provenance is stated, never invented

Per source: product id, dataset id, DOI, provider, `source tier = NRT`, product
valid time, local retrieval time, computed data age, NIO coverage, status, and
any error.

Two rules the code enforces rather than merely intends:

- **Product valid time and local retrieval time are separate fields and are
  never merged.** A test asserts both are present on every source, in every
  state including failure.
- **A provider-side generation time appears only when the provider actually
  states one.** Copernicus returns a catalogue *revision label*, not an
  acquisition timestamp, so the label is recorded as a note and
  `product_generated_time` stays `null`. A test asserts it is never populated
  with a fabricated value, and that unknown coverage is `null` rather than 0.

## 3. The tab, and what it refuses to show

A third route, **Latest Inputs**, sits beside Historical Replay, 3D Depth View
and Ocean Hazard Indicators. It shows the connectivity state, whether the
reading is a live retrieval or cached, the source-by-source table above, and —
prominently — what does not exist:

```
SUBSURFACE NRT RECONSTRUCTION NOT YET CERTIFIED
LATEST SUBSURFACE FIELD: NOT PRODUCED   (telemetry only in Phase 8A)
```

**The frozen L2 was not run on these inputs.** That is structural, not a
promise: `nrt/telemetry.py` imports no model, no replay module and no
diagnostics, and a test parses its import lines and call sites to prove it. A
second test walks the whole served payload asserting no key names a diagnostic
and that every textual mention of D26, TCHP or hazard is a statement that it is
*not* produced. A browser test asserts no temperature or kJ/cm² value appears
anywhere on the page.

**Ocean Hazard Indicators remains HISTORICAL.** No latest thermal-support label,
no latest D26/TCHP, and no NRT value reaches the hazard path — checked at the
function level, not by substring.

**Reserved wording is absent**: `Latest Qualified Ocean State` and
`Live Ocean Right Now` appear nowhere in the backend or any component.

## 4. Why SST and SLA first — visible, and not overclaimed

An expandable *"Why these inputs?"* panel carries the Experiment D reasoning
verbatim, including the qualification:

> …This does NOT mean those variables are physically unimportant or that the
> frozen L2 can accept arbitrary values in those channels. Full operational
> input qualification remains future work.

A test asserts the phrase "does NOT mean" survives and that the wording never
degrades into "only SST", "useless" or "do not matter".

## 5. One application, offline-first

```
launch                     → Historical Replay available, always
open Latest Inputs         → cached reading rendered instantly, then a real fetch
all sources satisfied      → ONLINE_CURRENT
some sources short         → ONLINE_PARTIAL, source by source
nothing answered + cache   → CACHED_TELEMETRY_NOT_CURRENT, labelled
nothing answered, no cache → DATA SOURCE CURRENTLY UNAVAILABLE
```

**Historical Replay cannot be taken down by the live path.** Two mechanisms:

1. `/api/latest*` is **exempt from the shared engine lock**. Every other `/api/`
   call is serialised behind one lock because xarray and the replay cache are
   single-process; a telemetry call that takes tens of seconds against a remote
   provider would otherwise block the offline science for its whole duration.
   A test asserts the exemption is in place.
2. The tab is rendered **outside** the replay-data guard, so a failure on either
   side cannot hide the other.

**Cached telemetry is never disguised as fresh.** It returns under its own
state, with `LAST SUCCESSFUL TELEMETRY - NOT CURRENT`, its original retrieval
time, and the staleness measured now. The *failed live attempt* is carried
separately (`live_attempt_sources`) so the operator can see both. Only a real
successful retrieval is ever written to the snapshot — a test asserts a failure
never writes one.

**An auth failure is not reported as an outage.** `AUTH_FAILED` and
`UNREACHABLE` are distinct states, because a rejected login and a dead network
are different problems for whoever has to fix them.

## 6. Demo-day resilience — rehearsed, not assumed

**Demo resilience was tested with the live-data path deliberately unavailable.**

`scripts/poc/run_demo_resilience_test.py` severs remote DNS and remote connects
at the socket layer, below every HTTP client and SDK, then drives the whole
application through the failure and back out. `outputs/phase8a/demo_resilience_test.json`
records **`result: PASS`**, all twelve checks:

| Check | Result |
|---|---|
| Historical Replay available with the network dead | PASS — field (101, 241, 15), 15-depth profile |
| Application did not crash | PASS |
| Latest Inputs rendered | PASS |
| Failure state reported | PASS |
| Cached snapshot labelled NOT CURRENT | PASS |
| Cached staleness measured | PASS |
| Unavailable state rendered | PASS |
| No-cache state informative | PASS — `DATA SOURCE CURRENTLY UNAVAILABLE` |
| Valid time kept separate from retrieval time | PASS |
| Historical Replay still available *after* the failure | PASS |
| **Recovery without restart** | PASS — `ONLINE_CURRENT` in the same process |
| Recovery re-attempted both sources | PASS |

**Two real defects were found by this rehearsal, which is what it is for.**

**The instrument was wrong first.** Blocking `socket.socket` outright also broke
asyncio's internal self-pipe, so Historical Replay appeared to fail with the
network cut. That would have been a serious false finding. Verified separately
that replay is genuinely network-independent, then narrowed the cut to remote
DNS and remote connects only, leaving loopback and local machinery intact. A
test instrument that produces a false failure is as dangerous as one that
produces a false pass.

**Then the state machine was wrong.** Recovery kept reporting
`CACHED_TELEMETRY_NOT_CURRENT` after the network returned. The cause was real:
`overall_state` treated a catalogue-only poll as offline, because a source that
had answered perfectly well but had not been asked for the region carried the
same status as one that had failed. That would have told an operator the network
was down when it was not. `CATALOGUE_ONLY` is now its own state, and a source
counts as satisfied when everything asked of it succeeded. Pinned by a test
named for the claim: *the provider answered — reporting that as offline would be
a lie*.

## 7. Tests

`tests/test_phase8a_telemetry.py` (32) and `web/e2e/latestInputs.spec.ts` (4).

Covered: telemetry imports no model, replay or diagnostics and calls none;
the payload carries no scientific value and only refusals; NOT CERTIFIED always
stated; reserved 8B wording absent; scope is the two ablation channels; the
rationale does not overclaim; all five state-machine transitions including
catalogue-only-is-not-offline; auth failure distinguished from unreachable; the
two clocks separate; generated time never invented; unknown coverage null not
zero; offline never raises; cached telemetry labelled with measured staleness;
no-cache state informative; failure never writes a snapshot; Historical Replay
unaffected by a dead network; the cached endpoint never touches the network; the
telemetry endpoints do not take the engine lock; historical endpoints still work
offline; hazard stays historical; the resilience artifact exists, passed, and
covers recovery; no latest inference, no SSS fallback, no quantile mapping;
frozen hashes unchanged; no Argo anywhere.

**A 553-second suite was reduced to 13 seconds.** Eight tests each spent ~60 s
waiting out the provider client's retry backoff against severed DNS. They are
about how the state machine behaves *once a source has failed*, not about the
vendor's retry schedule, so they now inject the failure at the same seam a real
outage hits. The genuine severed-network path is still exercised end to end —
by the resilience script, whose artifact is asserted.

**Two Phase 7 tests were updated at the phase boundary, and narrowed rather than
weakened.** Both are recorded in the test files with the reason:

- `test_no_nrt_or_live_code_reachable_from_the_application` (7E) banned a
  `Latest Inputs` tab, correct while 8A was unauthorised. Narrowed to the items
  still reserved for 8B; the reserved wording and `latest_qualified` entry point
  remain forbidden, and a new test asserts no latest-reconstruction entry point
  exists.
- `test_no_nrt_or_live_code_introduced` (7D) banned any NRT reference in
  `poc/app.py`, which now legitimately hosts the telemetry endpoints. Narrowed
  to what 7D actually guarantees — that no live source reaches the hazard
  indicator or the event replay — and checked at the function level.
- `test_nothing_outside_freeze_metadata_is_uncommitted` (7E) asserted the live
  tree was clean, which only measured "has anyone done anything since" once a
  later phase began. Replaced with the durable claim: the manifest's recorded
  state at generation time, plus a new test verifying the frozen commit still
  contains every artifact it claims, read from git.

The Phase 7 freeze itself is untouched: commit `9fb32ba` and all 17 hashed
artifacts still verify.

---

## 8. Limitations, stated

- **Coverage is measured, not qualified.** ~50 % is the finite-cell fraction of
  the retrieved native-grid rectangle. Much of the non-finite area is associated
  with land, but it is not an ocean-only coverage metric and not an assessment
  of whether the field is fit for inference. No qualification claim is made
  about either input.
- **Data age is real and non-trivial**: SST was 43.5 h old at retrieval. Whether
  that age is acceptable for operational inference is a Phase 8B question.
- **Only two of seven channels are touched.** The frozen L2 requires all seven,
  and nothing here suggests the other five can be omitted or substituted.
- **A catalogue revision label is not an acquisition time**, and is recorded as
  a label rather than promoted to one.
- **Telemetry says nothing about subsurface skill.** These are inputs.

---

# PHASE 8A GATE

```
Latest Inputs mode: TELEMETRY READY
Latest NRT subsurface reconstruction: NOT CERTIFIED
Historical Ocean Hazard Indicators: AVAILABLE
Latest/NRT Ocean Hazard Indicators: NOT CERTIFIED
Channel-choice explanation visible: YES
Offline failure path rehearsed: YES
Connection recovery without app restart: PASS
demo_resilience_test.json: PASS
Frozen L2 preserved: YES
2024 Argo: PROTECTED
Tests passing: 766 / 766  (637 pytest · 102 Vitest · 27 Playwright)
```

**PHASE 8A COMPLETE — AWAITING REVIEW.**

Historical OceanEmbed PoC: COMPLETE
Latest operational telemetry: READY
Latest subsurface reconstruction: NOT YET CERTIFIED

STOP — awaiting review before any Phase 8B work.
Phase 8B may begin ONLY after explicit authorization following review of this
report. Approval to begin Phase 8B does **NOT** authorize access to 2024 Argo;
that holdout remains PROTECTED pending its own separate explicit approval.
