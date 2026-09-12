"""Phase 8C, Phase 8: assemble the decision from the executed artifacts.

Applies the pre-registered decision table (c01c170) to what was measured. It
reads results; it never re-scores anything and never softens a gate.

    python scripts/nrt8c/make_decision.py
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

OUT = ROOT / "outputs" / "phase8c"
HASHED = ["OPERATIONAL_CURRENT_SUBSTITUTION_PREREGISTRATION.md", "candidate_product.json",
          "current_compatibility.csv", "substitution_by_depth.csv",
          "target_metrics_by_depth.csv", "target_bootstrap.csv",
          "substitution_result.json", "argo_comparison.csv", "argo_bootstrap.csv",
          "argo_result.json", "argo_comparison_total.csv", "argo_bootstrap_total.csv",
          "argo_result_total.json", "recency_comparison.json"]

APPROVED = "SUBSTITUTE_APPROVED"
MONITORING = "SUBSTITUTE_WITH_MONITORING"
REJECTED = "SUBSTITUTE_REJECTED"


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def main() -> int:
    sub = load("substitution_result.json")
    argo = load("argo_result.json")
    argo_total = load("argo_result_total.json")
    rec = load("recency_comparison.json")
    cand = load("candidate_product.json")

    c3 = sub["phase4_channel_decision"]
    gates = {
        "C1_C2_C3_channel_decision": c3,
        "C3_pass": c3 in (APPROVED, MONITORING),
        "C5_skill_vs_L0": sub["phase5_gates"]["C5_pass"],
        "C6_thermocline": sub["phase5_gates"]["C6_pass"],
        "C7_basins": sub["phase5_gates"]["C7_pass"],
        "C8_observational_non_inferiority": argo["C8_pass"],
    }
    # The pre-registered table: every gate must pass; C8 is not optional.
    if all(gates[k] for k in ("C3_pass", "C5_skill_vs_L0", "C6_thermocline",
                              "C7_basins", "C8_observational_non_inferiority")):
        decision = APPROVED if c3 == APPROVED else MONITORING
    else:
        decision = REJECTED

    failed = [k for k, v in gates.items() if k.endswith(("pass", "_L0", "thermocline",
                                                         "basins", "inferiority"))
              and v is False]

    record = {
        "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phase": "8C",
        "preregistration": "outputs/phase8c/OPERATIONAL_CURRENT_SUBSTITUTION_PREREGISTRATION.md",
        "preregistration_commit": "c01c170",
        "candidate": {"product_id": cand["product_id"], "dataset_id": cand["dataset_id"],
                      "primary_definition": cand["primary_definition"],
                      "secondary_definition": cand["secondary_definition"]},
        "gates": gates,
        "failed_gates": failed,
        "decision": decision,
        "integration_permitted": decision in (APPROVED, MONITORING),
        "evidence": {
            "phase3_band_vs_oscar_final": sub["phase3_compatibility"]["band_full_nio_vs_oscar_final"],
            "phase4_s_ratio_100m": sub["phase4_substitution"]["CANDIDATE"]["s_ratio_100m"],
            "phase4_band_100m": sub["phase4_substitution"]["CANDIDATE"]["band_100m"],
            "phase4_worst_band": sub["phase4_substitution"]["CANDIDATE"]["worst_band"],
            "phase5_depths_beating_L0_of_11": sub["phase5_gates"]["C5_depths_beating_L0_of_11"],
            "phase6_key_depths_spanning_zero": argo["c8_spanning_zero"],
            "phase6_worst_degradation_pct": argo["c8_worst_degradation_pct"],
            "phase6_allowed_degradation_pct": argo["c8_allowed_degradation_pct"],
            "phase6_secondary_variant_worst_degradation_pct":
                argo_total["c8_worst_degradation_pct"],
            "phase6_secondary_variant_pass": argo_total["C8_pass"],
            "phase6_control_reproduces_executed_l2":
                all(v["max_abs_diff"] == 0.0
                    for v in argo["control_reproduces_executed_l2"].values()),
            "phase7_old_common_date": rec["newest_complete_seven_channel_date_with_oscar"],
            "phase7_new_common_date_if_substituted":
                rec["newest_complete_seven_channel_date_with_candidate"],
            "phase7_gain_days": rec["gain_days"],
            "phase7_next_bottleneck": rec["next_bottleneck_after_substitution"],
        },
        "operational_current_source": "OSCAR_L4_OC_NRT_V2.0 (unchanged)",
        "historical_current_source": "OSCAR_L4_OC_FINAL_V2.0 (unchanged)",
        "production_reconstruction_models": 1,
        "l2_retrained": False,
        "historical_replay_changed": False,
        "argo_2024_opened": False,
        "artifacts": {n: hashlib.sha256((OUT / n).read_bytes()).hexdigest()
                      for n in HASHED if (OUT / n).is_file()},
        "source_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                        capture_output=True, text=True).stdout.strip(),
    }
    (OUT / "decision.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"decision": decision, "failed_gates": failed,
                      "gain_days_if_it_had_passed": rec["gain_days"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
