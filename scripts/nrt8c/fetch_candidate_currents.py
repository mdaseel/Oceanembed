"""Phase 8C: acquire the candidate operational current product.

Downloads the CMEMS GlobCurrent-lineage NRT daily currents over the padded NIO
box for the two pre-registered windows, and harmonises them onto the canonical
grid with the SAME functions every other channel uses.

Primary (decision-bearing) definition, fixed in the pre-registration:

    current_u = ugos + ue(15 m)      geostrophic + Ekman, tide EXCLUDED
    current_v = vgos + ve(15 m)

Secondary (reported, never decision-bearing):

    current_u_total = uo(15 m)       the product's own total, tide INCLUDED
    current_v_total = vo(15 m)

    python scripts/nrt8c/fetch_candidate_currents.py --window d1
    python scripts/nrt8c/fetch_candidate_currents.py --window d2
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

from oceanembed.config import EAST, NORTH, SOUTH, WEST  # noqa: E402
from oceanembed.nrt import harmonize as H  # noqa: E402

DATASET = "cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m"
PRODUCT = "MULTIOBS_GLO_PHY_MYNRT_015_003"
VARIABLES = ["ugos", "vgos", "ue", "ve", "uo", "vo"]
DEPTH_M = 15.0
PAD = 1.0
BOX = dict(minimum_longitude=WEST - PAD, maximum_longitude=EAST + PAD,
           minimum_latitude=SOUTH - PAD, maximum_latitude=NORTH + PAD)

WINDOWS = {
    # D1: the 56 pre-registered Phase 6C-D dates live inside this window.
    "d1": ("2024-07-01", "2024-12-15", "currents_candidate_d1"),
    # D2: the existing 2022-23 Argo collocations, from candidate coverage start.
    "d2": ("2022-05-01", "2023-12-31", "currents_candidate_d2"),
}
RAW = ROOT / "data" / "raw" / "nrt" / "currents_candidate"
CANON = ROOT / "data" / "processed" / "nrt"
META = ROOT / "outputs" / "phase8c" / "candidate_product.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def at_depth(ds: xr.Dataset, name: str) -> xr.DataArray:
    """One variable at the 15 m level; geostrophy has no depth axis."""
    a = ds[name]
    if "depth" in a.dims:
        a = a.sel(depth=DEPTH_M, method="nearest")
        a = a.drop_vars("depth", errors="ignore")
    return a


def harmonise(raw_path: Path) -> xr.Dataset:
    with xr.open_dataset(raw_path) as ds:
        ds = ds.load()
    out = xr.Dataset({
        "current_u": at_depth(ds, "ugos") + at_depth(ds, "ue"),
        "current_v": at_depth(ds, "vgos") + at_depth(ds, "ve"),
        "current_u_total": at_depth(ds, "uo"),
        "current_v_total": at_depth(ds, "vo"),
    })
    for v in out.data_vars:
        out[v].attrs = {
            "units": "m s-1", "unit_conversion": "none",
            "definition": ("ugos + ue at 15 m (geostrophic + Ekman, tide excluded)"
                           if not v.endswith("_total") else
                           "uo/vo at 15 m (product total, tide included)"),
            "depth_m": DEPTH_M, "source_dataset": DATASET}
    out = H.rename_coords(out)
    return H.to_canonical(H.__dict__["normalise_time_daily"](out))


def main() -> int:
    import copernicusmarine as cm
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", choices=sorted(WINDOWS), required=True)
    args = ap.parse_args()
    start, end, stem = WINDOWS[args.window]

    RAW.mkdir(parents=True, exist_ok=True)
    CANON.mkdir(parents=True, exist_ok=True)
    dst = RAW / f"{stem}_{start}_{end}.nc"
    t0 = time.time()
    if not (dst.exists() and dst.stat().st_size > 0):
        tmp = f"{stem}.part.nc"
        cm.subset(dataset_id=DATASET, variables=VARIABLES,
                  output_directory=str(RAW), output_filename=tmp,
                  file_format="netcdf", overwrite=True, disable_progress_bar=True,
                  start_datetime=f"{start}T00:00:00", end_datetime=f"{end}T23:59:59",
                  minimum_depth=DEPTH_M, maximum_depth=DEPTH_M, **BOX)
        (RAW / tmp).replace(dst)
    print(f"[{stem}] raw {dst.stat().st_size / 1e6:.1f} MB ({time.time() - t0:.0f}s)")

    canon = harmonise(dst)
    out_path = CANON / f"{stem}_canonical.nc"
    canon.to_netcdf(out_path)
    times = pd.DatetimeIndex(canon.time.values)
    print(f"[{stem}] canonical {dict(canon.sizes)} {times[0].date()}..{times[-1].date()}")

    META.parent.mkdir(parents=True, exist_ok=True)
    record = json.loads(META.read_text(encoding="utf-8")) if META.is_file() else {
        "product_id": PRODUCT, "dataset_id": DATASET,
        "provider": "Copernicus Marine",
        "primary_definition": "current_u = ugos + ue(15 m); current_v = vgos + ve(15 m) "
                              "(geostrophic + Ekman, tide excluded)",
        "secondary_definition": "current_u_total = uo(15 m); current_v_total = vo(15 m) "
                                "(product total, tide included) - reported only",
        "units": "m s-1", "depth_m": DEPTH_M,
        "harmonisation": "nrt.harmonize.to_canonical (training regrid), "
                         "ascending lat, [-180,180) lon, canonical 101x241",
        "replay_mode": "RETROSPECTIVE",
        "preregistration": "outputs/phase8c/OPERATIONAL_CURRENT_SUBSTITUTION_PREREGISTRATION.md",
        "preregistration_commit": "c01c170",
        "windows": {},
    }
    record["windows"][args.window] = {
        "start": start, "end": end,
        "raw_file": str(dst.relative_to(ROOT)).replace("\\", "/"),
        "raw_bytes": dst.stat().st_size, "raw_sha256": sha256(dst),
        "canonical_file": str(out_path.relative_to(ROOT)).replace("\\", "/"),
        "n_times": int(times.size),
        "first": str(times[0].date()), "last": str(times[-1].date()),
    }
    META.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"metadata -> {META.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
