"""Phase 6C-A: observational validation of frozen L0/L1/L2 against Argo.

No model is trained, no optimiser is created, no weight is written. The frozen
checkpoints are loaded, hashed, and used for inference only.

Design decisions fixed before any metric was computed:

* Predictions are produced ON THE GRID and then interpolated to the Argo
  position. The alternative - interpolating the surface inputs to the profile
  location and then predicting - would be a different operation for L1 and L2
  and would not be applicable to L0 or GLORYS at all. Predicting-then-
  interpolating treats all four systems identically.
* GLORYS here is the regridded 0.25 deg target the models were trained against,
  read from the frozen model-ready store, so "OceanEmbed vs GLORYS" compares
  like with like.
* The accepted sample population is INTERSECTED across L0, L1, L2 and GLORYS at
  every depth, so no system gains samples through more permissive missingness.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import pandas as pd
import torch
import xarray as xr
import yaml

from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.climatology import HarmonicClimatology
from oceanembed.ml.embedding_cache import EmbeddingCache
from oceanembed.ml.features import SURFACE, cyclic_doy
from oceanembed.ml.l2_dataset import DayFieldSampler
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.model import PointwiseMLP
from oceanembed.ml.scaler import ZScoreScaler
from oceanembed.validation import argo as A
from oceanembed.validation.collocate import METHOD, interp_point, nearest_grid_cell

B6 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = B6["targets"]["depths_m"]
BASE = REPO_ROOT / B6["paths"]["baselines"]
MODELS = REPO_ROOT / B6["paths"]["models"]
ARGO_OUT = REPO_ROOT / "outputs" / "argo"
FLOATS = REPO_ROOT / "data" / "raw" / "argo_gdac" / "floats"

AUDIT_START, AUDIT_END = "2022-01-01", "2023-12-31"
HELDOUT_START = "2024-01-01"


def sha(sd) -> str:
    h = hashlib.sha256()
    for k in sorted(sd):
        h.update(k.encode())
        h.update(np.ascontiguousarray(sd[k].detach().cpu().numpy()).tobytes())
    return h.hexdigest()


# ------------------------------------------------------------------ step 1
def build_argo_table() -> tuple[pd.DataFrame, dict]:
    """QC, convert to potential temperature, interpolate to the 15 depths."""
    files = sorted(glob.glob(str(FLOATS / "*_prof.nc")))
    print(f"reading {len(files)} float files")
    rows, stats = [], {
        "files_read": 0, "profiles_seen": 0, "outside_window": 0,
        "outside_domain": 0, "rejected_profile_qc": {}, "rejected_no_levels": 0,
        "rejected_adjusted_empty": 0, "accepted": 0,
        "data_mode": {}, "levels_accepted_total": 0,
    }
    for fp in files:
        try:
            ds = xr.open_dataset(fp, decode_timedelta=False)
        except Exception as exc:  # noqa: BLE001
            print(f"  unreadable {Path(fp).name}: {exc}")
            continue
        stats["files_read"] += 1
        n = ds.sizes.get("N_PROF", 0)
        juld = pd.to_datetime(ds["JULD"].values)
        lat = np.asarray(ds["LATITUDE"].values, dtype="float64")
        lon = np.asarray(ds["LONGITUDE"].values, dtype="float64")
        for i in range(n):
            stats["profiles_seen"] += 1
            t = juld[i]
            if pd.isna(t) or not (pd.Timestamp(AUDIT_START) <= t <=
                                  pd.Timestamp(AUDIT_END) + pd.Timedelta(days=1)):
                stats["outside_window"] += 1
                continue
            if not (5.0 <= lat[i] <= 30.0 and 45.0 <= lon[i] <= 105.0):
                stats["outside_domain"] += 1
                continue
            ok, why = A.profile_is_acceptable(ds, i)
            if not ok:
                stats["rejected_profile_qc"][why] = \
                    stats["rejected_profile_qc"].get(why, 0) + 1
                continue
            f = A.select_fields(ds, i)
            stats["data_mode"][f["data_mode"]] = stats["data_mode"].get(f["data_mode"], 0) + 1
            acc = A.accepted_levels(f)
            if acc.sum() < 2:
                if f["used_adjusted"] and f["TEMP"] is not None and \
                        not np.isfinite(np.asarray(f["TEMP"], dtype="float64")).any():
                    stats["rejected_adjusted_empty"] += 1
                else:
                    stats["rejected_no_levels"] += 1
                continue
            m = acc
            pt, depth = A.to_potential_temperature(
                np.asarray(f["PRES"])[:len(m)][m], np.asarray(f["TEMP"])[:len(m)][m],
                np.asarray(f["PSAL"])[:len(m)][m], lon[i], lat[i])
            vals, sup, gap = A.interp_to_depths(depth, pt, DEPTHS)
            if not sup.any():
                stats["rejected_no_levels"] += 1
                continue
            stats["accepted"] += 1
            stats["levels_accepted_total"] += int(m.sum())
            rows.append({
                "wmo": A._s(ds["PLATFORM_NUMBER"].values[i]),
                "cycle": int(ds["CYCLE_NUMBER"].values[i]),
                "date": t.normalize(), "juld": t,
                "lat": float(lat[i]), "lon": float(lon[i]),
                "data_mode": f["data_mode"], "used_adjusted": bool(f["used_adjusted"]),
                "temp_source": f["TEMP_source"], "psal_source": f["PSAL_source"],
                "n_levels_accepted": int(m.sum()),
                "min_depth_m": float(depth.min()), "max_depth_m": float(depth.max()),
                **{f"argo_pt_{d}m": vals[k] for k, d in enumerate(DEPTHS)},
                **{f"argo_sup_{d}m": bool(sup[k]) for k, d in enumerate(DEPTHS)},
                **{f"argo_gap_{d}m": gap[k] for k, d in enumerate(DEPTHS)},
            })
        ds.close()
    df = pd.DataFrame(rows)
    print(f"accepted {len(df):,} profiles of {stats['profiles_seen']:,} seen")
    return df, stats


# ------------------------------------------------------------------ step 2
def collocate(df: pd.DataFrame) -> pd.DataFrame:
    """Attach L0 / L1 / L2 / GLORYS predictions at each profile position."""
    ck2 = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu", weights_only=False)
    ck1 = torch.load(MODELS / "phase6b_l1_mlp.pt", map_location="cpu", weights_only=False)
    l2 = L2EmbeddingModel(latent=ck2["latent"], patch=ck2["patch"])
    l2.load_state_dict(ck2["state_dict"])
    l2.eval()
    l1 = PointwiseMLP(ck1["n_features"], tuple(ck1["hidden"]), ck1["n_out"])
    l1.load_state_dict(ck1["state_dict"])
    l1.eval()
    for p in list(l1.parameters()) + list(l2.parameters()):
        p.requires_grad_(False)
    sha_l2_before, sha_l1_before = sha(ck2["state_dict"]), sha(ck1["state_dict"])

    clim = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    assert clim.meta["fitted_on"] == "train"
    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"

    ds = splits.open_split("test", allow_test=True)
    cache = EmbeddingCache(REPO_ROOT / "outputs" / "embeddings", "test").load()
    cache.verify_encoder(l2.encoder.state_dict())
    smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=ck2["patch"])
    lat_axis, lon_axis = ds.lat.values, ds.lon.values
    times = pd.DatetimeIndex(ds.time.values)
    r, c = smp.r, smp.c

    out_rows = []
    for date, grp in df.groupby("date"):
        hit = np.where(times == pd.Timestamp(date))[0]
        if not len(hit):
            continue
        t = int(hit[0])
        ctx = torch.from_numpy(smp.context(t))

        # ---- L0 climatology on the grid
        g0 = np.full((len(DEPTHS), lat_axis.size, lon_axis.size), np.nan)
        cpred = clim.predict(times[t:t + 1], r, c)[0]           # (cells, depths)
        for k in range(len(DEPTHS)):
            g0[k, r, c] = cpred[:, k]

        # ---- L1 pointwise on the grid
        surf = np.column_stack([ds[v].isel(time=t).values[r, c] for v in SURFACE])
        s_, c_ = cyclic_doy(times[t:t + 1])
        X1 = np.column_stack([surf, smp.cell_lat, smp.cell_lon,
                              np.full(smp.n_cells, s_[0]), np.full(smp.n_cells, c_[0])])
        okx = np.isfinite(X1).all(axis=1)
        g1 = np.full_like(g0, np.nan)
        with torch.no_grad():
            if okx.any():
                p1 = ts.inverse_transform(
                    l1(torch.from_numpy(fs.transform(X1[okx]).astype("float32"))).numpy())
                for k in range(len(DEPTHS)):
                    g1[k, r[okx], c[okx]] = p1[:, k]
            # ---- L2 from the cached frozen embedding
            z = torch.from_numpy(np.asarray(cache.z[t]))
            p2 = ts.inverse_transform(l2.forward_from_z(z, ctx).numpy().astype("float64"))
        g2 = np.full_like(g0, np.nan)
        for k in range(len(DEPTHS)):
            g2[k, r, c] = p2[:, k]

        # ---- GLORYS reference (the regridded target the models were trained on)
        gg = np.full_like(g0, np.nan)
        for k, d in enumerate(DEPTHS):
            gg[k] = ds[f"temp_{d}m"].isel(time=t).values

        for _, row in grp.iterrows():
            la, lo = row["lat"], row["lon"]
            i, j, off = nearest_grid_cell(lat_axis, lon_axis, la, lo)
            rec = {"wmo": row["wmo"], "cycle": row["cycle"], "date": date,
                   "lat": la, "lon": lo, "grid_lat": float(lat_axis[i]),
                   "grid_lon": float(lon_axis[j]), "grid_offset_deg": off,
                   "data_mode": row["data_mode"],
                   "collocation_method": METHOD, "temporal_offset_days": 0}
            for name, stack in (("L0", g0), ("L1", g1), ("L2", g2), ("GLORYS", gg)):
                for k, d in enumerate(DEPTHS):
                    v, how = interp_point(stack[k], lat_axis, lon_axis, la, lo)
                    rec[f"{name}_{d}m"] = v
                    if name == "L2":
                        rec[f"how_{d}m"] = how
            for k, d in enumerate(DEPTHS):
                rec[f"argo_pt_{d}m"] = row[f"argo_pt_{d}m"]
                rec[f"argo_sup_{d}m"] = row[f"argo_sup_{d}m"]
            out_rows.append(rec)

    assert sha(l2.state_dict()) == sha_l2_before, "L2 weights changed"
    assert sha(l1.state_dict()) == sha_l1_before, "L1 weights changed"
    print(f"collocated {len(out_rows):,} profiles; frozen weights verified unchanged")
    return pd.DataFrame(out_rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    ARGO_OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    pq = ARGO_OUT / "matched_profiles.parquet"
    if pq.exists() and not args.rebuild:
        print(f"{pq} exists; pass --rebuild to redo")
        return 0

    df, stats = build_argo_table()
    if df.empty:
        raise SystemExit("no accepted Argo profiles")
    assert df.date.max() < pd.Timestamp(HELDOUT_START), "HOLDOUT LEAK: 2024 profile present"

    m = collocate(df)
    m.to_parquet(pq, index=False)
    stats["collocated"] = int(len(m))
    stats["audit_window"] = [AUDIT_START, AUDIT_END]
    stats["collocation_method"] = METHOD
    json.dump(stats, open(ARGO_OUT / "qc_summary.json", "w"), indent=2, default=str)
    json.dump({"method": METHOD, "n_matched": int(len(m)),
               "depths_m": DEPTHS, "audit_window": [AUDIT_START, AUDIT_END],
               "heldout_untouched": [HELDOUT_START, "2024-12-15"],
               "grid": "canonical 0.25 deg, 101 x 241",
               "temporal_matching": "same UTC calendar day, offset 0",
               "glorys_reference": "regridded model-ready target temp_<d>m"},
              open(ARGO_OUT / "collocation_manifest.json", "w"), indent=2)
    print(f"\nwrote {pq} ({len(m):,} rows) in {(time.time()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
