"""Phase 8B follow-up (2026-09-12): one controlled live check of date resolution.

Reports, per channel, what the providers actually hold; the newest common date
under the corrected intersection semantics; the seven-day availability window;
and then produces the two newest qualified states through the same frozen path
so the UI can show them and they can be compared.

Writes outputs/phase8b/latest_date_verification.json.

    python scripts/nrt8b/verify_latest_dates.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from oceanembed.nrt import latest as LQ  # noqa: E402
from oceanembed.replay.engine import (EXPECTED_L2_STATE_DICT,  # noqa: E402
                                      ReplayEngine, state_dict_sha256)

OUT = ROOT / "outputs" / "phase8b" / "latest_date_verification.json"


def main() -> int:
    engine = ReplayEngine()
    sha_before = state_dict_sha256(engine.model.state_dict())
    LQ.refresh_discovery()

    sets, errors = LQ.channel_dates()
    newest, records = LQ.resolve_common_date(sets, errors)
    window = LQ.available_window(7, sets, errors)

    per_channel = {}
    for key in LQ.PRODUCT_CHANNELS:
        days = sorted(sets.get(key, set()))
        per_channel[key] = {
            "channels": list(LQ.PRODUCT_CHANNELS[key]),
            "dataset_id": LQ.PRODUCTS[key]["dataset_id"],
            "newest_available_date": str(days[-1].date()) if days else None,
            "n_dates_in_window": len(days),
            "dates_retrievable": [str(d.date()) for d in days[-8:]],
            "error": errors.get(key),
        }
    print("newest common qualified date:", window["newest_qualified_date"])
    for k, v in per_channel.items():
        print(f"  {k:20s} newest {v['newest_available_date']}  "
              f"({v['n_dates_in_window']} dates in window)")
    for row in window["days"]:
        print(f"  {row['date']}  {row['status']}  {row.get('reason', '')}")

    produced = []
    fields = {}
    available = [r["date"] for r in window["days"] if r["status"] == "AVAILABLE"]
    for date in available[-2:]:                       # the two newest, one pass each
        try:
            # An immutable field already produced for this exact date is reused,
            # so a re-run does not hit the providers again.
            result = LQ.load_daily(engine, date)
            reused = result is not None
            if result is None:
                result = LQ.latest_qualified_field(engine, dates=sets,
                                                   day=pd.Timestamp(date))
                LQ.save_snapshot(result, LQ.daily_cache_dir(date))
                if date == window["newest_qualified_date"]:
                    LQ.save_snapshot(result)
            fields[date] = result.view.temperature
            produced.append({
                "date": date,
                "state": "QUALIFIED",
                "served_from": ("immutable per-date cache" if reused
                                else "new frozen-L2 run"),
                "joint_mask_coverage": result.meta["joint_mask_coverage"],
                "reconstruction_lag_hours": result.meta["reconstruction_lag_hours"],
                "oldest_input_age_hours": result.meta["oldest_input_age_hours"],
                "per_source": {s["product_key"]: {
                    "product_valid_time": s["product_valid_time"],
                    "local_retrieval_time": s["local_retrieval_time"],
                    "age_hours": s["age_hours"], "state": s["state"]}
                    for s in result.sources},
                "n_supported_cells": result.view.provenance["n_supported_cells"],
            })
            print(f"  produced {date}: coverage "
                  f"{result.meta['joint_mask_coverage']:.4f}, lag "
                  f"{result.meta['reconstruction_lag_hours']:.1f} h")
        except LQ.LatestRefused as exc:
            produced.append({"date": date, "state": "REFUSED",
                             "reasons": exc.reasons})
            print(f"  refused {date}: {exc.reasons}")

    differ = None
    if len(fields) == 2:
        a, b = [fields[d] for d in sorted(fields)]
        both = np.isfinite(a) & np.isfinite(b)
        differ = {"compared_dates": sorted(fields),
                  "identical": bool(np.array_equal(a, b, equal_nan=True)),
                  "max_abs_difference_degC": float(np.abs(a[both] - b[both]).max()),
                  "mean_abs_difference_degC": float(np.abs(a[both] - b[both]).mean())}
        print("  fields differ:", not differ["identical"],
              "max", round(differ["max_abs_difference_degC"], 3), "degC")

    sha_after = state_dict_sha256(engine.model.state_dict())
    record = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phase": "8B follow-up",
        "semantics": "newest date in the INTERSECTION of every channel's usable dates",
        "per_channel": per_channel,
        "newest_qualified_date": window["newest_qualified_date"],
        "seven_day_window": window["days"],
        "discovery_errors": errors,
        "produced_states": produced,
        "two_dates_differ": differ,
        "l2_state_dict_sha256_before": sha_before,
        "l2_state_dict_sha256_after": sha_after,
        "frozen_l2_unchanged": sha_before == sha_after == EXPECTED_L2_STATE_DICT,
        "argo_opened": False,
    }
    OUT.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    print("->", OUT.relative_to(ROOT))
    engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
