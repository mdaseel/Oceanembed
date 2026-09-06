"""SMAP RSS L2C NRT SSS -> daily 0.25 deg NIO field, gaps preserved.

There is no daily gridded NRT SMAP product at PO.DAAC (checked against the live
CMR catalogue: only L2 swath NRT, or an 8-day running-mean science L3). So the
L2C orbit-grid granules are binned onto the canonical grid.

Binning rule, stated plainly because it is the only processing applied:
  * a retrieval contributes to the single canonical cell containing its
    cellat/cellon, and to no other cell;
  * a cell's value is the arithmetic mean of the qualified retrievals that fell
    in it that day;
  * a cell with no qualified retrieval stays NaN.

No interpolation, no spreading, no smoothing, no gap filling. The gappiness of
this product is a result to be measured, not a defect to be repaired.

Volume forces a reduced date sample, which the pre-registration anticipated
(section 3.4); the reduced n is carried with every SMAP number.
"""
from __future__ import annotations

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

from oceanembed.config import EAST, NORTH, REPO_ROOT, RESOLUTION, SOUTH, WEST
from oceanembed.grid import canonical_lat, canonical_lon

OUT = REPO_ROOT / "data" / "raw" / "nrt" / "sss_nrt_smap"
COMMON_START, COMMON_END = "2024-07-01", "2024-12-15"
STRIDE_DAYS = 24                      # reduced sample; L2 swath volume

# bits 0-8 of iqc_flag: SSS not retrieved, or retrieved with strong/moderate
# degradation. Only fully qualified retrievals are kept.
QC_REJECT_MASK = 0b111111111

_local = threading.local()


def sess():
    import earthaccess
    if not hasattr(_local, "s"):
        _local.s = earthaccess.get_requests_https_session()
    return _local.s


def read_nc(content):
    with xr.open_dataset(io.BytesIO(content), engine="h5netcdf") as d:
        return d.load().copy(deep=True)


def granule_points(url: str):
    """Return (lat, lon, sss) for qualified retrievals inside the domain."""
    ce = "/cellat;/cellon;/sss_smap;/iqc_flag"
    r = sess().get(url + ".dap.nc4", params={"dap4.ce": ce}, timeout=600)
    r.raise_for_status()
    d = read_nc(r.content)
    lat = np.asarray(d["cellat"].values, dtype="float64")
    lon = np.asarray(d["cellon"].values, dtype="float64")
    sss = np.asarray(d["sss_smap"].values, dtype="float64")
    qc = np.asarray(d["iqc_flag"].values)
    if qc.ndim == sss.ndim + 1:            # some granules carry a trailing dim
        qc = qc[..., 0]
    # A non-finite quality flag is not evidence of quality: casting NaN to int
    # is undefined, so those retrievals are rejected outright.
    qc_ok = np.isfinite(qc)
    qc_int = np.where(qc_ok, qc, QC_REJECT_MASK).astype("int64")
    lat = np.where(lat <= -9000, np.nan, lat)
    lon = np.where(lon <= -9000, np.nan, lon)
    sss = np.where(sss <= -9000, np.nan, sss)
    lon = ((lon + 180.0) % 360.0) - 180.0
    good = (np.isfinite(lat) & np.isfinite(lon) & np.isfinite(sss)
            & qc_ok & ((qc_int & QC_REJECT_MASK) == 0)
            & (sss > 2.0) & (sss < 45.0)
            & (lat >= SOUTH) & (lat <= NORTH) & (lon >= WEST) & (lon <= EAST))
    return lat[good], lon[good], sss[good]


