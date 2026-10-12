"""RESEARCH COPY of agent.py with switchable rule variants (all off by default = identical to agent.py).
Used only by research/variant.py; tests/test_contract.py checks the defaults match agent.py.

Convex Sprint — Builderr Trading Round 2 agent.

When is it aggressive?  QQQ is above its 20- and 50-session averages, its 10-session realized
volatility is <= 40% a year, and it has not fallen 6% in 5 sessions recently. Then it holds the
3 strongest uptrending stocks at 25% each plus one 3x ETF sleeve (SOXL when semis lead, else
TQQQ) sized so beta-adjusted gross is 1.25.

What forces it to stop?  (1) QQQ closes under its 20-session average or volatility passes 40%:
the 3x sleeve is sold, leaders stay. (2) QQQ closes under its 50-session average, or a -6%
five-session drop in any of the last 3 sessions: everything goes to cash. (3) The account
falls to 90% of its $100,000 start: the sleeve is not allowed again until it recovers.

Single file, standard library only (`math`), no network, no files, no clock, no randomness.
Layers: DOMAIN (pure rules on closes) -> APPLICATION (`decide`: portfolio + market -> orders).
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------- parameters (round numbers)
LEADER_WEIGHT = 0.25        # per leader target
N_LEADERS = 3
TRIM_WEIGHT = 0.28          # any position above this is cut back to target (cap is 30%)
BAND = 0.03                 # re-trade a held target only when it is off by more than 3 points
BETA_TARGET = 1.25          # beta-adjusted gross target in ATTACK (cap is 1.5; room for a 40% overnight sleeve gap)
SLEEVE_MAX = 0.20
GROSS_TRIM = 1.35           # if beta gross drifts above this, every line is reset to target
VOL_LIMIT = 0.40            # QQQ 10-session realized vol, annualized
BRAKE_DROP = -0.06          # QQQ 5-session return that triggers the brake
BRAKE_MEMORY = 3            # brake stays on while any of the last 3 sessions shows the drop
CONFIRM = 3                 # trend tests use 2-of-the-last-3 closes (hysteresis)
KEEP_RANK = 6               # a held leader is kept while it stays uptrending and in the top 6
GOVERNOR = 0.90             # equity / start below this -> no sleeve
START_EQUITY = 100_000.0
CASH_BUFFER = 0.99          # spend at most 99% of available cash (open gaps, slippage)

SINGLES = ("NVDA", "MSFT", "AAPL", "META", "AMZN", "GOOGL", "AVGO", "AMD", "MU", "MRVL",
           "NFLX", "TSLA", "PLTR", "ORCL", "CRM", "JPM", "V", "MA", "COST", "LLY")
FALLBACK_ETFS = ("SMH", "QQQ", "XLK", "SPY")
SEMIS = {"NVDA", "AVGO", "AMD", "MU", "MRVL", "SMH"}
SEMIS_MAX = 3               # leaders allowed from the semiconductor group
SEMIS_SLEEVE_SWITCH = 9     # if this many leaders are semis, the sleeve is TQQQ instead of SOXL
SLEEVE_DAY_DROP = None      # if set: sleeve index (SMH for SOXL, QQQ for TQQQ) last-session return <= this -> no sleeve
SLEEVE_VOL_LIMIT = None     # if set: sleeve index 10-session realized vol above this -> no sleeve
SLEEVE_INDEX = {"SOXL": "SMH", "TQQQ": "QQQ", "QLD": "QQQ"}
LEADERS_BETA = None         # if set: in LEADERS add QLD up to this beta gross
SOXL_INDEX_BRAKE = False    # if True: SMH brake (5-session -6%) blocks SOXL (falls back to TQQQ)
BETA_3X = {"TQQQ", "SOXL", "UPRO", "SPXL", "TNA", "FAS", "TECL", "LABU", "CURE", "DRN", "UDOW", "NAIL"}
BETA_2X = {"QLD", "SSO", "DDM", "ROM", "UWM", "AGQ"}

ATTACK, LEADERS, CASH = "ATTACK", "LEADERS", "CASH"


# ======================================================================= DOMAIN (pure)
def beta(ticker: str) -> float:
    return 3.0 if ticker in BETA_3X else 2.0 if ticker in BETA_2X else 1.0


def sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def period_return(xs, n):
    return xs[-1] / xs[-1 - n] - 1 if len(xs) > n and xs[-1 - n] > 0 else None


def realized_vol(xs, n=10):
    if len(xs) <= n:
        return None
    r = [math.log(xs[i] / xs[i - 1]) for i in range(len(xs) - n, len(xs)) if xs[i - 1] > 0 and xs[i] > 0]
    if len(r) < 2:
        return None
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)


def brake_on(index_closes) -> bool:
    for k in range(BRAKE_MEMORY):
        xs = index_closes[: len(index_closes) - k] if k else index_closes
        r = period_return(xs, 5)
        if r is not None and r <= BRAKE_DROP:
            return True
    return False


def above_average(xs, n, confirm=None) -> bool:
    """Close above its n-session average on at least 2 of the last `confirm` sessions.
    A one-day poke through the average does not flip the regime (no daily whipsaw)."""
    confirm = CONFIRM if confirm is None else confirm
    hits = 0
    for k in range(confirm):
        ys = xs[: len(xs) - k] if k else xs
        m = sma(ys, n)
        if m is None:
            return False
        hits += ys[-1] > m
    return hits >= 2


def regime(index_closes) -> str:
    """ATTACK / LEADERS / CASH from the regime index (QQQ) closes alone."""
    if len(index_closes) < 50 + CONFIRM or brake_on(index_closes):
        return CASH
    if not above_average(index_closes, 50):
        return CASH
    vol = realized_vol(index_closes, 10)
    if above_average(index_closes, 20) and vol is not None and vol <= VOL_LIMIT:
        return ATTACK
    return LEADERS


def in_uptrend(xs) -> bool:
    s20, s50, r63 = sma(xs, 20), sma(xs, 50), period_return(xs, 63)
    return None not in (s20, s50, r63) and xs[-1] > s20 and xs[-1] > s50 and r63 > 0


def momentum_score(xs) -> float:
    return period_return(xs, 63) + (period_return(xs, 21) or 0.0)


def pick_leaders(closes: dict, n: int = N_LEADERS, held=()) -> list:
    """Top-n uptrending single stocks by momentum; 1x index ETFs fill empty slots.
    Held leaders are kept while still uptrending and ranked in the top KEEP_RANK (less churn)."""
    def ranked(pool):
        ok = [t for t in pool if t in closes and in_uptrend(closes[t])]
        return sorted(ok, key=lambda t: (-momentum_score(closes[t]), t))
    order = ranked(SINGLES)
    picks = []
    for t in [t for t in order[:KEEP_RANK] if t in held] + order:
        if len(picks) >= n:
            break
        if t in picks or (t in SEMIS and sum(p in SEMIS for p in picks) >= SEMIS_MAX):
            continue
        picks.append(t)
    for t in ranked(FALLBACK_ETFS):
        if len(picks) >= n:
            break
        if t not in picks:
            picks.append(t)
    return picks


def pick_sleeve(closes: dict):
    q, smh = closes.get("QQQ"), closes.get("SMH")
    if "SOXL" in closes and smh is not None and q is not None:
        s50, r_smh, r_q = sma(smh, 50), period_return(smh, 21), period_return(q, 21)
        if None not in (s50, r_smh, r_q) and smh[-1] > s50 and r_smh > r_q:
            return "SOXL"
    for t in ("TQQQ", "QLD"):
        if t in closes:
            return t
    return None


def target_weights(closes: dict, equity_ratio: float, held=()) -> dict:
    """{ticker: weight of equity}. Weights <= LEADER_WEIGHT; beta gross <= BETA_TARGET."""
    index = closes.get("QQQ") or closes.get("SPY")
    if not index:
        return {}
    mode = regime(index)
    if mode == CASH:
        return {}
    weights = {t: LEADER_WEIGHT for t in pick_leaders(closes, held=held)}
    if mode == LEADERS and LEADERS_BETA is not None and equity_ratio > GOVERNOR and "QLD" in closes:
        used = sum(w * beta(t) for t, w in weights.items())
        room = min((LEADERS_BETA - used) / 2.0, 1.0 - sum(weights.values()) - 0.01)
        if room > 0.01:
            weights["QLD"] = room
    if mode == ATTACK and equity_ratio > GOVERNOR:
        sleeve = pick_sleeve(closes)
        if sleeve == "SOXL" and SOXL_INDEX_BRAKE and brake_on(closes.get("SMH", [])):
            sleeve = "TQQQ" if "TQQQ" in closes else None
        if sleeve == "SOXL" and sum(t in SEMIS for t in weights) >= SEMIS_SLEEVE_SWITCH and "TQQQ" in closes:
            sleeve = "TQQQ"
        idx = closes.get(SLEEVE_INDEX.get(sleeve, ""), []) if sleeve else []
        if sleeve and SLEEVE_DAY_DROP is not None and len(idx) > 1 and idx[-1] / idx[-2] - 1 <= SLEEVE_DAY_DROP:
            sleeve = None
        if sleeve and SLEEVE_VOL_LIMIT is not None and (realized_vol(idx, 10) or 9.9) > SLEEVE_VOL_LIMIT:
            sleeve = None
        if sleeve and sleeve not in weights:
            used_beta = sum(w * beta(t) for t, w in weights.items())
            room = min(SLEEVE_MAX, (BETA_TARGET - used_beta) / beta(sleeve), 1.0 - sum(weights.values()) - 0.01)
            if room > 0.01:
                weights[sleeve] = room
    return weights


def plan_orders(targets: dict, holdings: dict, prices: dict, cash: float) -> list:
    """Turn target weights into orders: sells first, buys capped by cash after sells."""
    equity = cash + sum(q * prices.get(t, 0.0) for t, q in holdings.items())
    if equity <= 0:
        return []
    gross = sum(q * prices.get(t, 0.0) * beta(t) for t, q in holdings.items()) / equity
    sells, buys = [], []
    for t, q in sorted(holdings.items()):
        if q <= 0:
            continue
        p = prices.get(t)
        if t not in targets:
            sells.append({"ticker": t, "side": "sell", "quantity": q})
            continue
        if not p or p <= 0:
            continue
        w = q * p / equity
        if w > TRIM_WEIGHT or abs(w - targets[t]) > BAND or gross > GROSS_TRIM:
            delta = (targets[t] - w) * equity / p
            if delta < 0:
                sells.append({"ticker": t, "side": "sell", "quantity": min(q, -delta)})
            elif delta > 0:
                buys.append((t, delta, p))
    for t in sorted(targets):
        if holdings.get(t, 0) > 0:
            continue
        p = prices.get(t)
        if p and p > 0:
            buys.append((t, targets[t] * equity / p, p))
    spendable = (cash + sum(o["quantity"] * prices.get(o["ticker"], 0.0) for o in sells)) * CASH_BUFFER
    need = sum(q * p for _, q, p in buys)
    scale = min(1.0, spendable / need) if need > 0 else 0.0
    out = [dict(o, quantity=round(o["quantity"], 6)) for o in sells if o["quantity"] > 0]
    for t, q, p in buys:
        qty = math.floor(q * scale * 1e4) / 1e4
        if qty > 0:
            out.append({"ticker": t, "side": "buy", "quantity": qty})
    return out


# ================================================================== APPLICATION
def decide(market_state, portfolio_state, cash):
    closes = {}
    for t, bars in (market_state or {}).items():
        try:
            xs = [float(b["close"]) for b in bars[-80:]]
        except (KeyError, TypeError, ValueError):
            continue
        if xs and all(x > 0 and math.isfinite(x) for x in xs):
            closes[t] = xs
    if not closes.get("QQQ") and not closes.get("SPY"):
        return []
    portfolio_state = portfolio_state or {}
    cash = float(portfolio_state.get("cash", cash) or 0.0)
    last = portfolio_state.get("last_prices") or {}
    prices = {t: xs[-1] for t, xs in closes.items()}
    for t, p in last.items():
        try:
            if float(p) > 0:
                prices[t] = float(p)
        except (TypeError, ValueError):
            continue
    holdings = {}
    for p in portfolio_state.get("positions") or []:
        try:
            q = float(p.get("quantity") or 0)
        except (TypeError, ValueError):
            continue
        if q > 0:
            holdings[str(p.get("ticker"))] = holdings.get(str(p.get("ticker")), 0.0) + q
    equity = cash + sum(q * prices.get(t, 0.0) for t, q in holdings.items())
    targets = target_weights(closes, equity / START_EQUITY, held=set(holdings))
    return plan_orders(targets, holdings, prices, cash)
