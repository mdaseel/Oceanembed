# OceanEmbed Historical PoC

**Start:** double-click `Start-OceanEmbed.cmd` in the repository root. Keep its
console open while using the app. It opens http://127.0.0.1:8000 in your browser.
If the app is already running, open that address directly. Stop with Ctrl+C.

1. Pick a historical date, depth and temperature/anomaly layer.
2. Click the map or enter coordinates, then inspect the L2/L0 profile.
3. Open **3D Depth View**: drag to orbit, right-drag to pan, scroll to zoom.
   Depth scrub snaps to the 15 actual output levels. Adjust exaggeration and clip.
4. **Run frozen L2** demonstrates real local computation.
5. Open **Provenance & Validation** for executed scientific evidence, or **Exports**
   for the current profile CSV, map PNG and complete field NetCDF.

The local application works without internet after the following one-time setup.
Historical surface stores and frozen artifacts must already be present in their
repository paths. The app never fetches scientific products.

## One-time setup

Use Python 3.12 and Node.js 24. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd web
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe scripts/poc/serve.py
```

The tested Python package versions are recorded in
`outputs/phase7b/python-environment.txt`; npm dependencies are locked in
`web/package-lock.json`. The existing repository `httpx2` dependency is retained.

For development, run the local server without opening a browser:

```powershell
.\.venv\Scripts\python.exe scripts/poc/serve.py --no-browser
# In a second terminal:
cd web
npm run dev
```

## Verification

```powershell
$env:OMP_NUM_THREADS='4'
$env:MKL_NUM_THREADS='4'
.\.venv\Scripts\python.exe scripts/poc/verify_transport.py
.\.venv\Scripts\python.exe -m pytest -q
cd web
npm test
npm run test:e2e
```

Browser tests use the installed Microsoft Edge and the running local server at
port 8000. They block non-loopback requests to verify offline operation. The real
transport fixture is generated only for tests and is excluded from the build.

## Scientific interpretation

L2 emits absolute temperature at 15 depths. Anomaly is L2 minus separately
evaluated L0 climatology. The nominal 0 m target is approximately 0.494 m and is
different from the OSTIA input. Deep daily anomaly skill is weaker at 500–1000 m.
Missing L0 means missing anomaly; raw finite L2 remains available. The climatology
support mask is coefficient availability, not bathymetry.

Phase 7B only. See `PHASE7B_HISTORICAL_POC_REPORT.md` for verification and limits.
