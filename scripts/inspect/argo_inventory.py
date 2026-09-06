"""STEP 14 - Argo inventory ONLY.

Inspects both Argo resources supplied in the archives and reports what they
contain. Deliberately does NOT integrate Argo into training and does NOT build
the validation pipeline - that is a later phase.

Run:  PYTHONPATH=src python scripts/inspect/argo_inventory.py
"""
from __future__ import annotations

import glob
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from oceanembed.config import EAST, NORTH, REPO_ROOT, SOUTH, WEST  # noqa: E402

warnings.filterwarnings("ignore")

TAB = REPO_ROOT / "outputs" / "tables"
TAB.mkdir(parents=True, exist_ok=True)
LOG: list[str] = []


def say(m: str = "") -> None:
    print(m)
    LOG.append(m)


def _s(x) -> str:
    """Decode an Argo fixed-width byte string."""
    if isinstance(x, bytes):
        return x.decode("utf-8", "ignore").strip()
    return str(x).strip()


# ============================================================ A. GRIDDED ARGO
say("=" * 74)
say("A. INCOIS GRIDDED ARGO  (Argo gridded.nc)")
say("=" * 74)
g = xr.open_dataset(REPO_ROOT / "data/raw/_extracted/Ocean_embed_datas/Argo gridded.nc")
say(f"  title       : {g.attrs.get('title')}")
say(f"  institution : {g.attrs.get('institution')}")
say(f"  product type: GRIDDED (objective/variational analysis), NOT raw profiles")
say(f"  dims        : {dict(g.sizes)}")
say(f"  variables   : {list(g.data_vars)}")
say(f"  dates       : {[str(t)[:10] for t in g.time.values]}  -> MONTHLY fields")
say(f"  lat         : {float(g.latitude.min())} .. {float(g.latitude.max())} "
    f"(n={g.sizes['latitude']}, {float(g.attrs.get('geospatial_lat_resolution', 1.0))} deg)")
say(f"  lon         : {float(g.longitude.min())} .. {float(g.longitude.max())} "
    f"(n={g.sizes['longitude']})")
say(f"  depths (m)  : {[float(z) for z in g.ZAX.values]}")
t = g["TEMP"].values.astype("float64")
say(f"  TEMP        : units={g['TEMP'].attrs.get('units')} "
    f"min={np.nanmin(t):.2f} max={np.nanmax(t):.2f} missing={100*np.isnan(t).mean():.1f}%")
say(f"  QC info     : none present (this is an analysed field, not observations)")
say("")
say("  Depth comparison vs the 15 SIH target depths:")
sih = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]
zax = [float(z) for z in g.ZAX.values]
say(f"    SIH depths present in this product : {[d for d in sih if d in zax]}")
say(f"    SIH depths ABSENT from this product: {[d for d in sih if d not in zax]}")
say(f"    Extra levels this product carries  : {[z for z in zax if z not in sih]}")
say("")
say("  LIMITATIONS for validation use:")
say("    * 1 deg grid - 4x coarser than the 0.25 deg reconstruction target")
say("    * MONTHLY - cannot validate daily output without temporal aggregation")
say("    * only 2 timesteps supplied (2020-01-15, 2020-02-15)")
say("    * 0 m is not a level; shallowest is 5 m")
g.close()

# ============================================================ B. RAW PROFILES
say("")
say("=" * 74)
say("B. RAW ARGO PROFILES  (Agro data.zip -> *_prof.nc)")
say("=" * 74)
files = sorted(glob.glob(str(REPO_ROOT / "data/raw/_extracted/Agro_data/*_prof.nc")))
say(f"  files: {len(files)}  ({Path(files[0]).name} .. {Path(files[-1]).name})")

