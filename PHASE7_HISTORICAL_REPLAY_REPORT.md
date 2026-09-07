# Phase 7A — Historical Replay Backend

**OceanEmbed (SIH26066)** · INCOIS / Ministry of Earth Sciences · Theme: Disaster Management
Run 2026-09-06 · Full test suite **432 passed** (baseline before Phase 7: 384)
Scope: backend only. **No UI, no NRT, no D26/TCHP, no event replay, no 2024 Argo.**

---

## 1. Is frozen L2 still the final core? Is the hash unchanged?

**Yes to both.** The engine loads the frozen artifacts read-only and refuses to
start if any hash has moved — this is a hard failure, not a warning.

| artifact | sha256 | status |
|---|---|---|
| L2 state-dict | `b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d` | unchanged |
| L2 encoder | `30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808` | unchanged |
| L2 checkpoint file | `81979a6541927ff5c6b0a13c5ce7cdbcd486040d16a304dcdc10b2962a586e35` | unchanged |
| L1 checkpoint file | `fefebd216536b9a1b8383ae41b5d35057b8b46ed1b4b77a9642a514bc9c92b5b` | unchanged |
| feature scaler | `49671ce760b0dca5c1c82cb184dae91908cc064abfdea8cc7eb2f5bc3c320467` | unchanged |
| target scaler | `5b6f359db0d228dd7d3acf775ab8a6eea76dd521e7b4568ff1873c832e89e93b` | unchanged |
| L0 climatology | `748af4d79bc704cc2f742e1c208bacebe781131c5ff142cddc7c334963903cd5` | unchanged |
| surface climatology | `58f0c5812ebcb6d4394a4f18e5b133d0a69657960e0e4c98d74184e91f6e8932` | unchanged |

Nothing was retrained, fine-tuned, refit or rewritten. Patch 33, latent 32,
receptive field 33, 136,335 parameters — all read from the checkpoint, none
assumed. A test also re-hashes the live model **after** running replay, so an
in-place weight mutation would be caught.

Manifest: [`outputs/phase7/final_core_manifest.json`](outputs/phase7/final_core_manifest.json)
— records the model, the seven inputs, mask semantics, the 15 depths, all
artifact paths and hashes, the grid, the nominal-0 m convention, the replay
version, and `argo_2024 = PROTECTED`. The checkpoint is referenced, never
duplicated.

## 2. Can a full field be reconstructed?

**Yes.** `replay_field(date)` returns the canonical field-view object:

```
temperature   (101, 241, 15)   degC, NaN off-support
climatology   (101, 241, 15)   frozen L0 at the same 15 depths
anomaly       (101, 241, 15)   temperature - climatology
lat (101)  lon (241)  depths [0…1000]  ocean_mask (101,241)  surface_input_valid (101,241)
+ model / hash / provenance metadata
```

It runs the **existing** frozen whole-field path — `day_field` (unmodified) →
`embed_field` → `forward_from_z` → frozen target scaler. There is exactly one
inference implementation in the package.

**Anti-drift test.** `test_field_uses_the_exact_frozen_l2_path` recomputes the
field inline from the frozen primitives and requires equality to `atol=1e-12`.
If replay ever grew its own preprocessing, context construction, scaler use or
decode order, that test diverges.

## 3. Can a date/location be reconstructed? Does point derive from field?

**Yes, and yes — that is the design, not a convention.** `replay_point` calls
`replay_field` and samples the result. It performs no inference of its own; a
test monkeypatches `embed_field` and asserts it is called **exactly once** per
point request.

**The mandatory equivalence test** (`test_point_equals_field_at_the_resolved_cell`)
compares every one of the 15 depths of `replay_point` against
`replay_field[row, col, :]` at **`abs=0.0` — exact equality**, not a tolerance.
It passes. A NaN in the field must appear as `null` in the point profile, so
missing stays missing.

### Cell-support convention (documented, because it is a real choice)

