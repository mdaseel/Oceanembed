"""Phase 8C, Phase 6: observational check of the candidate currents against Argo.

Reuses the EXECUTED 2022-2023 Argo collocation population (Phase 6C-A) - the same
profiles, positions, times, QC and collocation rule - and asks one question:

    does the frozen L2 driven by the candidate currents preserve observational
    skill against the SAME Argo values as the frozen L2 driven by OSCAR?

The control is recomputed here and cross-checked against the stored executed
`L2_<depth>m` columns, so a difference in collocation cannot masquerade as a
difference in currents.

2024 Argo is never opened: the population is restricted to the stored 2022-2023
artifact, and to dates on or after the candidate's coverage start (2022-05-01),
exactly as pre-registered.

    python scripts/nrt8c/run_argo_current_check.py
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

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402
import xarray as xr  # noqa: E402
import yaml  # noqa: E402

from oceanembed.config import REPO_ROOT  # noqa: E402
from oceanembed.ml import splits  # noqa: E402
from oceanembed.ml.l2_dataset import DayFieldSampler  # noqa: E402
from oceanembed.ml.l2_model import L2EmbeddingModel  # noqa: E402
from oceanembed.ml.scaler import ZScoreScaler  # noqa: E402
from oceanembed.nrt.substitution import substituted_field  # noqa: E402
from oceanembed.validation.collocate import METHOD, interp_point  # noqa: E402

B6 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = B6["targets"]["depths_m"]
BASE = REPO_ROOT / B6["paths"]["baselines"]
MODELS = REPO_ROOT / B6["paths"]["models"]
ARGO = ROOT / "outputs" / "argo"
NRT = ROOT / "data" / "processed" / "nrt"
OUT = ROOT / "outputs" / "phase8c"
HELDOUT = pd.Timestamp("2024-01-01")
CANDIDATE_START = pd.Timestamp("2022-05-01")     # pre-registered subset rule
KEY_DEPTHS = [50, 75, 100, 125, 150, 200]
SEED, NBOOT = 20260912, 1000
#: 6C-C precedent: the weakest policy ever promoted degraded 100 m by +0.68 %.
WORST_DEGRADATION_PCT = 0.68
MIN_SPANNING = 4                                  # of the six key depths


def sha(sd) -> str:
    h = hashlib.sha256()
    for k in sorted(sd):
        h.update(k.encode())
        h.update(np.ascontiguousarray(sd[k].detach().cpu().numpy()).tobytes())
    return h.hexdigest()


def rmse(a, b):
    d = a - b
    return float(np.sqrt(np.mean(d * d)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=("primary", "total"), default="primary",
                    help="primary = ugos+ue (tide excluded, decision-bearing); "
                         "total = uo/vo (tide included, reported only)")
    args = ap.parse_args()
    suffix = "" if args.variant == "primary" else "_total"
    ucol = "current_u" if args.variant == "primary" else "current_u_total"
    vcol = "current_v" if args.variant == "primary" else "current_v_total"
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)

    matched = pd.read_parquet(ARGO / "matched_profiles.parquet")
    matched["date"] = pd.to_datetime(matched["date"])
    assert matched.date.max() < HELDOUT, "HOLDOUT LEAK: a 2024 profile is present"
    pop = matched[matched.date >= CANDIDATE_START].copy()
    print(f"population: {len(pop):,} profiles, {pop.wmo.nunique()} floats, "
          f"{pop.date.nunique()} dates, {pop.date.min().date()}..{pop.date.max().date()}")

    cand = xr.open_dataset(NRT / "currents_candidate_d2_canonical.nc")
    cand = cand.assign_coords(time=pd.DatetimeIndex(cand.time.values).normalize()).load()
    have = set(pd.DatetimeIndex(cand.time.values))

    ck = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu",
                    weights_only=False)
    l2 = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    l2.load_state_dict(ck["state_dict"])
    l2.eval()
    for p in l2.parameters():
        p.requires_grad_(False)
    sha_before = sha(ck["state_dict"])
    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"

    ds = splits.open_split("test", allow_test=True)
    times = pd.DatetimeIndex(ds.time.values)
    smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=ck["patch"])
    lat_ax, lon_ax = ds.lat.values, ds.lon.values
    r, c = smp.r, smp.c

    def predict(t_idx, replacements):
        field = substituted_field(ds, t_idx, fs, ck["patch"], replacements)
        ctx = torch.from_numpy(smp.context(t_idx))
        with torch.no_grad():
            z = l2.embed_field(torch.from_numpy(field)[None])[0]
            p = ts.inverse_transform(
                l2.forward_from_z(z[:, r, c].T, ctx).numpy().astype("float64"))
        g = np.full((len(DEPTHS), lat_ax.size, lon_ax.size), np.nan)
        for k in range(len(DEPTHS)):
            g[k, r, c] = p[:, k]
        return g

    rows, skipped = [], {"no_model_day": 0, "no_candidate_day": 0}
    for n, date in enumerate(sorted(pop.date.unique()), 1):
        day = pd.Timestamp(date)
        hit = np.where(times == day)[0]
        if not len(hit):
            skipped["no_model_day"] += 1
            continue
        if day not in have:
            skipped["no_candidate_day"] += 1
            continue
        t = int(hit[0])
        grids = {"CONTROL": predict(t, {}),
                 "CANDIDATE": predict(t, {
                     "current_u": np.asarray(cand[ucol].sel(time=day).values,
                                             dtype="float64"),
                     "current_v": np.asarray(cand[vcol].sel(time=day).values,
                                             dtype="float64")})}
        for _, row in pop[pop.date == date].iterrows():
            rec = {"wmo": row["wmo"], "cycle": row["cycle"], "date": day,
                   "lat": row["lat"], "lon": row["lon"]}
            for k, d in enumerate(DEPTHS):
                rec[f"argo_pt_{d}m"] = row[f"argo_pt_{d}m"]
                rec[f"argo_sup_{d}m"] = bool(row[f"argo_sup_{d}m"])
                rec[f"L0_{d}m"] = row[f"L0_{d}m"]
                rec[f"STORED_L2_{d}m"] = row[f"L2_{d}m"]
                for label, g in grids.items():
                    rec[f"{label}_{d}m"], _ = interp_point(
                        g[k], lat_ax, lon_ax, row["lat"], row["lon"])
            rows.append(rec)
        if n % 60 == 0:
            print(f"  {n} dates ({time.time() - t0:.0f}s)", flush=True)

    assert sha(l2.state_dict()) == sha_before, "FROZEN L2 CHANGED"
    df = pd.DataFrame(rows)
    df.to_parquet(OUT / f"argo_candidate_replay{suffix}.parquet", index=False)
    print(f"collocated rows: {len(df):,}  skipped dates: {skipped}")

    # ---- integrity: the recomputed control must reproduce the executed one
    checks = {}
    for d in KEY_DEPTHS:
        m = np.isfinite(df[f"CONTROL_{d}m"]) & np.isfinite(df[f"STORED_L2_{d}m"])
        diff = np.abs(df.loc[m, f"CONTROL_{d}m"] - df.loc[m, f"STORED_L2_{d}m"])
        checks[d] = {"n": int(m.sum()), "max_abs_diff": float(diff.max()),
                     "mean_abs_diff": float(diff.mean())}
    print("control vs stored executed L2, max abs diff:",
          {d: round(v["max_abs_diff"], 6) for d, v in checks.items()})

    # ---- metrics on the identical accepted population, per depth
    metrics, per_depth_arrays = [], {}
    for d in DEPTHS:
        ok = (df[f"argo_sup_{d}m"].astype(bool)
              & np.isfinite(df[f"argo_pt_{d}m"])
              & np.isfinite(df[f"L0_{d}m"])
              & np.isfinite(df[f"CONTROL_{d}m"])
              & np.isfinite(df[f"CANDIDATE_{d}m"]))
        sub = df[ok]
        if len(sub) < 30:
            continue
        obs = sub[f"argo_pt_{d}m"].to_numpy("float64")
        per_depth_arrays[d] = {
            "wmo": sub["wmo"].to_numpy(),
            "obs": obs,
            "CONTROL": sub[f"CONTROL_{d}m"].to_numpy("float64"),
            "CANDIDATE": sub[f"CANDIDATE_{d}m"].to_numpy("float64"),
            "L0": sub[f"L0_{d}m"].to_numpy("float64")}
        for label in ("L0", "CONTROL", "CANDIDATE"):
            pred = per_depth_arrays[d][label]
            metrics.append({"depth_m": d, "system": label, "n": int(len(sub)),
                            "rmse": rmse(pred, obs),
                            "bias": float(np.mean(pred - obs)),
                            "correlation": float(np.corrcoef(pred, obs)[0, 1])})
    md = pd.DataFrame(metrics)
    md.to_csv(OUT / f"argo_comparison{suffix}.csv", index=False)

    # ---- float-clustered paired bootstrap, candidate minus control
    rng = np.random.default_rng(SEED)
    boots = []
    for d in KEY_DEPTHS:
        if d not in per_depth_arrays:
            continue
        a = per_depth_arrays[d]
        floats = np.unique(a["wmo"])
        idx_by_float = {f: np.flatnonzero(a["wmo"] == f) for f in floats}
        diffs = []
        for _ in range(NBOOT):
            pick = rng.choice(floats, size=len(floats), replace=True)
            sel = np.concatenate([idx_by_float[f] for f in pick])
            diffs.append(rmse(a["CANDIDATE"][sel], a["obs"][sel])
                         - rmse(a["CONTROL"][sel], a["obs"][sel]))
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        base = rmse(a["CONTROL"], a["obs"])
        delta = rmse(a["CANDIDATE"], a["obs"]) - base
        boots.append({"depth_m": d, "n": int(len(a["obs"])),
                      "n_floats": int(len(floats)),
                      "rmse_control": base,
                      "rmse_candidate": rmse(a["CANDIDATE"], a["obs"]),
                      "difference_degC": float(delta),
                      "degradation_pct": float(100.0 * delta / base),
                      "ci_lo": float(lo), "ci_hi": float(hi),
                      "spans_zero": bool(lo <= 0 <= hi),
                      "significant": bool(hi < 0 or lo > 0)})
    bd = pd.DataFrame(boots)
    bd.to_csv(OUT / f"argo_bootstrap{suffix}.csv", index=False)

    spanning = int(bd["spans_zero"].sum())
    worst = float(bd["degradation_pct"].max())
    c8 = bool(spanning >= MIN_SPANNING and worst <= WORST_DEGRADATION_PCT)

    result = {
        "preregistration_commit": "c01c170",
        "variant": args.variant,
        "variant_role": ("decision-bearing (tide excluded)" if args.variant == "primary"
                         else "reported only, never decision-bearing (tide included)"),
        "population": {"profiles": int(len(df)), "floats": int(df.wmo.nunique()),
                       "dates": int(df.date.nunique()),
                       "window": [str(pop.date.min().date()), str(pop.date.max().date())],
                       "subset_rule": "existing 2022-23 collocations on/after 2022-05-01"},
        "collocation_method": METHOD,
        "control_reproduces_executed_l2": checks,
        "key_depths": KEY_DEPTHS,
        "c8_spanning_zero": spanning, "c8_required_spanning": MIN_SPANNING,
        "c8_worst_degradation_pct": worst,
        "c8_allowed_degradation_pct": WORST_DEGRADATION_PCT,
        "C8_pass": c8,
        "skipped_dates": skipped,
        "l2_state_dict_sha256_before": sha_before,
        "l2_state_dict_sha256_after": sha(l2.state_dict()),
        "argo_2024_opened": False,
        "wall_clock_seconds": round(time.time() - t0, 1),
    }
    (OUT / f"argo_result{suffix}.json").write_text(json.dumps(result, indent=2, default=str),
                                          encoding="utf-8")
    print(bd.to_string(index=False))
    print(json.dumps({k: result[k] for k in
                      ("c8_spanning_zero", "c8_worst_degradation_pct", "C8_pass")},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