rows = []
for f in files:
    d = xr.open_dataset(f)
    lat = d["LATITUDE"].values.astype("float64")
    lon = d["LONGITUDE"].values.astype("float64")
    juld = pd.to_datetime(d["JULD"].values)
    wmo = [_s(x) for x in d["PLATFORM_NUMBER"].values]
    mode = [_s(x) for x in d["DATA_MODE"].values]
    pqc = [_s(x) for x in d["POSITION_QC"].values]
    in_dom = (lat >= SOUTH) & (lat <= NORTH) & (lon >= WEST) & (lon <= EAST)
    temp = d["TEMP"].values.astype("float64")
    pres = d["PRES"].values.astype("float64")
    for i in range(d.sizes["N_PROF"]):
        rows.append({
            "file": Path(f).name,
            "date": str(juld[i])[:10],
            "wmo": wmo[i],
            "lat": lat[i],
            "lon": lon[i],
            "in_domain": bool(in_dom[i]),
            "data_mode": mode[i],          # R=real-time, A=adjusted, D=delayed
            "position_qc": pqc[i],
            "n_levels": int(np.isfinite(temp[i]).sum()),
            "max_pressure_dbar": float(np.nanmax(pres[i])) if np.isfinite(pres[i]).any() else np.nan,
        })
    d.close()

df = pd.DataFrame(rows)
say(f"  total profiles (global)      : {len(df)}")
say(f"  distinct floats (global)     : {df.wmo.nunique()}")
say(f"  date range                   : {df.date.min()} .. {df.date.max()}")
say(f"  global lat range             : {df.lat.min():.2f} .. {df.lat.max():.2f}")
say(f"  global lon range             : {df.lon.min():.2f} .. {df.lon.max():.2f}")
say("")
say("  >>> These files are GLOBAL, not pre-subset to the OceanEmbed domain. <<<")

dom = df[df.in_domain]
say("")
say(f"  IN DOMAIN ({SOUTH}-{NORTH}N, {WEST}-{EAST}E):")
say(f"    profiles            : {len(dom)}  ({100*len(dom)/len(df):.1f}% of global)")
say(f"    distinct floats     : {dom.wmo.nunique()}")
say(f"    days with >=1 profile: {dom.date.nunique()} of {df.date.nunique()}")
say(f"    mean profiles/day   : {len(dom)/max(df.date.nunique(),1):.1f}")
say(f"    lat range           : {dom.lat.min():.2f} .. {dom.lat.max():.2f}")
say(f"    lon range           : {dom.lon.min():.2f} .. {dom.lon.max():.2f}")
say(f"    max pressure (dbar) : median={dom.max_pressure_dbar.median():.0f} "
    f"max={dom.max_pressure_dbar.max():.0f}")
say(f"    levels per profile  : median={dom.n_levels.median():.0f} "
    f"min={dom.n_levels.min()} max={dom.n_levels.max()}")
say("")
say("  DATA_MODE breakdown in domain (R=real-time, A=adjusted, D=delayed/best):")
for k, v in dom.data_mode.value_counts().items():
    say(f"    {k}: {v}")
say("")
say("  POSITION_QC breakdown in domain (1=good, 8=interpolated):")
for k, v in dom.position_qc.value_counts().items():
    say(f"    {k}: {v}")

say("")
say("  QC variables available per profile: PRES_QC, TEMP_QC, PSAL_QC,")
say("    PROFILE_*_QC, plus *_ADJUSTED and *_ADJUSTED_ERROR fields.")

# Overlap with the Phase 6A smoke-test window
smoke = dom[dom.date.isin(["2020-01-01", "2020-01-02"])]
say("")
say(f"  Profiles inside the Phase 6A smoke-test window (2020-01-01..02): {len(smoke)}")
if len(smoke):
    say(smoke[["date", "wmo", "lat", "lon", "n_levels", "max_pressure_dbar",
               "data_mode"]].to_string(index=False))

df.to_csv(TAB / "argo_profile_inventory.csv", index=False)
dom.to_csv(TAB / "argo_profile_inventory_in_domain.csv", index=False)
say("")
say(f"  wrote {TAB / 'argo_profile_inventory.csv'} ({len(df)} rows)")
say(f"  wrote {TAB / 'argo_profile_inventory_in_domain.csv'} ({len(dom)} rows)")
say("")
say("  STEP 14 SCOPE: inventory only. Argo is NOT integrated into training and")
say("  the validation pipeline is NOT built in Phase 6A.")

(REPO_ROOT / "outputs" / "logs" / "argo_inventory.log").write_text("\n".join(LOG), encoding="utf-8")
