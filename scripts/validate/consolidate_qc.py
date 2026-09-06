"""Consolidate multi-year QC and classify the GLORYS suspicious values.

Two jobs the Phase 6A.5 report depends on:

1. Homogeneity. A 10-year record assembled from year-chunked files is NOT
   automatically homogeneous just because the files share a product name.
   This looks for year-to-year discontinuities in each variable's mean and
   missingness that are large relative to the record's own variability.

2. Classify the suspicious GLORYS target values. Phase 6A found a handful of
   negative temperatures at a Gulf of Aden shelf-break cell. Over the full
   record, are such values isolated boundary artifacts, persistent cells,
   provider fill leakage, or something reproducible? Nothing is removed here.

Run:  PYTHONPATH=src python scripts/validate/consolidate_qc.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from oceanembed.config import REPO_ROOT  # noqa: E402

TAB = REPO_ROOT / "outputs" / "tables"
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)

# A year-on-year step larger than this many robust sigma is worth reporting.
STEP_SIGMA = 4.0


def homogeneity(df: pd.DataFrame) -> pd.DataFrame:
    """Flag year-to-year steps that are large relative to the record itself."""
    rows = []
    fields = df[df["kind"] == "field"] if "kind" in df.columns else df
    for v, g in fields.groupby("variable"):
        g = g.sort_values("year")
        if len(g) < 3:
            continue
        for col in ("mean", "pct_missing"):
            s = g[col].to_numpy(dtype="float64")
            d = np.diff(s)
            # robust scale: MAD of the year-on-year differences
            mad = np.median(np.abs(d - np.median(d)))
            sigma = 1.4826 * mad if mad > 0 else (np.std(d) or np.nan)
            if not np.isfinite(sigma) or sigma == 0:
                continue
            z = np.abs(d - np.median(d)) / sigma
            for i, zz in enumerate(z):
                if zz >= STEP_SIGMA:
                    rows.append({
                        "variable": v, "metric": col,
                        "from_year": int(g.year.iloc[i]), "to_year": int(g.year.iloc[i + 1]),
                        "from_value": float(s[i]), "to_value": float(s[i + 1]),
                        "step": float(d[i]), "robust_sigma": float(sigma),
                        "n_sigma": float(zz),
                    })
    return pd.DataFrame(rows)


def classify_suspicious(df: pd.DataFrame) -> pd.DataFrame:
    """Characterise each offending grid cell over the whole record."""
    if df.empty:
        return df
    n_years = df.year.nunique()
    out = []
    for (la, lo), g in df.groupby(["lat", "lon"]):
        depths = sorted(g.depth_m.unique())
        yrs = sorted(g.year.unique())
        n_dates = g.date.nunique()
        below = int((g.reason == "below_plausible").sum())
        above = int((g.reason == "above_plausible").sum())
        # near-zero values are the signature of a provider fill leak
        near_zero = int((g.value_degC.abs() < 0.01).sum())

        if near_zero > 0:
            kind = "provider fill leakage (values pinned near 0.0)"
        elif len(yrs) >= max(3, 0.5 * n_years) and n_dates > 30:
            kind = "persistent cell (recurs across many years and dates)"
        elif below and min(depths) >= 200:
            kind = "isolated deep boundary artifact"
        elif above and max(depths) <= 10:
            kind = "shallow warm extreme - likely REAL (check basin)"
        else:
            kind = "isolated / episodic"

        out.append({
            "lat": la, "lon": lo,
            "n_values": len(g), "n_distinct_dates": n_dates,
            "years": ",".join(str(y) for y in yrs),
            "n_years": len(yrs),
            "depths_m": ",".join(str(int(d)) for d in depths),
            "min_degC": float(g.value_degC.min()), "max_degC": float(g.value_degC.max()),
            "n_below_plausible": below, "n_above_plausible": above,
            "n_near_zero": near_zero,
            "classification": kind,
        })
    return pd.DataFrame(out).sort_values("n_values", ascending=False)


def main() -> int:
    qc_path = TAB / "multiyear_qc_by_year.csv"
    if not qc_path.exists():
        print(f"missing {qc_path} - build years first")
        return 1
    qc = pd.read_csv(qc_path)
    years = sorted(qc.year.unique())
    print(f"QC covers {len(years)} year(s): {years[0]}..{years[-1]}")

    fields = qc[qc["kind"] == "field"]
    print("\n=== missingness by variable (min/median/max across years) ===")
    m = fields.groupby("variable")["pct_missing"].agg(["min", "median", "max"]).round(2)
    print(m.to_string())

    print("\n=== value ranges across the record ===")
    r = fields.groupby("variable").agg(min=("min", "min"), max=("max", "max"),
                                       mean=("mean", "mean")).round(3)
    print(r.to_string())

    print("\n=== calendar completeness ===")
    cal = qc.groupby("year").agg(days=("n_days", "max"),
                                 missing_days=("n_missing_days", "max"),
                                 dup_timestamps=("duplicate_timestamps", "max"))
    print(cal.to_string())

    h = homogeneity(qc)
    h.to_csv(TAB / "multiyear_homogeneity_flags.csv", index=False)
    print(f"\n=== homogeneity: {len(h)} year-to-year step(s) >= {STEP_SIGMA} sigma ===")
    print(h.to_string(index=False) if len(h) else "  none - record looks homogeneous")

    sus_path = TAB / "glorys_suspicious_values.csv"
    sus = pd.read_csv(sus_path) if sus_path.exists() else pd.DataFrame()
    print(f"\n=== GLORYS suspicious values: {len(sus)} across {len(years)} year(s) ===")
    cls = classify_suspicious(sus)
    if len(cls):
        cls.to_csv(TAB / "glorys_suspicious_classified.csv", index=False)
        print(cls.to_string(index=False))
        print(f"\nwrote {TAB / 'glorys_suspicious_classified.csv'}")
    else:
        print("  none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
