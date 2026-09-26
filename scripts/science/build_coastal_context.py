"""Build the static coastal/administrative lookup (PREREGISTRATION §5).

Inputs (data/raw/geography/, gitignored):
  ne_10m_admin_1_states_provinces.geojson   Natural Earth 1:10m Admin-1, public domain
  geoBoundaries-IND-ADM2_simplified.geojson  geoBoundaries gbOpen IND ADM2, ODbL 1.0

For every ocean cell of the canonical 101x241 grid: the nearest Admin-1 polygon
(its nearest point lies on that unit's coast), the haversine distance to that
point, and for Indian units the nearest district whose nearest point is within
10 km of the state's. Distances are found in a per-row locally scaled plane
(longitude x cos(latitude)), then measured with haversine.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import shapely
from shapely.geometry import shape

from oceanembed.config import REPO_ROOT
from oceanembed.replay.engine import ReplayEngine
from oceanembed.science.coastal import ARTIFACT_DIR, DISTRICT_MATCH_KM, haversine_km

RAW = REPO_ROOT / "data" / "raw" / "geography"
NE = RAW / "ne_10m_admin_1_states_provinces.geojson"
GB = RAW / "geoBoundaries-IND-ADM2_simplified.geojson"
GB_META = RAW / "geoBoundaries-IND-ADM2_metadata.json"
NE_VERSION = RAW / "natural_earth_VERSION.txt"
SEARCH = {"lat": (-12.0, 42.0), "lon": (28.0, 118.0)}
SIMPLIFY_DEG = 0.01


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_polygons(path: Path, props) -> tuple[list, list]:
    data = json.loads(path.read_text(encoding="utf-8"))
    geoms, meta = [], []
    box = shapely.box(SEARCH["lon"][0], SEARCH["lat"][0], SEARCH["lon"][1], SEARCH["lat"][1])
    for f in data["features"]:
        if not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        if not g.intersects(box):
            continue
        g = shapely.simplify(g, SIMPLIFY_DEG, preserve_topology=True)
        m = props(f["properties"])
        if m is None:
            continue
        geoms.append(g)
        meta.append(m)
    return geoms, meta


def nearest(geoms: list, lat_row: float, lats: np.ndarray, lons: np.ndarray):
    c = float(np.cos(np.radians(lat_row)))
    scaled = shapely.transform(np.array(geoms, dtype=object), lambda xy: xy * [c, 1.0])
    tree = shapely.STRtree(scaled)
    pts = shapely.points(lons * c, lats)
    idx = tree.query_nearest(pts, all_matches=False)
    order = np.argsort(idx[0])
    gi = idx[1][order]
    lines = shapely.shortest_line(pts, scaled[gi])
    end = shapely.get_coordinates(shapely.get_point(lines, 1))
    return gi, end[:, 1], end[:, 0] / c


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    engine = ReplayEngine()
    ds = engine._store(2023)
    ocean = np.asarray(ds["ocean_mask"].isel(time=0).values, dtype=bool)
    lat, lon = engine.lat, engine.lon

    states, smeta = load_polygons(NE, lambda p: {
        "name": p.get("name") or p.get("name_en"), "country": p.get("admin"),
        "type": p.get("type_en") or p.get("type"), "iso_3166_2": p.get("iso_3166_2")})
    districts, dmeta = load_polygons(GB, lambda p: {
        "name": p.get("shapeName"), "id": p.get("shapeID"), "country": "India"})
    print(f"admin-1 units in search box: {len(states)}; Indian districts: {len(districts)}")

    shape2 = ocean.shape
    state_index = np.full(shape2, -1, dtype="int16")
    district_index = np.full(shape2, -1, dtype="int16")
    distance = np.full(shape2, np.nan, dtype="float32")
    coast_lat = np.full(shape2, np.nan, dtype="float32")
    coast_lon = np.full(shape2, np.nan, dtype="float32")
    india = [i for i, m in enumerate(smeta) if m["country"] == "India"]

    for r in range(lat.size):
        cols = np.flatnonzero(ocean[r])
        if not cols.size:
            continue
        la = np.full(cols.size, lat[r])
        lo = lon[cols]
        gi, clat, clon = nearest(states, lat[r], la, lo)
        state_index[r, cols] = gi
        coast_lat[r, cols] = clat
        coast_lon[r, cols] = clon
        distance[r, cols] = haversine_km(la, lo, clat, clon)
        ind = np.isin(gi, india)
        if ind.any() and districts:
            dgi, dlat, dlon = nearest(districts, lat[r], la[ind], lo[ind])
            close = haversine_km(clat[ind], clon[ind], dlat, dlon) <= DISTRICT_MATCH_KM
            target = cols[ind]
            district_index[r, target[close]] = dgi[close]
        if r % 20 == 0:
            print(f"  row {r}/{lat.size}", flush=True)

    np.savez_compressed(ARTIFACT_DIR / "coastal_context.npz", lat=lat, lon=lon, ocean=ocean,
                        state_index=state_index, district_index=district_index,
                        distance_km=distance, coast_lat=coast_lat, coast_lon=coast_lon)
    (ARTIFACT_DIR / "coastal_units.json").write_text(
        json.dumps({"states": smeta, "districts": dmeta}, ensure_ascii=False), encoding="utf-8")
    gb_meta = json.loads(GB_META.read_text(encoding="utf-8"))
    meta = {
        "protocol": "outputs/science/PREREGISTRATION.md §5",
        "rule": ("nearest Admin-1 polygon to each ocean cell centre (its nearest point lies on "
                 "that unit's coastline); haversine distance to that point; Indian district = "
                 f"nearest district polygon whose nearest point is within {DISTRICT_MATCH_KM:.0f} km "
                 "of the state's nearest point"),
        "simplification_deg": SIMPLIFY_DEG,
        "sources": [
            {"name": "Natural Earth 1:10m Admin 1 - States, Provinces",
             "file": NE.name, "version": NE_VERSION.read_text().strip(),
             "sha256": sha(NE), "license": "Public domain (Natural Earth terms of use)",
             "url": "https://www.naturalearthdata.com/",
             "note": "de facto boundaries as depicted by Natural Earth"},
            {"name": "geoBoundaries gbOpen IND ADM2 (districts)", "file": GB.name,
             "version": f"{gb_meta.get('boundaryYearRepresented')} build {gb_meta.get('buildDate')}",
             "boundary_id": gb_meta.get("boundaryID"), "sha256": sha(GB),
             "license": gb_meta.get("boundaryLicense"),
             "source": gb_meta.get("boundarySource"),
             "citation": "Runfola et al. (2020) geoBoundaries, PLoS ONE 15(4): e0231866",
             "url": "https://www.geoboundaries.org/"}],
        "n_ocean_cells": int(ocean.sum()),
        "n_cells_with_district": int((district_index >= 0).sum()),
    }
    (ARTIFACT_DIR / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("n_ocean_cells", "n_cells_with_district")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
