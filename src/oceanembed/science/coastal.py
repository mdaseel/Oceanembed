"""Static coastal and administrative context (PREREGISTRATION §5).

Geographic exposure context only: which coast a grid cell faces and how far away
it is. It carries no hazard, damage or risk meaning, and OceanEmbed's thermal
state never changes it.

The lookup artefact is built by ``scripts/science/build_coastal_context.py`` from
Natural Earth Admin-1 (public domain) and geoBoundaries IND ADM2 (ODbL 1.0).
"""
from __future__ import annotations

import json
import math
from functools import lru_cache

import numpy as np

from ..config import REPO_ROOT

ARTIFACT_DIR = REPO_ROOT / "outputs" / "science" / "coastal"
EARTH_RADIUS_KM = 6371.0088
WORDING = ("Geographic exposure context only. OceanEmbed does not predict coastal "
           "damage, landfall or risk; distance is from the 0.25 degree cell centre to the "
           "nearest mapped coastline of that administrative unit.")
DISTRICT_MATCH_KM = 10.0


class CoastalContextUnavailable(RuntimeError):
    pass


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.minimum(1.0, np.sqrt(a)))


@lru_cache(maxsize=1)
def load():
    try:
        z = np.load(ARTIFACT_DIR / "coastal_context.npz")
        units = json.loads((ARTIFACT_DIR / "coastal_units.json").read_text(encoding="utf-8"))
        meta = json.loads((ARTIFACT_DIR / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CoastalContextUnavailable(f"coastal context artefact unavailable: {exc}") from exc
    return {k: z[k] for k in z.files}, units, meta


def provenance() -> dict:
    try:
        _, _, meta = load()
    except CoastalContextUnavailable as exc:
        return {"available": False, "note": str(exc)}
    return {"available": True, **meta}


def lookup(lat: float, lon: float) -> dict:
    arrays, units, meta = load()
    lats, lons = arrays["lat"], arrays["lon"]
    if not (lats.min() - 0.125 <= lat <= lats.max() + 0.125
            and lons.min() - 0.125 <= lon <= lons.max() + 0.125):
        return {"status": "OUTSIDE_DOMAIN", "wording": WORDING}
    row, col = int(np.abs(lats - lat).argmin()), int(np.abs(lons - lon).argmin())
    if not bool(arrays["ocean"][row, col]):
        return {"status": "LAND_OR_NO_OCEAN_CELL", "row": row, "col": col,
                "wording": WORDING}
    si = int(arrays["state_index"][row, col])
    if si < 0:
        return {"status": "NO_COAST_FOUND", "row": row, "col": col, "wording": WORDING}
    state = units["states"][si]
    di = int(arrays["district_index"][row, col])
    district = units["districts"][di] if di >= 0 else None
    dist = float(arrays["distance_km"][row, col])
    return {
        "status": "OK", "row": row, "col": col,
        "grid_lat": float(lats[row]), "grid_lon": float(lons[col]),
        "nearest_coast_lat": round(float(arrays["coast_lat"][row, col]), 3),
        "nearest_coast_lon": round(float(arrays["coast_lon"][row, col]), 3),
        "offshore_distance_km": round(dist),
        "coastal_state": state["name"], "country": state["country"],
        "admin_type": state["type"],
        "coastal_segment": f"{state['name']} coast",
        "coastal_district": district["name"] if district else None,
        "district_note": None if district else (
            "district context is derived for Indian coasts only"
            if state["country"] != "India" else
            f"no district coastline within {DISTRICT_MATCH_KM:.0f} km of the state's "
            "nearest coastline point"),
        "precision_note": "cell-centre distance; the 0.25 degree grid implies about +/-14 km",
        "wording": WORDING,
        "sources": meta.get("sources"),
    }


def lookup_many(points) -> list[dict]:
    return [lookup(float(p["lat"]), float(p["lon"])) for p in points]


def track_coastal_approach(samples: list[dict]) -> dict | None:
    """Closest approach of sampled path positions to a mapped coastline."""
    best = None
    for s in samples:
        if not s.get("in_domain"):
            continue
        c = lookup(float(s["lat"]), float(s["lon"]))
        if c.get("status") != "OK":
            continue
        if best is None or c["offshore_distance_km"] < best["offshore_distance_km"]:
            best = {**c, "distance_along_path_km": s.get("distance_km")}
    return best


def _km_per_degree_lon(lat: float) -> float:
    return math.pi / 180 * EARTH_RADIUS_KM * math.cos(math.radians(lat))
