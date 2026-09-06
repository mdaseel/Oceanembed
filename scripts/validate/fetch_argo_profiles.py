"""Fetch Argo per-float profile files for the 2022-2023 observational audit.

One file per float (``<wmo>_prof.nc`` holds every cycle), not one per profile:
6,598 matching profiles come from only 108 floats.

The 2024 period is a declared observational holdout and is refused here.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import requests

from oceanembed.config import REPO_ROOT

GDAC = "https://data-argo.ifremer.fr/dac"
RAW = REPO_ROOT / "data" / "raw" / "argo_gdac" / "floats"
OUT = REPO_ROOT / "outputs" / "argo"

AUDIT_START, AUDIT_END = "2022-01-01", "2023-12-31"
HELDOUT_START = "2024-01-01"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=str(OUT / "index_audit_2022_2023.csv"))
    ap.add_argument("--allow-heldout", action="store_true")
    args = ap.parse_args()

    idx = pd.read_csv(args.index)
    idx["dt"] = pd.to_datetime(idx["dt"])
    if not args.allow_heldout and (idx.dt >= HELDOUT_START).any():
        raise SystemExit("Index contains 2024 profiles, which are a declared "
                         "observational holdout. Refusing.")
    assert idx.dt.min() >= pd.Timestamp(AUDIT_START)
    assert idx.dt.max() <= pd.Timestamp(AUDIT_END) + pd.Timedelta(days=1)

    RAW.mkdir(parents=True, exist_ok=True)
    floats = idx[["dac", "wmo"]].drop_duplicates().sort_values(["dac", "wmo"])
    print(f"audit window {AUDIT_START}..{AUDIT_END}: {len(idx):,} profiles, "
          f"{len(floats)} floats")

    # Downloads are network-bound and independent, so they run in parallel.
    # Each writes to .part and renames, so an interrupted run leaves no
    # half-file that a later run would mistake for complete.
    local = threading.local()

    def session():
        if not hasattr(local, "s"):
            local.s = requests.Session()
        return local.s

    def fetch(dac, wmo):
        dst = RAW / f"{wmo}_prof.nc"
        url = f"{GDAC}/{dac}/{wmo}/{wmo}_prof.nc"
        if dst.exists() and dst.stat().st_size > 0:
            return {"wmo": wmo, "dac": dac, "url": url,
                    "bytes": dst.stat().st_size, "status": "cached"}
        try:
            with session().get(url, stream=True, timeout=600) as r:
                r.raise_for_status()
                tmp = dst.with_suffix(".part")
                with open(tmp, "wb") as f:
                    for ch in r.iter_content(1 << 20):
                        f.write(ch)
                tmp.replace(dst)
            return {"wmo": wmo, "dac": dac, "url": url,
                    "bytes": dst.stat().st_size, "status": "downloaded"}
        except Exception as exc:  # noqa: BLE001
            return {"wmo": wmo, "dac": dac, "url": url, "bytes": 0,
                    "status": f"failed: {type(exc).__name__}: {exc}"}

    manifest, ok, fail, skip = [], 0, 0, 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(fetch, row.dac, str(row.wmo)) for _, row in floats.iterrows()]
        for n, fut in enumerate(as_completed(futs), 1):
            m = fut.result()
            manifest.append(m)
            if m["status"] == "downloaded":
                ok += 1
            elif m["status"] == "cached":
                skip += 1
            else:
                fail += 1
                print(f"  FAIL {m['wmo']}: {m['status']}")
            if n % 20 == 0:
                print(f"  {n}/{len(floats)} floats  ({time.time()-t0:.0f}s)", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    json.dump({"source": GDAC,
               "index_file": "ar_index_global_prof.txt.gz",
               "audit_window": [AUDIT_START, AUDIT_END],
               "heldout_period_not_fetched": [HELDOUT_START, "2024-12-15"],
               "n_profiles_in_index": int(len(idx)),
               "n_floats": int(len(floats)),
               "downloaded": ok, "cached": skip, "failed": fail,
               "files": manifest},
              open(OUT / "download_manifest.json", "w"), indent=2)
    print(f"\ndownloaded={ok} cached={skip} failed={fail} in {(time.time()-t0)/60:.1f} min")
    print(f"manifest -> {OUT / 'download_manifest.json'}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
