"""Phase 6A end-to-end build: STEPS 6-13 and 15.

Loads every product, checks overlap, regrids to the canonical 0.25 deg grid,
interpolates the GLORYS target onto the debug depths, merges, validates,
plots, extracts a single-cell proof, and saves the development dataset.

Run:  PYTHONPATH=src python scripts/preprocess/build_phase6a.py
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from oceanembed.config import (  # noqa: E402
    DEBUG_DEPTHS, EAST, NORTH, PIPELINE_VERSION, REPO_ROOT, SOUTH, TEST_END,
    TEST_START, WEST,
)
from oceanembed.data import loaders as L  # noqa: E402
from oceanembed.grid import canonical_grid  # noqa: E402
from oceanembed.preprocessing.regrid import interp_depths, regrid_horizontal  # noqa: E402
from oceanembed.validation import sanity  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)

OUT = REPO_ROOT / "outputs"
FIG = OUT / "figures"
TAB = OUT / "tables"
PROC = REPO_ROOT / "data" / "processed"
for d in (FIG, TAB, PROC, OUT / "logs"):
    d.mkdir(parents=True, exist_ok=True)

LOG: list[str] = []


def say(msg: str = "") -> None:
    print(msg)
    LOG.append(msg)


def rule(title: str) -> None:
    say("\n" + "=" * 74)
    say(title)
    say("=" * 74)


# ===================================================================== LOAD
rule("LOAD PRODUCTS (native grids, padded domain)")
products = {
    "sst":      ("OSTIA L4 REP",            L.load_ostia),
    "sss":      ("SMAP L3 CAP v5 8-day",    L.load_smap_sss),
    "sla":      ("DUACS C3S 0.25deg daily", L.load_duacs_sla),
    "currents": ("OSCAR L4 FINAL v2.0",     L.load_oscar),
    "winds":    ("CCMP v3.1 -> daily",      L.load_ccmp),
    "glorys":   ("GLORYS12V1 thetao",       L.load_glorys),
}
loaded: dict[str, xr.Dataset] = {}
native_res: dict[str, str] = {}
for key, (label, fn) in products.items():
    ds = fn()
    loaded[key] = ds
    native_res[key] = str(ds.attrs.get("native_resolution_deg", "?"))
    say(f"  {key:9s} {label:26s} dims={dict(ds.sizes)}  vars={list(ds.data_vars)}")

# ============================================================ STEP 10 OVERLAP
rule("STEP 10 - TEMPORAL OVERLAP CHECK")
dates = {k: set(pd.DatetimeIndex(v.time.values).normalize()) for k, v in loaded.items()}
for k, s in dates.items():
    ds_sorted = sorted(s)
    say(f"  {k:9s} n={len(s):2d}  {str(ds_sorted[0])[:10]} .. {str(ds_sorted[-1])[:10]}")
common = sorted(set.intersection(*dates.values()))
say(f"\n  INTERSECTION across all products: n={len(common)}")
for d in common:
    say(f"    {str(d)[:10]}")

requested = pd.date_range(TEST_START, TEST_END, freq="D")
missing = [str(d)[:10] for d in requested if d not in set(common)]
say(f"\n  Configured test period: {TEST_START} .. {TEST_END} ({len(requested)} days)")
say(f"  Missing from intersection: {missing if missing else 'none'}")

use_dates = [d for d in common if d in set(requested)]
if not use_dates:
    raise SystemExit("FATAL: no overlap between the configured test period and the data")
say(f"  USING {len(use_dates)} real date(s): {[str(d)[:10] for d in use_dates]}")

# ========================================================= STEP 6 SANITY (native)
rule("STEP 6 - SANITY CHECKS ON NATIVE GRIDS")
native_flags: dict[str, list[str]] = {}
for k, ds in loaded.items():
    f = sanity.flags(ds)
    native_flags[k] = f
    say(f"  [{k}] {'OK' if not f else ''}")
    for line in f:
        say(f"      FLAG: {line}")

# ==================================================== STEP 8 REGRID SURFACE
rule("STEP 8 - REGRID SURFACE CHANNELS TO CANONICAL 0.25 DEG GRID")
grid = canonical_grid()
say(f"  target grid: {grid.attrs['n_lat']} lat x {grid.attrs['n_lon']} lon "
    f"= {grid.attrs['n_cells']} cells")

regrid_rows = []
surface: dict[str, xr.DataArray] = {}
for key in ("sst", "sss", "sla", "currents", "winds"):
    ds = loaded[key].sel(time=use_dates)
    before_miss = {v: float(100 * np.isnan(ds[v].values.astype("float64")).mean())
                   for v in ds.data_vars}
    rg = regrid_horizontal(ds, method="linear")
    for v in rg.data_vars:
        surface[v] = rg[v]
        after = float(100 * np.isnan(rg[v].values.astype("float64")).mean())
        regrid_rows.append({
            "variable": v,
            "source_product": ds.attrs.get("source_product", key),
            "native_resolution_deg": native_res[key],
            "target_resolution_deg": 0.25,
            "method": "xarray.interp linear (scipy)",
            "lat_flipped": ds.attrs.get("latitude_flipped_to_ascending", "?"),
            "lon_0_360_converted": ds.attrs.get("longitude_converted_from_0_360", "?"),
            "nan_handling": "propagate; no land fill; no extrapolation",
            "pct_missing_native": round(before_miss[v], 2),
            "pct_missing_regridded": round(after, 2),
        })
        say(f"  {v:10s} {native_res[key]:>9s} deg -> 0.25 deg   "
            f"NaN {before_miss[v]:5.1f}% -> {after:5.1f}%")

# ================================================ STEP 9 GLORYS TARGET
rule("STEP 9 - GLORYS VERTICAL INTERPOLATION TO DEBUG DEPTHS")
gl = loaded["glorys"].sel(time=use_dates)
native_depths = gl.depth.values.astype("float64")
say(f"  native levels available: {native_depths.size} "
    f"({native_depths.min():.3f} .. {native_depths.max():.2f} m)")

t_interp, provenance = interp_depths(gl["thetao"], [float(d) for d in DEBUG_DEPTHS])
say("\n  requested -> native levels used:")
depth_rows = []
for d, p in provenance.items():
    tag = "CLAMPED" if p["clamped"] else "linear"
    say(f"    {d:7.1f} m : below={p['native_below_m']:9.3f}  above={p['native_above_m']:9.3f}  [{tag}]")
    depth_rows.append({"requested_depth_m": d, **p})

say("\n  horizontally regridding target to canonical grid ...")
targets: dict[str, xr.DataArray] = {}
for i, d in enumerate(DEBUG_DEPTHS):
    da = t_interp.isel(depth=i).drop_vars("depth")
    rg = regrid_horizontal(xr.Dataset({"t": da}), method="linear")["t"]
    name = f"temp_{int(d)}m"
    rg.attrs = {"units": "degC", "long_name": f"GLORYS12V1 potential temperature at {d} m",
                "source_product": "GLORYS12V1", "doi": "10.48670/moi-00021",
                "vertical_method": provenance[float(d)]["method"],
                "native_levels_used": f"{provenance[float(d)]['native_below_m']}, "
                                      f"{provenance[float(d)]['native_above_m']}"}
    targets[name] = rg
    say(f"    {name:12s} NaN={100*np.isnan(rg.values.astype('float64')).mean():5.1f}%")

# ================================================ OCEAN MASK (documented fix)
rule("OCEAN MASK (documented correction, not a silent fix)")
say("  OSTIA analyses inland water bodies; 338 native cells inside the domain box")
say("  sit on the Tibetan Plateau (lat 28.5-31.0, lon 85.3-91.0) at 0.06-1.61 degC.")
say("  These are lakes, not ocean. Rather than clipping values, the merged dataset")
say("  is masked to cells where the GLORYS target itself is defined: if there is no")
say("  training target at a cell, it is not a valid model sample.")
ocean = np.isfinite(targets["temp_0m"])
say(f"  ocean cells per timestep: {int(ocean.isel(time=0).sum())} of {grid.attrs['n_cells']} "
    f"({100*float(ocean.isel(time=0).mean()):.1f}%)")

merged_vars = {}
for name, da in {**surface, **targets}.items():
    merged_vars[name] = da.where(ocean)

# ==================================================== STEP 11 MERGE
rule("STEP 11 - MERGE INTO ONE DATASET (time, lat, lon)")
merged = xr.Dataset(merged_vars)
merged = merged.transpose("time", "lat", "lon")
say(f"  dims: {dict(merged.sizes)}")
say(f"  surface vars: {[v for v in merged.data_vars if not v.startswith('temp_')]}")
say(f"  target vars : {[v for v in merged.data_vars if v.startswith('temp_')]}")

# ==================================================== STEP 12 VALIDATE
rule("STEP 12 - VALIDATION")
ref_t, ref_la, ref_lo = merged.time.values, merged.lat.values, merged.lon.values
for v in merged.data_vars:
    assert np.array_equal(merged[v].time.values, ref_t), f"{v}: time mismatch"
    assert np.array_equal(merged[v].lat.values, ref_la), f"{v}: lat mismatch"
    assert np.array_equal(merged[v].lon.values, ref_lo), f"{v}: lon mismatch"
say("  PASS: all variables share identical time / lat / lon coordinates")

assert len(np.unique(ref_t)) == len(ref_t), "duplicate times"
assert np.all(np.diff(ref_la) > 0) and np.all(np.diff(ref_lo) > 0), "coords not ascending"
assert ref_la.size == 101 and ref_lo.size == 241, "unexpected grid shape"
say(f"  PASS: no duplicate coords; ascending; shape {ref_la.size} x {ref_lo.size}")

stats_df = sanity.stats(merged)
stats_df.to_csv(TAB / "merged_variable_stats.csv", index=False)
say("\n" + stats_df.drop(columns=["argmin", "argmax"]).to_string(index=False))

say("\n  post-merge flags:")
mflags = sanity.flags(merged)
for line in (mflags or ["    none"]):
    say(f"    {line}")

pd.DataFrame(regrid_rows).to_csv(TAB / "regridding_report.csv", index=False)
pd.DataFrame(depth_rows).to_csv(TAB / "glorys_depth_interpolation.csv", index=False)

# ==================================================== STEP 12 FIGURES
rule("STEP 12 - DIAGNOSTIC FIGURES")
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

day = merged.isel(time=0)
daystr = str(merged.time.values[0])[:10]


def _panel(ax, da, title, cmap, units):
    m = ax.pcolormesh(merged.lon, merged.lat, da, cmap=cmap, shading="auto")
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("lon (degE)", fontsize=8)
    ax.set_ylabel("lat (degN)", fontsize=8)
    ax.tick_params(labelsize=7)
    cb = plt.colorbar(m, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label(units, fontsize=8)
    cb.ax.tick_params(labelsize=7)


figs = [
    ("sst",  "01_sst",  "SST (OSTIA)",            "RdYlBu_r", "degC"),
    ("sss",  "02_sss",  "SSS (SMAP 8-day)",       "viridis",  "PSU"),
    ("sla",  "03_sla",  "SLA (DUACS)",            "RdBu_r",   "m"),
]
for var, fname, title, cmap, units in figs:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    _panel(ax, day[var], f"{title} - {daystr}", cmap, units)
    fig.tight_layout()
    fig.savefig(FIG / f"{fname}_{daystr}.png", dpi=130)
    plt.close(fig)
    say(f"  wrote {fname}_{daystr}.png")

# vector plots
for pref, u, v, title, fname in [("current", "current_u", "current_v", "OSCAR surface currents", "04_currents"),
                                 ("wind", "wind_u", "wind_v", "CCMP 10 m winds (daily mean)", "05_winds")]:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    spd = np.sqrt(day[u] ** 2 + day[v] ** 2)
    _panel(ax, spd, f"{title} - {daystr}", "magma", "m s-1")
    # Subsample hard and scale by the field's own magnitude: at full density the
    # arrows overlap into a solid mass and the direction becomes unreadable.
    s = 6
    qscale = 220.0 if pref == "wind" else 12.0
    ax.quiver(merged.lon[::s], merged.lat[::s],
              day[u][::s, ::s], day[v][::s, ::s],
              scale=qscale, width=0.0022, color="w",
              headwidth=4, headlength=5, alpha=0.9)
    fig.tight_layout()
    fig.savefig(FIG / f"{fname}_{daystr}.png", dpi=130)
    plt.close(fig)
    say(f"  wrote {fname}_{daystr}.png")

fig, ax = plt.subplots(figsize=(9, 4.2))
_panel(ax, day["temp_100m"], f"GLORYS temperature at 100 m - {daystr}", "RdYlBu_r", "degC")
fig.tight_layout()
fig.savefig(FIG / f"06_glorys_temp100m_{daystr}.png", dpi=130)
plt.close(fig)
say(f"  wrote 06_glorys_temp100m_{daystr}.png")

# depth profile sanity figure
fig, ax = plt.subplots(figsize=(5, 5))
prof = [float(day[f"temp_{int(d)}m"].mean(skipna=True)) for d in DEBUG_DEPTHS]
ax.plot(prof, DEBUG_DEPTHS, "o-")
ax.invert_yaxis()
ax.set_xlabel("domain-mean temperature (degC)")
ax.set_ylabel("depth (m)")
ax.set_title(f"Mean vertical profile - {daystr}", fontsize=10)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(FIG / f"07_mean_profile_{daystr}.png", dpi=130)
plt.close(fig)
say(f"  wrote 07_mean_profile_{daystr}.png  (domain means: "
    f"{['%.2f' % p for p in prof]})")

# ==================================================== STEP 13 SINGLE CELL
rule("STEP 13 - SINGLE-CELL PROOF")
complete = merged.notnull().to_array().all("variable")
# require an open-ocean cell: away from the coast, all 12 variables present
open_ocean = complete & (merged.lat > 8) & (merged.lat < 20) & (merged.lon > 60) & (merged.lon < 90)
idx = np.argwhere(open_ocean.isel(time=0).values)
if not len(idx):
    raise SystemExit("FATAL: no grid cell has all variables present")
ilat, ilon = idx[len(idx) // 2]
cell = merged.isel(time=0, lat=int(ilat), lon=int(ilon))
say(f"  date {daystr}   lat {float(cell.lat):.2f} N   lon {float(cell.lon):.2f} E")
say(f"  (chosen from {len(idx)} fully-populated open-ocean cells)")

provenance_map = {
    "sst": "OSTIA L4 REP / METOFFICE-GLO-SST-L4-REP-OBS-SST (10.48670/moi-00168)",
    "sss": "SMAP JPL L3 CAP v5.0 8-day (10.5067/SMP50-3TPCS)",
    "sla": "DUACS c3s...0.25deg_P1D (10.48670/moi-00145)",
    "current_u": "OSCAR L4_OC_FINAL v2.0 var u (10.5067/OSCAR-25F20)",
    "current_v": "OSCAR L4_OC_FINAL v2.0 var v (10.5067/OSCAR-25F20)",
    "wind_u": "CCMP v3.1 uwnd, daily mean of 4x6h (10.5067/CCMP-6HW10M-L4V31)",
    "wind_v": "CCMP v3.1 vwnd, daily mean of 4x6h (10.5067/CCMP-6HW10M-L4V31)",
}
rows = []
order = ["sst", "sss", "sla", "current_u", "current_v", "wind_u", "wind_v"] + \
        [f"temp_{int(d)}m" for d in DEBUG_DEPTHS]
say("")
for v in order:
    val = float(cell[v])
    if v.startswith("temp_"):
        d = float(v[5:-1])
        p = provenance[d]
        src = (f"GLORYS12V1 thetao (10.48670/moi-00021); {p['method']}; "
               f"native levels {p['native_below_m']} / {p['native_above_m']} m")
    else:
        src = provenance_map[v]
    units = merged[v].attrs.get("units", "")
    say(f"    {v:12s} = {val:10.4f} {units:6s}  <- {src}")
    rows.append({"date": daystr, "lat": float(cell.lat), "lon": float(cell.lon),
                 "variable": v, "value": val, "units": units, "source": src})
pd.DataFrame(rows).to_csv(TAB / "single_cell_proof.csv", index=False)
say(f"\n  wrote {TAB / 'single_cell_proof.csv'}")

# ==================================================== STEP 15 SAVE
rule("STEP 15 - SAVE DEVELOPMENT DATASET")
merged.attrs = {
    "title": "OceanEmbed Phase 6A development dataset (smoke test)",
    "pipeline_version": PIPELINE_VERSION,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "domain": f"lat {SOUTH}-{NORTH} N, lon {WEST}-{EAST} E",
    "target_grid": f"{grid.attrs['n_lat']} x {grid.attrs['n_lon']} at 0.25 deg "
                   f"({grid.attrs['n_cells']} cells)",
    "time_period": f"{str(use_dates[0])[:10]} .. {str(use_dates[-1])[:10]}",
    "regridding_method": "xarray.interp linear; NaN propagated; no land fill; no extrapolation",
    "vertical_interpolation": "linear between bracketing GLORYS native levels; "
                              "0 m CLAMPED to shallowest native level 0.494 m",
    "ocean_mask": "cells where GLORYS thetao is defined",
    "source_sst": "OSTIA L4 REP (10.48670/moi-00168)",
    "source_sss": "SMAP JPL L3 CAP v5.0 8-day running mean (10.5067/SMP50-3TPCS)",
    "source_sla": "DUACS C3S 0.25deg daily (10.48670/moi-00145)",
    "source_currents": "OSCAR L4_OC_FINAL v2.0 (10.5067/OSCAR-25F20)",
    "source_winds": "CCMP v3.1 6-hourly -> daily vector mean (10.5067/CCMP-6HW10M-L4V31)",
    "source_target": "GLORYS12V1 (10.48670/moi-00021)",
    "note": "Smoke test only. Debug depth subset (5 of 15). Not for modelling claims.",
}
zpath = PROC / "oceanembed_smoketest_2020_01_dev.zarr"
npath = PROC / "oceanembed_smoketest_2020_01_dev.nc"
if zpath.exists():
    import shutil
    shutil.rmtree(zpath)
merged.to_zarr(zpath, mode="w", consolidated=True)
merged.to_netcdf(npath)
say(f"  wrote {zpath}  ({sum(f.stat().st_size for f in zpath.rglob('*') if f.is_file())/1e6:.1f} MB)")
say(f"  wrote {npath}  ({npath.stat().st_size/1e6:.1f} MB)")

(OUT / "logs" / "build_phase6a.log").write_text("\n".join(LOG), encoding="utf-8")
json.dump({"use_dates": [str(d)[:10] for d in use_dates],
           "depth_provenance": {str(k): v for k, v in provenance.items()},
           "native_flags": native_flags, "merged_flags": mflags},
          open(OUT / "logs" / "build_phase6a_meta.json", "w"), indent=2)
say("\nDONE.")
