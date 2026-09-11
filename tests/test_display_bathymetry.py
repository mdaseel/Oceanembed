import importlib.util
from pathlib import Path
import numpy as np
import xarray as xr

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("build_bathymetry",ROOT/"scripts/poc/build_bathymetry.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_bathymetry_linear_regrid_sign_and_canonical_axes():
    lat=np.array([4.,31.]); lon=np.array([44.,106.])
    z=-((lat[:,None]-4)*10+lon[None,:])
    dem=xr.DataArray(z,coords={"latitude":lat,"longitude":lon},dims=("latitude","longitude"),attrs={"positive":"up","units":"meters"})
    depth=module.regrid_depth(dem)
    assert depth.shape==(101,241)
    np.testing.assert_array_equal(depth.lat,np.arange(5,30.25,.25))
    np.testing.assert_array_equal(depth.lon,np.arange(45,105.25,.25))
    np.testing.assert_allclose(depth,((depth.lat.values[:,None]-4)*10+depth.lon.values[None,:]))
    land=(-dem).assign_attrs(dem.attrs)
    assert (module.regrid_depth(land).values == 0).all()

def test_bathymetry_rejects_unknown_sign():
    import pytest
    with pytest.raises(ValueError): module.regrid_depth(xr.DataArray([1]))

#: Regeneration tolerance, metres. One tenth of a millimetre: far below ETOPO's
#: vertical resolution and irrelevant at the 0.25 deg application grid.
REGEN_ATOL_M = 1e-4

def test_local_bundle_reproducible_and_same_terrain_source():
    """Two different claims, checked two different ways.

    Artifact identity: the committed ETOPO source and the committed depth.bin
    are pinned by EXACT SHA-256, so the bundle the app ships cannot change.

    Reproducibility: re-running the regrid on another run or environment can
    differ at floating-point / library level (observed <= 1.06e-5 m), so the
    regenerated field is compared numerically - identical NaN pattern, values
    within REGEN_ATOL_M - rather than byte for byte.
    """
    import json,hashlib
    out=ROOT/"web/public/assets/bathymetry"
    meta=json.loads((out/"metadata.json").read_text())
    stored_bytes=(out/"depth.bin").read_bytes()
    assert hashlib.sha256(module.SOURCE.read_bytes()).hexdigest()==meta["sourceSha256"]
    assert hashlib.sha256(stored_bytes).hexdigest()==meta["depthSha256"]

    with xr.open_dataset(module.SOURCE) as ds: depth=module.regrid_depth(ds.z)
    actual=np.asarray(depth,dtype="<f8").ravel()
    stored=np.frombuffer(stored_bytes,dtype="<f8")
    assert actual.shape==stored.shape
    np.testing.assert_array_equal(np.isnan(actual),np.isnan(stored))
    np.testing.assert_allclose(actual,stored,rtol=0,atol=REGEN_ATOL_M,equal_nan=True)
