"""Phase 8C, Phases 3-5: direct compatibility, frozen-L2 substitution, target skill.

Executes exactly the pre-registration
``outputs/phase8c/OPERATIONAL_CURRENT_SUBSTITUTION_PREREGISTRATION.md`` (c01c170)
on the 56 dates already pre-registered in Phase 6C-D.

    Phase 3  candidate currents vs the training-lineage OSCAR Final field
             (6C-D compatibility machinery and bands, unchanged)
    Phase 4  frozen L2 with everything identical EXCEPT currents
             (6C-D sensitivity bands and per-channel decision rule, unchanged)
    Phase 5  control and candidate against the SAME GLORYS reference, 15 depths

Nothing is trained. The frozen hashes are checked before and after. The GLORYS
target is read for evaluation only. No Argo of any year is opened here.

    python scripts/nrt8c/run_current_substitution.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

from oceanembed.ml.features import SURFACE  # noqa: E402
from oceanembed.nrt.compatibility import (SENS_BANDS, channel_stats,  # noqa: E402
                                          classify, pooled_from_daily,
                                          region_masks, sensitivity_band,
                                          worst_band)
from oceanembed.nrt.substitution import ShiftAccumulator, joint_mask  # noqa: E402
from oceanembed.replay.contract import DEPTHS  # noqa: E402
from oceanembed.replay.engine import (EXPECTED_L2_ENCODER,  # noqa: E402
                                      EXPECTED_L2_STATE_DICT, ReplayEngine,
                                      state_dict_sha256)

# the executed 6C-D per-channel decision rule, reused verbatim
_spec = importlib.util.spec_from_file_location(
    "substitution_run", ROOT / "scripts" / "nrt" / "substitution_run.py")
_SR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_SR)
channel_decision = _SR.channel_decision

MR = ROOT / "data" / "processed" / "model_ready"
NRT = ROOT / "data" / "processed" / "nrt"
OUT = ROOT / "outputs" / "phase8c"
TAB = ROOT / "outputs" / "tables"
CACHE = ROOT / "data" / "interim" / "phase8c"
SEED, NBOOT = 20260912, 1000
K = 3          # per-date sums: n, sum d, sum d^2


def preregistered_dates() -> list[pd.Timestamp]:
    man = json.load(open(ROOT / "outputs" / "nrt" / "fetch_manifest.json"))
    return [pd.Timestamp(d) for d in man["dates"]]


def load_canonical(name: str) -> xr.Dataset:
    d = xr.open_dataset(NRT / f"{name}_canonical.nc")
    return d.assign_coords(time=pd.DatetimeIndex(d.time.values).normalize()).load()


def masked_sums(x, y, m):
    d = np.where(m, x - y, 0.0)
    return np.stack([m.sum(axis=(0, 1)).astype("float64"),
                     d.sum(axis=(0, 1)), (d * d).sum(axis=(0, 1))], axis=-1)


def boot_rmse_diff(a, b, rng):
    nd = a.shape[0]
    idx = rng.integers(0, nd, size=(NBOOT, nd))
    ra = np.sqrt(a[idx, 2].sum(1) / a[idx, 0].sum(1))
    rb = np.sqrt(b[idx, 2].sum(1) / b[idx, 0].sum(1))
    lo, hi = np.percentile(ra - rb, [2.5, 97.5])
    return float(lo), float(hi)


def main() -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    eng = ReplayEngine()
    sha_before = state_dict_sha256(eng.model.state_dict())
    assert sha_before == EXPECTED_L2_STATE_DICT
    ref = eng._store(2024)                       # surface inputs only
    rtimes = pd.DatetimeIndex(ref.time.values).normalize()
    tgt = xr.open_zarr(MR / "oceanembed_2024.zarr", consolidated=True)[
        [f"temp_{d}m" for d in DEPTHS]]          # evaluation reference only

    cand = load_canonical("currents_candidate_d1")
    oscar_nrt = load_canonical("currents_nrt")   # context only
    have_cand = set(pd.DatetimeIndex(cand.time.values))
    have_osc = set(pd.DatetimeIndex(oscar_nrt.time.values))

    regions = region_masks(ref.lat.values, ref.lon.values)
    REG = {"whole_nio": regions["full_nio"],
           "arabian_sea": regions["arabian_sea"],
           "bay_of_bengal": regions["bay_of_bengal"]}
    reg_names = list(REG)
    ocean = np.asarray(ref["ocean_mask"].isel(time=0).values, dtype=bool)
    siv0 = np.asarray(ref["surface_input_valid"].isel(time=0).values, dtype=bool)
    rr, cc = np.nonzero(siv0)
    fs = eng.feature_scaler
    sigma = dict(zip(fs.names, fs.std))
    l2rmse = pd.read_csv(TAB / "phase6b_l2_metrics_by_depth_test.csv")
    l2rmse = l2rmse[l2rmse["model"].str.contains("L2")].set_index("depth_m")["rmse"]

    def infer(arrays, when):
        jm = joint_mask(arrays)
        shim = xr.Dataset(
            {**{v: (("time", "lat", "lon"), arrays[v][None]) for v in SURFACE},
             "surface_input_valid": (("time", "lat", "lon"), jm[None])},
            coords={"time": [np.datetime64(when)], "lat": ref.lat.values,
                    "lon": ref.lon.values})
        return eng._infer(shim, 0, when)

    dates = [d for d in preregistered_dates() if d in rtimes and d in have_cand]
    print(f"dates: {len(dates)} of 56 pre-registered")

    daily_compat, shift, cov = [], {}, {"CONTROL": [], "CANDIDATE": []}
    for name in ("CANDIDATE", "CANDIDATE_TOTAL_WITH_TIDE"):
        shift[name] = ShiftAccumulator(DEPTHS)
    per_date_sums, used = [], []

    for day in dates:
        t = int(np.flatnonzero(rtimes == day)[0])
        base = {v: np.asarray(ref[v].isel(time=t).values, dtype="float64")
                for v in SURFACE}
        cu = np.asarray(cand["current_u"].sel(time=day).values, dtype="float64")
        cv = np.asarray(cand["current_v"].sel(time=day).values, dtype="float64")
        tu = np.asarray(cand["current_u_total"].sel(time=day).values, dtype="float64")
        tv = np.asarray(cand["current_v_total"].sel(time=day).values, dtype="float64")

        # ---- Phase 3: direct product compatibility (vs OSCAR Final in store)
        for rname, rmask in regions.items():
            s = channel_stats(base["current_u"], cu, rmask, ocean)
            s.update({"channel": "current_u", "pair": "candidate_vs_oscar_final",
                      "region": rname, "date": str(day.date())})
            daily_compat.append(s)
            s = channel_stats(base["current_v"], cv, rmask, ocean)
            s.update({"channel": "current_v", "pair": "candidate_vs_oscar_final",
                      "region": rname, "date": str(day.date())})
            daily_compat.append(s)
            if day in have_osc:
                ou = np.asarray(oscar_nrt["current_u"].sel(time=day).values, "float64")
                ov = np.asarray(oscar_nrt["current_v"].sel(time=day).values, "float64")
                for ch, a, b in (("current_u", ou, cu), ("current_v", ov, cv)):
                    s = channel_stats(a, b, rmask, ocean)
                    s.update({"channel": ch, "pair": "candidate_vs_oscar_nrt",
                              "region": rname, "date": str(day.date())})
                    daily_compat.append(s)

        # ---- Phase 4: frozen L2, identical inputs except currents
        control, siv_c = infer(base, day)
        cov["CONTROL"].append(float(joint_mask(base)[rr, cc].mean()))
        for name, (uu, vv) in (("CANDIDATE", (cu, cv)),
                               ("CANDIDATE_TOTAL_WITH_TIDE", (tu, tv))):
            arrays = {**base, "current_u": uu, "current_v": vv}
            pred, jm = infer(arrays, day)
            both = siv_c[rr, cc] & jm[rr, cc]
            shift[name].update(control[rr, cc, :], pred[rr, cc, :],
                               np.repeat(both[:, None], len(DEPTHS), axis=1))
            if name == "CANDIDATE":
                candidate_field = pred
                cov["CANDIDATE"].append(float(jm[rr, cc].mean()))

        # ---- Phase 5: both against the SAME GLORYS reference
        L0 = np.moveaxis(eng.climatology.predict(pd.DatetimeIndex([day]))[0], 0, -1)
        G = np.stack([np.asarray(tgt[f"temp_{d}m"].isel(time=t).values, "float64")
                      for d in DEPTHS], axis=-1)
        pop = (np.isfinite(control) & np.isfinite(candidate_field)
               & np.isfinite(L0) & np.isfinite(G))
        S = np.zeros((3, len(REG), len(DEPTHS), K))
        for i, X in enumerate((control, candidate_field, L0)):
            for j, rn in enumerate(reg_names):
                S[i, j] = masked_sums(X, G, pop & REG[rn][:, :, None])
        per_date_sums.append(S)
        np.save(CACHE / f"candidate_{day.date()}.npy", candidate_field.astype("float32"))
        used.append(day)
        if len(used) % 10 == 0:
            print(f"  {len(used)}/{len(dates)} ({time.time() - t0:.0f}s)", flush=True)

    assert state_dict_sha256(eng.model.state_dict()) == sha_before, "L2 CHANGED"

    # ---------------------------------------------------- Phase 3 results
    dd = pd.DataFrame(daily_compat)
    rows = []
    for pair in dd["pair"].unique():
        for ch in ("current_u", "current_v"):
            for rname in regions:
                sub = dd[(dd["pair"] == pair) & (dd["channel"] == ch)
                         & (dd["region"] == rname)]
                if not len(sub):
                    continue
                rec = classify(pooled_from_daily(sub), float(sigma[ch]))
                rec.update({"pair": pair, "channel": ch, "region": rname})
                rows.append(rec)
    compat = pd.DataFrame(rows)
    compat.to_csv(OUT / "current_compatibility.csv", index=False)

    # ---------------------------------------------------- Phase 4 results
    ref_cov = float(np.mean(cov["CONTROL"]))
    frames, summary = [], {}
    for name in shift:
        f = shift[name].frame(name)
        f["l2_test_rmse"] = f["depth_m"].map(l2rmse)
        f["s_ratio"] = f["rmsd"] / f["l2_test_rmse"]
        f["sensitivity_band"] = [sensitivity_band(x) for x in f["s_ratio"]]
        cm_ = float(np.mean(cov["CANDIDATE"])) if name == "CANDIDATE" else np.nan
        f["coverage_mean"] = cm_
        f["coverage_loss_vs_control"] = ref_cov - cm_
        frames.append(f)
        at100 = f[f["depth_m"] == 100].iloc[0]
        summary[name] = {
            "s_ratio_100m": float(at100["s_ratio"]),
            "rmsd_100m_degC": float(at100["rmsd"]),
            "band_100m": at100["sensitivity_band"],
            "worst_band": worst_band(f["sensitivity_band"].tolist(), SENS_BANDS),
            "worst_depth_m": int(f.loc[f["s_ratio"].idxmax(), "depth_m"]),
            "max_s_ratio": float(f["s_ratio"].max()),
            "coverage_mean": cm_, "coverage_loss": float(ref_cov - cm_)}
    pd.concat(frames).to_csv(OUT / "substitution_by_depth.csv", index=False)

    cfull = compat[(compat["pair"] == "candidate_vs_oscar_final")
                   & (compat["region"] == "full_nio")]
    band = worst_band(cfull["compatibility_band"].tolist(),
                      ["INTERCHANGEABLE", "USABLE_WITH_CAVEAT", "MARGINAL",
                       "INCOMPATIBLE_RAW"])
    rho = float(cfull["correlation_daily_median"].min())
    bs = float(cfull["abs_bias_over_sigma"].max())
    qs = cfull["std_ratio"].to_numpy("float64")
    q = float(qs[int(np.argmax(np.abs(qs - 1.0)))])
    s_c = summary["CANDIDATE"]
    decision = channel_decision(band, s_c["band_100m"], s_c["worst_band"],
                                s_c["coverage_loss"], rho, bs, q)

    # ---------------------------------------------------- Phase 5 results
    SUMS = np.stack(per_date_sums)
    TOT = SUMS.sum(axis=0)
    systems = ("CONTROL_OSCAR", "CANDIDATE", "L0")
    trows = []
    for i, sysn in enumerate(systems):
        for j, rn in enumerate(reg_names):
            n, sd, sdd = TOT[i, j, :, 0], TOT[i, j, :, 1], TOT[i, j, :, 2]
            for k, d in enumerate(DEPTHS):
                trows.append({"system": sysn, "region": rn, "depth_m": d,
                              "n": int(n[k]), "rmse": float(np.sqrt(sdd[k] / n[k])),
                              "bias": float(sd[k] / n[k])})
    tm = pd.DataFrame(trows)
    tm.to_csv(OUT / "target_metrics_by_depth.csv", index=False)

    rng = np.random.default_rng(SEED)
    boot = []
    for j, rn in enumerate(reg_names):
        for k, d in enumerate(DEPTHS):
            for a, b in (("CANDIDATE", "L0"), ("CANDIDATE", "CONTROL_OSCAR"),
                         ("CONTROL_OSCAR", "L0")):
                lo, hi = boot_rmse_diff(SUMS[:, systems.index(a), j, k],
                                        SUMS[:, systems.index(b), j, k], rng)
                boot.append({"region": rn, "depth_m": d, "pair": f"{a}-{b}",
                             "ci_lo": lo, "ci_hi": hi})
    bt = pd.DataFrame(boot)
    bt.to_csv(OUT / "target_bootstrap.csv", index=False)

    def rmse(region, system):
        sub = tm[(tm["region"] == region) & (tm["system"] == system)]
        return dict(zip(sub["depth_m"], sub["rmse"]))
    rc, rl = rmse("whole_nio", "CANDIDATE"), rmse("whole_nio", "L0")
    depths_0_200 = [d for d in DEPTHS if d <= 200]
    c5_wins = sum(1 for d in depths_0_200 if rc[d] < rl[d])
    nl = bt[(bt["region"] == "whole_nio") & (bt["pair"] == "CANDIDATE-L0")] \
        .set_index("depth_m")["ci_hi"].to_dict()
    c6 = {d: bool(rc[d] < rl[d] and nl[d] < 0) for d in (75, 100, 125)}
    c7 = bool(rmse("arabian_sea", "CANDIDATE")[100] < rmse("arabian_sea", "L0")[100]
              and rmse("bay_of_bengal", "CANDIDATE")[100]
              < rmse("bay_of_bengal", "L0")[100])

    result = {
        "preregistration": "outputs/phase8c/OPERATIONAL_CURRENT_SUBSTITUTION_PREREGISTRATION.md",
        "preregistration_commit": "c01c170",
        "n_dates": len(used), "dates": [str(d.date()) for d in used],
        "phase3_compatibility": {
            "band_full_nio_vs_oscar_final": band,
            "correlation_daily_median_min": rho,
            "abs_bias_over_sigma_max": bs, "std_ratio": q},
        "phase4_substitution": summary,
        "phase4_channel_decision": decision,
        "phase5_gates": {"C5_depths_beating_L0_of_11": c5_wins,
                         "C5_pass": c5_wins >= 6,
                         "C6_per_depth": c6, "C6_pass": all(c6.values()),
                         "C7_pass": c7},
        "l2_state_dict_sha256_before": sha_before,
        "l2_state_dict_sha256_after": state_dict_sha256(eng.model.state_dict()),
        "l2_encoder_sha256": EXPECTED_L2_ENCODER,
        "argo_opened": False,
        "wall_clock_seconds": round(time.time() - t0, 1),
    }
    (OUT / "substitution_result.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: result[k] for k in
                      ("phase3_compatibility", "phase4_channel_decision",
                       "phase5_gates")}, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    eng.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
