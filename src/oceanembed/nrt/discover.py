"""Catalogue discovery for the registered products, used by the latency logger."""
from __future__ import annotations

import pandas as pd

from .registry import PRODUCTS


def _copernicus_newest(dataset_id: str):
    import copernicusmarine as cm
    cat = cm.describe(dataset_id=dataset_id, disable_progress_bar=True)
    for p in cat.products:
        for ds in p.datasets:
            if ds.dataset_id != dataset_id:
                continue
            for v in (ds.versions or []):
                for pt in (v.parts or []):
                    for s in (pt.services or []):
                        sn = str(getattr(s.service_name, "value", s.service_name))
                        if "arco-geo" not in sn:
                            continue
                        t = {c.coordinate_id: c for c in s.variables[0].coordinates}.get("time")
                        return (pd.to_datetime(t.maximum_value, unit="ms"),
                                getattr(v, "label", None))
    return None, None


def _podaac_newest(short_name: str, look_back_days: int = 20):
    import earthaccess
    end = pd.Timestamp.utcnow().tz_localize(None)
    start = end - pd.Timedelta(days=look_back_days)
    res = earthaccess.search_data(short_name=short_name,
                                  temporal=(str(start.date()), str(end.date())),
                                  count=400)
    if not res:
        return None, None, None
    newest, gid = None, None
    for g in res:
        try:
            t = pd.Timestamp(g["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"])
        except Exception:  # noqa: BLE001
            continue
        t = t.tz_localize(None) if t.tzinfo else t
        if newest is None or t > newest:
            newest, gid = t, g["meta"].get("native-id")
    return newest, gid, len(res)


def poll_product(key: str) -> dict:
    """One catalogue poll for one registered product."""
    p = PRODUCTS[key]
    q = pd.Timestamp.utcnow().tz_localize(None)
    rec = {"provider": p["provider"], "product_key": key,
           "product_id": p["product_id"], "dataset_id": p["dataset_id"],
           "query_time": q, "success": False, "error": None,
           "newest_valid_time": None, "revision": None, "granule_id": None}
    try:
        if "Copernicus" in p["provider"]:
            newest, rev = _copernicus_newest(p["dataset_id"])
            rec.update(newest_valid_time=newest, revision=rev, success=newest is not None)
        else:
            # A reference-tier PO.DAAC product can lag by many months, so a short
            # window returns nothing at all. Finding nothing is itself a latency
            # measurement, not an error, so the window is widened for those.
            look_back = 900 if p["role"] == "reference" else 20
            newest, gid, _ = _podaac_newest(p["dataset_id"], look_back_days=look_back)
            rec.update(newest_valid_time=newest, granule_id=gid, success=newest is not None)
        if not rec["success"]:
            rec["error"] = "no newest valid time resolved"
    except Exception as exc:  # noqa: BLE001
        rec["error"] = f"{type(exc).__name__}: {exc}"
    return rec