A date's predictions are produced at the cells where **that date's**
`surface_input_valid` is true. That mask is, by construction, identical to the
joint validity mask `day_field` computes internally from the same seven
channels — a test asserts the decoded cell set equals the encoder's mask channel
(`test_day_field_joint_mask_equals_surface_input_valid`). Off-support cells are
**NaN, never zero and never interpolated**.

Worth recording: `surface_input_valid` is **constant within a year but varies
between years** — 11,067 cells (2015), 11,136 (2021), 11,268 (2023/2024) out of
11,855 ocean cells. The frozen evaluation scripts open a multi-year split and
take `time=0`, so on a 2024 date they use the 2022 cell list. Single-date replay
uses that date's own mask, which is the scientifically correct per-day support.
The difference is small and affects only coastal cells, but it is a genuine
difference and is stated rather than glossed.

## 4. Are all 15 depths returned?

**Yes**, always, in the exact mandated order
`0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000 m`. Ordering
is asserted against a literal list in the tests and against the checkpoint's own
depth list at engine start-up.

Deep output is **not** suppressed. `test_deep_l2_output_is_not_suppressed`
asserts the 1000 m layer is finite on every supported cell and is *not* equal to
climatology — a silent L0 substitution at depth would fail it.

## 5. Is climatology correct? Is anomaly correct?

**Yes.** `test_climatology_equals_the_frozen_l0` compares the field's
climatology against `HarmonicClimatology.predict` at `atol=0` (exact, NaN-aware).
`test_anomaly_is_prediction_minus_climatology` asserts
`anomaly == temperature − climatology` exactly.

### One honest finding the UI will have to handle

L0 was fitted only where a GLORYS target existed, so **its NaN pattern is a
valid-water-depth mask**. At 100 m on 2023-05-14 the model predicts at 11,268
cells but climatology is defined at only 9,764; at 1000 m, 8,974. The frozen L2
has no bathymetry awareness and **will emit a 1000 m temperature over a shelf
cell with no 1000 m water**.

That prediction is **not suppressed** — §7B.3 forbids silently replacing deep L2
output. Instead the field-view exposes `climatology_defined`, a derived
valid-water-depth mask, so a consumer can render below-seafloor cells distinctly.
It is derived from a frozen artifact already loaded, **never from a target**. A
test asserts the mask is monotonically non-increasing with depth.

Consequence: `anomaly` is NaN below the seafloor, because climatology is. That
is correct, and it is why the point contract emits `null` rather than a number.

## 6. Is target leakage avoided? Were the tests non-destructive?

**Avoided structurally, and proved three independent ways. All non-destructive —
no project file was deleted, renamed, moved, corrupted or overwritten.**

1. **By construction.** `ALLOWED_STORE_VARS` is the seven surface channels plus
   `ocean_mask` and `surface_input_valid`. `_open_surface_store` selects only
   those, so `temp_*` and `target_valid_*` are **physically absent** from the
   Dataset replay holds. A target cannot reach inference even through a coding
   mistake. A second guard raises if a target name ever appears in the selection.
2. **By spying on the openers.** `test_replay_never_opens_a_target_or_argo_file`
   monkeypatches `xarray.open_zarr` / `open_dataset` / `open_mfdataset` and
   `pandas.read_parquet`, runs a full point replay, and asserts nothing matching
   `targets_cache`, `argo` or `embeddings` was opened.
3. **By an isolated environment.** `scripts/replay/phase7a_verify.py` builds a
   **temporary** Zarr store containing only the surface channels and masks — the
   targets are physically absent — and runs replay against it. Result: 15 depths,
   15 finite predictions, 11,136 supported cells. **PASS.** The temp directory is
   deleted afterwards; the real stores are untouched.

Also asserted: no future day is read — a spy on `day_field` confirms only the
requested date's time index is ever indexed
(`test_no_future_day_is_read`).

**On the locked test split:** replay deliberately has no `--allow-test` speed
bump. The locked-test concern is about **targets**, and replay reads none — only
surface inputs. A judge must be able to pick any historical date in the PoC. The
gate that matters is enforced above, not by blocking dates.

