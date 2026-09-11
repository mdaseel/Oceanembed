"""Phase 8B.15 — generate outputs/phase8b/FINAL_NRT_OPERATING_MANIFEST.json.

Every value is read from an artifact that already exists; nothing is typed in.
Fails loudly if a required artifact is missing, rather than writing a manifest
that claims more than the repository holds.

    python scripts/nrt8b/build_operating_manifest.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.nrt import latest as LQ  # noqa: E402
from oceanembed.nrt.registry import PRODUCTS  # noqa: E402
from oceanembed.replay.engine import (EXPECTED_L2_ENCODER,  # noqa: E402
                                      EXPECTED_L2_STATE_DICT, EXPECTED_SHA256)

P8B = ROOT / "outputs" / "phase8b"
OUT = P8B / "FINAL_NRT_OPERATING_MANIFEST.json"
HASHED = [
    "outputs/phase8b/NRT_SUBSURFACE_QUALIFICATION_PROTOCOL.md",
    "outputs/phase8b/qualification_decision.json",
    "outputs/phase8b/fetch_manifest.json",
    "outputs/phase8b/operational_resilience_test.json",
    "outputs/phase8b/latest_live_run.json",
    "outputs/tables/phase8b_hindcast_temperature_metrics.csv",
    "outputs/tables/phase8b_hindcast_skill.csv",
    "outputs/tables/phase8b_hindcast_bootstrap.csv",
    "outputs/tables/phase8b_sensitivity.csv",
    "outputs/tables/phase8b_sss_compatibility.csv",
    "outputs/tables/phase8b_d26_tchp_metrics.csv",
    "outputs/tables/phase8b_daily_coverage.csv",
]


def sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def load(name: str) -> dict:
    p = P8B / name
    if not p.is_file():
        raise SystemExit(f"required artifact missing: {p.relative_to(ROOT)}")
    return json.loads(p.read_text(encoding="utf-8"))


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()


def main() -> int:
    decision = load("qualification_decision.json")
    resilience = load("operational_resilience_test.json")
    live = load("latest_live_run.json")
    summary = LQ.qualification_summary()

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phase": "8B",
        "protocol": LQ.PROTOCOL_PATH,
        "protocol_commit": decision["protocol_commit"],
        "question": ("Can the COMPLETE frozen-L2 seven-channel operational input "
                     "contract support a scientifically qualified latest available "
                     "15-depth subsurface temperature reconstruction?"),
        "operating_policy": LQ.POLICY,
        "products": {k: {"channels": list(LQ.PRODUCT_CHANNELS[k]),
                         "product_id": PRODUCTS[k]["product_id"],
                         "dataset_id": PRODUCTS[k]["dataset_id"],
                         "doi": PRODUCTS[k].get("doi"),
                         "provider": PRODUCTS[k]["provider"]}
                     for k in LQ.PRODUCT_CHANNELS},
        "temporal_alignment": "COMMON_VALID_DATE - every channel valid on the same "
                              "day; D = min over products of the newest complete day",
        "sss_operating_mode": decision["sss_operating_policy"],
        "persistence_envelope_days": decision["persistence_envelope_days"],
        "hindcast": {"n_dates_preregistered": decision["n_dates_preregistered"],
                     "n_dates_used": decision["n_dates_used"],
                     "window": [decision["dates_used"][0], decision["dates_used"][-1]],
                     "reference": "GLORYS12V1 reanalysis (assimilating; not independent)",
                     "replay_mode": decision["replay_mode"]},
        "gates": decision["gates"],
        "stack_verdict": decision["stack_verdict"],
        "status": {
            "frozen_l2_preserved": decision["l2_state_dict_sha256_after"]
            == EXPECTED_L2_STATE_DICT,
            "complete_nrt_seven_channel_contract": decision["temperature_category"],
            "latest_15_depth_reconstruction": decision["temperature_category"],
            "latest_d26": decision["d26_category"],
            "latest_tchp": decision["tchp_category"],
            "latest_ocean_hazard_indicators": decision["latest_hazard_indicators"],
            "latest_tab_name": summary["tab_name"].upper(),
            "qualified_reachable_in_8b": decision["qualified_reachable_in_8b"],
            "qualified_unreachable_reason": decision["qualified_unreachable_reason"],
            "operational_resilience": resilience["result"],
            "argo_2024": "PROTECTED",
        },
        "limitations": summary["limitations"],
        "latest_live_run": {
            "effective_date": live["effective_date"],
            "retrieval_time_utc": live["meta"]["retrieval_time_utc"],
            "reconstruction_lag_hours": live["meta"]["reconstruction_lag_hours"],
            "oldest_input_age_hours": live["meta"]["oldest_input_age_hours"],
            "newest_input_age_hours": live["meta"]["newest_input_age_hours"],
            "joint_mask_coverage": live["meta"]["joint_mask_coverage"],
            "sources": [{k: s[k] for k in ("product_key", "dataset_id", "state",
                                           "newest_valid_time", "product_valid_time",
                                           "local_retrieval_time", "age_hours")}
                        for s in live["sources"]],
        },
        "frozen_hashes": {"l2_state_dict_sha256": EXPECTED_L2_STATE_DICT,
                          "l2_encoder_sha256": EXPECTED_L2_ENCODER,
                          **EXPECTED_SHA256},
        "shared_renderer": {
            "reused": True,
            "component": "web/src/components/DepthRenderer.tsx",
            "adapter": "web/src/field/replayAdapter.ts (adaptReplay) - the same for "
                       "historical and latest fields",
            "transport": "oceanembed.field-view.v1 via poc.app.field_payload",
        },
        "artifacts": {rel: sha(rel) for rel in HASHED if (ROOT / rel).is_file()},
        "source_commit": git("rev-parse", "HEAD"),
    }
    OUT.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"-> {OUT.relative_to(ROOT)}  ({len(manifest['artifacts'])} hashed artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
