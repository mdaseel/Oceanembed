"""Phase 8B — hindcast-the-NRT qualification of the complete operational stack.

Executes exactly ``outputs/phase8b/NRT_SUBSURFACE_QUALIFICATION_PROTOCOL.md``
(frozen, commit 5b69dda):

    date t (the 56 Phase 6C-D dates)
      -> NRT_STACK_V1: all seven channels from their operational products, valid t
      -> the SAME harmonisation as training / 6C-D (already on disk, canonical grid)
      -> the UNMODIFIED frozen day_field + frozen whole-field L2, through the
         ReplayEngine's own ``_infer`` - the one inference implementation
      -> N(t), compared with R(t) = replay_field(t), L0(t) and GLORYS G(t)

Pass 1 decides the temperature category (gates G1-G5). Pass 2 - D26/TCHP and the
hazard transfer - runs ONLY if temperature qualifies, as the protocol requires.

Nothing is trained or fitted. Frozen hashes are checked before and after. No
Argo file of any year is opened.

    python scripts/nrt8b/run_nrt_hindcast.py
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

from oceanembed.diagnostics import D26Status, d26_tchp  # noqa: E402
from oceanembed.ml.features import SURFACE  # noqa: E402
from oceanembed.nrt import qualification as Q  # noqa: E402
from oceanembed.nrt.compatibility import (SENS_BANDS, channel_stats, classify,  # noqa: E402
                                          pooled_from_daily, region_masks,
                                          sensitivity_band, worst_band)
from oceanembed.nrt.substitution import ShiftAccumulator, joint_mask  # noqa: E402
from oceanembed.replay.contract import DEPTHS  # noqa: E402
from oceanembed.replay.engine import (EXPECTED_L2_ENCODER,  # noqa: E402
                                      EXPECTED_L2_STATE_DICT, ReplayEngine,
                                      state_dict_sha256)

# The 6C-D per-channel decision rule is reused verbatim from its own script.
_spec = importlib.util.spec_from_file_location(
    "substitution_run", ROOT / "scripts" / "nrt" / "substitution_run.py")
_SR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_SR)
channel_decision = _SR.channel_decision

PROTOCOL = "outputs/phase8b/NRT_SUBSURFACE_QUALIFICATION_PROTOCOL.md"
PROTOCOL_COMMIT = "5b69dda"
MR = ROOT / "data" / "processed" / "model_ready"
NRT_DIR = ROOT / "data" / "processed" / "nrt"
OUT = ROOT / "outputs" / "phase8b"
TAB = ROOT / "outputs" / "tables"
CACHE = ROOT / "data" / "interim" / "phase8b_hindcast"

STACK = {"sst": "sst_nrt", "sss": "sss_nrt_multiobs", "sla": "sla_nrt",
         "current_u": "currents_nrt", "current_v": "currents_nrt",
         "wind_u": "wind_nrt", "wind_v": "wind_nrt"}
RUNS = {"ALL_NRT_V1": STACK, "NRT_SSS_MULTIOBS_ONLY": {"sss": "sss_nrt_multiobs"}}
SYSTEMS = ("N", "R", "L0")
SEED, NBOOT = 20260911, 1000
SSS_WINDOW = ("2024-07-01", "2024-12-15")

# per-date sums for one (system, region, depth):
#   n, sum d, sum d^2, sx, sy, sxx, syy, sxy, sax, say, saxx, sayy, saxy
K = 13


def load_nrt(key: str) -> xr.Dataset:
    p = NRT_DIR / f"{key}_canonical.nc"
    if not p.exists():
        raise FileNotFoundError(f"NRT source missing: {p}")
    d = xr.open_dataset(p)
    d = d.assign_coords(time=pd.DatetimeIndex(d.time.values).normalize())
    return d.load()


def pre_registered_dates() -> list[pd.Timestamp]:
    man = json.load(open(ROOT / "outputs" / "nrt" / "fetch_manifest.json"))
    assert man["n_dates"] == Q.PREREGISTERED_DATES, man["n_dates"]
    return [pd.Timestamp(d) for d in man["dates"]]


def masked_sums(x: np.ndarray, y: np.ndarray, l0: np.ndarray,
                m: np.ndarray) -> np.ndarray:
    """(lat, lon, depth) arrays and mask -> (depth, K) sums over the mask."""
    x0, y0 = np.where(m, x, 0.0), np.where(m, y, 0.0)
    ax = np.where(m, x - l0, 0.0)
    ay = np.where(m, y - l0, 0.0)
    d = x0 - y0
    s = lambda a: a.sum(axis=(0, 1))  # noqa: E731
    return np.stack([m.sum(axis=(0, 1)).astype("float64"), s(d), s(d * d),
                     s(x0), s(y0), s(x0 * x0), s(y0 * y0), s(x0 * y0),
                     s(ax), s(ay), s(ax * ax), s(ay * ay), s(ax * ay)], axis=-1)


def metrics_from_sums(S: np.ndarray) -> dict:
    n = S[..., 0]
    with np.errstate(invalid="ignore", divide="ignore"):
        rmse = np.sqrt(S[..., 2] / n)
        bias = S[..., 1] / n

        def corr(sx, sy, sxx, syy, sxy):
            vx = n * sxx - sx ** 2
            vy = n * syy - sy ** 2
            return (n * sxy - sx * sy) / np.sqrt(vx * vy)
        r = corr(S[..., 3], S[..., 4], S[..., 5], S[..., 6], S[..., 7])
        ar = corr(S[..., 8], S[..., 9], S[..., 10], S[..., 11], S[..., 12])
    return {"n": n, "rmse": rmse, "bias": bias, "correlation": r,
            "anomaly_correlation": ar}


def boot_rmse_diff(sums_a: np.ndarray, sums_b: np.ndarray, rng) -> tuple:
    """Paired date bootstrap of RMSE_a - RMSE_b. sums_*: (n_dates, K)."""
    nd = sums_a.shape[0]
    idx = rng.integers(0, nd, size=(NBOOT, nd))
    a = np.sqrt(sums_a[idx, 2].sum(1) / sums_a[idx, 0].sum(1))
    b = np.sqrt(sums_b[idx, 2].sum(1) / sums_b[idx, 0].sum(1))
    lo, hi = np.percentile(a - b, [2.5, 97.5])
    return float(lo), float(hi)


def main() -> int:
    t_start = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    eng = ReplayEngine()               # verifies every frozen hash or raises
    sha_before = state_dict_sha256(eng.model.state_dict())
    assert sha_before == EXPECTED_L2_STATE_DICT
    ref = eng._store(2024)             # SURFACE INPUTS ONLY - targets dropped
    rtimes = pd.DatetimeIndex(ref.time.values).normalize()
    # GLORYS target, opened separately and used ONLY as the evaluation reference.
    tgt = xr.open_zarr(MR / "oceanembed_2024.zarr", consolidated=True)[
        [f"temp_{d}m" for d in DEPTHS]]

    sources = {k: load_nrt(k) for k in sorted(set(STACK.values()))}
    for k, d in sources.items():
        assert np.allclose(d.lat.values, ref.lat.values) and \
            np.allclose(d.lon.values, ref.lon.values), f"{k} is not on the canonical grid"
    have = {k: set(pd.DatetimeIndex(d.time.values)) for k, d in sources.items()}

    fs = eng.feature_scaler
    sigma = dict(zip(fs.names, fs.std))
    regions = region_masks(ref.lat.values, ref.lon.values)
    REG = {"whole_nio": regions["full_nio"], "arabian_sea": regions["arabian_sea"],
           "bay_of_bengal": regions["bay_of_bengal"]}
    reg_names = list(REG)

    siv0 = np.asarray(ref["surface_input_valid"].isel(time=0).values, dtype=bool)
    rr, cc = np.nonzero(siv0)          # the 6C-D cell list, for sensitivity

    l2rmse = pd.read_csv(TAB / "phase6b_l2_metrics_by_depth_test.csv")
    l2rmse = l2rmse[l2rmse["model"].str.contains("L2")].set_index("depth_m")["rmse"]

    def infer(arrays: dict, when: pd.Timestamp):
        """The engine's own inference on an assembled seven-channel field."""
        jm = joint_mask(arrays)
        shim = xr.Dataset(
            {**{v: (("time", "lat", "lon"), arrays[v][None]) for v in SURFACE},
             "surface_input_valid": (("time", "lat", "lon"), jm[None])},
            coords={"time": [np.datetime64(when)], "lat": ref.lat.values,
                    "lon": ref.lon.values})
        return eng._infer(shim, 0, when)

    # ------------------------------------------------------------ pass 1
    dates = pre_registered_dates()
    used, skipped = [], []
    shift = {n: ShiftAccumulator(DEPTHS) for n in RUNS}
    cov = {n: [] for n in [*RUNS, "REFERENCE"]}
    per_date_sums = []                  # (system, region, depth, K) per date
    coverage_rows = []

    for day in dates:
        missing = [k for k in sorted(set(STACK.values())) if day not in have[k]]
        if day not in rtimes or missing:
            skipped.append({"date": str(day.date()),
                            "reason": f"missing {missing or ['reference']}"})
            continue
        t = int(np.flatnonzero(rtimes == day)[0])
        base = {v: np.asarray(ref[v].isel(time=t).values, dtype="float64")
                for v in SURFACE}

        R, siv_r = infer(base, day)
        # The assembled-field path must reproduce the authoritative historical
        # replay exactly; otherwise every number below measures a pipeline
        # difference, not a product difference.
        hist = eng.replay_field(day).temperature
        assert np.array_equal(R, hist, equal_nan=True), \
            f"{day.date()}: assembled reference path != replay_field"

        runs = {}
        for name, mapping in RUNS.items():
            rep = {ch: np.asarray(sources[k][ch].sel(time=day).values, dtype="float64")
                   for ch, k in mapping.items()}
            temp, jm = infer({**base, **rep}, day)
            runs[name] = (temp, jm)
            both = siv_r[rr, cc] & jm[rr, cc]
            shift[name].update(R[rr, cc, :], temp[rr, cc, :],
                               np.repeat(both[:, None], len(DEPTHS), axis=1))
            cov[name].append(float(jm[rr, cc].mean()))
        cov["REFERENCE"].append(float(siv_r[rr, cc].mean()))

        N = runs["ALL_NRT_V1"][0]
        np.save(CACHE / f"N_{day.date()}.npy", N.astype("float32"))
        L0 = np.moveaxis(eng.climatology.predict(pd.DatetimeIndex([day]))[0], 0, -1)
        G = np.stack([np.asarray(tgt[f"temp_{d}m"].isel(time=t).values,
                                 dtype="float64") for d in DEPTHS], axis=-1)

        pop = np.isfinite(N) & np.isfinite(R) & np.isfinite(L0) & np.isfinite(G)
        S = np.zeros((len(SYSTEMS), len(REG), len(DEPTHS), K))
        for i, X in enumerate((N, R, L0)):
            for j, rn in enumerate(reg_names):
                S[i, j] = masked_sums(X, G, L0, pop & REG[rn][:, :, None])
        per_date_sums.append(S)
        used.append(day)
        coverage_rows.append({"date": str(day.date()),
                              "coverage_REFERENCE": cov["REFERENCE"][-1],
                              **{f"coverage_{n}": cov[n][-1] for n in RUNS}})
        if len(used) % 10 == 0:
            print(f"  {len(used)} dates  ({time.time() - t_start:.0f}s)", flush=True)

    n_used = len(used)
    print(f"dates assembled: {n_used}/{len(dates)}  skipped: {len(skipped)}")
    assert state_dict_sha256(eng.model.state_dict()) == sha_before, "L2 CHANGED"

    if n_used < Q.MIN_DATES:
        category = Q.temperature_category(n_used, None)
        json.dump({"protocol": PROTOCOL, "protocol_commit": PROTOCOL_COMMIT,
                   "temperature_category": category, "n_dates_used": n_used,
                   "skipped": skipped}, open(OUT / "qualification_decision.json", "w"),
                  indent=2)
        print(category)
        return 0

    SUMS = np.stack(per_date_sums)      # (date, system, region, depth, K)
    TOT = SUMS.sum(axis=0)

    # ------------------------------------------------ temperature metrics
    rows = []
    for i, sysn in enumerate(SYSTEMS):
        for j, rn in enumerate(reg_names):
            m = metrics_from_sums(TOT[i, j])
            for k, d in enumerate(DEPTHS):
                rows.append({"system": sysn, "region": rn, "depth_m": d,
                             **{key: float(v[k]) for key, v in m.items()}})
    tm = pd.DataFrame(rows)
    piv = tm.pivot_table(index=["region", "depth_m"], columns="system",
                         values="rmse").reset_index()
    piv["skill_N_vs_L0"] = 1 - piv["N"] / piv["L0"]
    piv["skill_R_vs_L0"] = 1 - piv["R"] / piv["L0"]
    piv["degradation_N_vs_R"] = piv["N"] / piv["R"] - 1
    tm.to_csv(TAB / "phase8b_hindcast_temperature_metrics.csv", index=False)
    piv.to_csv(TAB / "phase8b_hindcast_skill.csv", index=False)

    # ------------------------------------------------ bootstrap intervals
    rng = np.random.default_rng(SEED)
    boot = []
    for j, rn in enumerate(reg_names):
        for k, d in enumerate(DEPTHS):
            for a, b in (("N", "L0"), ("N", "R"), ("R", "L0")):
                lo, hi = boot_rmse_diff(SUMS[:, SYSTEMS.index(a), j, k],
                                        SUMS[:, SYSTEMS.index(b), j, k], rng)
                boot.append({"region": rn, "depth_m": d, "pair": f"{a}-{b}",
                             "ci_lo": lo, "ci_hi": hi})
    bt = pd.DataFrame(boot)
    bt.to_csv(TAB / "phase8b_hindcast_bootstrap.csv", index=False)

    # ------------------------------------------------ sensitivity (6C-D 4.2)
    ref_cov = float(np.mean(cov["REFERENCE"]))
    sens_frames, sens_summary = [], {}
    for name in RUNS:
        f = shift[name].frame(name)
        f["l2_test_rmse"] = f["depth_m"].map(l2rmse)
        f["s_ratio"] = f["rmsd"] / f["l2_test_rmse"]
        f["sensitivity_band"] = [sensitivity_band(x) for x in f["s_ratio"]]
        f["coverage_mean"] = float(np.mean(cov[name]))
        f["coverage_loss_vs_reference"] = ref_cov - f["coverage_mean"]
        f["n_days_run"] = n_used
        sens_frames.append(f)
        at100 = f[f["depth_m"] == 100].iloc[0]
        sens_summary[name] = {
            "s_ratio_100m": float(at100["s_ratio"]),
            "rmsd_100m_degC": float(at100["rmsd"]),
            "band_100m": at100["sensitivity_band"],
            "worst_band": worst_band(f["sensitivity_band"].tolist(), SENS_BANDS),
            "worst_depth_m": int(f.loc[f["s_ratio"].idxmax(), "depth_m"]),
            "max_s_ratio": float(f["s_ratio"].max()),
            "coverage_mean": float(np.mean(cov[name])),
            "coverage_loss": float(ref_cov - np.mean(cov[name]))}
    pd.concat(sens_frames).to_csv(TAB / "phase8b_sensitivity.csv", index=False)
    pd.DataFrame(coverage_rows).to_csv(TAB / "phase8b_daily_coverage.csv", index=False)

    # ------------------------------------------------ SSS compatibility (5.1)
    sss = sources["sss_nrt_multiobs"]
    win = pd.date_range(*SSS_WINDOW, freq="D")
    common = [d for d in win if d in rtimes and d in have["sss_nrt_multiobs"]]
    ocean = np.asarray(ref["ocean_mask"].isel(time=0).values, dtype=bool)
    daily = []
    for d in common:
        a = np.asarray(ref["sss"].isel(time=int(np.flatnonzero(rtimes == d)[0])).values,
                       dtype="float64")
        b = np.asarray(sss["sss"].sel(time=d).values, dtype="float64")
        for rname, rmask in regions.items():
            s = channel_stats(a, b, rmask, ocean)
            s.update({"region": rname, "date": str(d.date())})
            daily.append(s)
    dd = pd.DataFrame(daily)
    compat = []
    for rname in regions:
        rec = classify(pooled_from_daily(dd[dd["region"] == rname]), float(sigma["sss"]))
        rec.update({"channel": "sss", "nrt_key": "sss_nrt_multiobs", "region": rname,
                    "n_days_available": int((dd["region"] == rname).sum())})
        compat.append(rec)
    cp = pd.DataFrame(compat)
    cp.to_csv(TAB / "phase8b_sss_compatibility.csv", index=False)
    cfull = cp[cp["region"] == "full_nio"].iloc[0]

    # ------------------------------------------------ gates (protocol 6)
    s_sss = sens_summary["NRT_SSS_MULTIOBS_ONLY"]
    sss_decision = channel_decision(
        cfull["compatibility_band"], s_sss["band_100m"], s_sss["worst_band"],
        s_sss["coverage_loss"], float(cfull.get("correlation_daily_median", np.nan)),
        float(cfull.get("abs_bias_over_sigma", np.nan)),
        float(cfull.get("std_ratio", np.nan)))
    s_all = sens_summary["ALL_NRT_V1"]
    verdict = Q.stack_verdict(s_all["band_100m"], s_all["worst_band"],
                              s_all["coverage_loss"])

    def rm(region, system):
        sub = tm[(tm["region"] == region) & (tm["system"] == system)]
        return dict(zip(sub["depth_m"], sub["rmse"]))
    rn_w, rl_w = rm("whole_nio", "N"), rm("whole_nio", "L0")
    g3, g3_wins = Q.gate_g3(rn_w, rl_w)
    nl = bt[(bt["region"] == "whole_nio") & (bt["pair"] == "N-L0")].set_index("depth_m")
    g4, g4_per = Q.gate_g4(rn_w, rl_w, nl["ci_hi"].to_dict())
    g5 = Q.gate_g5(rm("arabian_sea", "N")[100], rm("arabian_sea", "L0")[100],
                   rm("bay_of_bengal", "N")[100], rm("bay_of_bengal", "L0")[100])
    gates = {"G1": Q.gate_g1(sss_decision), "G2": Q.gate_g2(verdict),
             "G3": g3, "G4": g4, "G5": g5}
    category = Q.temperature_category(n_used, gates)
    print(f"gates {gates} -> {category}")

    depths_not_beating_l0 = {
        rn: [int(d) for d in DEPTHS if not (rm(rn, "N")[d] < rm(rn, "L0")[d])]
        for rn in reg_names}

    # ------------------------------------------------ pass 2 (only if qualified)
    d26_cat = tchp_cat = Q.NOT_QUALIFIED
    hazard_cat = "HISTORICAL ONLY"
    thermal_block: dict = {"evaluated": False,
                           "reason": "temperature not qualified; protocol section 8"}
    if Q.is_qualified(category):
        thermal_block = run_thermal_pass(eng, ref, tgt, rtimes, used, REG, rng)
        d26_cat = thermal_block["d26_category"]
        tchp_cat = thermal_block["tchp_category"]
        if tchp_cat == Q.QUALIFIED:
            hazard_cat = Q.QUALIFIED
            thermal_block["hazard_agreement"] = hazard_agreement(eng, ref, rtimes,
                                                                 used, tgt)

    sha_after = state_dict_sha256(eng.model.state_dict())
    enc_after = state_dict_sha256({k[len("encoder."):]: v for k, v in
                                   eng.model.state_dict().items()
                                   if k.startswith("encoder.")})
    assert sha_after == EXPECTED_L2_STATE_DICT and enc_after == EXPECTED_L2_ENCODER

    decision = {
        "protocol": PROTOCOL, "protocol_commit": PROTOCOL_COMMIT,
        "stack": "NRT_STACK_V1",
        "alignment": "COMMON_VALID_DATE",
        "sss_operating_policy": "SSS_MULTIOBS_NRT_SAME_DATE",
        "persistence_envelope_days": 0,
        "products": STACK,
        "n_dates_preregistered": len(dates), "n_dates_used": n_used,
        "dates_used": [str(d.date()) for d in used], "skipped": skipped,
        "sss_channel": {"compatibility_band": cfull["compatibility_band"],
                        "band_reason": cfull.get("band_reason"),
                        "sensitivity": s_sss, "decision": sss_decision},
        "stack_sensitivity": s_all, "stack_verdict": verdict,
        "g3_depths_beating_l0_0_200": g3_wins, "g4_per_depth": g4_per,
        "gates": gates,
        "temperature_category": category,
        "qualified_reachable_in_8b": Q.QUALIFIED_REACHABLE,
        "qualified_unreachable_reason": Q.QUALIFIED_UNREACHABLE_REASON,
        "depths_where_N_does_not_beat_L0": depths_not_beating_l0,
        "d26_category": d26_cat, "tchp_category": tchp_cat,
        "latest_hazard_indicators": hazard_cat,
        "thermal": thermal_block,
        "reference_coverage_mean": ref_cov,
        "l2_state_dict_sha256_before": sha_before, "l2_state_dict_sha256_after": sha_after,
        "l2_encoder_sha256_after": enc_after,
        "targets_read_for_evaluation_only": [f"temp_{d}m" for d in DEPTHS],
        "argo_opened": False, "argo_2024_status": "PROTECTED - not read",
        "replay_mode": "RETROSPECTIVE",
        "wall_clock_seconds": round(time.time() - t_start, 1),
    }
    json.dump(decision, open(OUT / "qualification_decision.json", "w"), indent=2,
              default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(json.dumps({k: decision[k] for k in
                      ("n_dates_used", "stack_verdict", "gates",
                       "temperature_category", "d26_category", "tchp_category",
                       "latest_hazard_indicators")}, indent=2, default=str))
    return 0


def run_thermal_pass(eng, ref, tgt, rtimes, used, REG, rng) -> dict:
    """Protocol section 8: D26/TCHP non-inferiority to the historical replay."""
    reg_names = list(REG)
    per = {q: [] for q in ("d26", "tchp")}     # per date (region, 5) sums
    status_counts = {s: {} for s in ("N", "R", "G")}
    for day in used:
        t = int(np.flatnonzero(rtimes == day)[0])
        N = np.load(CACHE / f"N_{day.date()}.npy").astype("float64")
        R = eng.replay_field(day).temperature
        G = np.stack([np.asarray(tgt[f"temp_{d}m"].isel(time=t).values,
                                 dtype="float64") for d in DEPTHS], axis=-1)
        ocean = np.asarray(ref["ocean_mask"].isel(time=t).values, dtype=bool)
        siv = np.asarray(ref["surface_input_valid"].isel(time=t).values, dtype=bool)
        pop = ocean & siv
        th = {"N": d26_tchp(N, DEPTHS), "R": d26_tchp(R, DEPTHS),
              "G": d26_tchp(G, DEPTHS)}
        for q, defined in (("d26", "d26_defined"), ("tchp", "tchp_defined")):
            both = pop & getattr(th["N"], defined) & getattr(th["R"], defined) \
                & getattr(th["G"], defined)
            vn, vr, vg = (getattr(th[s], q) for s in ("N", "R", "G"))
            S = np.zeros((len(reg_names), 5))
            for j, rn in enumerate(reg_names):
                m = both & REG[rn]
                en, er = vn[m] - vg[m], vr[m] - vg[m]
                S[j] = [m.sum(), np.abs(en).sum(), np.abs(er).sum(),
                        en.sum(), er.sum()]
            per[q].append(S)
        for s, r in th.items():
            inside = r.status[pop]
            for st in D26Status:
                status_counts[s][st.name] = status_counts[s].get(st.name, 0) + \
                    int((inside == st).sum())

    out = {"evaluated": True, "status_counts": status_counts, "metrics": [],
           "non_inferiority": {}}
    rows = []
    for q in ("d26", "tchp"):
        A = np.stack(per[q])                     # (date, region, 5)
        nd = A.shape[0]
        idx = rng.integers(0, nd, size=(NBOOT, nd))
        ok_all = True
        for j, rn in enumerate(reg_names):
            n = A[:, j, 0].sum()
            mae_n, mae_r = A[:, j, 1].sum() / n, A[:, j, 2].sum() / n
            nb = A[idx, j, 0].sum(1)
            diff = A[idx, j, 1].sum(1) / nb - A[idx, j, 2].sum(1) / nb
            lo, hi = np.percentile(diff, [2.5, 97.5])
            ni = Q.non_inferior(float(lo), float(hi))
            ok_all &= ni
            rows.append({"quantity": q, "region": rn, "n": int(n),
                         "mae_N_vs_G": float(mae_n), "mae_R_vs_G": float(mae_r),
                         "bias_N_vs_G": float(A[:, j, 3].sum() / n),
                         "bias_R_vs_G": float(A[:, j, 4].sum() / n),
                         "mae_diff_N_minus_R": float(mae_n - mae_r),
                         "ci_lo": float(lo), "ci_hi": float(hi),
                         "non_inferior": ni,
                         "unit": "m" if q == "d26" else "kJ/cm2"})
        out[f"{q}_category"] = Q.QUALIFIED if ok_all else Q.NOT_QUALIFIED
    pd.DataFrame(rows).to_csv(TAB / "phase8b_d26_tchp_metrics.csv", index=False)
    out["metrics"] = rows
    return out


def hazard_agreement(eng, ref, rtimes, used, tgt) -> dict:
    """Descriptive only (protocol section 9): N vs R category agreement."""
    from oceanembed.diagnostics.bathymetry import local_water_depth, qualify
    from oceanembed.diagnostics.hazard import categorize, load_thresholds
    th = load_thresholds(strict=True)
    wd = local_water_depth(strict=True)
    agree = total = 0
    for day in used:
        t = int(np.flatnonzero(rtimes == day)[0])
        N = np.load(CACHE / f"N_{day.date()}.npy").astype("float64")
        R = eng.replay_field(day).temperature
        pop = (np.asarray(ref["ocean_mask"].isel(time=t).values, dtype=bool)
               & np.asarray(ref["surface_input_valid"].isel(time=t).values, dtype=bool))
        cats = []
        for X in (N, R):
            r = d26_tchp(X, DEPTHS)
            _, tp = qualify(r, wd)
            cats.append(categorize(r.tchp, r.status, tp, th))
        agree += int((cats[0][pop] == cats[1][pop]).sum())
        total += int(pop.sum())
    return {"cells": total, "agreement_fraction": agree / total if total else None,
            "note": "descriptive; thresholds are the frozen Phase 7D values, not retuned"}


if __name__ == "__main__":
    raise SystemExit(main())
