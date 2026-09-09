"""Build a static 2D shaded-relief overlay from the cached real ETOPO subset."""
from pathlib import Path
import json
import hashlib
import numpy as np
import xarray as xr
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import gaussian_filter
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / "outputs/phase7b/terrain/etopo2022-60s-stride3.nc"
out = ROOT / "web/public/assets/terrain"
W, H = 1320, 555
with xr.open_dataset(source) as ds:
    dem = ds.z.sortby("latitude").sortby("longitude")
    lat = 30.125 - (np.arange(H) + .5) * 25.25 / H
    lon = 44.875 + (np.arange(W) + .5) * 60.25 / W
    yy, xx = np.meshgrid(lat, lon, indexing="ij")
    heights = RegularGridInterpolator((dem.latitude.values, dem.longitude.values), dem.values,
                                      bounds_error=False, fill_value=np.nan)(np.stack([yy,xx],axis=-1))
land = np.isfinite(heights) & (heights > 0)
z = np.maximum(np.nan_to_num(heights), 0)

def shade(elevation):
    gy, gx = np.gradient(elevation)
    gx /= 111000 * np.cos(np.deg2rad(lat[:,None])) * 60.25 / W
    gy /= 111000 * 25.25 / H
    nx, ny = -gx * 12, -gy * 12
    return np.clip((-.45*nx - .6*ny + .66) / np.sqrt(nx*nx + ny*ny + 1), 0, 1)

light = .75 * shade(z) + .25 * shade(gaussian_filter(z, 2))
rgba = np.zeros((H,W,4), dtype=np.uint8)
for c, (base, gain) in enumerate(((12,32),(25,48),(31,52))):
    rgba[:,:,c] = np.clip(base + light * gain, 0, 255)
rgba[:,:,3] = land.astype(np.uint8) * 255
out.mkdir(parents=True, exist_ok=True)
Image.fromarray(rgba).save(out / "map-relief.png")
(out / "map-relief.json").write_text(json.dumps({
    "dataset": "NOAA NCEI ETOPO 2022 v1, 60 arc-second product, subset sampled every third cell",
    "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "processing": "Bilinear DEM sampling, positive-elevation alpha, two-scale NW hillshade, 12x lighting exaggeration only",
    "pixelSize": [W,H], "bounds": [44.875,4.875,105.125,30.125],
    "contextOnly": True,
}, indent=2), encoding="utf-8")
print(out / "map-relief.png")
