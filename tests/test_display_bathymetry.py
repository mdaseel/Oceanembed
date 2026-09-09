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

def test_local_bundle_reproducible_and_same_terrain_source():
    import json,hashlib
    with xr.open_dataset(module.SOURCE) as ds: depth=module.regrid_depth(ds.z)
    actual=np.asarray(depth,dtype="<f8").tobytes()
    out=ROOT/"web/public/assets/bathymetry"
    assert actual==(out/"depth.bin").read_bytes()
    meta=json.loads((out/"metadata.json").read_text())
    assert hashlib.sha256(module.SOURCE.read_bytes()).hexdigest()==meta["sourceSha256"]
    assert hashlib.sha256(actual).hexdigest()==meta["depthSha256"]
