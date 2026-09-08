"""Generate a real replay transport fixture for tests, never shipped by the app."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from oceanembed.poc.app import get_view, view_payload

out = ROOT / "outputs/phase7b"
out.mkdir(parents=True, exist_ok=True)
view = get_view("2021-06-15", force_recompute=True)
payload = view_payload(view)
(out / "test-field.json").write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
evidence = {
    "date": view.date, "shape": list(view.temperature.shape),
    "source": view.provenance["inference_source"],
    "compute_seconds": view.provenance["compute_seconds"],
    "requested_location": [15.25, 87.75],
    "profile_c": view.temperature[41,171,:].tolist(),
    "provenance": view.provenance,
    "frozen_hashes": {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in [
        "outputs/models/phase6b_l2_final.pt", "outputs/models/phase6b_l1_mlp.pt",
        "outputs/baselines/phase6b_feature_scaler.json", "outputs/baselines/phase6b_target_scaler.json",
        "outputs/baselines/phase6b_climatology.nc", "outputs/baselines/phase6cb_surface_climatology.nc"]},
}
(out / "transport-verification.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps({k:v for k,v in evidence.items() if k not in ("provenance","frozen_hashes")}, indent=2))
