"""Build offline, display-only land terrain from a local geographic NetCDF DEM.

No OceanEmbed field, model mask, inference or export is read or modified.
Only positive DEM triangles are retained; coastline crossings end at zero.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import xarray as xr
from scipy.interpolate import RegularGridInterpolator

ROOT = Path(__file__).resolve().parents[2]


def land_mesh(lat, lon, elevation):
    """Indexed positive-elevation surface, clipped at the DEM's zero contour.

    Shared crossing vertices preserve separate islands/holes, without hulls,
    backing, vertical walls, or any generated elevations.
    """
    nlon = len(lon)
    vertices, triangles, lookup = [], [], {}

    def vertex(a, b=None):
        key = (a,) if b is None else tuple(sorted((a, b)))
        if key in lookup:
            return lookup[key]
        r, c = divmod(a, nlon)
        p = np.array([lon[c], lat[r], elevation[r, c]], dtype=float)
        if b is not None:
            rb, cb = divmod(b, nlon)
            q = np.array([lon[cb], lat[rb], elevation[rb, cb]], dtype=float)
            p += (q - p) * (p[2] / (p[2] - q[2]))
            p[2] = 0
        lookup[key] = len(vertices)
        vertices.append(p.tolist())
        return lookup[key]

    heights = elevation.ravel()
    for r in range(len(lat) - 1):
        for c in range(nlon - 1):
            a = r * nlon + c
            for tri in ((a, a + 1, a + nlon + 1), (a, a + nlon + 1, a + nlon)):
                if not np.isfinite(heights[list(tri)]).all():
                    continue  # missing DEM is a hole, never invented land
                polygon = []
                for u, v in zip(tri, (*tri[1:], tri[0])):
                    positive_u, positive_v = heights[u] > 0, heights[v] > 0
                    if positive_u:
                        polygon.append(vertex(u))
                    if positive_u != positive_v:
                        polygon.append(vertex(u, v))
                for j in range(1, len(polygon) - 1):
                    indices = [polygon[0], polygon[j], polygon[j + 1]]
                    p, q, s = np.asarray([vertices[k] for k in indices])
                    if abs((q[0] - p[0]) * (s[1] - p[1]) - (q[1] - p[1]) * (s[0] - p[0])) > 1e-12:
                        triangles.extend(indices)
    return np.asarray(vertices, dtype="<f4").reshape(-1, 3), np.asarray(triangles, dtype="<u4")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--variable", default="z")
    parser.add_argument("--lat", default="latitude")
    parser.add_argument("--lon", default="longitude")
    parser.add_argument("--step", type=float, default=0.05)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--attribution", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--native-arcseconds", type=float, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "web/public/assets/terrain")
    args = parser.parse_args()
    if not 0.025 <= args.step <= 0.25:
        parser.error("display step must be 0.025–0.25 degrees")
    with xr.open_dataset(args.source) as ds:
        dem = ds[args.variable].transpose(args.lat, args.lon).sortby(args.lat).sortby(args.lon)
        if dem.attrs.get("units", "").lower() not in ("m", "meter", "meters", "metre", "metres"):
            raise ValueError("DEM heights must explicitly be metres, positive upward")
        if dem.attrs.get("positive", "up") != "up":
            raise ValueError("DEM heights must be positive upward")
        lat = np.linspace(5, 30, round(25 / args.step) + 1)
        lon = np.linspace(45, 105, round(60 / args.step) + 1)
        src_lat, src_lon = dem[args.lat].values, dem[args.lon].values
        if src_lat[0] > 5 or src_lat[-1] < 30 or src_lon[0] > 45 or src_lon[-1] < 105:
            raise ValueError("DEM must cover 5–30 N, 45–105 E including boundary nodes")
        interpolator = RegularGridInterpolator((src_lat, src_lon), dem.values, bounds_error=True)
        yy, xx = np.meshgrid(lat, lon, indexing="ij")
        elevations = interpolator(np.stack([yy, xx], axis=-1))
        positions, indices = land_mesh(lat, lon, elevations)
        if not len(indices):
            raise ValueError("DEM has no positive land triangles")
        metadata = {
            "schema": 1, "contextOnly": True, "dataset": args.dataset, "version": args.version,
            "attribution": args.attribution, "sourceUrl": args.source_url,
            "sourceSha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
            "sourceNativeArcseconds": args.native_arcseconds,
            "inputSpacingDegrees": [float(np.median(np.diff(src_lat))), float(np.median(np.diff(src_lon)))],
            "displayStepDegrees": args.step, "bounds": [45, 5, 105, 30],
            "processing": "Bilinear display resampling; triangles clipped at positive-elevation zero contour; no bathymetry, backing or procedural relief",
            "verticalDatum": dem.attrs.get("vert_crs_name", "source DEM datum"),
            "vertices": len(positions), "triangles": len(indices) // 3,
            "maxElevationMetres": float(positions[:, 2].max()),
            "binaryLayout": "little-endian float32 lon,lat,elevation_m triples then uint32 triangle indices",
            "license": ds.attrs.get("license", "See source attribution"),
        }
    args.out.mkdir(parents=True, exist_ok=True)
    binary = positions.tobytes() + indices.tobytes()
    metadata["meshSha256"] = hashlib.sha256(binary).hexdigest()
    (args.out / "land.bin").write_bytes(binary)
    (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
