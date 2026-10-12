from conftest import trend_bars


def closes(**kw):
    return [b["close"] for b in trend_bars(**kw)]


def test_calm_uptrend_is_attack(agent):
    assert agent.regime(closes(daily=0.003)) == agent.ATTACK


def test_downtrend_is_cash(agent):
    assert agent.regime(closes(daily=-0.003)) == agent.CASH


def test_brake_after_six_percent_drop(agent):
    assert agent.regime(closes(daily=0.004, shock_at=118, shock=-0.09)) == agent.CASH


def test_brake_memory_three_sessions(agent):
    xs = closes(daily=0.004, shock_at=110, shock=-0.09)
    assert agent.brake_on(xs[:112]) and not agent.brake_on(xs)


def test_short_history_is_cash(agent):
    assert agent.regime(closes(n=30, daily=0.01)) == agent.CASH


def test_high_vol_uptrend_is_leaders(agent):
    xs, px = [], 100.0
    for i in range(120):
        px *= 1.004 + (0.035 if i % 2 else -0.03) * (i > 105)
        xs.append(px)
    assert agent.regime(xs) == agent.LEADERS
