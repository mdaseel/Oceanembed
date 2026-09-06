"""Phase 6A.5 - build the model-ready multi-year dataset, one year at a time.

Reuses the Phase 6A pipeline (loaders, standardise, regrid, sanity) unchanged.
The only structural addition is scale: GLORYS on its native 1/12 deg grid is
~12.7 GB for a single year at 36 levels, so the target is processed MONTH by
month and accumulated at 0.25 deg, where a whole year is only ~0.5 GB.

Writes one Zarr store per year plus annual QC tables.

Run:  PYTHONPATH=src python scripts/preprocess/build_phase6a5.py [--years 2015 2016 ...]
"""
from __future__ import annotations

import argparse
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from oceanembed.config import FINAL_DEPTHS, PIPELINE_VERSION, REPO_ROOT  # noqa: E402
from oceanembed.data import loaders as L  # noqa: E402
from oceanembed.grid import canonical_grid  # noqa: E402
from oceanembed.preprocessing.masks import add_all_masks  # noqa: E402
from oceanembed.preprocessing.regrid import interp_depths, regrid_horizontal  # noqa: E402
from oceanembed.download_utils import get_logger  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*Consolidated metadata.*")

OUT = REPO_ROOT / "outputs"
TAB = OUT / "tables"
MODEL_READY = REPO_ROOT / "data" / "processed" / "model_ready"
for d in (TAB, MODEL_READY, OUT / "logs"):
    d.mkdir(parents=True, exist_ok=True)

LOG = get_logger("build65", OUT / "logs" / "build_phase6a5.log")

SPLITS = yaml.safe_load(open(REPO_ROOT / "config" / "data_splits.yaml", encoding="utf-8"))
DATASET_START = SPLITS["dataset"]["start"]
DATASET_END = SPLITS["dataset"]["end"]

# Chunking: whole spatial field per chunk, 32 days of time.
# 24,341 cells x 32 x 4 B ~= 3 MB - inside Zarr's efficient range, and every
# planned access pattern (temporal windows, spatial patches, per-depth masks)
# reads whole maps over a short time span.
CHUNKS = {"time": 32, "lat": 101, "lon": 241}

SUSPICIOUS_LO = 3.0   # degC - below any plausible NIO value in the top 1000 m
SUSPICIOUS_HI = 36.0

qc_rows: list[dict] = []
suspicious_rows: list[dict] = []
depth_provenance: dict = {}


def year_slice(year: int) -> tuple[str, str]:
    return (max(f"{year}-01-01", DATASET_START), min(f"{year}-12-31", DATASET_END))


def process_glorys_year(year: int, start: str, end: str) -> xr.Dataset:
    """Vertical interp to all 15 depths, then horizontal regrid, month by month."""
    global depth_provenance
    pattern = f"data/raw/glorys/{year}/*.nc"
    gl_all = L.load_glorys(pattern)
    months = pd.date_range(start, end, freq="MS")
    pieces = []
    for m in months:
        m_end = min(m + pd.offsets.MonthEnd(0), pd.Timestamp(end))
        sub = gl_all.sel(time=slice(str(m.date()), str(m_end.date())))
        if sub.sizes.get("time", 0) == 0:
            continue
        sub = sub.load()
        t_i, prov = interp_depths(sub["thetao"], [float(d) for d in FINAL_DEPTHS])
        if not depth_provenance:
            depth_provenance = prov
        per_depth = {}
        for i, d in enumerate(FINAL_DEPTHS):
            da = t_i.isel(depth=i).drop_vars("depth")
            per_depth[f"temp_{int(d)}m"] = regrid_horizontal(
                xr.Dataset({"t": da}), method="linear")["t"]
        piece = xr.Dataset(per_depth)
        # audit BEFORE anything is masked, on the regridded target
        audit_suspicious(piece, year)
        pieces.append(piece)
        del sub, t_i, per_depth
    gl_all.close()
    return xr.concat(pieces, dim="time")


