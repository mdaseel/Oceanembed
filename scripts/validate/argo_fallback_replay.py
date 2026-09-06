"""Phase 6C-C: replay the registered fallback policies against 2022-2023 Argo.

Reuses the Phase 6C-A accepted profile population and the identical collocation
protocol. No model is trained; the frozen L2 hash is checked before and after.
The 2024 holdout is never opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import pandas as pd
import torch
import yaml

from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.climatology import HarmonicClimatology
from oceanembed.ml.features import SURFACE
from oceanembed.ml.l2_dataset import DayFieldSampler
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.scaler import ZScoreScaler
from oceanembed.ml.surface_climatology import SurfaceClimatology
from oceanembed.operational import (InputDeclaration, PersistenceStore,
                                    assemble_field, reference_complete_field)
from oceanembed.operational.policy import FILL_PERSIST, FILL_TRAIN_CLIM
from oceanembed.validation.collocate import METHOD, interp_point

B6 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = B6["targets"]["depths_m"]
BASE = REPO_ROOT / B6["paths"]["baselines"]
MODELS = REPO_ROOT / B6["paths"]["models"]
ARGO = REPO_ROOT / "outputs" / "argo"
OUT = ARGO / "fallback_replay.parquet"
HELDOUT = pd.Timestamp("2024-01-01")

# (label, absent, stale, prefer_fill)
MODES = [
    ("COMPLETE", set(), {}, None),
    ("SSS_ABSENT_PERSIST", {"sss"}, {}, FILL_PERSIST),
    ("SSS_ABSENT_CLIM", {"sss"}, {}, FILL_TRAIN_CLIM),
    ("CURRENT_STALE_1D", set(), {"current_u": 1, "current_v": 1}, None),
    ("CURRENT_STALE_2D", set(), {"current_u": 2, "current_v": 2}, None),
    ("CURRENT_STALE_3D", set(), {"current_u": 3, "current_v": 3}, None),
    ("WIND_STALE_1D", set(), {"wind_u": 1, "wind_v": 1}, None),
    ("SLA_STALE_1D", set(), {"sla": 1}, None),
    ("SSS_ABSENT_PERSIST_CURRENT_STALE_2D", {"sss"},
     {"current_u": 2, "current_v": 2}, FILL_PERSIST),
]


def sha(sd) -> str:
    h = hashlib.sha256()
    for k in sorted(sd):
        h.update(k.encode())
        h.update(np.ascontiguousarray(sd[k].detach().cpu().numpy()).tobytes())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-dates", type=int, default=0)
    args = ap.parse_args()
    t0 = time.time()

    matched = pd.read_parquet(ARGO / "matched_profiles.parquet")
    matched["date"] = pd.to_datetime(matched["date"])
    assert matched.date.max() < HELDOUT, "HOLDOUT LEAK: 2024 profile present"
    print(f"Argo population: {len(matched):,} profiles, {matched.wmo.nunique()} floats, "
          f"{matched.date.nunique()} dates, "
          f"{matched.date.min().date()}..{matched.date.max().date()}")

    ck = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu", weights_only=False)
    l2 = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    l2.load_state_dict(ck["state_dict"])
    l2.eval()
    for p in l2.parameters():
        p.requires_grad_(False)
    sha_before = sha(ck["state_dict"])

    clim = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    surf_clim = SurfaceClimatology.load(BASE / "phase6cb_surface_climatology.nc")
    assert clim.meta["fitted_on"] == "train" and surf_clim.meta["fitted_on"] == "train"
    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"

    ds = splits.open_split("test", allow_test=True)
    times = pd.DatetimeIndex(ds.time.values)
    smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=ck["patch"])
    lat_ax, lon_ax = ds.lat.values, ds.lon.values
    r, c = smp.r, smp.c

    dates = sorted(matched.date.unique())
    if args.limit_dates:
        dates = dates[:args.limit_dates]
    max_age = 3
    rows = []
    skipped = 0

    for n, date in enumerate(dates, 1):
        hit = np.where(times == pd.Timestamp(date))[0]
        if not len(hit):
            skipped += 1
            continue
        t = int(hit[0])
        if t < max_age:
            skipped += 1          # not enough history for the 3-day mode
            continue
        grp = matched[matched.date == date]
        ctx = torch.from_numpy(smp.context(t))
        when = pd.Timestamp(times[t])

        # persistence store holds the genuinely observed previous-day SSS
        store = PersistenceStore(max_age_days=7)
        store.push("sss", times[t - 1], ds["sss"].isel(time=t - 1).values,
                   source_product="model-ready SSS")

        grids = {}
        for label, absent, stale, fill in MODES:
            if label == "COMPLETE":
                field, man = reference_complete_field(ds, t, fs, ck["patch"])
            else:
                decl = InputDeclaration(requested_valid_time=str(when))
                for v in SURFACE:
                    decl.declare(v, absent=(v in absent), age_days=int(stale.get(v, 0)))
                field, man = assemble_field(ds, t, fs, ck["patch"], decl,
                                            surface_clim=surf_clim, store=store,
                                            prefer_fill=fill)
            with torch.no_grad():
                z = l2.embed_field(torch.from_numpy(field)[None])[0]
                p = ts.inverse_transform(
                    l2.forward_from_z(z[:, r, c].T, ctx).numpy().astype("float64"))
            g = np.full((len(DEPTHS), lat_ax.size, lon_ax.size), np.nan)
            for k in range(len(DEPTHS)):
                g[k, r, c] = p[:, k]
            grids[label] = g

        g0 = np.full((len(DEPTHS), lat_ax.size, lon_ax.size), np.nan)
        cp = clim.predict(times[t:t + 1], r, c)[0]
        for k in range(len(DEPTHS)):
            g0[k, r, c] = cp[:, k]
        grids["L0"] = g0

        for _, row in grp.iterrows():
            rec = {"wmo": row["wmo"], "cycle": row["cycle"], "date": date,
                   "lat": row["lat"], "lon": row["lon"]}
            for k, d in enumerate(DEPTHS):
                rec[f"argo_pt_{d}m"] = row[f"argo_pt_{d}m"]
                rec[f"argo_sup_{d}m"] = row[f"argo_sup_{d}m"]
            for label, g in grids.items():
                for k, d in enumerate(DEPTHS):
                    rec[f"{label}_{d}m"], _ = interp_point(g[k], lat_ax, lon_ax,
                                                           row["lat"], row["lon"])
            rows.append(rec)
        if n % 60 == 0:
            print(f"  {n}/{len(dates)} dates  ({time.time()-t0:.0f}s)", flush=True)

    assert sha(l2.state_dict()) == sha_before, "FROZEN L2 CHANGED during the replay"
    out = pd.DataFrame(rows)
    out.to_parquet(OUT, index=False)
    print(f"\nL2 unchanged: {sha_before[:16]}")
    print(f"replayed {len(out):,} profile matches over {len(dates)-skipped} dates "
          f"({skipped} dates skipped) in {(time.time()-t0)/60:.1f} min")

    json.dump({"n_matches": int(len(out)), "n_dates": int(len(dates) - skipped),
               "skipped_dates": int(skipped),
               "modes": [m[0] for m in MODES],
               "collocation_method": METHOD,
               "argo_window": ["2022-01-01", "2023-12-31"],
               "heldout_2024": "untouched",
               "l2_sha256_before": sha_before, "l2_sha256_after": sha(l2.state_dict()),
               "replay_mode": "RETROSPECTIVE"},
              open(ARGO / "fallback_replay_meta.json", "w"), indent=2)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
