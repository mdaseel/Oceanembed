"""Phase 7C — the three-stage D26 / TCHP discretization experiment.

Executes exactly the population frozen in
``outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md``:

    A  native reference   36 native GLORYS levels, horizontally regridded
    B  15-depth reference the same GLORYS field on the 15 mandated depths
    C  OceanEmbed         the frozen-L2 reconstruction on the same 15 depths

    A vs B = vertical discretization error
    B vs C = reconstruction contribution under identical 15-depth support
    A vs C = total end-to-end application error

Metrics are accumulated by streaming sums, so 216 dates x ~20k cells never has
to be held in memory at once.

    python scripts/diagnostics/run_d26_tchp_evaluation.py
    python scripts/diagnostics/run_d26_tchp_evaluation.py --limit 4   # smoke
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.data import loaders as L  # noqa: E402
from oceanembed.diagnostics import D26Status, ThermalResult, d26_tchp  # noqa: E402
from oceanembed.diagnostics.thermal import CP0, RHO0, RHO_CP  # noqa: E402
from oceanembed.ml.metrics import BASINS  # noqa: E402
from oceanembed.preprocessing.regrid import regrid_horizontal  # noqa: E402
from oceanembed.replay.contract import DEPTHS  # noqa: E402
from oceanembed.replay.engine import ReplayEngine  # noqa: E402

# ---- pre-registered population (protocol section 1.1) -----------------------
TEST_START = "2022-01-01"
TEST_END = "2024-12-15"
STRIDE_DAYS = 5

TABLES = ROOT / "outputs" / "tables"
PHASE7C = ROOT / "outputs" / "phase7c"


def protocol_dates() -> list[pd.Timestamp]:
    """Every 5th day from the first day of the locked test split."""
    all_days = pd.date_range(TEST_START, TEST_END, freq="D")
    return list(all_days[::STRIDE_DAYS])


class PairAccumulator:
    """Streaming MAE / RMSE / bias / correlation for one stage pair."""

    def __init__(self) -> None:
        self.n = 0
        self.sx = self.sy = self.sxx = self.syy = self.sxy = 0.0
        self.sae = self.sse = self.sde = 0.0

    def update(self, x: np.ndarray, y: np.ndarray) -> None:
        m = np.isfinite(x) & np.isfinite(y)
        if not m.any():
            return
        x, y = x[m].astype("float64"), y[m].astype("float64")
        d = x - y
        self.n += x.size
        self.sx += x.sum(); self.sy += y.sum()
        self.sxx += (x * x).sum(); self.syy += (y * y).sum()
        self.sxy += (x * y).sum()
        self.sae += np.abs(d).sum(); self.sse += (d * d).sum(); self.sde += d.sum()

    def result(self) -> dict:
        if self.n == 0:
            return {"n": 0, "mae": np.nan, "rmse": np.nan, "bias": np.nan,
                    "correlation": np.nan}
        n = self.n
        vx = n * self.sxx - self.sx ** 2
        vy = n * self.syy - self.sy ** 2
        cov = n * self.sxy - self.sx * self.sy
        corr = cov / np.sqrt(vx * vy) if vx > 0 and vy > 0 else np.nan
        return {"n": n, "mae": self.sae / n, "rmse": np.sqrt(self.sse / n),
                "bias": self.sde / n, "correlation": corr}


def region_masks(lat: np.ndarray, lon: np.ndarray) -> dict[str, np.ndarray]:
    """Whole NIO plus the FROZEN Phase 6B basin boxes, unchanged."""
    la = lat[:, None] * np.ones((1, lon.size))
    lo = np.ones((lat.size, 1)) * lon[None, :]
    out = {"whole_nio": np.ones((lat.size, lon.size), dtype=bool)}
    for name, box in BASINS.items():
        (s, n), (w, e) = box["lat"], box["lon"]
        out[name] = (la >= s) & (la <= n) & (lo >= w) & (lo <= e)
    return out


def native_stage(year_cache: dict, date: pd.Timestamp) -> tuple[np.ndarray, np.ndarray]:
    """Stage A: native 36-level GLORYS, horizontally regridded to canonical.

    Identical horizontal treatment to the frozen preprocessing; the ONLY thing
    stage A omits is the vertical reduction to 15 levels. That is what makes
    A vs B a clean measurement of vertical discretization.
    """
    year = date.year
    if year not in year_cache:
        year_cache[year] = L.load_glorys(f"data/raw/glorys/{year}/*.nc")
    gl = year_cache[year]
    day = gl["thetao"].sel(time=str(date.date())).squeeze().load()
    rg = regrid_horizontal(xr.Dataset({"t": day}), method="linear")["t"]
    levels = np.asarray(rg["depth"].values, dtype="float64")
    # (depth, lat, lon) -> (lat, lon, depth)
    return np.moveaxis(np.asarray(rg.values, dtype="float64"), 0, -1), levels


def reference_stage(store: xr.Dataset, t: int) -> np.ndarray:
    """Stage B: the frozen model-ready GLORYS target on the 15 mandated depths."""
    return np.stack([np.asarray(store[f"temp_{d}m"].isel(time=t).values,
                                dtype="float64") for d in DEPTHS], axis=-1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="evaluate only the first N pre-registered dates")
    args = ap.parse_args()

    dates = protocol_dates()
    if args.limit:
        dates = dates[:args.limit]
    print(f"pre-registered dates: {len(protocol_dates())}, evaluating {len(dates)}")

    TABLES.mkdir(parents=True, exist_ok=True)
    PHASE7C.mkdir(parents=True, exist_ok=True)

    engine = ReplayEngine()
    lat, lon = engine.lat, engine.lon
    regions = region_masks(lat, lon)

    pairs = [("A", "B"), ("B", "C"), ("A", "C")]
    acc = {(q, reg, var): PairAccumulator()
           for q in pairs for reg in regions for var in ("d26", "tchp")}
    status_counts = {s: {st.name: 0 for st in D26Status} for s in "ABC"}
    disagree = {q: {"both_ok": 0, "first_only": 0, "second_only": 0,
                    "neither": 0} for q in pairs}

    glorys_cache: dict[int, xr.Dataset] = {}
    store_cache: dict[int, xr.Dataset] = {}
    failures: list[dict] = []
    n_done = 0
    t_start = time.perf_counter()

    for date in dates:
        key = str(date.date())
        try:
            year = date.year
            if year not in store_cache:
                store_cache[year] = xr.open_zarr(
                    ROOT / "data" / "processed" / "model_ready" /
                    f"oceanembed_{year}.zarr", consolidated=True)
            store = store_cache[year]
            times = pd.DatetimeIndex(store.time.values).normalize()
            hit = np.flatnonzero(times == date)
            if not hit.size:
                failures.append({"date": key, "reason": "absent from model-ready store"})
                continue
            t = int(hit[0])

            ocean = np.asarray(store["ocean_mask"].isel(time=t).values, dtype=bool)
            siv = np.asarray(store["surface_input_valid"].isel(time=t).values,
                             dtype=bool)
            population = ocean & siv

            native, native_levels = native_stage(glorys_cache, date)
            res = {
                "A": d26_tchp(native, native_levels),
                "B": d26_tchp(reference_stage(store, t), DEPTHS),
                "C": d26_tchp(engine.replay_field(date).temperature, DEPTHS),
            }
        except Exception as exc:  # noqa: BLE001 - a failed date is reported, not hidden
            failures.append({"date": key, "reason": f"{type(exc).__name__}: {exc}"})
            continue

        for s, r in res.items():
            inside = r.status[population]
            for st in D26Status:
                status_counts[s][st.name] += int((inside == st).sum())

        for q in pairs:
            first, second = res[q[0]], res[q[1]]
            f_ok = first.d26_defined & population
            s_ok = second.d26_defined & population
            disagree[q]["both_ok"] += int((f_ok & s_ok).sum())
            disagree[q]["first_only"] += int((f_ok & ~s_ok).sum())
            disagree[q]["second_only"] += int((~f_ok & s_ok).sum())
            disagree[q]["neither"] += int((~f_ok & ~s_ok & population).sum())

            for reg, rmask in regions.items():
                use = rmask & population
                # D26 is compared only where BOTH stages resolved a crossing.
                d = use & first.d26_defined & second.d26_defined
                acc[(q, reg, "d26")].update(first.d26[d], second.d26[d])
                # TCHP additionally admits the whole-column-below-26 case,
                # where it is exactly zero rather than undefined.
                h = use & first.tchp_defined & second.tchp_defined
                acc[(q, reg, "tchp")].update(first.tchp[h], second.tchp[h])

        n_done += 1
        if n_done % 20 == 0 or n_done == len(dates):
            rate = (time.perf_counter() - t_start) / n_done
            print(f"  {n_done}/{len(dates)} dates  ({rate:.2f}s/date)")

    rows = []
    for (q, reg, var), a in acc.items():
        rows.append({"pair": f"{q[0]}_vs_{q[1]}", "quantity": var, "region": reg,
                     "unit": "m" if var == "d26" else "kJ/cm2", **a.result()})
    metrics = pd.DataFrame(rows).sort_values(
        ["quantity", "pair", "region"]).reset_index(drop=True)
    metrics.to_csv(TABLES / "phase7c_d26_tchp_metrics.csv", index=False)

    st_rows = [{"stage": s, **counts} for s, counts in status_counts.items()]
    pd.DataFrame(st_rows).to_csv(
        TABLES / "phase7c_d26_tchp_status_counts.csv", index=False)

    dis_rows = [{"pair": f"{q[0]}_vs_{q[1]}", **v} for q, v in disagree.items()]
    pd.DataFrame(dis_rows).to_csv(
        TABLES / "phase7c_d26_crossing_disagreement.csv", index=False)

    run = {
        "protocol": "outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md",
        "dates_preregistered": len(protocol_dates()),
        "dates_evaluated": n_done,
        "failed_dates": failures,
        "test_split": {"start": TEST_START, "end": TEST_END,
                       "stride_days": STRIDE_DAYS},
        "stages": {
            "A": "native GLORYS, 36 levels, regrid_horizontal(linear)",
            "B": "model_ready temp_<d>m, 15 mandated depths",
            "C": "replay_field(date).temperature, frozen L2",
        },
        "constants": {"rho0_kg_m3": RHO0, "cp0_J_kg_K": CP0,
                      "rho_cp_J_m3_K": RHO_CP,
                      "standard": "TEOS-10 (IOC/SCOR/IAPSO 2010)"},
        "basins": {k: v for k, v in BASINS.items()},
        "model": {
            "l2_state_dict_sha256": engine.l2_state_dict_sha256,
            "l2_encoder_sha256": engine.l2_encoder_sha256,
        },
        "argo_used": False,
        "argo_2024_status": "PROTECTED - not read by this phase",
        "wall_clock_seconds": round(time.perf_counter() - t_start, 1),
    }
    (PHASE7C / "evaluation_run.json").write_text(
        json.dumps(run, indent=2), encoding="utf-8")

    print(f"\n{len(failures)} failed dates")
    print(metrics.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