def audit_suspicious(ds: xr.Dataset, year: int) -> None:
    for name in ds.data_vars:
        if not name.startswith("temp_"):
            continue
        da = ds[name]
        bad = da.where((da < SUSPICIOUS_LO) | (da > SUSPICIOUS_HI))
        st = bad.stack(z=("time", "lat", "lon")).dropna("z")
        if st.size == 0:
            continue
        for t, la, lo, v in zip(st.time.values, st.lat.values, st.lon.values, st.values):
            suspicious_rows.append({
                "year": year, "date": str(t)[:10], "variable": name,
                "depth_m": int(name[5:-1]), "lat": float(la), "lon": float(lo),
                "value_degC": float(v),
                "reason": "below_plausible" if v < SUSPICIOUS_LO else "above_plausible",
            })


def qc_year(ds: xr.Dataset, year: int, start: str, end: str) -> None:
    expected = pd.date_range(start, end, freq="D")
    have = pd.DatetimeIndex(ds.time.values)
    missing = sorted(set(expected) - set(have))
    dupes = len(have) - len(have.unique())
    for v in ds.data_vars:
        if ds[v].dtype == bool:
            a = ds[v].values
            qc_rows.append({"year": year, "variable": v, "kind": "mask",
                            "n_true": int(a.sum()), "pct_true": float(100 * a.mean()),
                            "n_days": len(have), "n_missing_days": len(missing),
                            "duplicate_timestamps": dupes})
            continue
        a = ds[v].values.astype("float64")
        fin = np.isfinite(a)
        qc_rows.append({
            "year": year, "variable": v, "kind": "field",
            "n_finite": int(fin.sum()),
            "pct_missing": float(100 * (1 - fin.mean())),
            "min": float(np.nanmin(a)) if fin.any() else np.nan,
            "max": float(np.nanmax(a)) if fin.any() else np.nan,
            "mean": float(np.nanmean(a)) if fin.any() else np.nan,
            "std": float(np.nanstd(a)) if fin.any() else np.nan,
            "n_days": len(have), "n_missing_days": len(missing),
            "duplicate_timestamps": dupes,
        })
    if missing:
        LOG.warning(f"{year}: {len(missing)} missing day(s), first few "
                    f"{[str(d)[:10] for d in missing[:5]]}")
    if dupes:
        LOG.error(f"{year}: {dupes} duplicate timestamps")


