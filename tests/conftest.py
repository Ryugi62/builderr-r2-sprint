import gzip
import importlib.util
import json
import math
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_agent():
    """Fresh module per call, like the host (which loads the file by path)."""
    path = ROOT / os.environ.get("AGENT_FILE", "agent.py")
    spec = importlib.util.spec_from_file_location("agent_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def agent():
    return load_agent()


def _expand(rows):
    return [{"ts": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in rows]


@pytest.fixture(scope="session")
def regimes():
    raw = json.loads(gzip.open(ROOT / "sample_regimes.json.gz", "rb").read())
    return {k: {"bars": {t: _expand(r) for t, r in v["bars"].items()},
                "eval_start": v["eval_start"], "eval_end": v["eval_end"]} for k, v in raw.items()}


def trend_bars(n=120, start=100.0, daily=0.004, shock_at=None, shock=0.0, start_day=0):
    """Synthetic daily bars with a constant drift and an optional one-day shock."""
    out, px = [], start
    for i in range(n):
        if shock_at is not None and i == shock_at:
            px *= 1 + shock
        else:
            px *= 1 + daily + (0.003 if i % 2 else -0.003)
        d = f"2030-{1 + (start_day + i) // 28 % 12:02d}-{1 + (start_day + i) % 28:02d}"
        out.append({"ts": f"{2030 + (start_day + i) // 336}{d[4:]}", "open": px, "high": px * 1.01,
                    "low": px * 0.99, "close": px, "volume": 1e6})
    return out


@pytest.fixture
def bull_market():
    """QQQ/SMH/leaders in calm uptrends; semis lead."""
    return {
        "QQQ": trend_bars(daily=0.003), "SPY": trend_bars(daily=0.002), "SMH": trend_bars(daily=0.006),
        "SOXL": trend_bars(daily=0.018), "TQQQ": trend_bars(daily=0.009),
        "NVDA": trend_bars(daily=0.008), "AMD": trend_bars(daily=0.007), "MU": trend_bars(daily=0.0075),
        "MSFT": trend_bars(daily=0.002), "AAPL": trend_bars(daily=-0.001),
    }
