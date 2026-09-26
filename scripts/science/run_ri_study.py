"""Run the retrospective rapid-intensification study (PREREGISTRATION §7).

Reads IBTrACS, applies the frozen eligibility rule, samples frozen-L2 historical
fields ahead of each eligible storm through the validated replay path, and writes
descriptive group comparisons. Nothing here predicts, classifies or scores.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import pandas as pd

from oceanembed.events import track_analysis as track_lib
from oceanembed.replay.engine import ReplayEngine
from oceanembed.science import ri_study as R


def main() -> int:
    R.OUT.mkdir(parents=True, exist_ok=True)
    engine = ReplayEngine()
    csv_sha = hashlib.sha256(R.CSV.read_bytes()).hexdigest()
    storms = R.read_storms()
    avail_cache: dict = {}

    def available(date: str) -> bool:
        if date not in avail_cache:
            try:
                when = engine._normalise_date(date)
                ds = engine._store(when.year)
                t = engine._time_index(ds, when)
                avail_cache[date] = bool(np.asarray(ds["surface_input_valid"].isel(time=t).values).any())
            except Exception:  # noqa: BLE001 - outside the record is simply unavailable
                avail_cache[date] = False
        return avail_cache[date]

    views: dict = {}

    def values_for(rec: dict) -> dict:
        date = rec["pair"]["sample_date"]
        if date not in views:
            views[date] = track_lib.field_context(engine.replay_field(date))
        analysis = track_lib.analyze(views[date], rec["path"])
        return R.weighted_path_values(analysis)

    results = {}
    for wind in ("imd", "jtwc"):
        records = []
        for sid, storm in sorted(storms.items()):
            rec = R.storm_record(storm, wind, available)
            if rec["eligible"]:
                rec["values"] = values_for(rec)
            records.append(rec)
        eligible = [r for r in records if r["eligible"]]
        excluded = [r for r in records if not r["eligible"]]
        in_seasons = [r for r in records if R.SEASONS[0] <= r["season"] <= R.SEASONS[1]]
        reasons = pd.Series([r["exclusion"] for r in excluded if r["season"] >= R.SEASONS[0]
                             and r["season"] <= R.SEASONS[1]]).value_counts().to_dict()
        recent = [r for r in eligible if r["season"] >= 2021]
        tchp = [(r["max_dv_kt"], r["values"]["tchp"]) for r in eligible if r["values"]["tchp"] is not None]
        spearman = None
        if len(tchp) >= R.MIN_GROUP:
            from scipy.stats import spearmanr
            rho = spearmanr([x for x, _ in tchp], [y for _, y in tchp])
            spearman = {"rho": float(rho.statistic), "p_value": float(rho.pvalue), "n": len(tchp),
                        "note": "storm-level, descriptive; pairs from one storm are not independent "
                                "and are not used"}
        results[wind] = {
            "wind_source": "IMD 3-min (NEWDELHI_WIND)" if wind == "imd" else "JTWC 1-min (USA_WIND) - sensitivity",
            "counts": {"storms_in_file_2015_2024": len(in_seasons), "eligible": len(eligible),
                       "ri": sum(1 for r in eligible if r["ri"]),
                       "non_ri": sum(1 for r in eligible if not r["ri"]),
                       "excluded": len(in_seasons) - len(eligible)},
            "exclusion_reasons": reasons,
            "comparison": R.compare_groups(eligible),
            "sensitivity_2021_2024": {**R.compare_groups(recent), "n_storms": len(recent)},
            "storm_level_spearman_max_dv_vs_tchp": spearman,
            "storms": [{k: v for k, v in r.items() if k not in ("path",)} for r in records
                       if R.SEASONS[0] <= r["season"] <= R.SEASONS[1]],
        }
        rows = [{"sid": r["sid"], "name": r["name"], "season": r["season"], "wind": wind,
                 "eligible": r["eligible"], "exclusion": r["exclusion"], "ri": r["ri"],
                 "max_dv_kt": r.get("max_dv_kt"), "split": r.get("split"),
                 "t0": r.get("pair", {}).get("t0"), "sample_date": r.get("pair", {}).get("sample_date"),
                 **({f"v_{k}": v for k, v in r["values"].items()} if r["eligible"] else {})}
                for r in records if R.SEASONS[0] <= r["season"] <= R.SEASONS[1]]
        pd.DataFrame(rows).to_csv(R.OUT / f"ri_storms_{wind}.csv", index=False)

    summary = {
        "title": "Retrospective rapid-intensification study",
        "exploratory": True, "protocol": R.PROTOCOL, "definition": R.DEFINITION,
        "sampling": R.SAMPLING, "wording": R.WORDING,
        "constants": {"ri_kt": R.RI_KT, "min_peak_kt": R.MIN_PEAK_KT,
                      "window_hours": R.WINDOW_HOURS, "seasons": list(R.SEASONS),
                      "sample_offset_days": R.SAMPLE_OFFSET_DAYS, "bootstrap": R.BOOTSTRAP,
                      "seed": R.SEED, "min_group": R.MIN_GROUP},
        "source": {"dataset": "IBTrACS v04r01 North Indian", "file": R.CSV.name, "sha256": csv_sha},
        "model_sha256": engine.l2_state_dict_sha256,
        "split_disclosure": "2015-2020 sampling dates are in-sample for the frozen L2; see the "
                            "2021-2024 sensitivity.",
        "no_classifier": True, "no_probability": True,
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "results": results,
    }
    (R.OUT / "ri_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    for wind, res in results.items():
        print(wind, json.dumps(res["counts"]), json.dumps(res["exclusion_reasons"]))
        for v in res["comparison"]["variables"]:
            print("  ", v["variable"], v["n_ri"], v["n_non_ri"],
                  v["ri"] and round(v["ri"]["median"], 2), v["non_ri"] and round(v["non_ri"]["median"], 2),
                  v.get("p_value"), v.get("p_holm"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
