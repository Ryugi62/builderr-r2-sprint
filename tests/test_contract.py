"""Host contract: decide(market_state, portfolio_state, cash) -> list of well-formed orders."""
import ast
import math
import time
from pathlib import Path

from conftest import ROOT, trend_bars


def _valid(orders):
    assert isinstance(orders, list)
    for o in orders:
        assert set(o) == {"ticker", "side", "quantity"}
        assert o["side"] in ("buy", "sell")
        assert isinstance(o["quantity"], float) and math.isfinite(o["quantity"]) and o["quantity"] > 0


def test_empty_inputs_return_no_orders(agent):
    assert agent.decide({}, {"cash": 100000.0, "positions": [], "last_prices": {}}, 100000.0) == []
    assert agent.decide(None, None, 0.0) == []


def test_bull_market_from_cash_returns_valid_buys(agent, bull_market):
    orders = agent.decide(bull_market, {"cash": 100000.0, "positions": [], "last_prices": {}}, 100000.0)
    _valid(orders)
    assert orders and all(o["side"] == "buy" for o in orders)


def test_missing_tickers_are_skipped(agent):
    only = {"QQQ": trend_bars(daily=0.003), "NVDA": trend_bars(daily=0.008)}
    orders = agent.decide(only, {"cash": 100000.0, "positions": [], "last_prices": {}}, 100000.0)
    _valid(orders)
    assert {o["ticker"] for o in orders} <= {"QQQ", "NVDA"}


def test_bad_bars_do_not_raise(agent, bull_market):
    bad = dict(bull_market, NVDA=[{"ts": "x", "close": None}], AMD="garbage")
    _valid(agent.decide(bad, {"cash": 1e5, "positions": [{"ticker": "MU", "quantity": "nan?"}]}, 1e5))


def test_agent_imports_only_math_and_has_no_io_calls():
    tree = ast.parse((ROOT / "agent.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports <= {"math", "__future__"}
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not calls & {"open", "eval", "exec", "__import__", "input", "compile"}


def test_runtime_under_half_second(agent):
    big = {t: trend_bars(n=500, daily=0.001 * (i % 7)) for i, t in enumerate(
        list(agent.SINGLES) + ["QQQ", "SPY", "SMH", "SOXL", "TQQQ", "XLK"] + [f"X{i}" for i in range(16)])}
    ps = {"cash": 100000.0, "positions": [], "last_prices": {}}
    t0 = time.perf_counter()
    agent.decide(big, ps, 100000.0)
    assert time.perf_counter() - t0 < 0.5


def test_deterministic(agent, bull_market):
    ps = {"cash": 100000.0, "positions": [], "last_prices": {}}
    assert agent.decide(bull_market, ps, 1e5) == agent.decide(bull_market, ps, 1e5)


def test_agent_runs_when_copied_alone_like_host_private_agents(tmp_path, regimes):
    """The host copies one file to private_agents/<name>_agent.py and loads it by path."""
    import importlib.util
    import shutil

    from engine.sim import Market, run_live

    dst = tmp_path / "private_agents" / "sprint_agent.py"
    dst.parent.mkdir()
    shutil.copy(ROOT / "agent.py", dst)
    spec = importlib.util.spec_from_file_location(dst.stem, dst)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    decide = getattr(mod, "AGENT", mod.decide)
    reg = regimes["calm_uptrend"]
    r = run_live(decide, Market(reg["bars"]), reg["eval_start"], reg["eval_end"])
    assert r["trades"] > 0


def test_research_copy_with_defaults_matches_agent(regimes):
    """research/agent_research.py (rule variants, all off) must trade exactly like agent.py."""
    import importlib.util

    from engine.sim import Market, run_live
    from conftest import load_agent

    spec = importlib.util.spec_from_file_location("agent_research", ROOT / "research" / "agent_research.py")
    research = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(research)
    for reg in regimes.values():
        m = Market(reg["bars"])
        a = run_live(load_agent().decide, m, reg["eval_start"], reg["eval_end"])
        b = run_live(research.decide, m, reg["eval_start"], reg["eval_end"])
        assert a["curve"] == b["curve"]


def test_malformed_portfolio_and_one_bad_bar(agent, bull_market):
    bad = dict(bull_market)
    bad["QQQ"] = bull_market["QQQ"][:-5] + [{"ts": "x"}] + bull_market["QQQ"][-5:]
    ps = {"cash": "1e5", "positions": ["not-a-dict", {"ticker": "MU", "quantity": 1.0}], "last_prices": None}
    orders = agent.decide(bad, ps, 1e5)
    _valid(orders)
    assert orders  # QQQ kept despite one bad bar -> still trades
