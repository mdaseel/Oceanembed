"""Fetch the NRT candidate products over the discovered common overlap window.

Same 1 degree download pad and same domain as the frozen Phase 6A.5 pipeline.
Nothing is trained; this only acquires data for compatibility measurement.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import pandas as pd
import xarray as xr

from oceanembed.config import EAST, NORTH, REPO_ROOT, SOUTH, WEST
from oceanembed.nrt.registry import PRODUCTS

PAD = 1.0                      # identical to the training acquisition
BOX = dict(minimum_longitude=WEST - PAD, maximum_longitude=EAST + PAD,
           minimum_latitude=SOUTH - PAD, maximum_latitude=NORTH + PAD)
RAW = REPO_ROOT / "data" / "raw" / "nrt"

# Common overlap across every reference/NRT pair, discovered in Step 6.
COMMON_START, COMMON_END = "2024-07-01", "2024-12-15"


def cm_fetch(key: str, start: str, end: str, variables, extra=None) -> Path:
    import copernicusmarine as cm
    p = PRODUCTS[key]
    out = RAW / key
    out.mkdir(parents=True, exist_ok=True)
    dst = out / f"{key}_{start}_{end}.nc"
    if dst.exists() and dst.stat().st_size > 0:
        print(f"  [{key}] cached")
        return dst
    tmp = f"{key}.part.nc"
    t0 = time.time()
    cm.subset(dataset_id=p["dataset_id"], variables=variables,
              output_directory=str(out), output_filename=tmp,
              file_format="netcdf", overwrite=True, disable_progress_bar=True,
              start_datetime=f"{start}T00:00:00", end_datetime=f"{end}T23:59:59",
              **BOX, **(extra or {}))
    (out / tmp).replace(dst)
    print(f"  [{key}] {dst.stat().st_size/1e6:.1f} MB in {time.time()-t0:.0f}s")
    return dst


def oscar_nrt_fetch(dates) -> Path:
    """OSCAR NRT via OPeNDAP server-side subset, exactly as for OSCAR Final."""
    import earthaccess
    import requests
    out = RAW / "currents_nrt"
    out.mkdir(parents=True, exist_ok=True)
    dst = out / f"oscar_nrt_{str(dates[0].date())}_{str(dates[-1].date())}.nc"
    if dst.exists() and dst.stat().st_size > 0:
        print("  [currents_nrt] cached")
        return dst
    earthaccess.login(persist=True)
    local = threading.local()

    def sess():
        if not hasattr(local, "s"):
            local.s = earthaccess.get_requests_https_session()
        return local.s

    gr = earthaccess.search_data(short_name="OSCAR_L4_OC_NRT_V2.0",
                                 temporal=(str(dates[0].date()), str(dates[-1].date())),
                                 count=2000)
    want = {str(d.date()).replace("-", "") for d in dates}
    urls = []
    for g in gr:
        for u in g["umm"].get("RelatedUrls", []):
            if u.get("Type") == "USE SERVICE API" and "opendap" in u.get("URL", ""):
                if any(w in u["URL"] for w in want):
                    urls.append(u["URL"])
    urls = sorted(set(urls))
    print(f"  [currents_nrt] {len(urls)} granules via OPeNDAP")

    def read_nc(content):
        with xr.open_dataset(io.BytesIO(content), engine="h5netcdf") as d:
            return d.load().copy(deep=True)

    r = sess().get(urls[0] + ".dap.nc4", params={"dap4.ce": "/lat;/lon"}, timeout=180)
    r.raise_for_status()
    d0 = read_nc(r.content)
    lat = np.ravel(d0["lat"].values)
    lon = ((np.ravel(d0["lon"].values) + 180) % 360) - 180
    la = np.where((lat >= BOX["minimum_latitude"]) & (lat <= BOX["maximum_latitude"]))[0]
    lo = np.where((lon >= BOX["minimum_longitude"]) & (lon <= BOX["maximum_longitude"]))[0]
    ce = (f"/u[0:1:0][{lo.min()}:1:{lo.max()}][{la.min()}:1:{la.max()}];"
          f"/v[0:1:0][{lo.min()}:1:{lo.max()}][{la.min()}:1:{la.max()}];"
          f"/lat[{la.min()}:1:{la.max()}];/lon[{lo.min()}:1:{lo.max()}];/time[0:1:0]")

    def one(u):
        rr = sess().get(u + ".dap.nc4", params={"dap4.ce": ce}, timeout=300)
        rr.raise_for_status()
        return read_nc(rr.content)

    res = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut = {ex.submit(one, u): i for i, u in enumerate(urls)}
        for f in as_completed(fut):
            try:
                res[fut[f]] = f.result()
            except Exception as exc:  # noqa: BLE001
                print(f"    granule {fut[f]} failed: {exc}")
    ds = xr.concat([res[i] for i in sorted(res)], dim="time").sortby("time")
    ds.to_netcdf(dst)
    print(f"  [currents_nrt] {dst.stat().st_size/1e6:.1f} MB in {time.time()-t0:.0f}s")
    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=3)
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    dates = pd.date_range(COMMON_START, COMMON_END, freq="D")[::args.stride]
    print(f"common overlap {COMMON_START}..{COMMON_END}; sampling every "
          f"{args.stride} day(s) -> {len(dates)} dates\n")
    RAW.mkdir(parents=True, exist_ok=True)

    jobs = {
        "sst_nrt": lambda: cm_fetch("sst_nrt", COMMON_START, COMMON_END, ["analysed_sst"]),
        "sla_nrt": lambda: cm_fetch("sla_nrt", COMMON_START, COMMON_END, ["sla"]),
        "sss_nrt_smos": lambda: cm_fetch(
            "sss_nrt_smos", COMMON_START, COMMON_END,
            ["Sea_Surface_Salinity", "Sea_Surface_Salinity_QC",
             "Sea_Surface_Salinity_Error"]),
        "wind_nrt": lambda: cm_fetch("wind_nrt", COMMON_START, COMMON_END,
                                     ["eastward_wind", "northward_wind"]),
        "currents_nrt": lambda: oscar_nrt_fetch(dates),
    }
    keys = args.only or list(jobs)
    manifest = {}
    for k in keys:
        print(f"[{k}]")
        try:
            path = jobs[k]()
            manifest[k] = {"path": str(path), "bytes": path.stat().st_size,
                           "dataset_id": PRODUCTS[k]["dataset_id"],
                           "replay_mode": "RETROSPECTIVE",
                           "note": "downloaded from today's archive; availability at "
                                   "the original date is NOT implied"}
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            manifest[k] = {"error": f"{type(exc).__name__}: {exc}"}
    out = REPO_ROOT / "outputs" / "nrt"
    out.mkdir(parents=True, exist_ok=True)
    json.dump({"common_start": COMMON_START, "common_end": COMMON_END,
               "stride": args.stride, "n_dates": len(dates),
               "dates": [str(d.date()) for d in dates],
               "download_pad_deg": PAD, "box": BOX, "files": manifest},
              open(out / "fetch_manifest.json", "w"), indent=2)
    print(f"\nmanifest -> {out / 'fetch_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
