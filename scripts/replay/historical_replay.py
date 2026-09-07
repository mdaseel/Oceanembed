"""Phase 7A CLI — historical replay of the frozen L2 core.

Point mode:
    python scripts/replay/historical_replay.py --date 2023-05-14 --lat 15.25 --lon 85.75
    python scripts/replay/historical_replay.py --date 2023-05-14 --lat 15.25 --lon 85.75 --figure
    python scripts/replay/historical_replay.py --start 2023-05-12 --end 2023-05-16 --lat 15.25 --lon 85.75

Field mode (exercises replay_field directly):
    python scripts/replay/historical_replay.py --field --date 2023-05-14
    python scripts/replay/historical_replay.py --field --date 2023-05-14 --out field.nc

Reads surface inputs only. No target, no Argo, no network.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import xarray as xr

from oceanembed.config import REPO_ROOT
from oceanembed.replay import ReplayEngine
from oceanembed.replay.contract import LocationStatus, OutsideDomain


def print_profile(res) -> None:
    loc = res.location
    print(f"\ndate {res.date}   model {res.model['name']}")
    print(f"  checkpoint {res.model['checkpoint_sha256'][:16]}  "
          f"encoder {res.model['encoder_sha256'][:16]}")
    print(f"  requested {loc.requested_lat:.4f} N {loc.requested_lon:.4f} E   "
          f"status {loc.status.value}")
    if loc.grid_lat is not None:
        print(f"  resolved  {loc.grid_lat:.2f} N {loc.grid_lon:.2f} E "
              f"(row {loc.grid_row}, col {loc.grid_col})")
    if loc.status is not LocationStatus.OK and loc.nearest_usable_lat is not None:
        print(f"  suggestion only (NOT substituted): nearest usable cell "
              f"{loc.nearest_usable_lat:.2f} N {loc.nearest_usable_lon:.2f} E "
              f"({loc.nearest_usable_distance_deg:.2f} deg away)")
    print(f"  inference_source {res.status['inference_source']}   "
          f"target_used {res.status['target_used_for_inference']}   "
          f"argo_used {res.status['argo_used_for_inference']}")

    if res.surface_inputs:
        print("\n  surface inputs at the resolved cell")
        for k, v in res.surface_inputs.items():
            val = "n/a" if v["value"] is None else f"{v['value']:9.4f}"
            print(f"    {k:<10s} {val} {v['units']:<6s}  {v['product']}")

    if not res.profile:
        print("\n  no profile — location outside the domain")
        return
    print("\n  depth_m   OceanEmbed   L0 clim    anomaly")
    for row in res.profile:
        f = lambda x: "     n/a" if x is None else f"{x:8.3f}"  # noqa: E731
        flag = "  *" if row["depth_m"] >= 500 else ""
        print(f"  {row['depth_m']:>7d}  {f(row['prediction_c'])}  "
              f"{f(row['climatology_c'])}  {f(row['anomaly_c'])}{flag}")
    print("  * 500-1000 m: daily anomaly skill is weaker and more "
          "climatology-dominant")


def save_figure(res, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = [r["depth_m"] for r in res.profile]
    p = [np.nan if r["prediction_c"] is None else r["prediction_c"] for r in res.profile]
    c = [np.nan if r["climatology_c"] is None else r["climatology_c"] for r in res.profile]
    fig, ax = plt.subplots(figsize=(5.5, 7))
    ax.plot(p, d, "-o", ms=4, label="OceanEmbed (frozen L2)")
    ax.plot(c, d, "--s", ms=4, label="L0 climatology")
    ax.axhspan(500, 1000, color="0.85", zorder=0)
    ax.text(ax.get_xlim()[0], 700, "  deep: weaker daily anomaly skill",
            fontsize=7, va="center")
    ax.invert_yaxis()
    ax.set_yscale("symlog", linthresh=50)
    ax.set_xlabel("temperature (degC)")
    ax.set_ylabel("depth (m)")
    ax.set_title(f"{res.date}  {res.location.grid_lat:.2f} N "
                 f"{res.location.grid_lon:.2f} E", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)
    print(f"\nfigure -> {path}")


def field_mode(eng: ReplayEngine, args) -> int:
    t0 = time.perf_counter()
    view = eng.replay_field(args.date, force_recompute=args.force_recompute)
    wall = time.perf_counter() - t0
    p = view.provenance
    print(f"replay_field({view.date})")
    print(f"  shape (lat, lon, depth) = {view.temperature.shape}")
    print(f"  depths {view.depths}")
    print(f"  supported cells {p['n_supported_cells']:,} of "
          f"{p['n_ocean_cells']:,} ocean cells "
          f"({view.lat.size * view.lon.size:,} grid cells)")
    print(f"  inference_source {p['inference_source']}   wall {wall:.2f}s"
          + (f"   compute {p['compute_seconds']:.2f}s"
             if p["compute_seconds"] is not None else ""))
    print(f"  L2 {p['l2_state_dict_sha256'][:16]}  encoder {p['l2_encoder_sha256'][:16]}")
    print("\n  depth_m   n_finite    min      mean      max   | clim n_finite")
    for d in view.depths:
        lay = view.layer(d)
        cl = view.layer(d, "climatology")
        n = int(np.isfinite(lay).sum())
        print(f"  {d:>7d}   {n:>7d}  {np.nanmin(lay):7.3f} {np.nanmean(lay):8.3f} "
              f"{np.nanmax(lay):8.3f}   | {int(np.isfinite(cl).sum()):>7d}")

    if args.out:
        out = xr.Dataset(
            {"temperature": (("lat", "lon", "depth"), view.temperature),
             "climatology": (("lat", "lon", "depth"), view.climatology),
             "anomaly": (("lat", "lon", "depth"), view.anomaly),
             "ocean_mask": (("lat", "lon"), view.ocean_mask),
             "surface_input_valid": (("lat", "lon"), view.surface_input_valid)},
            coords={"lat": view.lat, "lon": view.lon, "depth": view.depths},
            attrs={k: (v if isinstance(v, (str, int, float)) else json.dumps(v))
                   for k, v in p.items() if v is not None})
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        out.to_netcdf(path)
        print(f"\nwrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--field", action="store_true",
                    help="run replay_field() for --date and summarise it")
    ap.add_argument("--out", default=None, help="field mode: write NetCDF here")
    ap.add_argument("--json", default=None, help="point mode: write JSON here")
    ap.add_argument("--figure", nargs="?", const="auto", default=None,
                    help="point mode: save a profile figure")
    ap.add_argument("--force-recompute", action="store_true",
                    help="bypass the validated cache and run the model")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    eng = ReplayEngine(use_cache=not args.no_cache)

    try:
        if args.field:
            if not args.date:
                raise SystemExit("--field requires --date")
            return field_mode(eng, args)

        if args.lat is None or args.lon is None:
            raise SystemExit("point mode requires --lat and --lon")

        if args.start or args.end:
            if not (args.start and args.end):
                raise SystemExit("--start and --end must be given together")
            results = eng.replay_range(args.start, args.end, args.lat, args.lon,
                                       force_recompute=args.force_recompute)
            print(f"multi-date replay {args.start}..{args.end} at "
                  f"{args.lat} N {args.lon} E  ({len(results)} independent "
                  f"replay_field calls; no temporal state, no L3)")
            for r in results:
                v = next((x["prediction_c"] for x in r.profile
                          if x["depth_m"] == 100), None)
                a = next((x["anomaly_c"] for x in r.profile
                          if x["depth_m"] == 100), None)
                print(f"  {r.date}  100 m = "
                      f"{'n/a' if v is None else f'{v:7.3f}'} degC   anomaly "
                      f"{'n/a' if a is None else f'{a:+7.3f}'}   "
                      f"[{r.status['inference_source']}]")
            if args.json:
                Path(args.json).write_text(
                    json.dumps([r.as_dict() for r in results], indent=2),
                    encoding="utf-8")
                print(f"\nwrote {args.json}")
            return 0

        if not args.date:
            raise SystemExit("point mode requires --date")
        res = eng.replay_point(args.date, args.lat, args.lon,
                               force_recompute=args.force_recompute)
        print_profile(res)
        if args.json:
            Path(args.json).write_text(json.dumps(res.as_dict(), indent=2),
                                       encoding="utf-8")
            print(f"\nwrote {args.json}")
        if args.figure and res.profile:
            path = (REPO_ROOT / "outputs" / "figures" / "phase7"
                    / f"profile_{res.date}_{res.location.grid_lat:.2f}N"
                      f"_{res.location.grid_lon:.2f}E.png") \
                if args.figure == "auto" else Path(args.figure)
            save_figure(res, path)
        return 0
    except OutsideDomain as exc:
        print(f"OUTSIDE_DOMAIN: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
