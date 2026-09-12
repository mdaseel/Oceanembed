"""Phase 8C, Phase 7: what the substitution would actually buy operationally.

Compares the newest complete seven-channel date with OSCAR NRT currents against
the same date with the candidate currents, from the providers' own time axes.
The gain is bounded by the NEXT slowest channel, and is reported as measured -
never promised in advance.

    python scripts/nrt8c/run_recency_comparison.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from oceanembed.nrt import latest as LQ  # noqa: E402

CANDIDATE_DATASET = "cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m"
OUT = ROOT / "outputs" / "phase8c" / "recency_comparison.json"


def candidate_dates() -> set:
    import copernicusmarine as cm
    ds = cm.open_dataset(dataset_id=CANDIDATE_DATASET)
    try:
        t = pd.DatetimeIndex(ds.time.values)
    finally:
        ds.close()
    return {d.normalize() for d in t}


def main() -> int:
    t0 = time.time()
    LQ.refresh_discovery()
    sets, errors = LQ.channel_dates()
    cand = candidate_dates()
    end = pd.Timestamp.utcnow().tz_localize(None).normalize()
    start = end - pd.Timedelta(days=LQ.LOOKBACK_DAYS)
    cand_window = {d for d in cand if start <= d <= end}

    with_oscar = LQ.common_dates(sets)
    swapped = {**sets, "currents_nrt": cand_window}
    with_candidate = LQ.common_dates(swapped)

    def newest(s):
        return str(max(s).date()) if s else None

    per_channel = {k: newest(v) for k, v in sets.items()}
    per_channel["candidate_currents"] = newest(cand_window)

    old, new = newest(with_oscar), newest(with_candidate)
    bottleneck_old = min(sets, key=lambda k: max(sets[k]) if sets[k] else pd.Timestamp.min)
    without_currents = {k: v for k, v in swapped.items() if k != "currents_nrt"}
    next_bottleneck = min(without_currents,
                          key=lambda k: max(without_currents[k]) if without_currents[k]
                          else pd.Timestamp.min)

    record = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "per_channel_newest": per_channel,
        "newest_complete_seven_channel_date_with_oscar": old,
        "newest_complete_seven_channel_date_with_candidate": new,
        "gain_days": (None if not (old and new)
                      else int((pd.Timestamp(new) - pd.Timestamp(old)).days)),
        "current_bottleneck_with_oscar": bottleneck_old,
        "next_bottleneck_after_substitution": next_bottleneck,
        "next_bottleneck_newest": per_channel.get(next_bottleneck),
        "candidate_dataset": CANDIDATE_DATASET,
        "discovery_errors": errors,
        "note": ("The gain is limited by the next slowest mandatory channel; the "
                 "candidate only moves the date as far as that channel allows."),
        "wall_clock_seconds": round(time.time() - t0, 1),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