def bin_day(points, glat, glon):
    """Nearest-cell binning; empty cells stay NaN."""
    acc = np.zeros((glat.size, glon.size), dtype="float64")
    cnt = np.zeros((glat.size, glon.size), dtype="int64")
    for lat, lon, sss in points:
        if lat.size == 0:
            continue
        i = np.rint((lat - glat[0]) / RESOLUTION).astype("int64")
        j = np.rint((lon - glon[0]) / RESOLUTION).astype("int64")
        ok = (i >= 0) & (i < glat.size) & (j >= 0) & (j < glon.size)
        np.add.at(acc, (i[ok], j[ok]), sss[ok])
        np.add.at(cnt, (i[ok], j[ok]), 1)
    out = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
    return out.astype("float32"), cnt


def main() -> int:
    import earthaccess
    earthaccess.login(persist=True)
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "smap_nrt_binned_daily.nc"
    if dst.exists():
        print("cached", dst)
        return 0

    glat, glon = canonical_lat(), canonical_lon()
    dates = pd.date_range(COMMON_START, COMMON_END, freq=f"{STRIDE_DAYS}D")
    print(f"reduced SMAP sample: {len(dates)} dates, every {STRIDE_DAYS} d")

    fields, counts, kept, meta = [], [], [], []
    for d in dates:
        t0 = time.time()
        # An explicit end-of-day bound: a date-only range spilled into the NEXT
        # day and silently doubled the swaths in a "daily" composite. The count
        # is well above the ~62 sub-orbital segments a day actually has, since
        # a truncated listing would understate coverage.
        gr = earthaccess.search_data(
            short_name="SMAP_RSS_L2_SSS_NRT_V6",
            temporal=(f"{d.date()}T00:00:00", f"{d.date()}T23:59:59"),
            count=500)
        # CMR already returns the orbits that OVERLAP this UTC day. A polar
        # orbit crossing midnight is kept, so a day means "the orbits covering
        # this UTC day", which is how a daily swath composite is normally built.
        urls = []
        for g in gr:
            for u in g["umm"].get("RelatedUrls", []):
                if (u.get("Type") == "USE SERVICE API"
                        and "opendap" in u.get("URL", "").lower()):
                    urls.append(u["URL"])
        urls = sorted(set(urls))
        pts, failed = [], 0
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(granule_points, u): u for u in urls}
            for f in as_completed(futs):
                try:
                    pts.append(f.result())
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    print(f"    granule failed: {type(exc).__name__}: {exc}")
        fld, cnt = bin_day(pts, glat, glon)
        fields.append(fld)
        counts.append(cnt.astype("int32"))
        kept.append(int(sum(p[0].size for p in pts)))
        meta.append({"date": str(d.date()), "n_granules": len(urls),
                     "n_failed": failed, "n_qualified_points": kept[-1],
                     "cells_filled": int((cnt > 0).sum())})
        print(f"  {d.date()}  granules={len(urls):2d} failed={failed} "
              f"points={kept[-1]:7d} cells={int((cnt>0).sum()):5d}/{glat.size*glon.size} "
              f"({time.time()-t0:.0f}s)")

    ds = xr.Dataset(
        {"sss": (("time", "lat", "lon"), np.stack(fields)),
         "n_obs": (("time", "lat", "lon"), np.stack(counts))},
        coords={"time": dates, "lat": glat, "lon": glon})
    ds["sss"].attrs = {
        "units": "PSU", "source": "SMAP_RSS_L2_SSS_NRT_V6 sss_smap (~70 km)",
        "qc": f"iqc_flag & 0b{QC_REJECT_MASK:b} == 0 (bits 0-8 clear)",
        "gridding": "nearest-cell mean of qualified retrievals; empty cells NaN; "
                    "no interpolation, spreading, smoothing or gap filling",
        "replay_mode": "RETROSPECTIVE"}
    ds.to_netcdf(dst)
    json.dump({"stride_days": STRIDE_DAYS, "n_dates": len(dates),
               "qc_reject_mask": QC_REJECT_MASK, "per_date": meta},
              open(REPO_ROOT / "outputs" / "nrt" / "smap_ingest_log.json", "w"),
              indent=2)
    print(f"-> {dst}  ({dst.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
