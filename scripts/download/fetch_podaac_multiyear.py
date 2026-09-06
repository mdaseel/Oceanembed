"""Phase 6A.5 - multi-year OSCAR + CCMP acquisition from PO.DAAC via OPeNDAP.

TRUE server-side subsetting using DAP4 constraint expressions. Measured on
2026-09-04 against a real granule:

    CCMP   0.84 MB of 32.0 MB per day  ( 2.6 %)
    OSCAR  0.24 MB of 31.7 MB per day  ( 0.8 %)

Both collections are published only as GLOBAL daily files, so a naive download
of 10 years would move ~231 GB to keep ~4 GB. Constraining the request to an
index range on the server reduces that to ~4 GB.

There is deliberately NO fallback to whole-granule download: if OPeNDAP fails
the run stops and reports, rather than silently transferring 231 GB.

Index ranges are DISCOVERED from each collection's own coordinate arrays.
The two products differ in ways that would break a hard-coded assumption:
    CCMP   coords 'latitude'/'longitude', var dims (time, latitude, longitude)
    OSCAR  coords 'lat'/'lon',            var dims (time, longitude, latitude)

Requires NASA Earthdata Login (`earthaccess.login(persist=True)`).

Run:  PYTHONPATH=src python scripts/download/fetch_podaac_multiyear.py
"""
from __future__ import annotations

import argparse
import io
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from oceanembed.config import EAST, NORTH, REPO_ROOT, SOUTH, WEST  # noqa: E402
from oceanembed.download_utils import cleanup_partials, get_logger, verify  # noqa: E402

DATASET_START = "2015-01-01"
DATASET_END = "2024-12-15"
PAD = 1.0
LAT_MIN, LAT_MAX = SOUTH - PAD, NORTH + PAD
LON_MIN, LON_MAX = WEST - PAD, EAST + PAD

WORKERS = 8
RETRIES = 3

RAW = REPO_ROOT / "data" / "raw"
LOG = get_logger("fetch_podaac", REPO_ROOT / "outputs" / "logs" / "download_phase6a5.log")

SPECS = {
    "oscar": dict(
        short_name="OSCAR_L4_OC_FINAL_V2.0", variables=["u", "v"],
        doi="10.5067/OSCAR-25F20", dirname="oscar",
        lat="lat", lon="lon", dim_order=("time", "longitude", "latitude"),
        n_time=1, full_mb=31.7,
    ),
    "ccmp": dict(
        short_name="CCMP_WINDS_10M6HR_L4_V3.1", variables=["uwnd", "vwnd"],
        doi="10.5067/CCMP-6HW10M-L4V31", dirname="ccmp",
        lat="latitude", lon="longitude", dim_order=("time", "latitude", "longitude"),
        n_time=4, full_mb=32.0,
    ),
}

_local = threading.local()


def session():
    """One authenticated requests session per thread."""
    if not hasattr(_local, "s"):
        import earthaccess
        _local.s = earthaccess.get_requests_https_session()
    return _local.s


def opendap_url(granule) -> str | None:
    for u in granule["umm"].get("RelatedUrls", []):
        if u.get("Type") == "USE SERVICE API" and "opendap" in u.get("URL", ""):
            return u["URL"]
    return None


def _read_nc(content: bytes) -> xr.Dataset:
    """Read a DAP4 .dap.nc4 response straight from memory.

    Avoids a temp file entirely - on Windows the open dataset keeps a handle
    that blocks unlink, and with 8 worker threads that races badly.
    """
    with xr.open_dataset(io.BytesIO(content), engine="h5netcdf") as ds:
        return ds.load().copy(deep=True)


def discover_indices(url: str, spec: dict) -> tuple[int, int, int, int]:
    """Fetch only the coordinate axes (~28 KB) and derive index ranges."""
    ce = f"/{spec['lat']};/{spec['lon']}"
    r = session().get(url + ".dap.nc4", params={"dap4.ce": ce}, timeout=180)
    r.raise_for_status()
    d = _read_nc(r.content)
    lat = np.ravel(d[spec["lat"]].values)
    lon = np.ravel(d[spec["lon"]].values)
    d.close()
    lonw = ((lon + 180.0) % 360.0) - 180.0
    la = np.where((lat >= LAT_MIN) & (lat <= LAT_MAX))[0]
    lo = np.where((lonw >= LON_MIN) & (lonw <= LON_MAX))[0]
    if la.size == 0 or lo.size == 0:
        raise ValueError("domain not covered by this granule's axes")
    if not (np.all(np.diff(la) == 1) and np.all(np.diff(lo) == 1)):
        raise ValueError("index range is not contiguous - a DAP4 slice would be wrong")
    return int(la.min()), int(la.max()), int(lo.min()), int(lo.max())


def constraint(spec: dict, idx: tuple[int, int, int, int]) -> str:
    la0, la1, lo0, lo1 = idx
    lat_s, lon_s = f"{la0}:1:{la1}", f"{lo0}:1:{lo1}"
    tsl = f"0:1:{spec['n_time']-1}"
    # slice order must follow each product's own dimension order
    if spec["dim_order"] == ("time", "longitude", "latitude"):
        var_sl = f"[{tsl}][{lon_s}][{lat_s}]"
    else:
        var_sl = f"[{tsl}][{lat_s}][{lon_s}]"
    parts = [f"/{v}{var_sl}" for v in spec["variables"]]
    parts += [f"/{spec['lat']}[{lat_s}]", f"/{spec['lon']}[{lon_s}]", f"/time[{tsl}]"]
    return ";".join(parts)


