"""Display mesh tests only; synthetic fixtures are not bundled as terrain."""
import importlib.util
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location(
    "terrain_builder", Path(__file__).resolve().parents[1] / "scripts/poc/build_terrain.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_zero_contour_clips_water_and_preserves_real_height():
    lat, lon = np.array([5., 6.]), np.array([45., 46.])
    z = np.array([[100., -100.], [100., -100.]])
    p, idx = builder.land_mesh(lat, lon, z)
    assert len(idx) > 0
    assert np.all(p[:, 0] <= 45.5)
    assert set(p[:, 2]) == {0., 100.}
    assert np.all(p[p[:, 2] == 0, 0] == 45.5)
    # All faces face upward in the renderer's x/elevation/-latitude mapping.
    for tri in idx.reshape(-1, 3):
        a, b, c = p[tri]
        assert np.cross(b - a, c - a)[2] > 0


def test_disconnected_islands_are_not_bridged_and_water_hole_stays_open():
    axis = np.arange(7, dtype=float)
    z = np.full((7, 7), -100.)
    z[1:4, 1:4] = 100
    z[2, 2] = -100  # lake/hole
    z[5, 5] = 200   # separate island
    p, idx = builder.land_mesh(axis, axis, z)
    for tri in idx.reshape(-1, 3):
        points = p[tri]
        assert np.ptp(points[:, 0]) <= 1
        assert np.ptp(points[:, 1]) <= 1
        centre = points[:, :2].mean(axis=0)
        assert not (abs(centre[0] - 2) < .2 and abs(centre[1] - 2) < .2)
    assert np.any(p[:, 2] == 200)


def test_ocean_and_missing_dem_never_generate_a_backing_plate():
    axis = np.arange(3, dtype=float)
    for z in (np.full((3, 3), -1.), np.full((3, 3), np.nan), np.zeros((3, 3))):
        p, idx = builder.land_mesh(axis, axis, z)
        assert p.size == idx.size == 0
