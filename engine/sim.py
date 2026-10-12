"""Local mirrors of the two Builderr evaluators (infrastructure layer).

`run_live`      mirrors the public `live_runner.run_bot` fill model used for the Round 2 board:
                decide on bars strictly before the session, fill at that session's OPEN with
                5 bps (10 bps for leveraged ETFs) slippage, sells before buys, buys clamped to
                cash, 30% of equity per name and 1.5x beta gross; mark to the CLOSE.
`run_admission` mirrors the template's `preview.py`: decide after the close with that day's bar,
                fill next OPEN, buys clamped to cash only (no cap clamp), then gate on errors,
                peak beta gross at any close, a >=30% weight held for more than 5 sessions, and
                a >50% drawdown.

Both read bars as {ticker: [{ts, open, high, low, close, volume}, ...]} oldest first.
`history` limits how many past bars the agent sees (the host sends ~220+); it only exists to
keep long backtests fast and never changes what a 63-session signal can see.
"""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right

BETA_3X = {"TQQQ", "SOXL", "UPRO", "SPXL", "TNA", "FAS", "TECL", "LABU", "CURE", "DRN", "UDOW", "NAIL"}
BETA_2X = {"QLD", "SSO", "DDM", "ROM", "UWM", "AGQ"}
SLIP_EQUITY = 0.0005
SLIP_LEVERAGED = 0.0010
MAX_NAME_WEIGHT = 0.30
MAX_BETA_GROSS = 1.50
START_CASH = 100_000.0


def beta(t: str) -> float:
    return 3.0 if t in BETA_3X else 2.0 if t in BETA_2X else 1.0


class Market:
    """Bars indexed by date for O(log n) slicing."""

    def __init__(self, bars: dict):
        self.bars = {t: rows for t, rows in bars.items() if rows}
        self.ts = {t: [b["ts"] for b in rows] for t, rows in self.bars.items()}
        self.by_date = {t: {b["ts"]: b for b in rows} for t, rows in self.bars.items()}
        self.dates = sorted({d for ts in self.ts.values() for d in ts})

    def before(self, date: str, history: int | None = None) -> dict:
        out = {}
        for t, rows in self.bars.items():
            i = bisect_left(self.ts[t], date)
            if i:
                out[t] = rows[max(0, i - history):i] if history else rows[:i]
        return out

    def through(self, date: str, history: int | None = None) -> dict:
        out = {}
        for t, rows in self.bars.items():
            i = bisect_right(self.ts[t], date)
            if i:
                out[t] = rows[max(0, i - history):i] if history else rows[:i]
        return out

    def px(self, t: str, date: str, field: str):
        b = self.by_date.get(t, {}).get(date)
        return None if b is None else b[field]


def _equity(cash, positions, prices):
    return cash + sum(q * prices.get(t, 0.0) for t, q in positions.items())


def run_live(decide, market: Market, start: str, end: str | None = None, history: int | None = 260,
             enforce_limits: bool = True) -> dict:
    """enforce_limits=False mirrors the host's "market context" line (QQQ buy-and-hold)."""
    dates = [d for d in market.dates if d >= start and (end is None or d <= end)]
    cash, positions, avg_cost = START_CASH, {}, {}
    curve, trades, gross_path, maxw_path = [], 0, [], []
    for date in dates:
        open_px = {t: p for t in market.bars if (p := market.px(t, date, "open")) is not None}
        close_px = {t: p for t in market.bars if (p := market.px(t, date, "close")) is not None}
        ms = market.before(date, history)
        prior_close = {t: rows[-1]["close"] for t, rows in ms.items() if rows}
        ps = {"cash": cash,
              "positions": [{"ticker": t, "quantity": q, "avg_cost": avg_cost.get(t, 0.0)}
                            for t, q in positions.items() if q > 0],
              "last_prices": prior_close}
        try:
            orders = decide(ms, ps, cash) or []
        except Exception:  # noqa: BLE001 - mirrors the host: an error is a no-op session
            orders = []
        norm = []
        for o in orders[:100] if isinstance(orders, list) else []:
            try:
                tk, side, qty = str(o["ticker"]).strip().upper(), o["side"], float(o["quantity"])
            except (KeyError, TypeError, ValueError):
                continue
            if side in ("buy", "sell") and math.isfinite(qty) and qty > 0 and tk in open_px:
                norm.append((tk, side, qty))
        for tk, side, qty in sorted(norm, key=lambda x: 0 if x[1] == "sell" else 1):
            px = open_px[tk]
            slip = SLIP_LEVERAGED if beta(tk) > 1 else SLIP_EQUITY
            held = positions.get(tk, 0.0)
            if side == "buy":
                fill = px * (1 + slip)
                eq_open = max(_equity(cash, positions, open_px), 1e-9)
                conc_room = max(0.0, MAX_NAME_WEIGHT * eq_open - held * fill)
                beta_used = sum(q * open_px.get(t, 0.0) * beta(t) for t, q in positions.items())
                beta_room = max(0.0, MAX_BETA_GROSS * eq_open - beta_used)
                room = min(cash, conc_room, beta_room / beta(tk)) if enforce_limits else cash
                qty = min(qty, room / fill)
                if qty <= 0:
                    continue
                avg_cost[tk] = (avg_cost.get(tk, 0.0) * held + fill * qty) / (held + qty)
                positions[tk] = held + qty
                cash -= fill * qty
            else:
                qty = min(qty, held)
                if qty <= 0:
                    continue
                cash += px * (1 - slip) * qty
                positions[tk] = held - qty
            trades += 1
        eq = max(_equity(cash, positions, close_px), 1e-9)
        curve.append(eq)
        vals = {t: q * close_px.get(t, 0.0) for t, q in positions.items()}
        gross_path.append(sum(v * beta(t) for t, v in vals.items()) / eq)
        maxw_path.append(max([v / eq for v in vals.values()] or [0.0]))
    return {"dates": dates, "curve": curve, "ret": (curve[-1] / START_CASH - 1) if curve else 0.0,
            "trades": trades, "gross": gross_path, "maxw": maxw_path,
            "positions": {t: q for t, q in positions.items() if q > 0}, "cash": cash}