def build_year(year: int) -> Path | None:
    start, end = year_slice(year)
    LOG.info("=" * 70)
    LOG.info(f"YEAR {year}  ({start} .. {end})")

    surf = {}
    try:
        surf_specs = [
            ("sst", L.load_ostia, f"data/raw/ostia/{year}/*.nc"),
            ("sss", L.load_multiobs_sss, f"data/raw/sss_multiobs/{year}/*.nc"),
            ("sla", L.load_duacs_sla, f"data/raw/duacs/{year}/*.nc"),
            ("cur", L.load_oscar, f"data/raw/oscar/{year}/*.nc"),
            ("wnd", L.load_ccmp, f"data/raw/ccmp/{year}/*.nc"),
        ]
        for key, fn, pat in surf_specs:
            ds = fn(pat)
            for v in ds.data_vars:
                surf[v] = ds[v]
            LOG.info(f"  loaded {key:4s} {list(ds.data_vars)} n_time={ds.sizes['time']}")
    except FileNotFoundError as exc:
        LOG.error(f"  SKIP {year}: {exc}")
        return None

    # common dates across every surface product and GLORYS
    gl = process_glorys_year(year, start, end)
    date_sets = [set(pd.DatetimeIndex(v.time.values)) for v in surf.values()]
    date_sets.append(set(pd.DatetimeIndex(gl.time.values)))
    common = sorted(set.intersection(*date_sets))
    LOG.info(f"  common dates: {len(common)} of {len(pd.date_range(start, end, freq='D'))}")

    merged = xr.Dataset({k: regrid_horizontal(xr.Dataset({"x": v.sel(time=common)}),
                                              method="linear")["x"]
                         for k, v in surf.items()})
    merged = merged.merge(gl.sel(time=common))

    # ocean mask from the GLORYS surface level; surface channels masked to ocean
    om = np.isfinite(merged["temp_0m"])
    for v in ["sst", "sss", "sla", "current_u", "current_v", "wind_u", "wind_v"]:
        merged[v] = merged[v].where(om)

    merged = add_all_masks(merged, FINAL_DEPTHS)
    merged = merged.transpose("time", "lat", "lon")
    qc_year(merged, year, start, end)

    grid = canonical_grid()
    merged.attrs = {
        "title": f"OceanEmbed model-ready dataset {year}",
        "pipeline_version": PIPELINE_VERSION,
        "phase": "6A.5",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "domain": "lat 5-30 N, lon 45-105 E",
        "target_grid": f"{grid.attrs['n_lat']} x {grid.attrs['n_lon']} at 0.25 deg",
        "dataset_window": f"{DATASET_START} .. {DATASET_END}",
        "source_sst": "OSTIA L4 REP METOFFICE-GLO-SST-L4-REP-OBS-SST (10.48670/moi-00168)",
        "source_sss": "CMEMS MULTIOBS cmems_obs-mob_glo_phy-sss_my_multi_P1D var sos (10.48670/moi-00051)",
        "source_sla": "DUACS c3s_obs-sl_glo_phy-ssh_my_twosat-l4-duacs-0.25deg_P1D (10.48670/moi-00145)",
        "source_currents": "OSCAR L4_OC_FINAL v2.0 u,v (10.5067/OSCAR-25F20)",
        "source_winds": "CCMP v3.1 6-hourly -> daily vector mean (10.5067/CCMP-6HW10M-L4V31)",
        "source_target": "GLORYS12V1 thetao (10.48670/moi-00021)",
        "regridding_method": "xarray.interp linear; NaN propagated; no land fill; no extrapolation",
        "vertical_interpolation": "linear between bracketing GLORYS native levels",
        "depth_0m_policy": "0 m is CLAMPED to the shallowest GLORYS native level "
                           "(~0.494 m). It is NOT a native GLORYS 0 m level.",
        "ocean_mask": "isfinite(temp_0m); independent of deep-water validity",
        "chunking": f"time={CHUNKS['time']}, lat={CHUNKS['lat']}, lon={CHUNKS['lon']}",
    }

    path = MODEL_READY / f"oceanembed_{year}.zarr"
    if path.exists():
        import shutil
        shutil.rmtree(path)
    enc_chunks = {k: min(v, merged.sizes[k]) for k, v in CHUNKS.items()}
    merged.chunk(enc_chunks).to_zarr(path, mode="w", consolidated=True)
    size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6
    LOG.info(f"  WROTE {path.name}  {size:.1f} MB  dims={dict(merged.sizes)}")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int, default=list(range(2015, 2025)))
    args = ap.parse_args()

    built = []
    for y in args.years:
        p = build_year(y)
        if p:
            built.append(p)

    # Merge into the canonical tables rather than overwriting them: years are
    # built incrementally as their GLORYS download lands, so a plain overwrite
    # would leave the tables describing only the most recent run.
    def merge_csv(path: Path, new: pd.DataFrame, years: list[int]) -> pd.DataFrame:
        if path.exists():
            old = pd.read_csv(path)
            if "year" in old.columns:
                old = old[~old["year"].isin(years)]      # drop rebuilt years
            new = pd.concat([old, new], ignore_index=True)
        if "year" in new.columns:
            new = new.sort_values("year", kind="stable")
        new.to_csv(path, index=False)
        return new

    if qc_rows:
        df_q = merge_csv(TAB / "multiyear_qc_by_year.csv",
                         pd.DataFrame(qc_rows), args.years)
        LOG.info(f"wrote {TAB / 'multiyear_qc_by_year.csv'} "
                 f"({len(df_q)} rows, {df_q.year.nunique()} years)")
    df_s = merge_csv(TAB / "glorys_suspicious_values.csv",
                     pd.DataFrame(suspicious_rows), args.years)
    LOG.info(f"wrote {TAB / 'glorys_suspicious_values.csv'} ({len(df_s)} rows)")
    if depth_provenance:
        rows = [{"requested_depth_m": k, **v} for k, v in sorted(depth_provenance.items())]
        pd.DataFrame(rows).to_csv(TAB / "glorys_depth_interpolation_15.csv", index=False)
        LOG.info(f"wrote {TAB / 'glorys_depth_interpolation_15.csv'}")

    LOG.info(f"BUILT {len(built)} year(s)")
    return 0 if built else 1


if __name__ == "__main__":
    raise SystemExit(main())
