"""Phase 6C-D figures.

Every panel is drawn from the CSV/JSON artefacts written by the earlier steps,
so a figure can never disagree with the table it is supposed to illustrate.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from oceanembed.config import REPO_ROOT

TAB = REPO_ROOT / "outputs" / "tables"
FIG = REPO_ROOT / "outputs" / "figures"
OUTD = REPO_ROOT / "outputs" / "nrt"
NRT = REPO_ROOT / "data" / "processed" / "nrt"
MR = REPO_ROOT / "data" / "processed" / "model_ready"

BAND_COLOR = {"INTERCHANGEABLE": "#1a7f37", "USABLE_WITH_CAVEAT": "#8a9a1a",
              "MARGINAL": "#d08a00", "INCOMPATIBLE_RAW": "#b42318",
              "NEGLIGIBLE": "#1a7f37", "MINOR": "#8a9a1a",
              "MATERIAL": "#d08a00", "SEVERE": "#b42318"}
CHANNEL_UNITS = {"sst": "degC", "sss": "PSU", "sla": "m", "current_u": "m/s",
                 "current_v": "m/s", "wind_u": "m/s", "wind_v": "m/s"}


def save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=140)
    plt.close(fig)
    print("  ", name)


# 1 -------------------------------------------------------------------------
def fig_latency():
    d = pd.read_csv(OUTD / "latency_summary.csv").sort_values(
        "latency_at_first_sight_days")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    col = ["#b42318" if v > 30 else "#1a7f37" for v in d["latency_at_first_sight_days"]]
    ax.barh(d["product_key"], d["latency_at_first_sight_days"], color=col)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("days from newest valid time to first sight by OceanEmbed")
    ax.set_title("Prospective provider availability latency\n"
                 "(snapshot: an UPPER BOUND, few poll cycles so far)")
    for y, v in enumerate(d["latency_at_first_sight_days"]):
        ax.text(v, y, f" {v:.2f}", va="center", fontsize=8)
    ax.grid(axis="x", alpha=0.3)
    save(fig, "phase6cd_01_latency.png")


# 2 -------------------------------------------------------------------------
def fig_overlap():
    doc = json.loads((OUTD / "overlap_manifest.json").read_text())
    pairs = doc["pairs"]
    fig, ax = plt.subplots(figsize=(9, 4))
    for i, (name, p) in enumerate(sorted(pairs.items())):
        s, e = pd.Timestamp(p["overlap_start"]), pd.Timestamp(p["overlap_end"])
        ax.barh(i, (e - s).days, left=s, height=0.55, color="#3b6fb6")
        ax.text(s, i, f"  {p['overlap_days']} d", va="center", fontsize=8,
                color="white")
    inter = doc["all_pair_intersection"]
    ax.axvspan(pd.Timestamp(inter["start"]), pd.Timestamp(inter["end"]),
               color="#d08a00", alpha=0.25,
               label=f"all-pair intersection ({inter['days']} d)")
    ax.set_yticks(range(len(pairs)))
    ax.set_yticklabels(sorted(pairs))
    ax.set_title("Reference / NRT overlap discovered independently per pair")
    ax.legend(loc="lower left", fontsize=8)
    ax.grid(axis="x", alpha=0.3)
    save(fig, "phase6cd_02_overlap.png")


# 3 -------------------------------------------------------------------------
def fig_compat_bands():
    d = pd.read_csv(TAB / "phase6cd_channel_compatibility.csv")
    order = ["INTERCHANGEABLE", "USABLE_WITH_CAVEAT", "MARGINAL", "INCOMPATIBLE_RAW"]
    keys = d[["channel", "nrt_key"]].drop_duplicates()
    labels = [f"{r.channel}\n{r.nrt_key}" for r in keys.itertuples()]
    regions = ["full_nio", "arabian_sea", "bay_of_bengal"]
    M = np.full((len(keys), 3), np.nan)
    for i, r in enumerate(keys.itertuples()):
        for j, reg in enumerate(regions):
            sel = d[(d["channel"] == r.channel) & (d["nrt_key"] == r.nrt_key)
                    & (d["region"] == reg)]
            if len(sel):
                M[i, j] = order.index(sel["compatibility_band"].iloc[0])
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(M, cmap=matplotlib.colors.ListedColormap(
        [BAND_COLOR[o] for o in order]), vmin=-0.5, vmax=3.5, aspect="auto")
    ax.set_xticks(range(3)); ax.set_xticklabels(regions, rotation=20)
    ax.set_yticks(range(len(labels))); ax.set_yticklabels(labels, fontsize=8)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if np.isfinite(M[i, j]):
                ax.text(j, i, order[int(M[i, j])].replace("_", "\n"),
                        ha="center", va="center", fontsize=6, color="white")
    cb = fig.colorbar(im, ticks=range(4))
    cb.ax.set_yticklabels(order, fontsize=7)
    ax.set_title("RAW channel compatibility band\n(no calibration applied)")
    save(fig, "phase6cd_03_compatibility_bands.png")


# 4 -------------------------------------------------------------------------
def fig_bias_and_spread():
    d = pd.read_csv(TAB / "phase6cd_channel_compatibility.csv")
    d = d[d["region"] == "full_nio"].copy()
    d["label"] = d["channel"] + "\n" + d["nrt_key"]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    for ax, col, ttl in zip(
            axes, ["rmsd_over_sigma", "abs_bias_over_sigma", "std_ratio"],
            ["RMSD / sigma_train", "|bias| / sigma_train", "std(NRT) / std(reference)"]):
        col_c = [BAND_COLOR[b] for b in d["compatibility_band"]]
        ax.bar(range(len(d)), d[col], color=col_c)
        ax.set_xticks(range(len(d)))
        ax.set_xticklabels(d["label"], rotation=75, fontsize=7)
        ax.set_title(ttl, fontsize=10)
        ax.grid(axis="y", alpha=0.3)
    axes[0].axhline(0.10, ls="--", c="k", lw=0.8)
    axes[0].axhline(0.25, ls=":", c="k", lw=0.8)
    axes[2].axhline(1.0, ls="--", c="k", lw=0.8)
    fig.suptitle("Raw discrepancy normalised by the frozen training spread "
                 "(dashed lines = pre-registered band edges)", fontsize=10)
    save(fig, "phase6cd_04_normalised_discrepancy.png")


# 5 -------------------------------------------------------------------------
def fig_sss_coverage():
    daily = pd.read_csv(TAB / "phase6cd_channel_daily.csv")
    d = daily[(daily["region"] == "full_nio")
              & (daily["channel"] == "sss")].copy()
    d["date"] = pd.to_datetime(d["date"])
    fig, ax = plt.subplots(figsize=(10, 4))
    ref = d[d["nrt_key"] == "sss_nrt_smos"]
    ax.plot(ref["date"], ref["ref_coverage"], color="k", lw=1.2,
            label="MULTIOBS L4 reference")
    for key, style in (("sss_nrt_smos", "-o"), ("sss_nrt_smap", "-s")):
        s = d[d["nrt_key"] == key]
        ax.plot(s["date"], s["nrt_coverage"], style, ms=3, lw=1,
                label=f"{key} (n={len(s)} days)")
    ax.set_ylabel("fraction of ocean cells with a value")
    ax.set_ylim(0, 1.05)
    ax.set_title("Daily SSS coverage: a gap-free L4 versus gappy single-mission NRT\n"
                 "gaps are shown as they arrive - nothing is filled")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    save(fig, "phase6cd_05_sss_coverage.png")


# 6 -------------------------------------------------------------------------
def fig_sss_maps():
    ref = xr.open_zarr(MR / "oceanembed_2024.zarr", consolidated=True)["sss"]
    smos = xr.open_dataset(NRT / "sss_nrt_smos_canonical.nc")["sss"]
    smap = xr.open_dataset(NRT / "sss_nrt_smap_canonical.nc")["sss"]
    day = pd.Timestamp(smap.time.values[2])
    fig, axes = plt.subplots(1, 3, figsize=(14, 3.6))
    for ax, da, ttl in zip(
            axes,
            [ref.sel(time=day), smos.sel(time=day, method="nearest"),
             smap.sel(time=day)],
            ["MULTIOBS L4 (training reference)", "SMOS L3 ascending (NRT)",
             "SMAP L2C binned (NRT)"]):
        v = np.asarray(da.values, dtype="float64")
        im = ax.pcolormesh(da.lon, da.lat, v, vmin=32, vmax=37, cmap="viridis")
        cov = np.isfinite(v).mean()
        ax.set_title(f"{ttl}\n{day.date()}  valid={cov:.1%} of grid", fontsize=9)
        fig.colorbar(im, ax=ax, label="PSU")
    save(fig, "phase6cd_06_sss_maps.png")


# 7 -------------------------------------------------------------------------
def fig_difference_maps():
    ref = xr.open_zarr(MR / "oceanembed_2024.zarr", consolidated=True)
    pairs = [("sst", "sst_nrt", "sst", "degC"), ("sla", "sla_nrt", "sla", "m"),
             ("current_u", "currents_nrt", "current_u", "m/s"),
             ("wind_u", "wind_nrt", "wind_u", "m/s")]
    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    for ax, (rv, key, nv, unit) in zip(axes.ravel(), pairs):
        nrt = xr.open_dataset(NRT / f"{key}_canonical.nc")[nv]
        t = pd.DatetimeIndex(nrt.time.values).normalize()
        rt = pd.DatetimeIndex(ref.time.values).normalize()
        common = t.intersection(rt)
        diff = (nrt.sel(time=common).values
                - ref[rv].sel(time=common).values).mean(axis=0)
        lim = float(np.nanpercentile(np.abs(diff), 99))
        im = ax.pcolormesh(nrt.lon, nrt.lat, diff, cmap="RdBu_r",
                           vmin=-lim, vmax=lim)
        ax.set_title(f"{rv}: mean(NRT - reference), {len(common)} days", fontsize=9)
        fig.colorbar(im, ax=ax, label=unit)
    fig.suptitle("Spatial structure of the raw product difference", fontsize=11)
    save(fig, "phase6cd_07_difference_maps.png")


# 8 -------------------------------------------------------------------------
def fig_gradient_ratio():
    d = pd.read_csv(TAB / "phase6cd_channel_compatibility.csv")
    d = d[(d["region"] == "full_nio") & d["grad_ratio"].notna()].copy()
    d["label"] = d["channel"] + "\n" + d["nrt_key"]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(range(len(d)), d["grad_ratio"],
           color=[BAND_COLOR[b] for b in d["compatibility_band"]])
    ax.axhline(1.0, ls="--", c="k", lw=1)
    ax.set_xticks(range(len(d)))
    ax.set_xticklabels(d["label"], rotation=75, fontsize=7)
    ax.set_ylabel("mean |grad| NRT / reference")
    ax.set_title("Effective resolution proxy: spatial gradient ratio\n"
                 ">1 means the NRT product carries more small-scale structure")
    ax.grid(axis="y", alpha=0.3)
    save(fig, "phase6cd_08_gradient_ratio.png")


# 9 -------------------------------------------------------------------------
def fig_sensitivity_profiles():
    d = pd.read_csv(TAB / "phase6cd_substitution_sensitivity.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharey=True)
    for run, g in d.groupby("run"):
        g = g.sort_values("depth_m")
        axes[0].plot(g["rmsd"], g["depth_m"], "-o", ms=3, label=run)
        axes[1].plot(g["s_ratio"], g["depth_m"], "-o", ms=3, label=run)
    for ax in axes:
        ax.invert_yaxis(); ax.set_yscale("symlog", linthresh=50)
        ax.set_ylabel("depth (m)"); ax.grid(alpha=0.3)
    axes[0].set_xlabel("prediction shift RMSD (degC)")
    for x, lab in ((0.10, "NEGLIGIBLE"), (0.25, "MINOR"), (0.50, "MATERIAL")):
        axes[1].axvline(x, ls="--", c="k", lw=0.8)
        axes[1].text(x, 1.5, lab, rotation=90, fontsize=7, va="bottom")
    axes[1].set_xlabel("shift / frozen L2 test RMSE at that depth")
    axes[1].legend(fontsize=7, loc="lower right")
    fig.suptitle("Frozen-L2 SENSITIVITY to product substitution "
                 "(prediction vs prediction - not accuracy)", fontsize=11)
    save(fig, "phase6cd_09_sensitivity_profiles.png")


# 10 ------------------------------------------------------------------------
def fig_oscar_decomposition():
    d = pd.read_csv(TAB / "phase6cd_oscar_age_vs_product.csv").sort_values("depth_m")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].plot(d["rmsd_age_only"], d["depth_m"], "-o", ms=3,
                 label="age only (Final at t-3)")
    axes[0].plot(d["rmsd_product_only"], d["depth_m"], "-s", ms=3,
                 label="product only (NRT at t)")
    axes[0].plot(d["rmsd_age_and_product"], d["depth_m"], "-^", ms=3,
                 label="both (NRT at t-3, the operational case)")
    axes[0].plot(np.sqrt(d["var_sum_if_independent"]), d["depth_m"], "k:",
                 label="quadrature sum if independent")
    axes[0].set_xlabel("prediction shift RMSD (degC)")
    axes[0].legend(fontsize=8)
    axes[1].fill_betweenx(d["depth_m"], 0, d["age_share_of_independent_sum"],
                          color="#3b6fb6", alpha=0.7, label="age share")
    axes[1].fill_betweenx(d["depth_m"], d["age_share_of_independent_sum"], 1.0,
                          color="#d08a00", alpha=0.7, label="product share")
    axes[1].axvline(0.5, ls="--", c="k", lw=1)
    axes[1].set_xlabel("share of the (variance) discrepancy")
    axes[1].set_xlim(0, 1); axes[1].legend(fontsize=8)
    for ax in axes:
        ax.invert_yaxis(); ax.set_yscale("symlog", linthresh=50)
        ax.set_ylabel("depth (m)"); ax.grid(alpha=0.3)
    fig.suptitle("OSCAR: separating the AGE effect from the PRODUCT effect "
                 "(k = 3 days, pre-registered)", fontsize=11)
    save(fig, "phase6cd_10_oscar_age_vs_product.png")


# 11 ------------------------------------------------------------------------
def fig_decisions():
    d = pd.read_csv(TAB / "phase6cd_substitution_summary.csv")
    fig, ax = plt.subplots(figsize=(10, 5))
    col = [BAND_COLOR[b] for b in d["band_100m"]]
    y = np.arange(len(d))
    ax.barh(y, d["s_ratio_100m"], color=col)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r.run}  (n={int(r.n_days_run)} d)"
                        for r in d.itertuples()], fontsize=8)
    for x, lab in ((0.10, "NEGLIGIBLE"), (0.25, "MINOR"), (0.50, "MATERIAL")):
        ax.axvline(x, ls="--", c="k", lw=0.8)
        ax.text(x, -0.8, lab, rotation=90, fontsize=7, va="bottom")
    for i, r in enumerate(d.itertuples()):
        dec = getattr(r, "decision", None)
        txt = dec if isinstance(dec, str) else str(getattr(r, "kind", ""))
        ax.text(r.s_ratio_100m, i, f"  {txt}  (cov loss {r.coverage_loss:.1%})",
                va="center", fontsize=7)
    ax.set_xlabel("100 m prediction shift / frozen L2 test RMSE")
    ax.invert_yaxis()
    ax.set_title("Per-channel and whole-stack substitution outcome at 100 m\n"
                 "bands and decision rule were frozen before these results")
    ax.grid(axis="x", alpha=0.3)
    save(fig, "phase6cd_11_decisions.png")


def main() -> int:
    print("figures ->", FIG)
    for fn in (fig_latency, fig_overlap, fig_compat_bands, fig_bias_and_spread,
               fig_sss_coverage, fig_sss_maps, fig_difference_maps,
               fig_gradient_ratio, fig_sensitivity_profiles,
               fig_oscar_decomposition, fig_decisions):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"   {fn.__name__} FAILED: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
