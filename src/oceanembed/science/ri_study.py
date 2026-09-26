"""Retrospective rapid-intensification study (PREREGISTRATION §7).

Exploratory and retrospective. The external observed intensity record (IBTrACS)
defines the groups; OceanEmbed fields are only sampled ahead of the storm and
never receive intensity. There is no classifier, no threshold search and no
probability. A null result is a valid result.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import REPO_ROOT
from ..events.rule import RECORD_END, RECORD_START, fixes_from_rows, inside_domain

CSV = REPO_ROOT / "data" / "raw" / "ibtracs" / "ibtracs.NI.list.v04r01.csv"
OUT = REPO_ROOT / "outputs" / "science" / "ri_study"
PROTOCOL = "outputs/science/PREREGISTRATION.md §7"
RI_KT = 30.0
MIN_PEAK_KT = 34.0
WINDOW_HOURS = 24
SEASONS = (2015, 2024)
SAMPLE_OFFSET_DAYS = 1
BOOTSTRAP = 2000
SEED = 20260914
MIN_GROUP = 5
WIND = {"imd": "imd_wind_kt", "jtwc": "usa_wind_kt"}
VARIABLES = [
    ("tchp", "TCHP (along-path mean)", "kJ/cm²", True),
    ("d26", "D26 (along-path mean)", "m", False),
    ("t50", "50 m temperature", "°C", False),
    ("a50", "50 m anomaly", "°C", False),
    ("t75", "75 m temperature", "°C", False),
    ("a75", "75 m anomaly", "°C", False),
    ("t100", "100 m temperature", "°C", False),
    ("a100", "100 m anomaly", "°C", False),
]
DEFINITION = (f"RI pair: IMD 3-min wind increase >= {RI_KT:.0f} kt between two IBTrACS fixes "
              f"exactly {WINDOW_HOURS} h apart, both over water (DIST2LAND > 0) and inside "
              f"5-30N 45-105E; RI storm: any such pair. Storms: seasons {SEASONS[0]}-{SEASONS[1]} "
              f"with an IMD fix >= {MIN_PEAK_KT:.0f} kt.")
SAMPLING = (f"For each storm, the eligible pair with the largest 24-h change (ties: earliest). "
            f"Field valid on date(t0) - {SAMPLE_OFFSET_DAYS} day; IBTrACS positions t0..t0+24 h "
            "resampled every 10 km; length-weighted mean over in-domain samples with a value.")
WORDING = ("Retrospective association between reconstructed ocean heat ahead of real storms "
           "and their observed intensity change. Not a predictor: no classifier, no "
           "probability and no forecast.")


def read_storms(path: Path = CSV) -> dict:
    storms = defaultdict(lambda: {"rows": []})
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                season = int(row["SEASON"])
            except (TypeError, ValueError):
                continue                       # the IBTrACS units row
            if row.get("BASIN", "").strip() != "NI":
                continue
            s = storms[row["SID"]]
            s.update({"sid": row["SID"], "name": row["NAME"].strip(), "season": season,
                      "subbasin": row.get("SUBBASIN", "").strip()})
            s["rows"].append(row)
    return dict(storms)


def pairs_24h(fixes: list[dict], wind_key: str) -> list[dict]:
    by_time = {pd.Timestamp(p["time"]): p for p in fixes}
    out = []
    for t0, a in sorted(by_time.items()):
        b = by_time.get(t0 + pd.Timedelta(hours=WINDOW_HOURS))
        if b is None or a[wind_key] is None or b[wind_key] is None:
            continue
        over_water = (a["dist2land_km"] or 0) > 0 and (b["dist2land_km"] or 0) > 0
        in_domain = inside_domain(a["lat"], a["lon"]) and inside_domain(b["lat"], b["lon"])
        sample = (t0.normalize() - pd.Timedelta(days=SAMPLE_OFFSET_DAYS))
        out.append({"t0": str(t0), "t1": str(t0 + pd.Timedelta(hours=WINDOW_HOURS)),
                    "v0": a[wind_key], "v1": b[wind_key], "dv": b[wind_key] - a[wind_key],
                    "over_water": over_water, "in_domain": in_domain,
                    "sample_date": str(sample.date()),
                    "in_record": RECORD_START <= sample <= RECORD_END})
    return out


def storm_record(storm: dict, wind: str = "imd", available=lambda date: True) -> dict:
    key = WIND[wind]
    fixes = fixes_from_rows(storm["rows"])
    base = {"sid": storm["sid"], "name": storm["name"], "season": storm["season"],
            "subbasin": storm.get("subbasin"), "wind_source": wind}
    peak = max((p[key] for p in fixes if p[key] is not None), default=None)
    base["peak_wind_kt"] = peak

    def excluded(reason):
        return {**base, "eligible": False, "exclusion": reason, "ri": None}

    if not SEASONS[0] <= storm["season"] <= SEASONS[1]:
        return excluded("season outside 2015-2024")
    if peak is None or peak < MIN_PEAK_KT:
        return excluded(f"no {wind.upper()} fix >= {MIN_PEAK_KT:.0f} kt")
    pairs = pairs_24h(fixes, key)
    if not pairs:
        return excluded("no two fixes exactly 24 h apart with wind values")
    usable = [p for p in pairs if p["over_water"] and p["in_domain"]]
    if not usable:
        return excluded("no 24-h pair over water inside the OceanEmbed domain")
    usable = [p for p in usable if p["in_record"] and available(p["sample_date"])]
    if not usable:
        return excluded("sampling date outside the record or without surface input")
    best = sorted(usable, key=lambda p: (-p["dv"], p["t0"]))[0]
    t0, t1 = pd.Timestamp(best["t0"]), pd.Timestamp(best["t1"])
    path = [{"lat": p["lat"], "lon": p["lon"], "time": p["time"], "point_type": "observed"}
            for p in fixes if t0 <= pd.Timestamp(p["time"]) <= t1]
    return {**base, "eligible": True, "exclusion": None, "n_pairs": len(usable),
            "max_dv_kt": best["dv"], "ri": bool(any(p["dv"] >= RI_KT for p in usable)),
            "pair": best, "path": path, "split": split_name(best["sample_date"])}


def split_name(date: str) -> str:
    d = pd.Timestamp(date)
    return "train" if d.year <= 2020 else "validation" if d.year == 2021 else "test"


def weighted_path_values(analysis: dict) -> dict:
    samples = [s for s in analysis["samples"] if s["in_domain"]]

    def mean(get):
        vals = [(get(s), s["length_km"]) for s in samples if get(s) is not None]
        if not vals:
            return None
        v = np.array([x for x, _ in vals], dtype="float64")
        w = np.array([x for _, x in vals], dtype="float64")
        return float(np.average(v, weights=w)) if w.sum() > 0 else float(v.mean())

    out = {"tchp": mean(lambda s: s["tchp"]), "d26": mean(lambda s: s["d26"])}
    for d in (50, 75, 100):
        out[f"t{d}"] = mean(lambda s, d=d: s["levels"][str(d)]["temperature"])
        out[f"a{d}"] = mean(lambda s, d=d: s["levels"][str(d)]["anomaly"])
    total = sum(s["length_km"] for s in samples)
    high = sum(s["length_km"] for s in samples if s["category"] == "HIGH")
    out["high_fraction"] = None if total <= 0 else high / total
    out["n_samples"] = len(samples)
    return out


def holm(pvalues: list[float | None]) -> list[float | None]:
    idx = [i for i, p in enumerate(pvalues) if p is not None]
    order = sorted(idx, key=lambda i: pvalues[i])
    m = len(order)
    adjusted: list[float | None] = [None] * len(pvalues)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def compare_groups(records: list[dict], seed: int = SEED) -> dict:
    """Descriptive group comparison; tests only when both groups have >= MIN_GROUP storms."""
    from scipy.stats import mannwhitneyu
    ri = [r for r in records if r["ri"]]
    non = [r for r in records if r["ri"] is False]
    testable = len(ri) >= MIN_GROUP and len(non) >= MIN_GROUP
    rng = np.random.default_rng(seed)
    rows, raw_p = [], []
    for key, label, unit, primary in VARIABLES:
        a = np.array([r["values"][key] for r in ri if r["values"][key] is not None], dtype="float64")
        b = np.array([r["values"][key] for r in non if r["values"][key] is not None], dtype="float64")
        row = {"variable": key, "label": label, "unit": unit, "primary": primary,
               "n_ri": int(a.size), "n_non_ri": int(b.size)}
        for name, v in (("ri", a), ("non_ri", b)):
            row[name] = ({"median": float(np.median(v)), "q1": float(np.percentile(v, 25)),
                          "q3": float(np.percentile(v, 75)), "min": float(v.min()),
                          "max": float(v.max())} if v.size else None)
        p = None
        if testable and a.size >= MIN_GROUP and b.size >= MIN_GROUP:
            res = mannwhitneyu(a, b, alternative="two-sided")
            p = float(res.pvalue)
            row["mann_whitney_u"] = float(res.statistic)
            row["rank_biserial"] = float(2 * res.statistic / (a.size * b.size) - 1)
            boots = [np.median(rng.choice(a, a.size)) - np.median(rng.choice(b, b.size))
                     for _ in range(BOOTSTRAP)]
            row["median_difference"] = float(np.median(a) - np.median(b))
            row["median_difference_ci95"] = [float(np.percentile(boots, 2.5)),
                                             float(np.percentile(boots, 97.5))]
        row["p_value"] = p
        raw_p.append(p)
        rows.append(row)
    for row, adj in zip(rows, holm(raw_p)):
        row["p_holm"] = adj
    return {"n_ri": len(ri), "n_non_ri": len(non), "tests_run": testable,
            "tests_note": None if testable else
            f"fewer than {MIN_GROUP} storms in a group: descriptive only, no test",
            "variables": rows}