## 7. Is the nominal-0 m convention documented?

**Yes**, in five places: the contract module constant, the manifest
(`targets.nominal_zero_m_note`), every `replay_point` JSON response, the API
`/replay/field` payload, and here:

> Nominal 0 m is the shallowest GLORYS target level (approximately 0.494 m), not
> the OSTIA sea-surface-temperature input. The two are physically related but are
> not the same quantity and are not fully independent.

A manifest test asserts the string contains `0.494`.

## 8. What is the uncached `replay_field` wall-clock time?

**Median 0.116 s** over 5 uncached calls with the cache disabled entirely.

| | seconds |
|---|---|
| median wall-clock | **0.116** |
| min / max | 0.103 / 0.199 |
| median inference + L0 | 0.098 |
| warm-up (first call, includes opening the store) | 0.650 |

Measured on the 16-core CPU, `OMP_NUM_THREADS=8`, no GPU.
Raw data: [`outputs/phase7/phase7a_verification.json`](outputs/phase7/phase7a_verification.json)

**What this means for Phase 7B.** At ~0.12 s a whole field can be recomputed
essentially interactively. Consequences:

- A **date change** can run the real frozen model live — no need to pre-render.
  The "demonstrate genuine local computation" requirement is easy to satisfy.
- The **3D depth-scrub does not need per-slice inference at all**: one
  `replay_field` gives all 15 depths, so scrubbing is pure client-side indexing
  of an array already in memory. §7.2's interactivity target is comfortably met.
- The cache is a convenience, not a necessity. A 7.3 MB / 3-entry cache exists
  after this phase's runs; deleting it costs ~0.12 s per date.

## 9. Caching discipline

Cache entries contain **only** output previously produced by the actual
frozen-L2 pipeline. That is enforced by the key, not by trust: the identity
includes the date, the L2 state-dict and encoder hashes, the feature/target
scaler hashes, the climatology hash, the processing version, the grid version,
the patch, and the depth list. Change any of them and every prior entry becomes
unreachable rather than silently reused.

- `inference_source` is reported on every response: `LIVE_MODEL_RUN` or
  `VALIDATED_CACHE`.
- `--force-recompute` (CLI) and `force_recompute=True` (API/Python) bypass a
  populated cache — tested.
- A hand-edited sidecar fails closed: `test_a_tampered_cache_sidecar_is_a_miss_not_a_silent_hit`
  corrupts the recorded identity and asserts the next call is a `LIVE_MODEL_RUN`.
- Round-trip is bit-identical, NaN-aware.

## 10. Location handling

Requested and resolved coordinates are **both** returned. A land or
input-invalid cell is reported with its own status and the **requested cell is
still what gets resolved** — never silently swapped. A nearest usable cell may
be offered as a clearly-labelled *suggestion*.

| status | meaning | tested |
|---|---|---|
| `OK` | ocean, all seven inputs present | ✓ |
| `OUTSIDE_DOMAIN` | outside 5–30 °N / 45–105 °E | ✓ (5 coordinates) |
| `INVALID_OCEAN_CELL` | land | ✓ + suggestion is not a substitution |
| `INPUT_NOT_VALID` | ocean, but an input is missing that day | ✓ |

Dates outside 2015-01-01 → 2024-12-15 raise `OutsideDomain` (tested at both ends
and one day past the record).

## 11. Multi-date replay

`replay_range(start, end, lat, lon)` runs **one independent `replay_field` per
day**. No temporal state, no L3. A test asserts a day taken from a range is
identical to that day requested alone.

## 12. Deliverables

**Code** (`src/oceanembed/replay/`)

| file | role |
|---|---|
| `contract.py` | `FieldView` canonical contract (§7.0), `LocationStatus`, `PointResult`, the 0 m and deep-skill notes |
| `engine.py` | `ReplayEngine` — the one inference path; hash verification; location resolution |
| `cache.py` | provenance-keyed field cache |
| `api.py` | thin local FastAPI wrapper — transport only, no inference |

