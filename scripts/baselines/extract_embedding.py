"""Extract the satellite embedding z for a requested date / latitude / longitude.

This is the artefact the Satellite Embedding Engine exists to produce. The
embedding is the encoder output for the 17x17 surface patch centred on the
requested cell; it is computed from surface observations alone and never sees
temperature.

Individual latent dimensions are NOT interpreted as physical variables here -
that is deliberate and belongs to a later phase.

Examples
--------
  python scripts/baselines/extract_embedding.py --date 2021-05-01 --lat 13.25 --lon 85.75
  python scripts/baselines/extract_embedding.py --date 2021-05-01 --lat 13.25 --lon 85.75 --with-profile
  python scripts/baselines/extract_embedding.py --date 2021-05-01 --field --out z_field.nc
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import pandas as pd
import torch
import xarray as xr
import yaml

from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.features import cyclic_doy
from oceanembed.ml.l2_dataset import DayFieldSampler
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.scaler import ZScoreScaler

CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = CFG["targets"]["depths_m"]
BASE = REPO_ROOT / CFG["paths"]["baselines"]
MODELS = REPO_ROOT / CFG["paths"]["models"]


def split_for_date(date: str) -> tuple[str, bool]:
    d = pd.Timestamp(date)
    for name in ("train", "validation", "test"):
        s, e = splits.split_bounds(name)
        if pd.Timestamp(s) <= d <= pd.Timestamp(e):
            return name, name == "test"
    raise SystemExit(f"{date} is outside the dataset window "
                     f"{splits.SPLITS['dataset']['start']}..{splits.SPLITS['dataset']['end']}")


def load_model(tag: str):
    ck = torch.load(MODELS / f"phase6b_l2_{tag}.pt", map_location="cpu", weights_only=False)
    m = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    m.load_state_dict(ck["state_dict"])
    m.eval()
    return m, ck


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--tag", default="final")
    ap.add_argument("--field", action="store_true", help="embed every cell for the date")
    ap.add_argument("--out", default=None)
    ap.add_argument("--with-profile", action="store_true",
                    help="also decode the 15-depth profile")
    ap.add_argument("--allow-test", action="store_true")
    args = ap.parse_args()

    split, is_test = split_for_date(args.date)
    if is_test and not args.allow_test:
        raise SystemExit(f"{args.date} falls in the LOCKED test split. "
                         "Pass --allow-test if that is genuinely intended.")
    model, ck = load_model(args.tag)
    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")

    ds = splits.open_split(split, allow_test=args.allow_test)
    times = pd.DatetimeIndex(ds.time.values)
    hits = np.where(times == pd.Timestamp(args.date))[0]
    if not len(hits):
        raise SystemExit(f"{args.date} not present in split {split}")
    t = int(hits[0])

    smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=ck["patch"])
    field, ctx, _, _, _ = smp.day(t)
    with torch.no_grad():
        zf = model.embed_field(torch.from_numpy(field)[None])[0].numpy()  # (latent, nlat, nlon)

    print(f"date {args.date}  split={split}  patch={ck['patch']}  latent={ck['latent']}")

    if args.field:
        out = xr.Dataset(
            {"satellite_embedding": (("z", "lat", "lon"), zf)},
            coords={"z": np.arange(zf.shape[0]), "lat": ds.lat.values, "lon": ds.lon.values},
            attrs={"description": "L2 satellite embedding, one vector per grid cell",
                   "date": args.date, "patch": int(ck["patch"]),
                   "latent_dim": int(ck["latent"]),
                   "receptive_field": int(ck["receptive_field"]),
                   "source": "surface observations only; no temperature input"})
        path = args.out or f"outputs/models/z_field_{args.date}.nc"
        out.to_netcdf(path)
        print(f"wrote {path}  shape={zf.shape}")
        return 0

    if args.lat is None or args.lon is None:
        raise SystemExit("--lat and --lon are required unless --field is given")

    i = int(np.abs(ds.lat.values - args.lat).argmin())
    j = int(np.abs(ds.lon.values - args.lon).argmin())
    z = zf[:, i, j]
    print(f"nearest grid cell: lat {float(ds.lat.values[i]):.2f} N  "
          f"lon {float(ds.lon.values[j]):.2f} E")
    ocean = bool(ds["ocean_mask"].isel(time=t).values[i, j])
    valid = bool(ds["surface_input_valid"].isel(time=t).values[i, j])
    print(f"ocean_mask={ocean}  surface_input_valid={valid}")
    print(f"\nsatellite_embedding z (dim {z.size}):")
    print(np.array2string(z, precision=4, max_line_width=100))

    if args.with_profile:
        s, cc = cyclic_doy(times[t:t + 1])
        raw = np.array([[float(ds.lat.values[i]), float(ds.lon.values[j]), s[0], cc[0]]])
        ctx1 = ((raw - fs.mean[7:]) / fs.std[7:]).astype("float32")
        with torch.no_grad():
            p = ts.inverse_transform(
                model.forward_from_z(torch.from_numpy(z[None]),
                                     torch.from_numpy(ctx1)).numpy().astype("float64"))[0]
        print("\ndecoded profile (degC):")
        for d, v in zip(DEPTHS, p):
            print(f"  temp_{d:<5d}m  {v:7.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
