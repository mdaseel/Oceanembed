"""Launch the bundled offline PoC and open its local page when ready."""
import argparse
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")


def open_when_ready(port):
    url = f"http://127.0.0.1:{port}/"
    for _ in range(60):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not (ROOT / "web/dist/index.html").is_file():
        raise SystemExit("Build missing. In web/, run npm ci followed by npm run build once before offline use.")
    import uvicorn
    print(f"OceanEmbed Historical Replay: http://127.0.0.1:{args.port}\nPress Ctrl+C to stop.")
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(args.port,), daemon=True).start()
    uvicorn.run("oceanembed.poc.app:app", host="127.0.0.1", port=args.port, workers=1)