def max_drawdown(curve):
    peak, mdd = -1e18, 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    return mdd


def run_admission(decide, market: Market, eval_start: str, eval_end: str, history: int | None = None) -> dict:
    dates = [d for d in market.dates if eval_start <= d <= eval_end]
    cash, positions, avg_cost = START_CASH, {}, {}
    curve, pending = [], []
    peak_gross = peak_conc = 0.0
    streak, worst_streak, trades, errors = {}, 0, 0, 0
    for date in dates:
        for o in pending:
            px = market.px(o["ticker"], date, "open")
            if px is None:
                continue
            slip = SLIP_LEVERAGED if beta(o["ticker"]) > 1 else SLIP_EQUITY
            if o["side"] == "buy":
                fill = px * (1 + slip)
                qty = o["quantity"]
                if fill * qty > cash:
                    qty = cash / fill if fill > 0 else 0
                if qty <= 0:
                    continue
                held = positions.get(o["ticker"], 0.0)
                avg_cost[o["ticker"]] = (avg_cost.get(o["ticker"], 0.0) * held + fill * qty) / (held + qty)
                positions[o["ticker"]] = held + qty
                cash -= fill * qty
                trades += 1
            else:
                held = positions.get(o["ticker"], 0.0)
                qty = min(o["quantity"], held)
                if qty <= 0:
                    continue
                cash += px * (1 - slip) * qty
                positions[o["ticker"]] = held - qty
                trades += 1
        pending = []
        prices = {t: p for t in market.bars if (p := market.px(t, date, "close")) is not None}
        vals = {t: q * prices.get(t, 0.0) for t, q in positions.items()}
        eq = max(cash + sum(vals.values()), 1e-9)
        curve.append(eq)
        peak_gross = max(peak_gross, sum(abs(v) * beta(t) for t, v in vals.items()) / eq)
        for t in market.bars:
            frac = abs(vals.get(t, 0.0)) / eq
            peak_conc = max(peak_conc, frac)
            streak[t] = streak.get(t, 0) + 1 if frac >= MAX_NAME_WEIGHT else 0
            worst_streak = max(worst_streak, streak[t])
        ms = market.through(date, history)
        ps = {"cash": cash,
              "positions": [{"ticker": t, "quantity": q, "avg_cost": avg_cost.get(t, 0.0)}
                            for t, q in positions.items() if q > 0],
              "last_prices": prices}
        try:
            orders = decide(ms, ps, cash)
        except Exception:  # noqa: BLE001
            errors += 1
            orders = []
        for o in orders or []:
            try:
                if o["side"] in ("buy", "sell") and float(o["quantity"]) > 0 and o["ticker"] in market.bars:
                    pending.append({"ticker": o["ticker"], "side": o["side"], "quantity": float(o["quantity"])})
            except (KeyError, TypeError, ValueError):
                errors += 1
    mdd = max_drawdown(curve)
    passed = errors == 0 and peak_gross <= MAX_BETA_GROSS + 1e-6 and worst_streak <= 5 and mdd < 0.50
    return {"ret": (curve[-1] / START_CASH - 1) if curve else 0.0, "mdd": mdd, "peak_gross": peak_gross,
            "peak_conc": peak_conc, "max_conc_streak": worst_streak, "errors": errors, "trades": trades,
            "days": len(curve), "passed": passed}
