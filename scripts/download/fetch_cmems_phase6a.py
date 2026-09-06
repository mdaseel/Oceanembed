"""Download ONLY the Phase 6A gaps from Copernicus Marine.

Three datasets are missing from the supplied archives (see
outputs/data_inventory.md conflicts C2/C3/C4):

  1. OSTIA SST          - PS-mandated SST product (archive supplied AVHRR-OI)
  2. DUACS SLA          - PS-mandated sea-level channel, absent entirely
  3. GLORYS multi-depth - archive supplied ONLY the 0.494 m surface level

Every dataset id and DOI below was verified against the live Copernicus Marine
catalogue (`copernicusmarine.describe`) on 2026-09-04. Nothing is invented.

Scope is deliberately tiny: 2 days, one 27 x 62 degree box, one variable each.

Requires `copernicusmarine login` to have been run once (credentials are read
from ~/.copernicusmarine/). This script never prints or stores credentials.
"""
from __future__ import annotations

import sys
from pathlib import Path

import copernicusmarine as cm

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from oceanembed.config import EAST, NORTH, REPO_ROOT, SOUTH, TEST_END, TEST_START, WEST  # noqa: E402

# Pad the request box by 1 degree so horizontal interpolation onto the canonical
# grid has real neighbours at the domain edge instead of extrapolating.
PAD = 1.0
BOX = dict(
    minimum_longitude=WEST - PAD,
    maximum_longitude=EAST + PAD,
    minimum_latitude=SOUTH - PAD,
    maximum_latitude=NORTH + PAD,
)
TIME = dict(start_datetime=f"{TEST_START}T00:00:00", end_datetime=f"{TEST_END}T23:59:59")

RAW = REPO_ROOT / "data" / "raw"

JOBS = [
    dict(
        label="OSTIA SST (PS-mandated, DOI 10.48670/moi-00168)",
        dataset_id="METOFFICE-GLO-SST-L4-REP-OBS-SST",
        variables=["analysed_sst"],
        output_directory=RAW / "ostia",
        output_filename="ostia_sst_20200101_20200102.nc",
        extra={},
    ),
    dict(
        label="DUACS SLA (PS-mandated, DOI 10.48670/moi-00145)",
        dataset_id="c3s_obs-sl_glo_phy-ssh_my_twosat-l4-duacs-0.25deg_P1D",
        variables=["sla"],
        output_directory=RAW / "duacs",
        output_filename="duacs_sla_20200101_20200102.nc",
        extra={},
    ),
    dict(
        # 0..1200 m brackets every debug depth including 1000 m (GLORYS native
        # levels straddle it at roughly 902 m and 1046 m).
        label="GLORYS12V1 thetao, full depth 0-1200 m (DOI 10.48670/moi-00021)",
        dataset_id="cmems_mod_glo_phy_my_0.083deg_P1D-m",
        variables=["thetao"],
        output_directory=RAW / "glorys",
        output_filename="glorys_thetao_0_1200m_20200101_20200102.nc",
        extra=dict(minimum_depth=0.0, maximum_depth=1200.0),
    ),
]


def main() -> int:
    failures = []
    for job in JOBS:
        out = Path(job["output_directory"]) / job["output_filename"]
        print("=" * 74)
        print(job["label"])
        print(f"  dataset_id : {job['dataset_id']}")
        print(f"  variables  : {job['variables']}")
        print(f"  time       : {TIME['start_datetime']} .. {TIME['end_datetime']}")
        print(f"  box        : lat {BOX['minimum_latitude']}..{BOX['maximum_latitude']}, "
              f"lon {BOX['minimum_longitude']}..{BOX['maximum_longitude']}")
        print(f"  -> {out}")
        if out.exists():
            print("  SKIP (already downloaded)")
            continue
        Path(job["output_directory"]).mkdir(parents=True, exist_ok=True)
        try:
            cm.subset(
                dataset_id=job["dataset_id"],
                variables=job["variables"],
                output_directory=str(job["output_directory"]),
                output_filename=job["output_filename"],
                file_format="netcdf",
                overwrite=False,
                disable_progress_bar=False,
                **BOX,
                **TIME,
                **job["extra"],
            )
            print(f"  OK  ({out.stat().st_size/1e6:.1f} MB)")
        except Exception as exc:  # noqa: BLE001 - report, do not paper over
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            failures.append((job["dataset_id"], f"{type(exc).__name__}: {exc}"))

    print("=" * 74)
    if failures:
        print("FAILURES:")
        for did, msg in failures:
            print(f"  {did}: {msg}")
        return 1
    print("All Phase 6A gap downloads complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
