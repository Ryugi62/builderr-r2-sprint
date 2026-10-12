"""No lookahead: what happens after a session can never change the orders for it."""
import random

from conftest import load_agent
from engine.sim import Market, run_live


def _scramble_after(bars, cut, seed=7):
    rng = random.Random(seed)
    out = {}
    for t, rows in bars.items():
        new = []
        for b in rows:
            if b["ts"] >= cut:
                k = rng.uniform(0.5, 1.5)
                b = {**b, "open": b["open"] * k, "high": b["high"] * k, "low": b["low"] * k, "close": b["close"] * k}
            new.append(b)
        out[t] = new
    return out


def test_orders_ignore_future_bars(regimes):
    reg = regimes["vol_spike_snapback"]
    m = Market(reg["bars"])
    dates = [d for d in m.dates if reg["eval_start"] <= d <= reg["eval_end"]]
    agent = load_agent()
    for d in dates[::5]:
        ms = m.before(d)
        m2 = Market(_scramble_after(reg["bars"], d))
        ps = {"cash": 100000.0, "positions": [], "last_prices": {}}
        assert agent.decide(ms, ps, 1e5) == agent.decide(m2.before(d), ps, 1e5)


def test_replay_prefix_unchanged_when_future_scrambled(regimes):
    reg = regimes["calm_uptrend"]
    m = Market(reg["bars"])
    dates = [d for d in m.dates if reg["eval_start"] <= d <= reg["eval_end"]]
    cut = dates[len(dates) // 2]
    a = run_live(load_agent().decide, m, reg["eval_start"], reg["eval_end"])
    b = run_live(load_agent().decide, Market(_scramble_after(reg["bars"], cut)), reg["eval_start"], reg["eval_end"])
    k = dates.index(cut)
    assert a["curve"][:k] == b["curve"][:k]
    assert a["curve"][k:] != b["curve"][k:]  # the scramble really did change the future


def test_market_state_never_contains_the_session_being_traded(regimes):
    reg = regimes["moderate_selloff"]
    m = Market(reg["bars"])
    seen = []

    def spy(ms, ps, cash):
        seen.append(max(rows[-1]["ts"] for rows in ms.values()))
        return []

    r = run_live(spy, m, reg["eval_start"], reg["eval_end"])
    assert all(s < d for s, d in zip(seen, r["dates"]))


class _Recorder(dict):
    """market_state proxy that records every bar timestamp the agent reads."""

    def __init__(self, data, seen):
        super().__init__({t: _Rows(rows, seen) for t, rows in data.items()})


class _Rows(list):
    def __init__(self, rows, seen):
        super().__init__(rows)
        self._seen = seen

    def __getitem__(self, i):
        out = super().__getitem__(i)
        for b in (out if isinstance(out, list) else [out]):
            self._seen.append(b["ts"])
        return out


def test_agent_reads_only_bars_before_the_session(regimes):
    reg = regimes["vol_spike_snapback"]
    m = Market(reg["bars"])
    agent = load_agent()
    for d in [x for x in m.dates if reg["eval_start"] <= x <= reg["eval_end"]][::4]:
        seen = []
        agent.decide(_Recorder(m.before(d), seen), {"cash": 1e5, "positions": [], "last_prices": {}}, 1e5)
        assert seen and max(seen) < d


def test_no_hidden_state_from_a_later_call(regimes):
    """Calling the same module on a later date first must not change an earlier date's orders."""
    reg = regimes["calm_uptrend"]
    m = Market(reg["bars"])
    dates = [x for x in m.dates if reg["eval_start"] <= x <= reg["eval_end"]]
    ps = {"cash": 1e5, "positions": [], "last_prices": {}}
    used = load_agent()
    used.decide(m.before(dates[-1]), ps, 1e5)
    assert used.decide(m.before(dates[3]), ps, 1e5) == load_agent().decide(m.before(dates[3]), ps, 1e5)


def test_agent_source_has_no_dates_or_clock():
    import ast
    import re
    from conftest import ROOT
    tree = ast.parse((ROOT / "agent.py").read_text())
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not [s for s in strings if re.search(r"(19|20)\d\d-\d\d", s)]
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"time", "datetime", "now", "today", "random", "environ"}
