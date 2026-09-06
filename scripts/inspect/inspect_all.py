"""Phase 6A STEP 0 - inspect every supplied file. Read-only."""
import sys, glob, os
import numpy as np
import xarray as xr

BASE = "data/raw/_extracted/Ocean_embed_datas"
ARGO = "data/raw/_extracted/Agro_data"


def summ(ds, name):
    print("=" * 78)
    print(name)
    print("=" * 78)
    print("DIMS:", dict(ds.sizes))
    print("COORDS:", list(ds.coords))
    print("DATA VARS:", list(ds.data_vars))
    for c in ds.coords:
        v = ds[c]
        try:
            vals = v.values
            if vals.ndim == 0:
                print(f"  coord {c}: {vals} ({v.dtype})")
            else:
                print(f"  coord {c}: n={vals.size} [{np.nanmin(vals)} .. {np.nanmax(vals)}] ({v.dtype}) first={vals.flatten()[:3]} last={vals.flatten()[-3:]}")
        except Exception as e:
            print(f"  coord {c}: <{e}>")
    for vn in ds.data_vars:
        v = ds[vn]
        attrs = {k: v.attrs[k] for k in ("units", "standard_name", "long_name", "_FillValue", "scale_factor", "add_offset") if k in v.attrs}
        try:
            arr = v.values.astype("float64")
            fin = np.isfinite(arr)
            pct_miss = 100 * (1 - fin.mean())
            rng = (np.nanmin(arr), np.nanmax(arr), np.nanmean(arr)) if fin.any() else (None, None, None)
            print(f"  var {vn} dims={v.dims} shape={v.shape} min/max/mean={rng} miss%={pct_miss:.1f} attrs={attrs}")
        except Exception as e:
            print(f"  var {vn} dims={v.dims} shape={v.shape} <{e}> attrs={attrs}")
    print("GLOBAL ATTRS (subset):")
    for k in ("title", "source", "product_version", "institution", "geospatial_lat_min", "geospatial_lat_max",
              "geospatial_lon_min", "geospatial_lon_max", "time_coverage_start", "time_coverage_end",
              "spatial_resolution", "geospatial_lat_resolution", "geospatial_lon_resolution", "Conventions"):
        if k in ds.attrs:
            print(f"  {k}: {ds.attrs[k]}")
    print()


def do(path, **kw):
    try:
        ds = xr.open_dataset(path, **kw)
        summ(ds, path)
        ds.close()
    except Exception as e:
        print("=" * 78)
        print(path)
        print("  OPEN FAILED:", repr(e))
        print()


# one representative per product
do(sorted(glob.glob(f"{BASE}/sst/*.nc"))[0])
do(sorted(glob.glob(f"{BASE}/sss/*.nc"))[0])
do(sorted(glob.glob(f"{BASE}/ssh/*.nc"))[0])
do(sorted(glob.glob(f"{BASE}/ssh/*.nc"))[1])
do(sorted(glob.glob(f"{BASE}/oscar/*.nc"))[0])
do(sorted(glob.glob(f"{BASE}/ccmp/*.nc"))[0])
do(sorted(glob.glob(f"{BASE}/ascat/*.nc"))[0])
do(f"{BASE}/Glorys.nc")
do(f"{BASE}/Argo gridded.nc")
do(sorted(glob.glob(f"{ARGO}/*.nc"))[0])
