"""Phase 6C-D Steps 11-14: frozen-L2 product-substitution SENSITIVITY.

No model is trained and no target is read. Each run swaps one channel's product
for its NRT counterpart, holds the other six at their reference values, and
compares the frozen model's prediction against the reference-input prediction.
The number produced is a prediction SHIFT, not an error.

Step 14 additionally separates the OSCAR discrepancy into an AGE effect and a
PRODUCT effect using the pre-registered k = 3 day operational age.
"""
from __future__ import annotations

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
from oceanembed.ml.features import SURFACE, cyclic_doy
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.patches import N_DATA_CHANNELS
from oceanembed.ml.scaler import ZScoreScaler
from oceanembed.nrt.compatibility import SENS_BANDS, sensitivity_band, worst_band
from oceanembed.nrt.substitution import ShiftAccumulator, joint_mask, substituted_field

B6 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = B6["targets"]["depths_m"]
BASE = REPO_ROOT / B6["paths"]["baselines"]
MODELS = REPO_ROOT / B6["paths"]["models"]
TAB = REPO_ROOT / "outputs" / "tables"
OUTD = REPO_ROOT / "outputs" / "nrt"
NRT = REPO_ROOT / "data" / "processed" / "nrt"
MR = REPO_ROOT / "data" / "processed" / "model_ready"

ALLOWED_REFERENCE_VARS = set(SURFACE) | {"ocean_mask", "surface_input_valid"}
OSCAR_AGE_DAYS = 3          # pre-registered

# run -> (channels replaced, nrt file key)
SINGLE_RUNS = [
    ("NRT_SST_ONLY", ("sst",), "sst_nrt"),
    ("NRT_SSS_SMOS_ONLY", ("sss",), "sss_nrt_smos"),
    ("NRT_SSS_SMAP_ONLY", ("sss",), "sss_nrt_smap"),
    ("NRT_SLA_ONLY", ("sla",), "sla_nrt"),
    ("NRT_CURRENTS_ONLY", ("current_u", "current_v"), "currents_nrt"),
    ("NRT_WIND_ONLY", ("wind_u", "wind_v"), "wind_nrt"),
]

# Whole-stack runs. ALL_NRT_RAW is the pre-registered one and is gated on at
# least four single-channel runs qualifying (pre-registration 3.2); the gate is
# evaluated in code below rather than by eye. The two extra rows are labelled
# post-hoc and never substitute for the pre-registered verdict.
STACK_RUNS = [
    ("ALL_NRT_RAW", {"sst": "sst_nrt", "sss": "sss_nrt_smos", "sla": "sla_nrt",
                     "current_u": "currents_nrt", "current_v": "currents_nrt",
                     "wind_u": "wind_nrt", "wind_v": "wind_nrt"}, "preregistered"),
    ("ALL_NRT_RAW_SMAP_SSS", {"sst": "sst_nrt", "sss": "sss_nrt_smap",
                              "sla": "sla_nrt", "current_u": "currents_nrt",
                              "current_v": "currents_nrt", "wind_u": "wind_nrt",
                              "wind_v": "wind_nrt"}, "post_hoc"),
    ("ALL_NRT_EXCEPT_SSS", {"sst": "sst_nrt", "sla": "sla_nrt",
                            "current_u": "currents_nrt", "current_v": "currents_nrt",
                            "wind_u": "wind_nrt", "wind_v": "wind_nrt"}, "post_hoc"),
]

QUALIFYING = {"SUBSTITUTE_APPROVED", "SUBSTITUTE_WITH_MONITORING"}


def channel_decision(band: str, s100: str, worst: str, cov_loss: float,
                     rho: float, b_over_sigma: float, q: float) -> str:
    """The pre-registered per-channel decision rule (section 4.3).

    One ambiguity in the pre-registered table is resolved here and reported as
    resolved: the REJECT_RAW conditions can hold at the same time as the
    SUBSTITUTE_WITH_MONITORING condition, and the table gave no precedence.
    REJECT_RAW is treated as an overriding disqualifier, which is the reading a
    reader would expect. On this phase's results the choice changes no verdict,
    because every channel it could have affected is already SEVERE at 100 m.
    """
    def le(a, b):
        return SENS_BANDS.index(a) <= SENS_BANDS.index(b)

    if s100 == "SEVERE" or (np.isfinite(rho) and rho < 0.75) or cov_loss >= 0.20:
        return "REJECT_RAW"
    if (band in ("INTERCHANGEABLE", "USABLE_WITH_CAVEAT")
            and s100 in ("NEGLIGIBLE", "MINOR") and le(worst, "MATERIAL")
            and cov_loss < 0.02):
        return "SUBSTITUTE_APPROVED"
    if le(s100, "MATERIAL") and worst != "SEVERE":
        return "SUBSTITUTE_WITH_MONITORING"
    if (band in ("MARGINAL", "INCOMPATIBLE_RAW") and np.isfinite(rho) and rho >= 0.90
            and (b_over_sigma >= 0.15 or not (0.85 <= q <= 1.15))):
        return "ADAPTER_REQUIRED"
    return "REJECT_RAW"


