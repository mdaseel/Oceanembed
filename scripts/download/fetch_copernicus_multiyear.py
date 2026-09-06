"""Phase 6A.5 - multi-year Copernicus Marine acquisition (annual chunks).

Products (all IDs verified against the live catalogue on 2026-09-04):
  OSTIA  METOFFICE-GLO-SST-L4-REP-OBS-SST                        10.48670/moi-00168
  SSS    cmems_obs-mob_glo_phy-sss_my_multi_P1D  (var 'sos')     10.48670/moi-00051
  DUACS  c3s_obs-sl_glo_phy-ssh_my_twosat-l4-duacs-0.25deg_P1D   10.48670/moi-00145
  GLORYS cmems_mod_glo_phy_my_0.083deg_P1D-m     (var 'thetao')  10.48670/moi-00021

Resume-safe: re-running skips any year that already opens with the right number
of days, and re-fetches anything partial. Requires `copernicusmarine login`.

Run:  PYTHONPATH=src python scripts/download/fetch_copernicus_multiyear.py [--product NAME]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import copernicusmarine as cm

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from oceanembed.config import EAST, NORTH, REPO_ROOT, SOUTH, WEST  # noqa: E402
from oceanembed.download_utils import cleanup_partials, get_logger, verify  # noqa: E402

DATASET_START = "2015-01-01"
DATASET_END = "2024-12-15"  # hard end of the official multi-year SSS reanalysis

PAD = 1.0
BOX = dict(
    minimum_longitude=WEST - PAD, maximum_longitude=EAST + PAD,
    minimum_latitude=SOUTH - PAD, maximum_latitude=NORTH + PAD,
)

RAW = REPO_ROOT / "data" / "raw"
LOG = get_logger("fetch_cmems", REPO_ROOT / "outputs" / "logs" / "download_phase6a5.log")

PRODUCTS = {
    "duacs": dict(dataset_id="c3s_obs-sl_glo_phy-ssh_my_twosat-l4-duacs-0.25deg_P1D",
                  variables=["sla"], doi="10.48670/moi-00145", extra={}, dirname="duacs"),
    "sss":   dict(dataset_id="cmems_obs-mob_glo_phy-sss_my_multi_P1D",
                  variables=["sos"], doi="10.48670/moi-00051", extra={}, dirname="sss_multiobs"),
    "ostia": dict(dataset_id="METOFFICE-GLO-SST-L4-REP-OBS-SST",
                  variables=["analysed_sst"], doi="10.48670/moi-00168", extra={}, dirname="ostia"),
    "glorys": dict(dataset_id="cmems_mod_glo_phy_my_0.083deg_P1D-m",
                   variables=["thetao"], doi="10.48670/moi-00021",
                   extra=dict(minimum_depth=0.0, maximum_depth=1200.0), dirname="glorys"),
}
# smallest first, so a credential or catalogue problem surfaces in seconds
ORDER = ["duacs", "sss", "ostia", "glorys"]


def year_bounds(year: int) -> tuple[str, str]:
    start = max(f"{year}-01-01", DATASET_START)
    end = min(f"{year}-12-31", DATASET_END)
    return start, end


def fetch_year(key: str, spec: dict, year: int) -> str:
    start, end = year_bounds(year)
    outdir = RAW / spec["dirname"] / str(year)
    outdir.mkdir(parents=True, exist_ok=True)
    fname = f"{key}_{year}.nc"
    final = outdir / fname

    good, reason = verify(final, start, end)
    if good:
        LOG.info(f"SKIP  {key} {year}  ({reason})")
        return "skip"
    if final.exists():
        LOG.warning(f"REDO  {key} {year}  existing file rejected: {reason}")
        final.unlink()

    cleanup_partials(outdir)
    LOG.info(f"GET   {key} {year}  dataset_id={spec['dataset_id']} vars={spec['variables']} "
             f"time={start}..{end} box=lat[{BOX['minimum_latitude']},{BOX['maximum_latitude']}] "
             f"lon[{BOX['minimum_longitude']},{BOX['maximum_longitude']}] extra={spec['extra']}")

    # Must end in .nc - the toolbox appends .nc to any other extension, which
    # would leave the partial file under an unexpected name.
    tmp_name = f"{key}_{year}.part.nc"
    t0 = time.time()
    try:
        cm.subset(
            dataset_id=spec["dataset_id"], variables=spec["variables"],
            output_directory=str(outdir), output_filename=tmp_name,
            file_format="netcdf", overwrite=True, disable_progress_bar=True,
            start_datetime=f"{start}T00:00:00", end_datetime=f"{end}T23:59:59",
            **BOX, **spec["extra"],
        )
    except Exception as exc:  # noqa: BLE001
        LOG.error(f"FAIL  {key} {year}: {type(exc).__name__}: {exc}")
        return "fail"

    tmp = outdir / tmp_name
    if not tmp.exists():
        LOG.error(f"FAIL  {key} {year}: no output produced")
        return "fail"

    good, reason = verify(tmp, start, end)
    if not good:
        LOG.error(f"FAIL  {key} {year}: downloaded file rejected: {reason}")
        tmp.unlink()
        return "fail"

    tmp.replace(final)  # atomic: only a verified file ever gets the real name
    mb = final.stat().st_size / 1e6
    LOG.info(f"OK    {key} {year}  {mb:.1f} MB in {time.time()-t0:.0f}s  ({reason})")
    return "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", nargs="*", default=ORDER, choices=ORDER)
    ap.add_argument("--years", nargs="*", type=int, default=list(range(2015, 2025)))
    args = ap.parse_args()

    LOG.info("=" * 70)
    LOG.info(f"Phase 6A.5 Copernicus acquisition  {DATASET_START} .. {DATASET_END}")
    LOG.info(f"products={args.product} years={args.years}")

    tally: dict[str, int] = {"ok": 0, "skip": 0, "fail": 0}
    failures = []
    for key in args.product:
        spec = PRODUCTS[key]
        LOG.info("-" * 70)
        LOG.info(f"PRODUCT {key}  DOI {spec['doi']}")
        for year in args.years:
            r = fetch_year(key, spec, year)
            tally[r] += 1
            if r == "fail":
                failures.append(f"{key} {year}")

    LOG.info("=" * 70)
    LOG.info(f"DONE  ok={tally['ok']} skipped={tally['skip']} failed={tally['fail']}")
    if failures:
        LOG.error(f"FAILURES: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
