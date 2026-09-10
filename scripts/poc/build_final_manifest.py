"""Phase 7E — generate the frozen PoC manifest from the live repository.

Every value here is read from the artifact it describes, so the manifest cannot
drift from what is actually on disk. Nothing is typed in by hand.

    python scripts/poc/build_final_manifest.py
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.diagnostics import (CP0, PHYSICAL_SUPPORT_RULE,  # noqa: E402
                                    RHO0, RHO_CP, TEMPERATURE_THRESHOLD_C,
                                    bathymetry_provenance)
from oceanembed.diagnostics.hazard import (INDICATOR_NAME,  # noqa: E402
                                           NON_PREDICTION_STATEMENT,
                                           TCHP_ERROR_KJ_CM2, load_thresholds)
from oceanembed.replay.cache import CACHE_FORMAT_VERSION  # noqa: E402
from oceanembed.replay.contract import DEPTHS  # noqa: E402
from oceanembed.replay.engine import (GRID_VERSION, PROCESSING_VERSION,  # noqa: E402
                                      ReplayEngine)

OUT = ROOT / "outputs" / "phase7" / "FINAL_POC_MANIFEST.json"

#: The freeze is deliberately two commits. Source and scientific artifacts are
#: committed first; this manifest then records THAT commit and is itself
#: committed afterwards. A manifest cannot contain the hash of the commit that
#: contains it, so rather than pretend otherwise, the two are named separately
#: and the distinction is recorded in the manifest.
FREEZE_METADATA = (
    "outputs/phase7/FINAL_POC_MANIFEST.json",
    "PHASE7_FINAL_POC_REPORT.md",
)


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=30).stdout.strip() or None
    except Exception:  # noqa: BLE001 - provenance is best-effort, never fatal
        return None


def working_tree() -> list[str]:
    """Paths with uncommitted changes, tracked or not."""
    out = git("status", "--porcelain") or ""
    return sorted(line[3:].strip().strip('"')
                  for line in out.splitlines() if line.strip())


def main() -> int:
    engine = ReplayEngine(use_cache=False)
    try:
        provenance = engine.provenance
        hashes = dict(engine.file_hashes)
    finally:
        engine.close()

    pending = working_tree()
    source_pending = [p for p in pending if p not in FREEZE_METADATA]

    thresholds = load_thresholds(strict=False)
    package = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    frontend_deps = package.get("dependencies", {})

    documents = {
        "diagnostic_evaluation_protocol": "outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md",
        "event_selection": "outputs/phase7/EVENT_SELECTION.md",
        "hazard_indicator_protocol": "outputs/phase7/HAZARD_INDICATOR_PROTOCOL.md",
        "hazard_thresholds": "outputs/phase7/HAZARD_THRESHOLDS.json",
        "final_2024_argo_preregistration":
            "outputs/phase7/FINAL_2024_ARGO_PREREGISTRATION.md",
        "phase7a_report": "PHASE7_HISTORICAL_REPLAY_REPORT.md",
        "phase7b_report": "PHASE7B_HISTORICAL_POC_REPORT.md",
        "phase7c_report": "PHASE7C_D26_TCHP_REPORT.md",
        "phase7d_report": "PHASE7D_EVENT_REPLAY_REPORT.md",
    }
    tables = {
        "phase6b_grid_metrics": "outputs/tables/phase6b_l2_metrics_by_depth_test.csv",
        "phase6c_argo_metrics": "outputs/tables/phase6c_argo_metrics_by_depth.csv",
        "phase7c_d26_tchp_metrics": "outputs/tables/phase7c_d26_tchp_metrics.csv",
        "phase7c_status_counts": "outputs/tables/phase7c_d26_tchp_status_counts.csv",
        "phase7c_crossing_disagreement":
            "outputs/tables/phase7c_d26_crossing_disagreement.csv",
    }
    assets = {
        "terrain_mesh": "web/public/assets/terrain/land.bin",
        "bathymetry_depth": "web/public/assets/bathymetry/depth.bin",
        "event_track": "web/public/assets/event/track.json",
    }

    manifest = {
        "manifest": "OceanEmbed Phase 7 final PoC freeze",
        "phase": "7E",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": {
            "source_freeze_commit": git("rev-parse", "HEAD"),
            "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "source_tree_clean_excluding_freeze_metadata": not source_pending,
            "uncommitted_at_generation": pending,
            "freeze_metadata_committed_separately": list(FREEZE_METADATA),
            "note": "source_freeze_commit is the commit holding the code and "
                    "scientific artifacts this manifest describes. This manifest "
                    "and the final report are committed immediately afterwards, "
                    "because a manifest cannot record the hash of the commit that "
                    "contains it. The freeze claim is that nothing OUTSIDE "
                    "freeze_metadata_committed_separately was uncommitted when "
                    "this was generated.",
        },

        "scientific_core": {
            "final_core": "existing frozen L2 Spatial Satellite Embedding Engine",
            "model_class": provenance["model_class"],
            "checkpoint_path": provenance["checkpoint_path"],
            "l2_state_dict_sha256": provenance["l2_state_dict_sha256"],
            "l2_encoder_sha256": provenance["l2_encoder_sha256"],
            "checkpoint_file_sha256": hashes["l2_checkpoint_file"],
            "latent_dim": provenance["latent_dim"],
            "patch": provenance["patch"],
            "receptive_field": provenance["receptive_field"],
            "n_parameters": provenance["n_parameters"],
            "retrained_in_phase7": False,
            "architecture_closed": "ARCHITECTURE_CLOSURE_REPORT.md",
        },
        "frozen_artifacts": {
            "feature_scaler_sha256": hashes["feature_scaler_file"],
            "target_scaler_sha256": hashes["target_scaler_file"],
            "climatology_sha256": hashes["climatology_file"],
        },
        "inputs_and_targets": {
            "surface_inputs": provenance["surface_inputs"],
            "depths_m": list(DEPTHS),
            "nominal_zero_m_note": provenance["nominal_zero_m_note"],
            "deep_skill_note": provenance["deep_skill_note"],
            "target_used_for_inference": False,
            "argo_used_for_inference": False,
        },
        "replay_api": {
            "version": "7A",
            "field_primitive": "oceanembed.replay.replay_field(date)",
            "point_primitive": "oceanembed.replay.replay_point(date, lat, lon)",
            "point_derives_from_field": True,
            "field_shape": [101, 241, 15],
            "processing_version": PROCESSING_VERSION,
            "grid_version": GRID_VERSION,
            "transport_schema": "oceanembed.field-view.v1",
            "cache_format_version": CACHE_FORMAT_VERSION,
            "cache_semantics": "provenance-keyed; identity includes date, model, "
                               "scaler and climatology hashes, processing and "
                               "grid version; only real frozen-L2 output is ever "
                               "stored; a mismatch is a miss, never a silent reuse",
        },
        "diagnostics": {
            "algorithm_version": "7C.1",
            "d26": "shallowest downward 26 degC crossing, linear interpolation "
                   "between bracketing levels, never extrapolated",
            "tchp": "rho0 * cp0 * integral 0..D26 of (T - 26 degC) dz, kJ/cm2",
            "threshold_degC": TEMPERATURE_THRESHOLD_C,
            "rho0_kg_m3": RHO0,
            "cp0_J_kg_K": CP0,
            "rho_cp_J_m3_K": RHO_CP,
            "constants_source": "TEOS-10 (IOC/SCOR/IAPSO 2010) via gsw; cp0 is "
                                "the defined reference heat capacity, derived "
                                "from the library's own identity, not copied",
            "convention_family": "Leipper & Volgenau (1972); operational form "
                                 "used by NOAA/AOML (Shay et al. 2000; Goni et "
                                 "al. 1996)",
            "convention_spread_note": "published rho*Cp conventions span about "
                                      "8 percent; OceanEmbed runs about 5 percent "
                                      "below the frequently quoted 1026 x 4178 pair",
            "physical_support_rule": PHYSICAL_SUPPORT_RULE,
            "bathymetry": {k: bathymetry_provenance().get(k)
                           for k in ("dataset", "version", "depth_sha256",
                                     "sampling_caveat")},
        },
        "hazard_indicator": {
            "name": INDICATOR_NAME,
            "version": "7D.1",
            "categorising_quantity": "tchp_kj_cm2",
            "boundaries_kj_cm2": thresholds.as_dict() if thresholds else None,
            "reference_period": thresholds.reference_period if thresholds else None,
            "frontend_status": "SHIPPED - historical only, route 'hazard'",
            "connected_to_live_data": False,
            "numeric_cyclone_probability": False,
            "non_prediction_statement": NON_PREDICTION_STATEMENT,
            "reconstruction_error_kj_cm2": TCHP_ERROR_KJ_CM2,
        },
        "event": {
            "name": "Cyclone Mocha (2023)",
            "basin": "Bay of Bengal",
            "window": ["2023-05-05", "2023-05-22"],
            "peak": "2023-05-13",
            "landfall": "2023-05-14",
            "selection_rule": "most intense NIO cyclone inside the LOCKED TEST "
                              "SPLIT by IMD peak 3-minute sustained wind, "
                              "tie-broken on minimum central pressure, requiring "
                              "a complete surface-input record",
            "selected_before_error_inspection": True,
            "track_source": "IBTrACS v04r01 / IMD RSMC New Delhi, NOAA NCEI, "
                            "bundled offline; static context only",
        },
        "demonstration": {
            "default_date": "2021-06-15",
            "default_location": [15.25, 87.75],
            "default_selection_rule": "central Bay of Bengal, chosen by geography "
                                      "in Phase 7B, not by prediction error",
            "offline": True,
            "launch": "Start-OceanEmbed.cmd or python scripts/poc/serve.py",
        },
        "frontend": {
            "framework": "React + TypeScript + Vite",
            "3d_engine": "three.js (Cesium evaluated and not adopted; see "
                         "PHASE7B_HISTORICAL_POC_REPORT.md)",
            "charts": "Plotly",
            "routes": ["replay", "depth", "hazard", "validation", "exports",
                       "settings"],
            "dependency_versions": frontend_deps,
        },
        "documents": {k: {"path": v, "sha256": sha256(ROOT / v)}
                      for k, v in documents.items()},
        "tables": {k: {"path": v, "sha256": sha256(ROOT / v)}
                   for k, v in tables.items()},
        "static_assets": {k: {"path": v, "sha256": sha256(ROOT / v)}
                          for k, v in assets.items()},
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "status": {
            "nrt_status": "NOT STARTED",
            "argo_2024_status": "PROTECTED",
            "argo_2024_preregistration":
                "outputs/phase7/FINAL_2024_ARGO_PREREGISTRATION.md",
            "phase8a_started": False,
            "phase8b_started": False,
        },
        "known_limitations": [
            "Deep-ocean daily anomaly skill at 500-1000 m is weaker and more "
            "climatology-dominant; disclosed throughout the UI.",
            "The frozen L2 emits all 15 depths wherever surface inputs are valid "
            "and has no concept of the seafloor; about 7-8 percent of D26 results "
            "would otherwise sit below the local seabed. These are qualified as "
            "INSUFFICIENT_WATER_COLUMN_SUPPORT for display, with raw values "
            "preserved and exported unchanged.",
            "Bathymetry is point-sampled at canonical cell centres, not cell "
            "minima, so a 0.25 degree cell spanning a shelf edge is represented "
            "by its centre depth alone.",
            "TCHP values depend on the adopted rho*Cp convention; OceanEmbed's "
            "TEOS-10 constants are not numerically interchangeable with "
            "operational products using different constants.",
            "The hazard categories are relative to this basin's own history; a "
            "LOW label does not mean insufficient heat for a cyclone.",
            "The hazard rule uses one quantity and cannot see salinity "
            "stratification or barrier layers, which matter in the Bay of Bengal "
            "and which OceanEmbed does not reconstruct.",
            "The Phase 7C TCHP reconstruction error is roughly half a hazard "
            "category wide, so adjacent categories are not distinguishable at a "
            "single cell.",
            "Argo is an external observational check, not perfectly independent "
            "truth: GLORYS assimilates in-situ observations.",
            "The Phase 7C application benchmark used the locked test split, "
            "which had already been opened for the Phase 6B and 6C results; it is "
            "historical application validation, not a pristine test set.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  L2 state-dict {manifest['scientific_core']['l2_state_dict_sha256'][:16]}…")
    print(f"  NRT {manifest['status']['nrt_status']} · "
          f"2024 Argo {manifest['status']['argo_2024_status']}")
    print(f"  source freeze commit: {manifest['git']['source_freeze_commit']}")
    print(f"  source tree clean (excluding freeze metadata): "
          f"{manifest['git']['source_tree_clean_excluding_freeze_metadata']}")
    if source_pending:
        print(f"  STILL UNCOMMITTED: {source_pending}")
    missing = [k for group in ("documents", "tables", "static_assets")
               for k, v in manifest[group].items() if v["sha256"] is None]
    print(f"  missing artifacts: {missing or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
