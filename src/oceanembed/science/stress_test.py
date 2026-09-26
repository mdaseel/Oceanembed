"""Historical-track stress test (PREREGISTRATION §6).

The same observed IBTrACS geometry, unmoved, sampled against the historical event
field and against the latest qualified field. The difference describes how the
two ocean states differ along one fixed line on the map. It says nothing about any
future storm.
"""
from __future__ import annotations

LABEL = "REPLAYED HISTORICAL GEOMETRY — NOT A FORECAST OR PREDICTION"
NOTE = ("The observed track of a past cyclone is used only as a fixed line on the map. It "
        "is not moved, re-timed or extrapolated, no intensity is inferred, and nothing "
        "implies that this storm, or any storm, will recur along it.")


def _v(x):
    return None if x is None else float(x)


def _pick(summary: dict) -> dict:
    s = summary
    out = {
        "peak_tchp": _v((s["tchp"]["max"] or {}).get("value")),
        "median_tchp": _v(s["tchp"]["median"]),
        "high_km": _v(s["category_distance_km"].get("HIGH", 0.0)),
        "elevated_km": _v(s["category_distance_km"].get("ELEVATED", 0.0)),
    }
    for d in ("50", "75", "100"):
        out[f"max_anomaly_{d}m"] = _v((s["anomaly"][d]["max"] or {}).get("value"))
        out[f"min_anomaly_{d}m"] = _v((s["anomaly"][d]["min"] or {}).get("value"))
    return out


METRIC_LABELS = {
    "peak_tchp": ("Peak TCHP", "kJ/cm²"), "median_tchp": ("Median TCHP", "kJ/cm²"),
    "high_km": ("HIGH thermal-support length", "km"),
    "elevated_km": ("ELEVATED thermal-support length", "km"),
    "max_anomaly_50m": ("Largest 50 m anomaly", "°C"), "min_anomaly_50m": ("Lowest 50 m anomaly", "°C"),
    "max_anomaly_75m": ("Largest 75 m anomaly", "°C"), "min_anomaly_75m": ("Lowest 75 m anomaly", "°C"),
    "max_anomaly_100m": ("Largest 100 m anomaly", "°C"), "min_anomaly_100m": ("Lowest 100 m anomaly", "°C"),
}


def compare(historical: dict, latest: dict) -> list[dict]:
    h, l = _pick(historical["summary"]), _pick(latest["summary"])
    rows = []
    for key, (label, unit) in METRIC_LABELS.items():
        a, b = h[key], l[key]
        rows.append({"metric": key, "label": label, "unit": unit, "historical": a, "latest": b,
                     "difference": None if a is None or b is None else b - a})
    return rows


def same_geometry(points_a: list[dict], points_b: list[dict]) -> bool:
    return [(p["lat"], p["lon"]) for p in points_a] == [(p["lat"], p["lon"]) for p in points_b]
