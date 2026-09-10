"""Phase 7C figures — the three stages, the error attribution, and the D26 pick.

Four figures required by the master prompt (7C.6). Invalid and no-crossing cells
are rendered in their own colour rather than omitted: a cell where the isotherm
does not exist is a result, not a gap in the picture.

Date and cell are chosen POSITIONALLY, never by how the result looks:
  * date = the median date of the pre-registered population (index 108 of 216)
  * cell = the Phase 7B default demo location, 15.25 N 87.75 E, which was itself
    selected by geography in Phase 7B and not by prediction error

    python scripts/diagnostics/make_d26_tchp_figures.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.diagnostics import D26Status, d26_tchp  # noqa: E402
from oceanembed.replay.contract import DEPTHS  # noqa: E402
from oceanembed.replay.engine import ReplayEngine  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "diagnostics"))
from run_d26_tchp_evaluation import (native_stage, protocol_dates,  # noqa: E402
                                     reference_stage)

FIG = ROOT / "outputs" / "figures" / "phase7c"
TABLES = ROOT / "outputs" / "tables"
STAGE_LABEL = {"A": "A — GLORYS native (36 levels)",
               "B": "B — GLORYS on the 15 mandated depths",
               "C": "C — OceanEmbed (frozen L2, 15 depths)"}
DEMO_LAT, DEMO_LON = 15.25, 87.75


def _basemap(ax, field, population, extent, cmap, vmin, vmax, title):
    """Draw one stage, with land and undefined cells in their own colours."""
    # Categorical underlay: 0 = outside the population (land / invalid input),
    # 1 = in the population but the diagnostic does not exist there.
    under = np.where(population, 1.0, 0.0)
    ax.imshow(under, origin="lower", extent=extent, aspect="auto",
              cmap=ListedColormap(["#2b3038", "#c96f4a"]), vmin=0, vmax=1)
    shown = np.ma.masked_invalid(np.where(population, field, np.nan))
    im = ax.imshow(shown, origin="lower", extent=extent, aspect="auto",
                   cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_title(title, fontsize=9)
    ax.set_xlabel("longitude (°E)", fontsize=8)
    ax.tick_params(labelsize=7)
    return im


def stage_map_figure(stages, population, extent, key, unit, cmap, name, date):
    values = np.concatenate([
        np.asarray(getattr(r, key))[population &
                                    (r.d26_defined if key == "d26" else r.tchp_defined)]
        for r in stages.values()])
    vmin, vmax = np.percentile(values, [2, 98])

    fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.2), constrained_layout=True)
    for ax, (s, r) in zip(axes, stages.items()):
        defined = r.d26_defined if key == "d26" else r.tchp_defined
        field = np.where(defined, getattr(r, key), np.nan)
        im = _basemap(ax, field, population, extent, cmap, vmin, vmax,
                      STAGE_LABEL[s])
    axes[0].set_ylabel("latitude (°N)", fontsize=8)
    cb = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.01)
    cb.set_label(unit, fontsize=8)
    cb.ax.tick_params(labelsize=7)
    fig.legend(handles=[
        Patch(facecolor="#c96f4a", label="in population, no 26 °C crossing "
                                         "(not a value)"),
        Patch(facecolor="#2b3038", label="land or surface input invalid")],
        loc="lower center", ncol=2, fontsize=8, frameon=False,
        bbox_to_anchor=(0.5, -0.07))
    fig.suptitle(f"{name} — {date}   ·   identical dates, cells and horizontal "
                 f"treatment in all three stages", fontsize=10)
    return fig


def attribution_figure() -> plt.Figure:
    m = pd.read_csv(TABLES / "phase7c_d26_tchp_metrics.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    order = ["A_vs_B", "B_vs_C", "A_vs_C"]
    labels = ["A vs B\ndiscretization", "B vs C\nreconstruction",
              "A vs C\ntotal"]
    colors = ["#4c9f70", "#c05746", "#37474f"]
    regions = ["whole_nio", "arabian_sea", "bay_of_bengal"]
    for ax, (q, unit) in zip(axes, [("d26", "m"), ("tchp", "kJ/cm²")]):
        width = 0.25
        x = np.arange(len(regions))
        for i, (pair, lab, c) in enumerate(zip(order, labels, colors)):
            vals = [float(m[(m.pair == pair) & (m.quantity == q) &
                            (m.region == r)]["mae"].iloc[0]) for r in regions]
            bars = ax.bar(x + (i - 1) * width, vals, width, label=lab, color=c)
            ax.bar_label(bars, fmt="%.1f", fontsize=7, padding=1)
        ax.set_xticks(x)
        ax.set_xticklabels(["whole NIO", "Arabian Sea", "Bay of Bengal"],
                           fontsize=8)
        ax.set_ylabel(f"MAE ({unit})", fontsize=9)
        ax.set_title(f"{'D26' if q == 'd26' else 'TCHP'} error attribution",
                     fontsize=10)
        ax.tick_params(labelsize=8)
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Vertical discretization and reconstruction are reported "
                 "separately, never collapsed into one number", fontsize=10)
    return fig


def profile_figure(profiles, levels, date) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.6), constrained_layout=True)
    colors = {"A": "#37474f", "B": "#4c9f70", "C": "#c05746"}
    for ax, (top, title) in zip(axes, [(1050, "full column"),
                                       (200, "upper 200 m — where D26 sits")]):
        for slot, (s, (t, z)) in enumerate(profiles.items()):
            ax.plot(t, z, color=colors[s], lw=1.6, marker="o", ms=2.6,
                    label=STAGE_LABEL[s])
            r = d26_tchp(t, z)
            if D26Status(int(r.status)) is D26Status.OK:
                ax.axhline(float(r.d26), color=colors[s], ls=":", lw=1.1)
                if top == 200:
                    # Stacked in axes coordinates so the three readouts cannot
                    # collide when their D26 values are close together.
                    ax.text(0.03, 0.30 - 0.09 * slot,
                            f"{s}:  D26 {float(r.d26):.1f} m   ·   "
                            f"TCHP {float(r.tchp):.1f} kJ/cm²",
                            transform=ax.transAxes, fontsize=8.5,
                            color=colors[s], fontweight="medium")
        ax.axvline(26.0, color="#8d6e63", lw=1.2, ls="--")
        ax.set_ylim(top, 0)
        ax.set_xlabel("potential temperature (°C)", fontsize=9)
        ax.set_title(title, fontsize=10)
        ax.grid(alpha=0.25)
        ax.tick_params(labelsize=8)
    axes[0].set_ylabel("depth (m)", fontsize=9)
    axes[0].legend(fontsize=8, frameon=False, loc="lower left")
    axes[1].legend(handles=[
        Line2D([], [], color="#8d6e63", ls="--", label="26 °C threshold"),
        Line2D([], [], color="#666", ls=":", label="interpolated D26")],
        fontsize=8, frameon=False, loc="upper left")
    fig.suptitle(f"Representative profile — {DEMO_LAT}°N {DEMO_LON}°E, {date}. "
                 f"D26 is interpolated between bracketing levels, never snapped "
                 f"and never extrapolated.", fontsize=10)
    return fig


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    dates = protocol_dates()
    date = dates[len(dates) // 2]
    key = str(date.date())
    print(f"representative date (positional median of the population): {key}")

    engine = ReplayEngine()
    store = xr.open_zarr(ROOT / "data" / "processed" / "model_ready" /
                         f"oceanembed_{date.year}.zarr", consolidated=True)
    t = int(np.flatnonzero(
        pd.DatetimeIndex(store.time.values).normalize() == date)[0])
    population = (np.asarray(store["ocean_mask"].isel(time=t).values, dtype=bool)
                  & np.asarray(store["surface_input_valid"].isel(time=t).values,
                               dtype=bool))

    native, native_levels = native_stage({}, date)
    ref = reference_stage(store, t)
    rec = engine.replay_field(date).temperature
    stages = {"A": d26_tchp(native, native_levels),
              "B": d26_tchp(ref, DEPTHS), "C": d26_tchp(rec, DEPTHS)}

    extent = [float(engine.lon[0]), float(engine.lon[-1]),
              float(engine.lat[0]), float(engine.lat[-1])]

    f = stage_map_figure(stages, population, extent, "d26", "D26 (m)",
                         "viridis", "Depth of the 26 °C isotherm", key)
    f.savefig(FIG / "01_d26_three_stages.png", dpi=150, bbox_inches="tight")
    plt.close(f)

    f = stage_map_figure(stages, population, extent, "tchp", "TCHP (kJ/cm²)",
                         "inferno", "Tropical cyclone heat potential", key)
    f.savefig(FIG / "02_tchp_three_stages.png", dpi=150, bbox_inches="tight")
    plt.close(f)

    f = attribution_figure()
    f.savefig(FIG / "03_error_attribution.png", dpi=150, bbox_inches="tight")
    plt.close(f)

    row = int(np.abs(engine.lat - DEMO_LAT).argmin())
    col = int(np.abs(engine.lon - DEMO_LON).argmin())
    f = profile_figure({"A": (native[row, col], native_levels),
                        "B": (ref[row, col], np.array(DEPTHS, dtype="float64")),
                        "C": (rec[row, col], np.array(DEPTHS, dtype="float64"))},
                       None, key)
    f.savefig(FIG / "04_representative_profile.png", dpi=150, bbox_inches="tight")
    plt.close(f)

    for s, r in stages.items():
        print(f"  stage {s}: {r.counts()}")
    print(f"wrote 4 figures to {FIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
