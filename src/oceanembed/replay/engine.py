"""The authoritative historical replay engine.

    historical date
      -> canonical 101x241 historical surface fields
      -> exact frozen preprocessing (day_field)
      -> frozen whole-field L2 (embed_field -> forward_from_z)
      -> 101x241x15 reconstruction
      -> frozen L0 climatology
      -> anomaly
      -> field and point views

There is exactly ONE inference implementation here. ``replay_point`` does not
call the network; it samples the field result. That is the property the
mandatory Phase 7A equivalence test pins, and it is why the map, the profile and
the 3D view can never disagree.

Cell support: a date's predictions are produced at the cells where THAT date's
``surface_input_valid`` is true. That mask is, by construction, identical to the
joint validity mask ``day_field`` computes internally from the same seven
channels, so the decoded cell set and the encoder's mask channel always agree.
Off-support cells are NaN - never zero, never interpolated.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import xarray as xr
import yaml

from ..config import EAST, NORTH, REPO_ROOT, RESOLUTION, SOUTH, WEST
from ..grid import canonical_lat, canonical_lon
from ..ml.climatology import HarmonicClimatology
from ..ml.features import SURFACE, cyclic_doy
from ..ml.l2_model import L2EmbeddingModel
from ..ml.patches import N_DATA_CHANNELS, day_field
from ..ml.scaler import ZScoreScaler
from .cache import ReplayCache
from .contract import (ALLOWED_STORE_VARS, DEPTHS, DEEP_SKILL_NOTE, FieldView,
                       InferenceSource, LocationStatus, NOMINAL_ZERO_M_NOTE,
                       OutsideDomain, PointResult, ResolvedLocation)

_CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
_SPLITS = yaml.safe_load(open(REPO_ROOT / "config" / "data_splits.yaml",
                              encoding="utf-8"))

MODEL_READY = REPO_ROOT / "data" / "processed" / "model_ready"
BASELINES = REPO_ROOT / _CFG["paths"]["baselines"]
MODELS = REPO_ROOT / _CFG["paths"]["models"]
CACHE_ROOT = REPO_ROOT / "outputs" / "phase7" / "replay_cache"

L2_CHECKPOINT = MODELS / "phase6b_l2_final.pt"
FEATURE_SCALER = BASELINES / "phase6b_feature_scaler.json"
TARGET_SCALER = BASELINES / "phase6b_target_scaler.json"
CLIMATOLOGY = BASELINES / "phase6b_climatology.nc"

DATASET_START = pd.Timestamp(_SPLITS["dataset"]["start"])
DATASET_END = pd.Timestamp(_SPLITS["dataset"]["end"])

PROCESSING_VERSION = _CFG.get("baseline_version", "6B.1")
GRID_VERSION = f"{SOUTH}-{NORTH}N_{WEST}-{EAST}E_{RESOLUTION}deg"

#: Frozen artifact hashes. A mismatch is a hard failure, not a warning.
EXPECTED_SHA256 = {
    "l2_checkpoint_file":
        "81979a6541927ff5c6b0a13c5ce7cdbcd486040d16a304dcdc10b2962a586e35",
    "feature_scaler_file":
        "49671ce760b0dca5c1c82cb184dae91908cc064abfdea8cc7eb2f5bc3c320467",
    "target_scaler_file":
        "5b6f359db0d228dd7d3acf775ab8a6eea76dd521e7b4568ff1873c832e89e93b",
    "climatology_file":
        "748af4d79bc704cc2f742e1c208bacebe781131c5ff142cddc7c334963903cd5",
}
EXPECTED_L2_STATE_DICT = \
    "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"
EXPECTED_L2_ENCODER = \
    "30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808"


class FrozenArtifactChanged(RuntimeError):
    """A frozen scientific artifact no longer matches its recorded hash."""


def file_sha256(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def state_dict_sha256(sd) -> str:
    h = hashlib.sha256()
    for k in sorted(sd):
        h.update(k.encode("utf-8"))
        h.update(np.ascontiguousarray(sd[k].detach().cpu().numpy()).tobytes())
    return h.hexdigest()


def _open_surface_store(year: int, model_ready: Path | None = None) -> xr.Dataset:
    """Open one year's model-ready store with SURFACE INPUTS ONLY.

    The target variables are dropped here, not merely "not used later". A
    target therefore cannot reach inference even through a coding mistake.
    """
    root = Path(model_ready) if model_ready is not None else MODEL_READY
    path = root / f"oceanembed_{year}.zarr"
    if not path.exists():
        raise FileNotFoundError(
            f"model-ready store missing for {year}: {path}. Replay needs the "
            f"processed surface fields; see the Phase 7A data prerequisites.")
    ds = xr.open_zarr(path, consolidated=True)
    keep = [v for v in ds.data_vars if v in ALLOWED_STORE_VARS]
    leaked = [v for v in keep if v.startswith(("temp_", "target_valid_"))]
    if leaked:
        raise RuntimeError(f"target variable selected for replay: {leaked}")
    missing = set(SURFACE) - set(keep)
    if missing:
        raise RuntimeError(f"{path.name} is missing surface channels: "
                           f"{sorted(missing)}")
    return ds[keep]


class ReplayEngine:
    """Loads the frozen core once and serves authoritative replay results."""

    def __init__(self, model_ready: Path | None = None,
                 cache_root: Path | None = None, use_cache: bool = True,
                 verify_hashes: bool = True):
        self.model_ready = Path(model_ready) if model_ready else MODEL_READY
        self.cache = ReplayCache(cache_root or CACHE_ROOT, enabled=use_cache)
        self._stores: dict[int, xr.Dataset] = {}

        files = {
            "l2_checkpoint_file": L2_CHECKPOINT,
            "feature_scaler_file": FEATURE_SCALER,
            "target_scaler_file": TARGET_SCALER,
            "climatology_file": CLIMATOLOGY,
        }
        self.file_hashes = {k: file_sha256(p) for k, p in files.items()}
        if verify_hashes:
            for k, want in EXPECTED_SHA256.items():
                if self.file_hashes[k] != want:
                    raise FrozenArtifactChanged(
                        f"{files[k].name} hash {self.file_hashes[k]} != expected {want}")

        ck = torch.load(L2_CHECKPOINT, map_location="cpu", weights_only=False)
        self.patch = int(ck["patch"])
        self.latent = int(ck["latent"])
        self.receptive_field = int(ck["receptive_field"])
        self.model = L2EmbeddingModel(latent=self.latent, patch=self.patch)
        self.model.load_state_dict(ck["state_dict"])
        self.model.eval()
        for p in self.model.parameters():
            p.requires_grad_(False)

        self.l2_state_dict_sha256 = state_dict_sha256(ck["state_dict"])
        encoder_sd = {k[len("encoder."):]: v for k, v in ck["state_dict"].items()
                      if k.startswith("encoder.")}
        self.l2_encoder_sha256 = state_dict_sha256(encoder_sd)
        if verify_hashes:
            if self.l2_state_dict_sha256 != EXPECTED_L2_STATE_DICT:
                raise FrozenArtifactChanged("L2 state-dict hash changed")
            if self.l2_encoder_sha256 != EXPECTED_L2_ENCODER:
                raise FrozenArtifactChanged("L2 encoder hash changed")
        if list(ck["depths"]) != DEPTHS:
            raise FrozenArtifactChanged(
                f"checkpoint depth list {ck['depths']} != mandated {DEPTHS}")

        self.feature_scaler = ZScoreScaler.from_json(FEATURE_SCALER)
        self.target_scaler = ZScoreScaler.from_json(TARGET_SCALER)
        if self.feature_scaler.fitted_on != "train" or \
                self.target_scaler.fitted_on != "train":
            raise FrozenArtifactChanged("a scaler is not the train-only artifact")
        self.climatology = HarmonicClimatology.load(CLIMATOLOGY)
        if self.climatology.meta.get("fitted_on") != "train":
            raise FrozenArtifactChanged("L0 climatology is not the train-only artifact")

        self.lat = canonical_lat()
        self.lon = canonical_lon()
        self.n_params = self.model.n_parameters

    # ------------------------------------------------------------- provenance
    @property
    def provenance(self) -> dict:
        return {
            "model_name": "L2 Spatial Satellite Embedding Engine",
            "model_class": "oceanembed.ml.l2_model.L2EmbeddingModel",
            "checkpoint_path": str(L2_CHECKPOINT.relative_to(REPO_ROOT)),
            "l2_state_dict_sha256": self.l2_state_dict_sha256,
            "l2_encoder_sha256": self.l2_encoder_sha256,
            "feature_scaler_sha256": self.file_hashes["feature_scaler_file"],
            "target_scaler_sha256": self.file_hashes["target_scaler_file"],
            "climatology_sha256": self.file_hashes["climatology_file"],
            "l2_checkpoint_file_sha256": self.file_hashes["l2_checkpoint_file"],
            "patch": self.patch,
            "latent_dim": self.latent,
            "receptive_field": self.receptive_field,
            "n_parameters": self.n_params,
            "surface_inputs": list(SURFACE),
            "depths_m": list(DEPTHS),
            "processing_version": PROCESSING_VERSION,
            "grid_version": GRID_VERSION,
            "nominal_zero_m_note": NOMINAL_ZERO_M_NOTE,
            "deep_skill_note": DEEP_SKILL_NOTE,
            "target_used_for_inference": False,
            "argo_used_for_inference": False,
        }

    # ------------------------------------------------------------------ dates
    @staticmethod
    def _normalise_date(date) -> pd.Timestamp:
        d = pd.Timestamp(date).normalize()
        if d < DATASET_START or d > DATASET_END:
            raise OutsideDomain(
                f"{d.date()} is outside the processed record "
                f"{DATASET_START.date()}..{DATASET_END.date()}")
        return d

    def _store(self, year: int) -> xr.Dataset:
        if year not in self._stores:
            self._stores[year] = _open_surface_store(year, self.model_ready)
        return self._stores[year]

    def _time_index(self, ds: xr.Dataset, when: pd.Timestamp) -> int:
        times = pd.DatetimeIndex(ds.time.values).normalize()
        hits = np.flatnonzero(times == when)
        if not len(hits):
            raise OutsideDomain(f"{when.date()} is not present in the store")
        return int(hits[0])

    # ------------------------------------------------------- the one inference
    def _infer(self, ds: xr.Dataset, t: int, when: pd.Timestamp):
        """The EXISTING frozen whole-field L2 path. The only inference here.

        Identical in structure to the frozen evaluation loop: build the padded
        standardised field with the unmodified ``day_field``, encode the whole
        field once, decode at the supported cells with the frozen context, and
        return physical temperature.
        """
        siv = np.asarray(ds["surface_input_valid"].isel(time=t).values, dtype=bool)
        rows, cols = np.nonzero(siv)

        field = day_field(ds, t, self.feature_scaler, self.patch)
        cell_lat = self.lat[rows]
        cell_lon = self.lon[cols]
        s, c = cyclic_doy(pd.DatetimeIndex([when]))
        raw_ctx = np.column_stack([cell_lat, cell_lon,
                                   np.full(rows.size, s[0]),
                                   np.full(rows.size, c[0])]).astype("float64")
        ctx = ((raw_ctx - self.feature_scaler.mean[N_DATA_CHANNELS:])
               / self.feature_scaler.std[N_DATA_CHANNELS:]).astype("float32")

        with torch.no_grad():
            z = self.model.embed_field(torch.from_numpy(field)[None])[0]
            std_pred = self.model.forward_from_z(
                z[:, rows, cols].T, torch.from_numpy(ctx)).numpy().astype("float64")
        pred_cells = self.target_scaler.inverse_transform(std_pred)

        temperature = np.full((self.lat.size, self.lon.size, len(DEPTHS)),
                              np.nan, dtype="float64")
        temperature[rows, cols, :] = pred_cells
        return temperature, siv

    # ------------------------------------------------------------ field replay
    def replay_field(self, date, force_recompute: bool = False) -> FieldView:
        """Authoritative 101x241x15 reconstruction for one historical date."""
        when = self._normalise_date(date)
        key = str(when.date())
        prov = self.provenance

        arrays, source, seconds = None, InferenceSource.LIVE_MODEL_RUN, None
        if not force_recompute:
            hit = self.cache.get(key, prov)
            if hit is not None:
                arrays, _ = hit
                source = InferenceSource.VALIDATED_CACHE

        ds = self._store(when.year)
        t = self._time_index(ds, when)
        ocean = np.asarray(ds["ocean_mask"].isel(time=t).values, dtype=bool)

        if arrays is None:
            t0 = time.perf_counter()
            temperature, siv = self._infer(ds, t, when)
            # (n_times, n_depths, nlat, nlon) -> (nlat, nlon, n_depths)
            clim = self.climatology.predict(pd.DatetimeIndex([when]))[0]
            climatology = np.moveaxis(clim, 0, -1).astype("float64")
            seconds = time.perf_counter() - t0
            arrays = {"temperature": temperature, "climatology": climatology,
                      "surface_input_valid": siv}
            self.cache.put(key, prov, arrays)
        else:
            temperature = arrays["temperature"]
            climatology = arrays["climatology"]
            siv = arrays["surface_input_valid"].astype(bool)

        view = FieldView(
            date=key,
            temperature=temperature,
            climatology=climatology,
            anomaly=temperature - climatology,
            lat=self.lat.copy(),
            lon=self.lon.copy(),
            depths=list(DEPTHS),
            ocean_mask=ocean,
            surface_input_valid=siv,
            provenance={**prov,
                        "inference_source": source.value,
                        "compute_seconds": seconds,
                        "operating_mode": "HISTORICAL_COMPLETE_INPUT",
                        "n_supported_cells": int(siv.sum()),
                        "n_ocean_cells": int(ocean.sum()),
                        "climatology_defined_note":
                            "isfinite(climatology) records CLIMATOLOGY DEPTH-SUPPORT "
                            "availability - where the frozen L0 has coefficients. It "
                            "is NOT a bathymetry product and NOT an authoritative "
                            "seafloor mask; it is one reanalysis's target "
                            "availability on a single reference day. Anomaly is NaN "
                            "where it is False because there is no baseline to "
                            "subtract. The raw frozen-L2 temperature is preserved at "
                            "all 15 mandated depths regardless."},
        ).validate()
        return view

    # ------------------------------------------------------------ location
    def resolve(self, view: FieldView, lat: float, lon: float,
                suggest_nearest: bool = True) -> ResolvedLocation:
        lat, lon = float(lat), float(lon)
        if not (SOUTH <= lat <= NORTH and WEST <= lon <= EAST):
            return ResolvedLocation(lat, lon, LocationStatus.OUTSIDE_DOMAIN)

        row = int(np.abs(view.lat - lat).argmin())
        col = int(np.abs(view.lon - lon).argmin())
        glat, glon = float(view.lat[row]), float(view.lon[col])

        if not bool(view.ocean_mask[row, col]):
            status = LocationStatus.INVALID_OCEAN_CELL
        elif not bool(view.surface_input_valid[row, col]):
            status = LocationStatus.INPUT_NOT_VALID
        else:
            status = LocationStatus.OK

        near_lat = near_lon = near_d = None
        if status is not LocationStatus.OK and suggest_nearest:
            usable = np.argwhere(view.surface_input_valid)
            if usable.size:
                dlat = view.lat[usable[:, 0]] - glat
                dlon = view.lon[usable[:, 1]] - glon
                d = np.hypot(dlat, dlon)
                j = int(d.argmin())
                near_lat = float(view.lat[usable[j, 0]])
                near_lon = float(view.lon[usable[j, 1]])
                near_d = float(d[j])

        return ResolvedLocation(lat, lon, status, row, col, glat, glon,
                                near_lat, near_lon, near_d)

    # ------------------------------------------------------------ point replay
    def replay_point(self, date, lat: float, lon: float,
                     force_recompute: bool = False) -> PointResult:
        """Sample the authoritative field. Runs no inference of its own."""
        view = self.replay_field(date, force_recompute=force_recompute)
        loc = self.resolve(view, lat, lon)

        surface_inputs: dict = {}
        profile: list[dict] = []
        if loc.status is not LocationStatus.OUTSIDE_DOMAIN:
            ds = self._store(pd.Timestamp(view.date).year)
            t = self._time_index(ds, pd.Timestamp(view.date))
            for v in SURFACE:
                val = float(ds[v].isel(time=t).values[loc.grid_row, loc.grid_col])
                surface_inputs[v] = {
                    "value": None if not np.isfinite(val) else val,
                    "units": _UNITS[v],
                    "product": _PRODUCTS[v],
                }
            prof = view.profile_at(loc.grid_row, loc.grid_col)
            for k, d in enumerate(view.depths):
                profile.append({
                    "depth_m": int(d),
                    "prediction_c": _finite_or_none(prof["prediction_c"][k]),
                    "climatology_c": _finite_or_none(prof["climatology_c"][k]),
                    "anomaly_c": _finite_or_none(prof["anomaly_c"][k]),
                })

        prov = dict(view.provenance)
        return PointResult(
            date=view.date,
            location=loc,
            model={"name": prov["model_name"],
                   "checkpoint_sha256": prov["l2_state_dict_sha256"],
                   "encoder_sha256": prov["l2_encoder_sha256"],
                   "latent_dim": prov["latent_dim"],
                   "receptive_field": prov["receptive_field"],
                   "n_parameters": prov["n_parameters"]},
            surface_inputs=surface_inputs,
            profile=profile,
            provenance={k: prov[k] for k in
                        ("processing_version", "grid_version", "depths_m",
                         "surface_inputs", "n_supported_cells", "n_ocean_cells")},
            status={"operating_mode": prov["operating_mode"],
                    "location_status": loc.status.value,
                    "target_used_for_inference": False,
                    "argo_used_for_inference": False,
                    "inference_source": prov["inference_source"]},
        )

    # ------------------------------------------------------------ multi-date
    def replay_range(self, start, end, lat: float, lon: float,
                     force_recompute: bool = False) -> list[PointResult]:
        """Each day is an independent replay_field. No temporal state, no L3."""
        a, b = self._normalise_date(start), self._normalise_date(end)
        if b < a:
            raise OutsideDomain(f"end {b.date()} precedes start {a.date()}")
        return [self.replay_point(d, lat, lon, force_recompute=force_recompute)
                for d in pd.date_range(a, b, freq="D")]

    def close(self) -> None:
        for ds in self._stores.values():
            ds.close()
        self._stores.clear()


_UNITS = {"sst": "degC", "sss": "PSU", "sla": "m", "current_u": "m s-1",
          "current_v": "m s-1", "wind_u": "m s-1", "wind_v": "m s-1"}
_PRODUCTS = {"sst": "OSTIA L4 REP", "sss": "CMEMS MULTIOBS",
             "sla": "DUACS L4 (C3S two-satellite)",
             "current_u": "OSCAR L4 Final v2.0",
             "current_v": "OSCAR L4 Final v2.0",
             "wind_u": "CCMP v3.1", "wind_v": "CCMP v3.1"}


def _finite_or_none(x) -> float | None:
    v = float(x)
    return v if np.isfinite(v) else None


_DEFAULT: ReplayEngine | None = None


def _engine() -> ReplayEngine:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = ReplayEngine()
    return _DEFAULT


def replay_field(date, force_recompute: bool = False) -> FieldView:
    return _engine().replay_field(date, force_recompute=force_recompute)


def replay_point(date, lat: float, lon: float,
                 force_recompute: bool = False) -> PointResult:
    return _engine().replay_point(date, lat, lon, force_recompute=force_recompute)


def replay_range(start, end, lat: float, lon: float,
                 force_recompute: bool = False) -> list[PointResult]:
    return _engine().replay_range(start, end, lat, lon,
                                  force_recompute=force_recompute)
