"""Phase 8B: acquire the MULTIOBS NRT SSS candidate over the 6C-D window.

Same 1 degree download pad and box as the training acquisition and Phase 6C-D,
same window (2024-07-01 .. 2024-12-15). Harmonised with
``nrt.harmonize.harmonise_multiobs_sss``, which mirrors the training SSS loader.
Downloaded AFTER the Phase 8B protocol was frozen (commit 5b69dda).

Authentication is delegated to the configured Copernicus Marine client; this
script never reads, prints or stores a credential.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

from oceanembed.config import EAST, NORTH, REPO_ROOT, SOUTH, WEST  # noqa: E402
from oceanembed.nrt.harmonize import harmonise_multiobs_sss  # noqa: E402
from oceanembed.nrt.registry import PRODUCTS  # noqa: E402

KEY = "sss_nrt_multiobs"
PAD = 1.0
BOX = dict(minimum_longitude=WEST - PAD, maximum_longitude=EAST + PAD,
           minimum_latitude=SOUTH - PAD, maximum_latitude=NORTH + PAD)
START, END = "2024-07-01", "2024-12-15"
RAW = REPO_ROOT / "data" / "raw" / "nrt" / KEY
CANON = REPO_ROOT / "data" / "processed" / "nrt" / f"{KEY}_canonical.nc"
MANIFEST = REPO_ROOT / "outputs" / "phase8b" / "fetch_manifest.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    import copernicusmarine as cm

    p = PRODUCTS[KEY]
    RAW.mkdir(parents=True, exist_ok=True)
    dst = RAW / f"{KEY}_{START}_{END}.nc"
    t0 = time.time()
    if not (dst.exists() and dst.stat().st_size > 0):
        tmp = f"{KEY}.part.nc"
        cm.subset(dataset_id=p["dataset_id"], variables=["sos"],
                  output_directory=str(RAW), output_filename=tmp,
                  file_format="netcdf", overwrite=True, disable_progress_bar=True,
                  start_datetime=f"{START}T00:00:00", end_datetime=f"{END}T23:59:59",
                  **BOX)
        (RAW / tmp).replace(dst)
    print(f"[{KEY}] raw {dst.stat().st_size / 1e6:.1f} MB ({time.time() - t0:.0f}s)")

    with xr.open_dataset(dst) as ds:
        canon = harmonise_multiobs_sss(ds.load())
    CANON.parent.mkdir(parents=True, exist_ok=True)
    canon.to_netcdf(CANON)
    times = pd.DatetimeIndex(canon.time.values)
    print(f"[{KEY}] canonical {dict(canon.sizes)}  {times[0].date()}..{times[-1].date()}")

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "product_key": KEY,
        "product_id": p["product_id"],
        "dataset_id": p["dataset_id"],
        "doi": p["doi"],
        "window": [START, END],
        "download_pad_deg": PAD,
        "box": BOX,
        "raw_file": str(dst.relative_to(REPO_ROOT)).replace("\\", "/"),
        "raw_bytes": dst.stat().st_size,
        "raw_sha256": sha256(dst),
        "canonical_file": str(CANON.relative_to(REPO_ROOT)).replace("\\", "/"),
        "canonical_n_times": int(times.size),
        "canonical_first": str(times[0].date()),
        "canonical_last": str(times[-1].date()),
        "harmonisation": "nrt.harmonize.harmonise_multiobs_sss (sos -> sss, PSU, "
                         "no conversion, singleton depth dropped, training regrid)",
        "replay_mode": "RETROSPECTIVE",
        "note": "pulled from today's archive state; says nothing about what was "
                "retrievable on the original date",
        "downloaded_after_protocol_commit": "5b69dda",
        "credentials_handled_by_this_script": False,
    }, open(MANIFEST, "w"), indent=2)
    print(f"manifest -> {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
