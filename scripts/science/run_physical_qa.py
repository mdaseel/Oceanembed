"""Physical plausibility QA + basin physics comparison (PREREGISTRATION §4, §N).

Reconstruction vs GLORYS target on identical support, every 7th day of 2021 and
2023 (2024 excluded), plus the 2022-2023 Argo collocation already on disk
(observed vs collocated L2). Writes small JSON summaries under outputs/science/.
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
from oceanembed.diagnostics.bathymetry import local_water_depth
from oceanembed.diagnostics.thermal import d26_tchp
from oceanembed.ml.metrics import BASINS
from oceanembed.replay.engine import DEPTHS, ReplayEngine
from oceanembed.science import frozen
from oceanembed.science.physical_qa import (BANDS, INVERSION_TOL_C, RULE, STRONG_INVERSION_C,
                                           band_of_pair, profile_diagnostics, usable_levels)

OUT = REPO_ROOT / "outputs" / "science"
QS = np.linspace(0, 100, 101)


_TARGETS: dict = {}


def target_store(year: int):
    """GLORYS reference variables only, for comparison - never for inference."""
    import xarray as xr
    if year not in _TARGETS:
        ds = xr.open_zarr(REPO_ROOT / "data" / "processed" / "model_ready" / f"oceanembed_{year}.zarr",
                          consolidated=True)
        keep = [v for v in ds.data_vars if v.startswith(("temp_", "target_valid_"))]
        _TARGETS[year] = ds[keep]
    return _TARGETS[year]


def dates() -> list[pd.Timestamp]:
    out = []
    for year in (2021, 2023):
        out += list(pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="7D"))
    assert all(d.year != 2024 for d in out)
    return out


def region_masks(lat, lon):
    la, lo = np.meshgrid(lat, lon, indexing="ij")
    masks = {"nio": np.ones_like(la, dtype=bool)}
    for name, b in BASINS.items():
        masks[name] = ((la >= b["lat"][0]) & (la <= b["lat"][1])
                       & (lo >= b["lon"][0]) & (lo <= b["lon"][1]))
    return masks


def summarise(diag, pair_bands, regions_flat):
    out = {}
    for region, sel in regions_flat.items():
        n_prof = int(sel.sum())
        pv, inv, strong = diag["pair_valid"][sel], diag["inversion"][sel], diag["strong_inversion"][sel]
        sg = diag["strongest_gradient"][sel]
        sg = sg[np.isfinite(sg)]
        bands = {}
        for band in BANDS:
            cols = [i for i, b in enumerate(pair_bands) if b == band]
            n = int(pv[:, cols].sum())
            bands[band] = {"pairs": n,
                           "inversion_frequency": None if n == 0 else round(float(inv[:, cols].sum() / n), 5),
                           "strong_inversion_frequency": None if n == 0 else round(float(strong[:, cols].sum() / n), 6)}
        per_pair = []
        for i, b in enumerate(pair_bands):
            n = int(pv[:, i].sum())
            per_pair.append({"from_m": DEPTHS[i], "to_m": DEPTHS[i + 1], "pairs": n,
                             "inversion_frequency": None if n == 0 else round(float(inv[:, i].sum() / n), 5)})
        out[region] = {
            "profiles": n_prof,
            "profiles_with_inversion": round(float((diag["inversion_count"][sel] > 0).mean()), 5) if n_prof else None,
            "bands": bands, "per_pair": per_pair,
            "strongest_gradient_quantiles": [round(float(x), 6) for x in np.percentile(sg, QS)] if sg.size else [],
        }
    return out


def main() -> int:
    t0 = time.time()
    engine = ReplayEngine()
    water = local_water_depth(strict=True)
    lat, lon = engine.lat, engine.lon
    regions = region_masks(lat, lon)
    pair_bands = band_of_pair(DEPTHS)
    stack = {"L2": [], "GLORYS": []}
    regions_stack = {k: [] for k in regions}
    tchp = {"L2": {k: [] for k in regions}, "GLORYS": {k: [] for k in regions}}
    d26 = {"L2": {k: [] for k in regions}, "GLORYS": {k: [] for k in regions}}
    anomaly = {k: {50: [], 100: []} for k in regions}
    mean_prof = {m: {k: [] for k in regions} for m in ("L2", "GLORYS")}

    for day in dates():
        field, siv, when = frozen.historical_inputs(engine, day)
        rec = frozen.forward_field(engine, field, siv, when)
        # The engine's store deliberately exposes surface inputs only. The GLORYS
        # reference is read from a separate handle and never reaches inference.
        ts_ = target_store(when.year)
        t = int(np.flatnonzero(pd.DatetimeIndex(ts_.time.values).normalize() == when)[0])
        target = np.stack([ts_[f"temp_{d}m"].isel(time=t).values for d in DEPTHS], axis=-1)
        tvalid = np.stack([ts_[f"target_valid_{d}m"].isel(time=t).values for d in DEPTHS], axis=-1)
        target = np.where(tvalid.astype(bool), target, np.nan)
        clim = np.moveaxis(engine.climatology.predict(pd.DatetimeIndex([when]))[0], 0, -1)
        common = siv[..., None] & np.isfinite(rec) & np.isfinite(target)
        rec_c = np.where(common, rec, np.nan)
        tgt_c = np.where(common, target, np.nan)
        use = usable_levels(rec_c, DEPTHS, water) & usable_levels(tgt_c, DEPTHS, water)
        cells = use[..., 0] & use[..., 1]
        for name, arr in (("L2", rec_c), ("GLORYS", tgt_c)):
            stack[name].append((arr[cells], use[cells]))
            th = d26_tchp(np.where(use, arr, np.nan), DEPTHS)
            ok_t = th.tchp_defined & np.isfinite(th.tchp)
            ok_d = np.isfinite(th.d26) & (th.d26 <= water)
            for region, sel in regions.items():
                m = cells & sel
                tchp[name][region].append(th.tchp[m & ok_t])
                d26[name][region].append(th.d26[m & ok_d])
                mean_prof[name][region].append(np.nanmean(np.where(use, arr, np.nan)[m], axis=0))
        for region, sel in regions.items():
            regions_stack[region].append(sel[cells])
            for dep in (50, 100):
                k = DEPTHS.index(dep)
                a = (rec - clim)[..., k][cells & sel & use[..., k]]
                anomaly[region][dep].append(a[np.isfinite(a)])
    print(f"reconstructed + read {len(dates())} dates ({time.time() - t0:.0f}s)", flush=True)

    reg_flat = {k: np.concatenate(v) for k, v in regions_stack.items()}
    summaries, diags = {}, {}
    for name in ("L2", "GLORYS"):
        T = np.concatenate([a for a, _ in stack[name]])
        U = np.concatenate([u for _, u in stack[name]])
        diags[name] = profile_diagnostics(T, DEPTHS, U)
        summaries[name] = summarise(diags[name], pair_bands, reg_flat)

    envelope = {}
    for region, sel in reg_flat.items():
        ref = diags["GLORYS"]["strongest_gradient"][sel]
        rec = diags["L2"]["strongest_gradient"][sel]
        ok = np.isfinite(ref) & np.isfinite(rec)
        p1, p99 = np.percentile(ref[ok], [1, 99])
        envelope[region] = {
            "reference_p1": round(float(p1), 6), "reference_p99": round(float(p99), 6),
            "fraction_within_reference_envelope": round(float(((rec[ok] >= p1) & (rec[ok] <= p99)).mean()), 5),
            "fraction_steeper_than_reference_p1": round(float((rec[ok] < p1).mean()), 5),
            "reference_fraction_steeper_than_p1": round(float((ref[ok] < p1).mean()), 5),
            "profiles": int(ok.sum())}

    argo = argo_comparison()
    result = {
        "protocol": "outputs/science/PREREGISTRATION.md §4",
        "rule": RULE, "inversion_tolerance_c": INVERSION_TOL_C,
        "strong_inversion_c": STRONG_INVERSION_C,
        "dates": {"n": len(dates()), "first": str(dates()[0].date()), "last": str(dates()[-1].date()),
                  "rule": "every 7th day of 2021 and of 2023; 2024 excluded"},
        "support": "surface input valid, finite in reconstruction and GLORYS, and within the ETOPO "
                   "water column, contiguously from the top; identical support for both",
        "reconstruction": summaries["L2"], "reference_glorys": summaries["GLORYS"],
        "gradient_envelope": envelope, "argo": argo,
        "model_sha256": engine.l2_state_dict_sha256,
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "no_single_score": True,
    }
    (OUT / "physical_qa_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    def q(values, qs=(5, 25, 50, 75, 95)):
        v = np.concatenate(values) if values else np.array([])
        v = v[np.isfinite(v)]
        return {"n": int(v.size), **{f"p{p}": round(float(np.percentile(v, p)), 3) for p in qs}} if v.size else {"n": 0}

    basin = {
        "protocol": "outputs/science/PREREGISTRATION.md §4 (same dates and support)",
        "regions": {}, "argo_skill": argo_skill(), "attribution": None,
        "caveat": ("Differences are descriptive. Where they match known regime contrasts (for "
                   "example stronger near-surface stratification in the Bay of Bengal) they are "
                   "described as consistent with those regimes; OceanEmbed does not diagnose "
                   "barrier-layer thickness."),
    }
    for region in regions:
        basin["regions"][region] = {
            "mean_profile_l2_c": [round(float(x), 3) for x in np.nanmean(np.stack(mean_prof["L2"][region]), axis=0)],
            "mean_profile_glorys_c": [round(float(x), 3) for x in np.nanmean(np.stack(mean_prof["GLORYS"][region]), axis=0)],
            "tchp_l2": q(tchp["L2"][region]), "tchp_glorys": q(tchp["GLORYS"][region]),
            "d26_l2": q(d26["L2"][region]), "d26_glorys": q(d26["GLORYS"][region]),
            "anomaly_50m_l2": q(anomaly[region][50]), "anomaly_100m_l2": q(anomaly[region][100]),
            "inversion_frequency_l2": summaries["L2"][region]["bands"],
            "inversion_frequency_glorys": summaries["GLORYS"][region]["bands"],
            "gradient_envelope": envelope[region],
        }
    basin["depths_m"] = DEPTHS
    (OUT / "basin_physics.json").write_text(json.dumps(basin, indent=2), encoding="utf-8")
    print(json.dumps({r: summaries["L2"][r]["bands"] for r in regions}, indent=1))
    print(json.dumps(envelope, indent=1))
    print(f"done ({time.time() - t0:.0f}s)")
    return 0


def argo_comparison() -> dict:
    """Inversions in observed Argo vs collocated L2 on levels where both are finite."""
    df = pd.read_parquet(REPO_ROOT / "outputs" / "argo" / "matched_profiles.parquet")
    assert pd.to_datetime(df["date"]).max() < pd.Timestamp("2024-01-01"), "HOLDOUT LEAK"
    levels = [d for d in DEPTHS if f"argo_pt_{d}m" in df and f"L2_{d}m" in df]
    obs = df[[f"argo_pt_{d}m" for d in levels]].to_numpy("float64")
    l2 = df[[f"L2_{d}m" for d in levels]].to_numpy("float64")
    both = np.isfinite(obs) & np.isfinite(l2)
    use = np.cumprod(both, axis=1).astype(bool)
    out = {"levels_m": levels, "profiles": int(len(df)),
           "period": "2022-01-01..2023-12-31 (2024 protected)"}
    for name, arr in (("argo_observed", obs), ("l2_collocated", l2)):
        d = profile_diagnostics(arr, levels, use)
        n = int(d["pair_valid"].sum())
        sg = d["strongest_gradient"][np.isfinite(d["strongest_gradient"])]
        out[name] = {"pairs": n,
                     "inversion_frequency": round(float(d["inversion"].sum() / n), 5) if n else None,
                     "strong_inversion_frequency": round(float(d["strong_inversion"].sum() / n), 6) if n else None,
                     "profiles_with_inversion": round(float((d["inversion_count"] > 0).mean()), 5),
                     "strongest_gradient_median": round(float(np.median(sg)), 5) if sg.size else None}
    return out


def argo_skill() -> dict:
    t = pd.read_csv(REPO_ROOT / "outputs" / "tables" / "phase6c_argo_basin_summary.csv")
    out = {}
    for basin in BASINS:
        rows = t[(t.basin == basin) & (t.model.isin(["L0", "L2"])) & (t.depth_m.isin([50, 75, 100, 150]))]
        out[basin] = [{"depth_m": int(r.depth_m), "model": r.model, "n": int(r.n),
                       "rmse_c": round(float(r.rmse), 3)} for _, r in rows.iterrows()]
    return out


if __name__ == "__main__":
    raise SystemExit(main())