def sha(sd) -> str:
    h = hashlib.sha256()
    for k in sorted(sd):
        h.update(k.encode())
        h.update(np.ascontiguousarray(sd[k].detach().cpu().numpy()).tobytes())
    return h.hexdigest()


def open_reference(year: int = 2024) -> xr.Dataset:
    ds = xr.open_zarr(MR / f"oceanembed_{year}.zarr", consolidated=True)
    keep = [v for v in ds.data_vars if v in ALLOWED_REFERENCE_VARS]
    assert not any(v.startswith(("temp_", "target_valid_")) for v in keep), \
        "LEAK: a target variable was selected"
    return ds[keep]


def load_nrt(key: str) -> xr.Dataset | None:
    p = NRT / f"{key}_canonical.nc"
    if not p.exists():
        return None
    d = xr.open_dataset(p)
    d = d.assign_coords(time=pd.DatetimeIndex(d.time.values).normalize())
    return d.load()


def main() -> int:
    t_start = time.time()
    ck = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu",
                    weights_only=False)
    l2 = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    l2.load_state_dict(ck["state_dict"])
    l2.eval()
    for p in l2.parameters():
        p.requires_grad_(False)
    sha_before = sha(ck["state_dict"])
    patch = int(ck["patch"])
    print(f"frozen L2 patch={patch} latent={ck['latent']} sha={sha_before[:16]}")

    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"

    ref = open_reference(2024)
    rtimes = pd.DatetimeIndex(ref.time.values).normalize()
    siv = np.asarray(ref["surface_input_valid"].isel(time=0).values, dtype=bool)
    cells = np.argwhere(siv)
    r, c = cells[:, 0], cells[:, 1]
    cell_lat, cell_lon = ref.lat.values[r], ref.lon.values[c]
    ctx_mean, ctx_std = fs.mean[N_DATA_CHANNELS:], fs.std[N_DATA_CHANNELS:]
    print(f"cells: {len(r)}   reference vars: {sorted(ref.data_vars)}")

    sources = {k: load_nrt(k) for _, _, k in SINGLE_RUNS}
    sources["currents_nrt_lag3"] = load_nrt("currents_nrt_lag3")
    available = {k: v is not None for k, v in sources.items()}
    print("NRT sources available:", {k: v for k, v in available.items()})

    # Dates: the pre-registered stride-3 sample, restricted to days every
    # required source actually has. OSCAR is the limiting source (56 days).
    dates = pd.date_range("2024-07-01", "2024-12-15", freq="D")[::3]
    dates = pd.DatetimeIndex([d for d in dates if d in rtimes])
    have = {}
    for k, d in sources.items():
        have[k] = set(pd.DatetimeIndex(d.time.values)) if d is not None else set()
    print(f"sampled dates: {len(dates)}  ({dates[0].date()}..{dates[-1].date()})")

    runs = [(n, {ch: k for ch in chans}) for n, chans, k in SINGLE_RUNS
            if available.get(k)]
    skipped = [(n, k) for n, chans, k in SINGLE_RUNS if not available.get(k)]
    run_source = {n: k for n, chans, k in SINGLE_RUNS}
    oscar_ok = bool(available.get("currents_nrt")
                    and available.get("currents_nrt_lag3"))

    def context(t_stamp):
        s_, c_ = cyclic_doy(pd.DatetimeIndex([t_stamp]))
        raw = np.column_stack([cell_lat, cell_lon,
                               np.full(len(r), s_[0]), np.full(len(r), c_[0])])
        return torch.from_numpy(((raw - ctx_mean) / ctx_std).astype("float32"))

    def predict(arrays, t_idx, ctxt):
        field = substituted_field(ref, t_idx, fs, patch, arrays)
        with torch.no_grad():
            z = l2.embed_field(torch.from_numpy(field)[None])[0]
            return ts.inverse_transform(
                l2.forward_from_z(z[:, r, c].T, ctxt).numpy().astype("float64"))

    def execute(run_defs, do_oscar=False):
        """Run a set of substitutions over the sampled dates.

        A run is skipped on a day whose sources are not all present, and the
        number of days it actually ran on is returned with it - a run evaluated
        on fewer days must never be read as if it had the same support.
        """
        acc = {n: ShiftAccumulator(DEPTHS) for n, _ in run_defs}
        cov = {n: [] for n, _ in run_defs}
        cov["REFERENCE"] = []
        oscar = ({k: ShiftAccumulator(DEPTHS)
                  for k in ("age_B", "product_C", "both_D")} if do_oscar else {})
        per_date = []
        for n_done, day in enumerate(dates, 1):
            t_idx = int(np.where(rtimes == day)[0][0])
            ctxt = context(day)
            base_arrays = {v: np.asarray(ref[v].isel(time=t_idx).values,
                                         dtype="float64") for v in SURFACE}
            jm_ref = joint_mask(base_arrays)
            cov["REFERENCE"].append(float(jm_ref[r, c].mean()))
            p_ref = predict({}, t_idx, ctxt)
            alive_ref = jm_ref[r, c]
            row = {"date": str(day.date()),
                   "coverage_REFERENCE": cov["REFERENCE"][-1]}

            for name, mapping in run_defs:
                if not all(day in have[k] for k in set(mapping.values())):
                    row[f"coverage_{name}"] = np.nan
                    continue
                rep = {ch: np.asarray(sources[k][ch].sel(time=day).values,
                                      dtype="float64")
                       for ch, k in mapping.items()}
                jm = joint_mask({**base_arrays, **rep})
                both = alive_ref & jm[r, c]
                cov[name].append(float(jm[r, c].mean()))
                row[f"coverage_{name}"] = cov[name][-1]
                p = predict(rep, t_idx, ctxt)
                acc[name].update(p_ref, p,
                                 np.repeat(both[:, None], len(DEPTHS), axis=1))

            if (do_oscar and day in have.get("currents_nrt", ())
                    and day in have.get("currents_nrt_lag3", ())
                    and t_idx - OSCAR_AGE_DAYS >= 0):
                lag_idx = t_idx - OSCAR_AGE_DAYS
                fin, lag = sources["currents_nrt"], sources["currents_nrt_lag3"]
                lag_times = pd.DatetimeIndex(lag.time.values)
                li = int(np.where(lag_times
                                  == day - pd.Timedelta(days=OSCAR_AGE_DAYS))[0][0])
                variants = {
                    "age_B": {ch: np.asarray(ref[ch].isel(time=lag_idx).values,
                                             dtype="float64")
                              for ch in ("current_u", "current_v")},
                    "product_C": {ch: np.asarray(fin[ch].sel(time=day).values,
                                                 dtype="float64")
                                  for ch in ("current_u", "current_v")},
                    "both_D": {ch: np.asarray(lag[ch].isel(time=li).values,
                                              dtype="float64")
                               for ch in ("current_u", "current_v")},
                }
                for k, rep in variants.items():
                    jm = joint_mask({**base_arrays, **rep})
                    both = alive_ref & jm[r, c]
                    p = predict(rep, t_idx, ctxt)
                    oscar[k].update(p_ref, p,
                                    np.repeat(both[:, None], len(DEPTHS), axis=1))
            per_date.append(row)
            if n_done % 20 == 0:
                print(f"  {n_done}/{len(dates)} days ({time.time()-t_start:.0f}s)",
                      flush=True)
        return acc, cov, oscar, per_date

    print("pass 1: single-channel substitutions")
    acc, cov, oscar, per_date = execute(runs, do_oscar=oscar_ok)
    assert sha(l2.state_dict()) == sha_before, "FROZEN L2 CHANGED during pass 1"

    l2rmse = pd.read_csv(TAB / "phase6b_l2_metrics_by_depth_test.csv")
    l2rmse = l2rmse[l2rmse["model"].str.contains("L2")].set_index("depth_m")["rmse"]
    compat_tab = pd.read_csv(TAB / "phase6cd_channel_compatibility.csv")

    def frame_for(name, key, acc_d, cov_d, ref_cov):
        f = acc_d[name].frame(name)
        f["nrt_key"] = key
        f["l2_test_rmse"] = f["depth_m"].map(l2rmse)
        f["s_ratio"] = f["rmsd"] / f["l2_test_rmse"]
        f["sensitivity_band"] = [sensitivity_band(x) for x in f["s_ratio"]]
        f["n_days_run"] = len(cov_d[name])
        f["coverage_mean"] = float(np.mean(cov_d[name])) if cov_d[name] else np.nan
        f["coverage_loss_vs_reference"] = ref_cov - f["coverage_mean"]
        return f

    def summarise(f, name, key, kind):
        at100 = f[f["depth_m"] == 100].iloc[0]
        return {"run": name, "nrt_key": key, "kind": kind,
                "n_days_run": int(at100["n_days_run"]),
                "coverage_mean": float(at100["coverage_mean"]),
                "coverage_loss": float(at100["coverage_loss_vs_reference"]),
                "rmsd_100m_degC": float(at100["rmsd"]),
                "mean_shift_100m_degC": float(at100["mean_shift"]),
                "s_ratio_100m": float(at100["s_ratio"]),
                "band_100m": at100["sensitivity_band"],
                "worst_band": worst_band(f["sensitivity_band"].tolist(), SENS_BANDS),
                "worst_depth_m": int(f.loc[f["s_ratio"].idxmax(), "depth_m"]),
                "max_s_ratio": float(f["s_ratio"].max())}

    ref_cov = float(np.mean(cov["REFERENCE"]))
    frames = [frame_for(n, run_source[n], acc, cov, ref_cov) for n, _ in runs]

    # ------------------------------------------------ per-channel decisions
    decisions = []
    for name, mapping in runs:
        key = run_source[name]
        f = [x for x in frames if x["run"].iloc[0] == name][0]
        row = summarise(f, name, key, "single_channel")
        cm = compat_tab[(compat_tab["nrt_key"] == key)
                        & (compat_tab["region"] == "full_nio")]
        # A two-component channel (currents, wind) has two compatibility rows;
        # the WORSE of the two is taken, since the pair enters the model together.
        band = worst_band(cm["compatibility_band"].tolist(),
                          ["INTERCHANGEABLE", "USABLE_WITH_CAVEAT", "MARGINAL",
                           "INCOMPATIBLE_RAW"])
        rho = float(cm["correlation_daily_median"].min()) if len(cm) else np.nan
        bs = float(cm["abs_bias_over_sigma"].max()) if len(cm) else np.nan
        if len(cm):
            qs = cm["std_ratio"].to_numpy(dtype="float64")
            q = float(qs[int(np.argmax(np.abs(qs - 1.0)))])
        else:
            q = np.nan
        row.update({"compatibility_band_full_nio": band, "correlation": rho,
                    "abs_bias_over_sigma": bs, "std_ratio": q,
                    "decision": channel_decision(band, row["band_100m"],
                                                 row["worst_band"],
                                                 row["coverage_loss"], rho, bs, q)})
        decisions.append(row)

    n_qualifying = sum(d["decision"] in QUALIFYING for d in decisions)
    gate_open = n_qualifying >= 4
    print("\nqualifying single-channel substitutions: %d/6 -> ALL_NRT_RAW %s "
          "(pre-registered gate: at least 4)"
          % (n_qualifying, "RUNS" if gate_open else "DOES NOT RUN"))

    # -------------------------------------------------- pass 2: stack runs
    stack_summary = []
    if gate_open:
        stack_defs = [(n, m) for n, m, _ in STACK_RUNS
                      if all(available.get(k) for k in set(m.values()))]
        kinds = {n: k for n, _, k in STACK_RUNS}
        print("pass 2: whole-stack substitutions")
        acc2, cov2, _, per_date2 = execute(stack_defs, do_oscar=False)
        assert sha(l2.state_dict()) == sha_before, "FROZEN L2 CHANGED during pass 2"
        ref_cov2 = float(np.mean(cov2["REFERENCE"]))
        for name, _ in stack_defs:
            f = frame_for(name, "multiple", acc2, cov2, ref_cov2)
            frames.append(f)
            stack_summary.append(summarise(f, name, "multiple", kinds[name]))
        for a, b in zip(per_date, per_date2):
            a.update({k: v for k, v in b.items() if k != "date"})

    print("L2 unchanged: %s" % sha_before[:16])

    shifts = pd.concat(frames, ignore_index=True)
    shifts.to_csv(TAB / "phase6cd_substitution_sensitivity.csv", index=False)
    pd.DataFrame(decisions + stack_summary).to_csv(
        TAB / "phase6cd_substitution_summary.csv", index=False)

    # ------------------------------------------------ whole-stack verdict
    verdict = "NRT_STACK_NOT_VIABLE_RAW"
    verdict_reason = "ALL_NRT_RAW did not run"
    pre = [x for x in stack_summary if x["run"] == "ALL_NRT_RAW"]
    if pre:
        a = pre[0]
        if (a["band_100m"] in ("NEGLIGIBLE", "MINOR")
                and SENS_BANDS.index(a["worst_band"]) <= SENS_BANDS.index("MATERIAL")
                and a["coverage_loss"] < 0.05):
            verdict = "NRT_STACK_VIABLE_RAW"
        elif (SENS_BANDS.index(a["band_100m"]) <= SENS_BANDS.index("MATERIAL")
              and a["worst_band"] != "SEVERE"):
            verdict = "NRT_STACK_VIABLE_WITH_MONITORING"
        verdict_reason = ("100 m band %s, worst %s, coverage loss %.3f"
                          % (a["band_100m"], a["worst_band"], a["coverage_loss"]))

    # ------------------------------------------------------ OSCAR Step 14
    if oscar:
        of = []
        for k in ("age_B", "product_C", "both_D"):
            f = oscar[k].frame(k)
            f["l2_test_rmse"] = f["depth_m"].map(l2rmse)
            f["s_ratio"] = f["rmsd"] / f["l2_test_rmse"]
            of.append(f)
        od = pd.concat(of, ignore_index=True)
        # RMSDs do not add; variances of independent effects do. The
        # decomposition is done on squared shifts, so "age accounts for X of the
        # discrepancy" is a statement that can actually be true.
        piv = od.pivot(index="depth_m", columns="run", values="rmsd").rename(
            columns={"age_B": "rmsd_age_only", "product_C": "rmsd_product_only",
                     "both_D": "rmsd_age_and_product"})
        va = piv["rmsd_age_only"] ** 2
        vp = piv["rmsd_product_only"] ** 2
        vb = piv["rmsd_age_and_product"] ** 2
        piv["var_age_only"], piv["var_product_only"] = va, vp
        piv["var_age_and_product"] = vb
        piv["var_sum_if_independent"] = va + vp
        piv["interaction_var"] = vb - (va + vp)
        piv["age_share_of_independent_sum"] = va / (va + vp)
        piv["product_share_of_independent_sum"] = vp / (va + vp)
        piv["dominant_effect"] = np.where(va > vp, "AGE", "PRODUCT")
        piv.reset_index().to_csv(TAB / "phase6cd_oscar_age_vs_product.csv",
                                 index=False)
        od.to_csv(TAB / "phase6cd_oscar_decomposition_detail.csv", index=False)

    pd.DataFrame(per_date).to_csv(TAB / "phase6cd_daily_coverage.csv", index=False)
    json.dump({"l2_sha256": sha_before, "patch": patch,
               "n_dates": int(len(dates)),
               "dates": [str(d.date()) for d in dates],
               "oscar_age_days": OSCAR_AGE_DAYS,
               "runs_executed": [n for n, _ in runs]
                                + [x["run"] for x in stack_summary],
               "runs_skipped_source_missing": skipped,
               "n_qualifying_single_channel": int(n_qualifying),
               "all_nrt_raw_gate_open": bool(gate_open),
               "whole_stack_verdict": verdict,
               "whole_stack_verdict_reason": verdict_reason,
               "targets_opened": [],
               "note": "prediction-to-prediction sensitivity; no target read, "
                       "no accuracy claim"},
              open(OUTD / "substitution_meta.json", "w"), indent=2)

    cols = ["run", "nrt_key", "kind", "n_days_run", "coverage_loss",
            "rmsd_100m_degC", "s_ratio_100m", "band_100m", "worst_band",
            "compatibility_band_full_nio", "decision"]
    out = pd.DataFrame(decisions + stack_summary)
    print("\n" + out.reindex(
        columns=[c for c in cols if c in out.columns]).to_string(index=False))
    print("\nwhole-stack verdict: %s  (%s)" % (verdict, verdict_reason))
    print("total %.1f min" % ((time.time() - t_start) / 60))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
