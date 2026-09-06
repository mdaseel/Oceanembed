"""Compare the retired smoke-test SSS against the official replacement.

OLD  SMAP JPL L3 CAP v5.0, 8-day running mean   (supplied archive)
NEW  CMEMS MULTIOBS cmems_obs-mob_glo_phy-sss_my_multi_P1D, var 'sos'
     DOI 10.48670/moi-00051, genuinely daily

Diagnostic only. Neither product is treated as truth - the point is to
characterise what changed when the model-ready SSS was swapped, in particular
whether the 8-day running mean was suppressing real spatial structure.

Run:  PYTHONPATH=src python scripts/validate/sss_comparison.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from oceanembed.config import REPO_ROOT  # noqa: E402
from oceanembed.data import loaders as L  # noqa: E402
from oceanembed.preprocessing.regrid import regrid_horizontal  # noqa: E402

warnings.filterwarnings("ignore")
TAB = REPO_ROOT / "outputs" / "tables"
FIG = REPO_ROOT / "outputs" / "figures"
for d in (TAB, FIG):
    d.mkdir(parents=True, exist_ok=True)

DATES = ["2020-01-01", "2020-01-02"]


def grad_mag(a: np.ndarray) -> np.ndarray:
    """Spatial gradient magnitude - the statistic an 8-day mean should damp."""
    gy, gx = np.gradient(a)
    return np.sqrt(gy ** 2 + gx ** 2)


def main() -> int:
    old_ds = regrid_horizontal(L.load_smap_sss().sel(time=DATES), method="linear")
    new_ds = regrid_horizontal(L.load_multiobs_sss("data/raw/sss_multiobs/2020/*.nc")
                               .sel(time=DATES), method="linear")

    rows = []
    for i, d in enumerate(DATES):
        a = old_ds["sss"].isel(time=i).values.astype("float64")
        b = new_ds["sss"].isel(time=i).values.astype("float64")
        both = np.isfinite(a) & np.isfinite(b)
        diff = b[both] - a[both]
        r = np.corrcoef(a[both], b[both])[0, 1] if both.sum() > 2 else np.nan
        rows.append({
            "date": d,
            "n_common_cells": int(both.sum()),
            "old_mean": float(np.nanmean(a)), "new_mean": float(np.nanmean(b)),
            "mean_difference_new_minus_old": float(diff.mean()),
            "rmse": float(np.sqrt((diff ** 2).mean())),
            "correlation": float(r),
            "old_spatial_std": float(np.nanstd(a)), "new_spatial_std": float(np.nanstd(b)),
            "old_mean_grad": float(np.nanmean(grad_mag(np.where(np.isfinite(a), a, np.nan)))),
            "new_mean_grad": float(np.nanmean(grad_mag(np.where(np.isfinite(b), b, np.nan)))),
            "old_pct_missing": float(100 * (1 - np.isfinite(a).mean())),
            "new_pct_missing": float(100 * (1 - np.isfinite(b).mean())),
        })

    df = pd.DataFrame(rows)
    df.to_csv(TAB / "sss_product_comparison.csv", index=False)
    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 25)
    print(df.to_string(index=False))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    a = old_ds["sss"].isel(time=0)
    b = new_ds["sss"].isel(time=0)
    fig, axes = plt.subplots(1, 3, figsize=(16, 3.8))
    for ax, da, title, cmap, lim in [
        (axes[0], a, "OLD  SMAP 8-day running mean", "viridis", None),
        (axes[1], b, "NEW  MULTIOBS daily (sos)", "viridis", None),
        (axes[2], b - a, "NEW - OLD", "RdBu_r", 2.0),
    ]:
        kw = dict(cmap=cmap, shading="auto")
        if lim:
            kw.update(vmin=-lim, vmax=lim)
        else:
            kw.update(vmin=32, vmax=37)
        m = ax.pcolormesh(old_ds.lon, old_ds.lat, da, **kw)
        ax.set_title(f"{title}\n{DATES[0]}", fontsize=9)
        ax.set_xlabel("lon (degE)", fontsize=8)
        ax.set_ylabel("lat (degN)", fontsize=8)
        ax.tick_params(labelsize=7)
        cb = plt.colorbar(m, ax=ax, fraction=0.04)
        cb.set_label("PSU", fontsize=8)
        cb.ax.tick_params(labelsize=7)
    fig.tight_layout()
    out = FIG / f"08_sss_product_comparison_{DATES[0]}.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"\nwrote {TAB / 'sss_product_comparison.csv'}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