def fetch_granule(url: str, ce: str) -> xr.Dataset:
    last = None
    for attempt in range(RETRIES):
        try:
            r = session().get(url + ".dap.nc4", params={"dap4.ce": ce}, timeout=300)
            r.raise_for_status()
            return _read_nc(r.content)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{type(last).__name__}: {last}")


def fetch_year(ea, key: str, spec: dict, year: int) -> str:
    start = max(f"{year}-01-01", DATASET_START)
    end = min(f"{year}-12-31", DATASET_END)
    outdir = RAW / spec["dirname"] / str(year)
    outdir.mkdir(parents=True, exist_ok=True)
    final = outdir / f"{key}_{year}.nc"

    n_days = len(pd.date_range(start, end, freq="D"))
    tol = 0 if spec["n_time"] == 1 else n_days * (spec["n_time"] - 1)
    good, reason = verify(final, start, end, tolerance=tol)
    if good:
        LOG.info(f"SKIP  {key} {year}  ({reason})")
        return "skip"
    if final.exists():
        LOG.warning(f"REDO  {key} {year}  rejected: {reason}")
        final.unlink()
    cleanup_partials(outdir)

    LOG.info(f"GET   {key} {year}  short_name={spec['short_name']} vars={spec['variables']} "
             f"time={start}..{end} box=lat[{LAT_MIN},{LAT_MAX}] lon[{LON_MIN},{LON_MAX}] "
             f"method=OPeNDAP-DAP4-server-side-subset")

    granules = ea.search_data(short_name=spec["short_name"], temporal=(start, end),
                              count=2000)
    urls = [u for u in (opendap_url(g) for g in granules) if u]
    if len(urls) != len(granules):
        LOG.warning(f"      {len(granules)-len(urls)} granule(s) had no OPeNDAP endpoint")
    if not urls:
        LOG.error(f"FAIL  {key} {year}: no OPeNDAP endpoints - NOT falling back to "
                  f"global download (would transfer ~{spec['full_mb']*n_days/1000:.0f} GB)")
        return "fail"

    t0 = time.time()
    try:
        idx = discover_indices(urls[0], spec)
    except Exception as exc:  # noqa: BLE001
        LOG.error(f"FAIL  {key} {year}: index discovery failed: {exc}")
        return "fail"
    ce = constraint(spec, idx)
    LOG.info(f"      {len(urls)} granules; lat[{idx[0]}:{idx[1]}] lon[{idx[2]}:{idx[3]}]")

    results: dict[int, xr.Dataset] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_granule, u, ce): i for i, u in enumerate(urls)}
        done = 0
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{urls[i].rsplit('/',1)[-1]}: {exc}")
            done += 1
            if done % 100 == 0:
                LOG.info(f"      {done}/{len(urls)}  ({time.time()-t0:.0f}s)")

    if errors:
        LOG.error(f"      {len(errors)} granule(s) failed, e.g. {errors[:2]}")
    if not results:
        LOG.error(f"FAIL  {key} {year}: no granules retrieved")
        return "fail"

    out = xr.concat([results[i] for i in sorted(results)], dim="time").sortby("time")
    for ds in results.values():
        ds.close()

    tmp = outdir / f"{key}_{year}.part.nc"
    out.to_netcdf(tmp)
    out.close()

    good, reason = verify(tmp, start, end, tolerance=tol)
    if not good:
        LOG.error(f"FAIL  {key} {year}: rejected: {reason}")
        tmp.unlink()
        return "fail"
    tmp.replace(final)
    mb = final.stat().st_size / 1e6
    LOG.info(f"OK    {key} {year}  {mb:.1f} MB in {time.time()-t0:.0f}s ({reason}) "
             f"[vs ~{spec['full_mb']*n_days/1000:.1f} GB if unsubsetted]")
    return "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", nargs="*", default=["oscar", "ccmp"], choices=["oscar", "ccmp"])
    ap.add_argument("--years", nargs="*", type=int, default=list(range(2015, 2025)))
    args = ap.parse_args()

    import earthaccess
    auth = earthaccess.login(persist=True)
    if not auth or not getattr(auth, "authenticated", False):
        raise SystemExit("NASA Earthdata authentication failed. Run: "
                         'python -c "import earthaccess; earthaccess.login(persist=True)"')

    LOG.info("=" * 70)
    LOG.info(f"Phase 6A.5 PO.DAAC acquisition (OPeNDAP server-side subset) "
             f"products={args.product} years={args.years}")

    tally = {"ok": 0, "skip": 0, "fail": 0}
    failures = []
    for key in args.product:
        for year in args.years:
            r = fetch_year(earthaccess, key, SPECS[key], year)
            tally[r] += 1
            if r == "fail":
                failures.append(f"{key} {year}")
    LOG.info(f"DONE  ok={tally['ok']} skipped={tally['skip']} failed={tally['fail']}")
    if failures:
        LOG.error(f"FAILURES: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
