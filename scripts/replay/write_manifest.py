"""Phase 7A §4.1 — write outputs/phase7/final_core_manifest.json.

Records what the frozen core IS, by reading it. Nothing is copied from prose and
no checkpoint is duplicated or rewritten: the manifest points at the existing
artifacts and records their hashes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd

from oceanembed.config import EAST, NORTH, REPO_ROOT, RESOLUTION, SOUTH, WEST
from oceanembed.ml.features import SURFACE
from oceanembed.ml.patches import N_CHANNELS, N_DATA_CHANNELS
from oceanembed.replay.contract import DEEP_SKILL_NOTE, DEPTHS, NOMINAL_ZERO_M_NOTE
from oceanembed.replay.engine import (CLIMATOLOGY, FEATURE_SCALER, GRID_VERSION,
                                      L2_CHECKPOINT, PROCESSING_VERSION,
                                      TARGET_SCALER, ReplayEngine)

OUT = REPO_ROOT / "outputs" / "phase7"


def _json_default(o):
    """NetCDF attrs come back as numpy scalars; keep the manifest serialisable."""
    import numpy as np
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"{type(o).__name__} is not JSON serializable")


def main() -> int:
    eng = ReplayEngine(use_cache=False)
    OUT.mkdir(parents=True, exist_ok=True)
    rel = lambda p: str(Path(p).relative_to(REPO_ROOT)).replace("\\", "/")  # noqa: E731

    manifest = {
        "generated": str(pd.Timestamp.utcnow().tz_localize(None)),
        "phase": "7A",
        "final_core_decision": {
            "model_name": "L2 Spatial Satellite Embedding Engine",
            "decision": "FINAL CORE — unchanged",
            "source": "ARCHITECTURE_CLOSURE_REPORT.md",
            "rejected_alternatives": {
                "L3_temporal_GRU": "tested, rejected — validation gain did not "
                                   "generalise out of sample",
                "L2_RESIDUAL_climatology_residual": "tested, rejected — worse at "
                                                    "every depth 0-500 m; 3 of 4 "
                                                    "pre-registered gate criteria failed",
                "EOF_decoder": "diagnosed only; no decoder adopted",
                "ViT_GNN_autoencoder": "not justified before SIH; see ARCHITECTURE_REVIEW.md",
            },
        },
        "model": {
            "model_class": "oceanembed.ml.l2_model.L2EmbeddingModel",
            "checkpoint_path": rel(L2_CHECKPOINT),
            "checkpoint_file_sha256": eng.file_hashes["l2_checkpoint_file"],
            "l2_state_dict_sha256": eng.l2_state_dict_sha256,
            "l2_encoder_sha256": eng.l2_encoder_sha256,
            "patch": eng.patch,
            "receptive_field": eng.receptive_field,
            "latent_dim": eng.latent,
            "n_parameters": eng.n_params,
            "n_encoder_parameters": eng.model.n_encoder_parameters,
            "dilations": [int(d) for d in eng.model.encoder.dilations],
        },
        "inputs": {
            "seven_physical_inputs": list(SURFACE),
            "n_data_channels": N_DATA_CHANNELS,
            "n_model_channels": N_CHANNELS,
            "mask_semantics": {
                "channels": "7 standardised data channels + 1 validity-mask channel",
                "joint_mask": "isfinite(all seven surface channels).all(axis=0) — a "
                              "SINGLE joint mask; it cannot express a per-channel outage",
                "missing_is_not_zero": "missing cells are set to 0 AFTER standardisation "
                                       "(the training mean) and flagged by the mask channel",
                "edges": "internal zero-pad by patch//2 with mask=0; no external halo, "
                         "no reflection or replication",
            },
            "products": {
                "sst": "OSTIA L4 REP (DOI 10.48670/moi-00168)",
                "sss": "CMEMS MULTIOBS (DOI 10.48670/moi-00051)",
                "sla": "DUACS L4 C3S two-satellite (DOI 10.48670/moi-00145)",
                "current_u/current_v": "OSCAR L4 Final v2.0 (DOI 10.5067/OSCAR-25F20)",
                "wind_u/wind_v": "CCMP v3.1 (DOI 10.5067/CCMP-6HW10M-L4V31)",
            },
        },
        "targets": {
            "depths_m": list(DEPTHS),
            "n_targets": len(DEPTHS),
            "training_target_product": "GLORYS12V1 thetao (DOI 10.48670/moi-00021)",
            "nominal_zero_m_note": NOMINAL_ZERO_M_NOTE,
            "deep_skill_note": DEEP_SKILL_NOTE,
        },
        "frozen_artifacts": {
            "feature_scaler": {"path": rel(FEATURE_SCALER),
                               "sha256": eng.file_hashes["feature_scaler_file"],
                               "fitted_on": eng.feature_scaler.fitted_on},
            "target_scaler": {"path": rel(TARGET_SCALER),
                              "sha256": eng.file_hashes["target_scaler_file"],
                              "fitted_on": eng.target_scaler.fitted_on},
            "l0_climatology": {"path": rel(CLIMATOLOGY),
                               "sha256": eng.file_hashes["climatology_file"],
                               "fitted_on": eng.climatology.meta.get("fitted_on"),
                               "method": eng.climatology.meta.get("method"),
                               "n_harmonics": eng.climatology.meta.get("n_harmonics"),
                               "fit_start": eng.climatology.meta.get("fit_start"),
                               "fit_end": eng.climatology.meta.get("fit_end")},
        },
        "grid": {
            "domain": {"south": SOUTH, "north": NORTH, "west": WEST, "east": EAST},
            "resolution_deg": RESOLUTION,
            "shape": [int(eng.lat.size), int(eng.lon.size)],
            "lat_first_last": [float(eng.lat[0]), float(eng.lat[-1])],
            "lon_first_last": [float(eng.lon[0]), float(eng.lon[-1])],
            "grid_version": GRID_VERSION,
        },
        "replay": {
            "processing_version": PROCESSING_VERSION,
            "field_primitive": "oceanembed.replay.replay_field(date)",
            "point_primitive": "oceanembed.replay.replay_point(date, lat, lon)",
            "point_derives_from_field": True,
            "cell_support_rule": (
                "predictions are produced at the cells where THAT date's "
                "surface_input_valid is true, which is by construction identical "
                "to the joint validity mask day_field computes internally; "
                "off-support cells are NaN, never zero and never interpolated"),
            "anomaly_definition": "frozen_L2_prediction - frozen_L0_climatology",
            "field_view_shape": "(nlat, nlon, n_depths) = (101, 241, 15)",
        },
        "documentation": {
            "architecture_closure": "ARCHITECTURE_CLOSURE_REPORT.md",
            "architecture_review": "ARCHITECTURE_REVIEW.md",
            "l2_report": "PHASE6B_L2_REPORT.md",
            "argo_validation": "PHASE6C_ARGO_VALIDATION_REPORT.md",
            "nrt_compatibility": "PHASE6C_NRT_COMPATIBILITY_REPORT.md",
        },
        "holdout_status": {
            "argo_2024": "PROTECTED",
            "note": "never downloaded, opened, collocated or scored; replay reads "
                    "no Argo data at all",
        },
    }

    path = OUT / "final_core_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, default=_json_default), encoding="utf-8")
    print(f"wrote {path}")
    print(f"  L2 state-dict {eng.l2_state_dict_sha256[:16]}  "
          f"encoder {eng.l2_encoder_sha256[:16]}")
    print(f"  grid {eng.lat.size}x{eng.lon.size}  depths {len(DEPTHS)}  "
          f"params {eng.n_params:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
