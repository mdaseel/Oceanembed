"""Build offline physical depth support from the SAME local ETOPO source as terrain."""
import hashlib
import json
from pathlib import Path
import numpy as np
import xarray as xr
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from oceanembed.preprocessing.regrid import regrid_horizontal

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "outputs/phase7b/terrain/etopo2022-60s-stride3.nc"

def regrid_depth(dem):
    if dem.attrs.get("positive") != "up" or dem.attrs.get("units") not in ("m", "meters", "metres"):
        raise ValueError("Require explicitly positive-up elevation in metres")
    dem = dem.rename({"latitude": "lat", "longitude": "lon"}).transpose("lat", "lon").sortby("lat").sortby("lon")
    elevation = regrid_horizontal(dem.to_dataset(name="elevation"))["elevation"]
    return xr.where(np.isfinite(elevation), np.maximum(0, -elevation), np.nan)

def main():
    terrain = json.loads((ROOT / "web/public/assets/terrain/metadata.json").read_text())
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if source_hash != terrain["sourceSha256"]:
        raise ValueError("ETOPO source must match existing terrain provenance")
    with xr.open_dataset(SOURCE) as ds:
        depth = regrid_depth(ds.z)
    out = ROOT / "web/public/assets/bathymetry"
    out.mkdir(parents=True, exist_ok=True)
    binary = np.asarray(depth.values, dtype="<f8").tobytes()
    (out / "depth.bin").write_bytes(binary)
    meta = {"schema": 1, "dataset": terrain["dataset"], "version": terrain["version"],
      "sourceUrl": terrain["sourceUrl"], "sourceSha256": source_hash,
      "sourceNativeArcseconds": 60, "inputSpacingDegrees": 0.05,
      "verticalDatum": "EGM2008", "signConvention": "source positive up; water_depth_m = max(0, -elevation_m)",
      "regridding": "oceanembed.preprocessing.regrid.regrid_horizontal: xarray.interp linear; no extrapolation; NaN propagates; point samples at canonical cell centres, not cell minima",
      "lat": depth.lat.values.tolist(), "lon": depth.lon.values.tolist(),
      "binaryLayout": "little-endian float64 water depth metres, latitude-major, longitude-minor",
      "depthSha256": hashlib.sha256(binary).hexdigest(),
      "displayRule": "existing ocean/input support AND finite bathymetry AND water_depth_m >= requested_depth_m; existing finite field-value check also applies",
      "missingPolicy": "do not render unverified depth; never infer bathymetry from climatology or temperature"}
    (out / "metadata.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({"sourceSha256": source_hash, "shape": list(depth.shape), "min": float(depth.min()), "max": float(depth.max())}))

if __name__ == "__main__":
    main()
