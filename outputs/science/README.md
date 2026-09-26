# OceanEmbed — Model Science & Disaster Intelligence artefacts

Protocols were frozen first in [`PREREGISTRATION.md`](PREREGISTRATION.md). Every
artefact below is regenerable; none writes a production model, scaler,
climatology, threshold or the replay cache. 2024 Argo is not read.

| Artefact | Produced by | Protocol |
|---|---|---|
| `cache/attribution/*.json` (gitignored) | `/api/science/attribution` (on request, cached by model hash, date, cell, method, steps, version) | §1 |
| `basin_attribution.json` | `python scripts/science/run_basin_attribution.py` | §1 |
| occlusion (in memory, never stored as a field) | `/api/science/occlusion` | §2 |
| `../models/science/SST_ONLY_s20260905.pt`, `sst_only_eval_meta.json`, `../tables/science/sst_only_*.csv` | `python scripts/science/train_sst_only.py` then `python scripts/science/evaluate_sst_only.py` | §3 |
| `physical_qa_summary.json`, `basin_physics.json` | `python scripts/science/run_physical_qa.py` | §4 |
| `coastal/coastal_context.npz`, `coastal/coastal_units.json`, `coastal/meta.json` | `python scripts/science/build_coastal_context.py` (inputs in `data/raw/geography/`) | §5 |
| stress test (computed per request) | `/api/events/{event_id}/stress-test` | §6 |
| `ri_study/ri_summary.json`, `ri_study/ri_storms_*.csv` | `python scripts/science/run_ri_study.py` | §7 |
| `cache/extreme_baseline/` (gitignored) | `python scripts/science/build_thermal_extreme_baseline.py` | §8 |
| `logs/*.log` | the runs above | — |

Geography sources (downloaded to `data/raw/geography/`, not committed):

- Natural Earth 1:10m Admin-1 states/provinces — public domain, release recorded in `coastal/meta.json` with its SHA256.
- geoBoundaries gbOpen IND ADM2 (districts) — ODbL 1.0, source lgdirectory.gov.in via Pathways Data; boundary id and SHA256 recorded in `coastal/meta.json`.

Tests: `tests/test_science_model.py`, `tests/test_science_physical_qa.py`,
`tests/test_science_context.py`, `tests/test_science_research.py`, and the browser
spec `web/e2e/scienceExpansion.spec.ts`.
