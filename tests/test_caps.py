"""30% single-name cap and 1.5x beta-gross cap, enforced by targets, trims and replay."""
from conftest import trend_bars
from engine.sim import Market, beta, run_admission, run_live

PS0 = {"cash": 100000.0, "positions": [], "last_prices": {}}


def _projected(orders, bars):
    px = {t: rows[-1]["close"] for t, rows in bars.items()}
    vals = {o["ticker"]: o["quantity"] * px[o["ticker"]] for o in orders if o["side"] == "buy"}
    return vals


def test_attack_book_weights_and_beta(agent, bull_market):
    vals = _projected(agent.decide(bull_market, PS0, 1e5), bull_market)
    assert max(v / 1e5 for v in vals.values()) <= 0.25 + 1e-9
    assert sum(v * beta(t) for t, v in vals.items()) / 1e5 <= 1.25 + 1e-6
    assert sum(vals.values()) <= 1e5
    assert "SOXL" in vals  # semis lead in this fixture -> 3x semis sleeve


def test_attack_buys_three_leaders_by_momentum(agent, bull_market):
    names = {o["ticker"] for o in agent.decide(bull_market, PS0, 1e5)}
    assert {"NVDA", "MU", "AMD"} <= names and "AAPL" not in names


def test_drifted_leader_is_trimmed_to_target(agent, bull_market):
    p = bull_market["NVDA"][-1]["close"]
    held = {"NVDA": 29000 / p}
    ps = {"cash": 71000.0, "positions": [{"ticker": "NVDA", "quantity": held["NVDA"], "avg_cost": p}],
          "last_prices": {}}
    sells = [o for o in agent.decide(bull_market, ps, 71000.0) if o["side"] == "sell" and o["ticker"] == "NVDA"]
    assert sells and abs((held["NVDA"] - sells[0]["quantity"]) * p / 1e5 - 0.25) < 0.002


def test_brake_sells_everything(agent, bull_market):
    crash = dict(bull_market, QQQ=trend_bars(daily=0.003, shock_at=118, shock=-0.08))
    ps = {"cash": 5000.0, "positions": [{"ticker": t, "quantity": 100.0, "avg_cost": 1.0} for t in ("NVDA", "SOXL")],
          "last_prices": {}}
    orders = agent.decide(crash, ps, 5000.0)
    assert {o["ticker"] for o in orders if o["side"] == "sell"} == {"NVDA", "SOXL"}
    assert not [o for o in orders if o["side"] == "buy"]


def test_below_sma20_drops_sleeve_keeps_leaders(agent, bull_market):
    soft = dict(bull_market, QQQ=trend_bars(daily=0.003)[:-6] + trend_bars(n=6, start=trend_bars(daily=0.003)[-7]["close"], daily=-0.008))
    w = agent.target_weights({t: [b["close"] for b in r] for t, r in soft.items()}, 1.0)
    assert w and all(beta(t) == 1.0 for t in w)


def test_governor_removes_sleeve(agent, bull_market):
    closes = {t: [b["close"] for b in r] for t, r in bull_market.items()}
    assert "SOXL" in agent.target_weights(closes, 1.0)
    assert "SOXL" not in agent.target_weights(closes, 0.89)


def test_admission_mirror_passes_public_windows(agent, regimes):
    for name, reg in regimes.items():
        m = Market(reg["bars"])
        r = run_admission(load_fresh(), m, reg["eval_start"], reg["eval_end"])
        assert r["passed"], (name, r)
        assert r["peak_gross"] <= 1.5 and r["max_conc_streak"] <= 1, (name, r)


def test_live_mirror_never_holds_30pct_two_closes(agent, regimes):
    for name, reg in regimes.items():
        r = run_live(load_fresh(), Market(reg["bars"]), reg["eval_start"], reg["eval_end"])
        assert max(r["gross"]) < 1.5, name
        streak = best = 0
        for w in r["maxw"]:
            streak = streak + 1 if w >= 0.30 else 0
            best = max(best, streak)
        assert best <= 1, name


def load_fresh():
    from conftest import load_agent
    return load_agent().decide


def test_gross_drift_above_135_resets_sleeve(agent, bull_market):
    closes = {t: r[-1]["close"] for t, r in bull_market.items()}
    eq = 100000.0
    # leaders at 25% each + SOXL drifted to 22% -> beta gross 0.75 + 0.66 = 1.41 > 1.35
    pos = [{"ticker": t, "quantity": 25000 / closes[t], "avg_cost": 1} for t in ("NVDA", "MU", "AMD")]
    pos.append({"ticker": "SOXL", "quantity": 22000 / closes["SOXL"], "avg_cost": 1})
    ps = {"cash": eq - 75000 - 22000, "positions": pos, "last_prices": {}}
    orders = agent.decide(bull_market, ps, ps["cash"])
    assert [o for o in orders if o["ticker"] == "SOXL" and o["side"] == "sell"]


def test_held_name_without_price_is_still_sold_when_not_targeted(agent, bull_market):
    ps = {"cash": 1000.0, "positions": [{"ticker": "DELISTED", "quantity": 10.0, "avg_cost": 5.0}], "last_prices": {}}
    orders = agent.decide(bull_market, ps, 1000.0)
    assert {"ticker": "DELISTED", "side": "sell", "quantity": 10.0} in orders


def test_sleeve_gap_up_40pct_stays_under_cap_at_close(agent, bull_market):
    """Stress: the 3x sleeve gaps up 40% overnight while leaders are flat (admission checks closes)."""
    from conftest import load_agent
    bars = {t: [dict(b) for b in rows] for t, rows in bull_market.items()}
    for b in bars["SOXL"][110:]:
        for k in ("open", "high", "low", "close"):
            b[k] *= 1.40
    m = Market(bars)
    r = run_admission(load_agent().decide, m, m.dates[100], m.dates[-1])
    assert r["passed"] and r["peak_gross"] < 1.45, r
