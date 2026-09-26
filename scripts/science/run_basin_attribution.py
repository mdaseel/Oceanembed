"""Basin-level channel attribution sample (PREREGISTRATION §1 method, §N basin comparison).

For the 15th of every month of 2021 (validation year), 25 cells drawn uniformly
(seed 20260914) from supported cells inside each frozen basin box. Integrated
Gradients as in the Attribution tab. Reports the mean gross share per depth and
channel with its sample size. Descriptive only.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import pandas as pd

from oceanembed.config import REPO_ROOT
from oceanembed.ml.metrics import BASINS
from oceanembed.replay.engine import DEPTHS, ReplayEngine
from oceanembed.science import attribution, frozen
from oceanembed.science.channels import CHANNELS, SHORT

OUT = REPO_ROOT / "outputs" / "science" / "basin_attribution.json"
SEED = 20260914
PER_BASIN = 25


def main() -> int:
    t0 = time.time()
    engine = ReplayEngine()
    rng = np.random.default_rng(SEED)
    la, lo = np.meshgrid(engine.lat, engine.lon, indexing="ij")
    shares = {b: [] for b in BASINS}
    nets = {b: [] for b in BASINS}
    dates = [pd.Timestamp(f"2021-{m:02d}-15") for m in range(1, 13)]
    for day in dates:
        field, siv, when = frozen.historical_inputs(engine, day)
        for basin, box in BASINS.items():
            sel = siv & (la >= box["lat"][0]) & (la <= box["lat"][1]) \
                & (lo >= box["lon"][0]) & (lo <= box["lon"][1])
            cells = np.argwhere(sel)
            pick = cells[rng.choice(len(cells), size=min(PER_BASIN, len(cells)), replace=False)]
            for r, c in pick:
                res = attribution.attribute_cell(engine, field, siv, when, int(r), int(c),
                                                 use_cache=False)
                shares[basin].append(np.array(res["gross_share"]))
                nets[basin].append(np.array(res["net_c"]))
        print(f"  {day.date()} ({time.time() - t0:.0f}s)", flush=True)
    out = {"method": attribution.METHOD, "steps": attribution.STEPS,
           "baseline": attribution.BASELINE, "seed": SEED,
           "dates": [str(d.date()) for d in dates], "cells_per_basin_per_date": PER_BASIN,
           "depths_m": list(DEPTHS), "channels": list(CHANNELS),
           "channel_short": [SHORT[c] for c in CHANNELS],
           "model_sha256": engine.l2_state_dict_sha256,
           "wording": attribution.WORDING, "basins": {}}
    for basin in BASINS:
        s = np.stack(shares[basin])
        n = np.stack(nets[basin])
        out["basins"][basin] = {"n_cells": int(s.shape[0]),
                                "mean_gross_share": np.round(s.mean(0), 4).tolist(),
                                "mean_net_c": np.round(n.mean(0), 4).tolist()}
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    for basin in BASINS:
        m = np.array(out["basins"][basin]["mean_gross_share"])
        for k in (0, 7, 11):
            print(basin, DEPTHS[k], dict(zip(out["channel_short"], np.round(m[k], 3))))
    print(f"done ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