**Scripts** (`scripts/replay/`) — `write_manifest.py`, `historical_replay.py`
(CLI), `phase7a_verify.py` (timing + isolation).

**Outputs** — `outputs/phase7/final_core_manifest.json`,
`outputs/phase7/phase7a_verification.json`, `outputs/phase7/replay_cache/`.

**CLI**

```bash
python scripts/replay/historical_replay.py --date 2023-05-14 --lat 15.25 --lon 85.75
python scripts/replay/historical_replay.py --date 2023-05-14 --lat 15.25 --lon 85.75 --figure --json p.json
python scripts/replay/historical_replay.py --start 2023-05-12 --end 2023-05-16 --lat 15.25 --lon 85.75
python scripts/replay/historical_replay.py --field --date 2023-05-14 --out field.nc
```

**API** (`python -m uvicorn oceanembed.replay.api:app --port 8000`) —
`/health`, `/manifest`, `/replay/point`, `/replay/range`, `/replay/field`
(full field or one depth slice; the payload Phase 7B's field-view adapter will
consume). Tested to return the same numbers as the Python primitives.

**Tests** — `tests/test_phase7a_replay.py`, **48 tests**, all passing. Full suite
**432 passed** (384 → 432).

## 13. Deviations and notes

1. **FastAPI was built in 7A**, per §5.6.1 of the master prompt, which places the
   backend API in this phase. It is transport only and contains no inference, so
   it is not "UI" and not scaffolding for a later phase's science. New
   dependencies recorded in `requirements.txt`: `fastapi`, `uvicorn[standard]`,
   `httpx2` (the starlette test-client dependency).
2. **Two implementation bugs found and fixed during the phase**, both caught by
   running rather than by inspection: `cache_identity` read a provenance key that
   did not exist (`depths` vs `depths_m`); and `np.savez_compressed` appends
   `.npz` to any path not already ending in it, so the `*.npz.part` temp name
   silently became `*.npz.part.npz` and the atomic rename failed. The cache now
   writes through an open handle. This is the same `.npz`/auto-suffix trap that
   bit the Phase 6A.5 downloader.
3. **Field-view axis order is `(lat, lon, depth)`**, matching the §7.0 contract
   wording "101 × 241 × 15".
4. **Observation, not a claim:** at 15.25 °N 87.75 °E on 2023-05-14 the
   reconstruction shows a −5.8 °C anomaly at 100 m decaying to −0.3 °C at
   1000 m, while the surface anomaly is only −0.9 °C. Two grid cells west the
   100 m anomaly is +0.45 °C. This is the kind of subsurface structure Phase 7D
   exists to examine; nothing has been verified against an external source here
   and no event interpretation is offered.

---

# PHASE 7A GATE

Both primitives work end-to-end on real historical input fields → exact frozen
L2 → 15-depth reconstruction → frozen L0 → anomaly, and all required tests pass.

```
Final core: existing frozen L2
Frozen L2 preserved: YES
Historical point replay: WORKING
Historical field replay: WORKING
Point/field equivalence test: PASS
15-depth profile: WORKING
Climatology + anomaly: WORKING
0m convention documented: YES
replay_field() uncached time: 0.116 seconds (median; min 0.103, max 0.199)
Tests passing: 432 / 432
```

Additional status:

```
Target leakage avoided: YES (structural + opener spy + isolated no-target run)
Target-leakage tests non-destructive: YES
Isolated no-target sanity run: PASS
2024 Argo: PROTECTED (never downloaded; collocation still 2022-01-01..2023-12-31)
Local replay API: WORKING (transport only, no inference)
Cache discipline: provenance-keyed; tampered sidecar fails closed
```

**PHASE 7A COMPLETE — AWAITING REVIEW.**
**Do not proceed to the next phase until the user explicitly replies "CONTINUE".**
