"""OSCAR NRT at the lagged valid times needed for the age-vs-product split."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import pandas as pd
import importlib.util
spec = importlib.util.spec_from_file_location(
    "fn", Path(__file__).with_name("fetch_nrt.py"))
fn = importlib.util.module_from_spec(spec); spec.loader.exec_module(fn)

K = 3  # pre-registered operational age for OSCAR NRT
dates = pd.date_range(fn.COMMON_START, fn.COMMON_END, freq="D")[::3] - pd.Timedelta(days=K)
print(f"lagged (t-{K}) dates: {dates[0].date()} .. {dates[-1].date()} ({len(dates)})")
fn.oscar_nrt_fetch(dates)
