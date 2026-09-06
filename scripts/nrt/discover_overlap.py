"""STEP 6 - discover the valid overlap window INDEPENDENTLY for every pair.

No universal overlap is assumed. Each reference/NRT pair is intersected on its
own, and the intersection is further restricted to the reference data actually
held locally (the frozen model-ready archive), because a reference day that was
never harmonised cannot be compared against anything.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import xarray as xr

from oceanembed.config import REPO_ROOT
from oceanembed.nrt.registry import PAIRS, PRODUCTS

MR = REPO_ROOT / "data" / "processed" / "model_ready"


def local_reference_range():
    zs = sorted(MR.glob("oceanembed_*.zarr"))
    lo = hi = None
    for z in zs:
        with xr.open_zarr(z) as d:
            t = pd.to_datetime(d.time.values)
            lo = t.min() if lo is None else min(lo, t.min())
            hi = t.max() if hi is None else max(hi, t.max())
    return lo, hi, [z.name for z in zs]


def parse(s):
    try:
        return pd.Timestamp(s)
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    lo, hi, zs = local_reference_range()
    print(f"local harmonised reference archive: {lo.date()} .. {hi.date()} "
          f"({len(zs)} stores)")

    pairs = {}
    for name, (rk, nk) in PAIRS.items():
        r, n = PRODUCTS[rk], PRODUCTS[nk]
        rs, re = parse(r["temporal_extent"][0]), parse(r["temporal_extent"][1])
        ns, ne = parse(n["temporal_extent"][0]), parse(n["temporal_extent"][1])
        # A reference extent that could not be parsed ("~2025") is treated as
        # unknown and the LOCAL archive bound is used instead - never guessed.
        cat_re = re if re is not None else None
        start = max(x for x in [rs, ns, lo] if x is not None)
        ends = [x for x in [cat_re, ne, hi] if x is not None]
        end = min(ends)
        n_days = int((end - start).days) + 1
        pairs[name] = {
            "reference_key": rk, "nrt_key": nk,
            "reference_catalogue_extent": r["temporal_extent"],
            "nrt_catalogue_extent": n["temporal_extent"],
            "reference_extent_end_parsed": str(cat_re.date()) if cat_re is not None else None,
            "local_reference_archive": [str(lo.date()), str(hi.date())],
            "overlap_start": str(start.date()), "overlap_end": str(end.date()),
            "overlap_days": n_days,
            "binding_lower_constraint": (
                "nrt_product_start" if start == ns else
                "reference_product_start" if start == rs else "local_archive_start"),
            "binding_upper_constraint": (
                "local_archive_end" if end == hi else
                "nrt_product_end" if end == ne else "reference_product_end"),
        }
        print(f"  {name:10s} {pairs[name]['overlap_start']} .. "
              f"{pairs[name]['overlap_end']}  ({n_days:4d} d)  "
              f"lower={pairs[name]['binding_lower_constraint']}  "
              f"upper={pairs[name]['binding_upper_constraint']}")

    common_start = max(pd.Timestamp(v["overlap_start"]) for v in pairs.values())
    common_end = min(pd.Timestamp(v["overlap_end"]) for v in pairs.values())
    print(f"\nintersection of ALL pairs: {common_start.date()} .. {common_end.date()} "
          f"({(common_end - common_start).days + 1} d)")

    out = REPO_ROOT / "outputs" / "nrt"
    out.mkdir(parents=True, exist_ok=True)
    doc = {
        "generated": str(pd.Timestamp.utcnow().tz_localize(None)),
        "method": "per-pair intersection of reference catalogue extent, NRT "
                  "catalogue extent, and the locally held harmonised reference "
                  "archive; no universal window assumed",
        "local_reference_archive": {"start": str(lo.date()), "end": str(hi.date()),
                                    "stores": zs},
        "pairs": pairs,
        "all_pair_intersection": {
            "start": str(common_start.date()), "end": str(common_end.date()),
            "days": int((common_end - common_start).days) + 1,
            "note": "used ONLY for the whole-stack substitution experiment, where "
                    "every channel must be swapped on the same day; per-channel "
                    "comparisons use their own per-pair windows"},
        "caveat": "Overlap here is CATALOGUE overlap measured today. It says "
                  "nothing about whether a product was retrievable on the "
                  "original date; that is what the prospective latency log "
                  "measures separately.",
    }
    json.dump(doc, open(out / "overlap_manifest.json", "w"), indent=2)
    print(f"\n-> {out / 'overlap_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
