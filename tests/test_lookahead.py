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
