"""Backtests for the README and the success conditions in SPEC.md (S1, S3, S6, S7).

Return = account value at the last session's close / $100,000 - 1, counted from the first scored
session (the board's definition).

python research/backtest.py            # needs data/bars5y.json (research/fetch_bars.py)
Writes results/backtest.json and prints a summary. All runs use engine/sim.py, whose QQQ
buy-and-hold matches the official Round 2 market curve to within 0.07% (see results).
"""
import importlib.util
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.sim import Market, run_admission, run_live, max_drawdown  # noqa: E402

WINDOW = 15
OFFICIAL = ROOT / "data" / "official_round2_results_2026-10-09.json"
HISTORY = ROOT / "data" / "official_round2_history_2026-10-09.json"


SINGLES_FOR_CHECK = ("NVDA", "MSFT", "AAPL", "META", "AMZN", "GOOGL", "AMD", "NFLX", "TSLA", "ORCL", "CRM",
                     "JPM", "V", "MA", "COST", "LLY")


def fresh(path=ROOT / "agent.py", **overrides):
    spec = importlib.util.spec_from_file_location("agent_bt", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k, v in overrides.items():
        setattr(mod, k, v)
    return mod.decide


def buy_hold(ticker):
    def decide(ms, ps, cash):
        if ps["positions"] or ticker not in ms:
            return []
        return [{"ticker": ticker, "side": "buy", "quantity": float(int(cash * 0.999 // ms[ticker][-1]["close"]))}]
    return decide


def windows(market, start, end, n=WINDOW):
    ds = [d for d in market.dates if start <= d <= end]
    return [(ds[i], ds[i + n - 1]) for i in range(0, len(ds) - n + 1)]


def rolling(market, make, start, end, n=WINDOW, enforce_limits=True):
    out = []
    for a, b in windows(market, start, end, n):
        r = run_live(make(), market, a, b, history=80, enforce_limits=enforce_limits)
        out.append({"start": a, "end": b, "ret": r["ret"], "max_gross": max(r["gross"]), "maxw": r["maxw"]})
    return out


def stats(rets):
    s = sorted(rets)
    return {"n": len(s), "p_ge_6pct": sum(r >= 0.06 for r in s) / len(s), "p_ge_8_5pct": sum(r >= 0.085 for r in s) / len(s),
            "p_gt_arnav_gate": sum(r > -0.0299 for r in s) / len(s), "median": statistics.median(s),
            "p10": s[len(s) // 10], "p90": s[9 * len(s) // 10], "worst": s[0], "best": s[-1]}


def main():
    bars = json.load(open(ROOT / "data" / "bars5y.json"))
    m = Market(bars)
    res = {}
    # S6 — every 15-session window
    ours = rolling(m, fresh, "2022-03-01", "2026-10-09")
    qqq = rolling(m, lambda: buy_hold("QQQ"), "2022-03-01", "2026-10-09", enforce_limits=False)
    res["S6_rolling_15"] = {"agent": stats([w["ret"] for w in ours]), "qqq_buy_hold": stats([w["ret"] for w in qqq])}
    streak_fail = 0
    for w in ours:
        st = 0
        for x in w["maxw"]:
            st = st + 1 if x >= 0.30 else 0
            streak_fail += st >= 2
    adm_all = run_admission(fresh(), m, "2022-03-01", "2026-10-09", history=80)
    res["S3_caps_replay"] = {"max_close_beta_gross": max(w["max_gross"] for w in ours),
                             "windows_with_30pct_two_closes": streak_fail,
                             "admission_engine_continuous_2022_2026": {k: adm_all[k] for k in
                                 ("peak_gross", "peak_conc", "max_conc_streak", "mdd", "errors", "passed", "days")}}
    import hashlib
    res["data_snapshot"] = {"file": "data/bars5y.json (not committed; research/fetch_bars.py)",
                            "sha256": hashlib.sha256((ROOT / "data" / "bars5y.json").read_bytes()).hexdigest(),
                            "fetched": "2026-10-12 (Yahoo chart API, adjusted)", "last_bar": max(m.dates)}
    # Independence caveat: non-overlapping 15-session blocks, and per calendar year
    blocks = [w["ret"] for w in ours[::WINDOW]]
    p6 = sum(r >= 0.06 for r in blocks) / len(blocks)
    res["S6_nonoverlapping_blocks"] = {"n": len(blocks), "p_ge_6pct": p6, "p_ge_8_5pct": sum(r >= 0.085 for r in blocks) / len(blocks),
                                       "p_gt_arnav_gate": sum(r > -0.0299 for r in blocks) / len(blocks),
                                       "se_p_ge_6pct": (p6 * (1 - p6) / len(blocks)) ** 0.5}
    res["S6_by_start_year"] = {y: stats([w["ret"] for w in ours if w["start"].startswith(y)])
                               for y in ("2022", "2023", "2024", "2025", "2026")}
    # Hindsight check: drop the four singles that became 2025-26 leaders
    hs = SINGLES_FOR_CHECK
    rr = rolling(m, lambda: fresh(SINGLES=hs), "2022-03-01", "2026-10-09")
    res["S6_without_PLTR_MU_MRVL_AVGO"] = stats([w["ret"] for w in rr])
    # Moving bar: model each current top-3 entrant's next 15 sessions as beta x QQQ over the same
    # window (beta fitted on their official Round 2 daily curve), and count windows where this agent
    # ends above that moved bar.
    off0 = json.load(open(OFFICIAL))
    mk = json.load(open(HISTORY))["market"]["curve"]
    qret = [mk[i] / mk[i - 1] - 1 for i in range(1, len(mk))]
    bars_mv = {}
    for name in ("opu", "vishwas", "sham", "arnav"):
        c = off0[name]["curve"]
        n = len(c)
        rr_ = [c[i] / c[i - 1] - 1 for i in range(len(c) - n + 1, n)]
        q_ = qret[-len(rr_):]
        mq = sum(q_) / len(q_); mr = sum(rr_) / len(rr_)
        b = sum((a - mq) * (r - mr) for a, r in zip(q_, rr_)) / sum((a - mq) ** 2 for a in q_)
        bars_mv[name] = {"now": off0[name]["ret"], "beta": b}
    qq = {w["start"]: w["ret"] for w in qqq}
    first, third = bars_mv["opu"], bars_mv["sham"]
    beat1 = [w["ret"] > (1 + first["now"]) * (1 + first["beta"] * qq[w["start"]]) - 1 for w in ours]
    beat3 = [w["ret"] > (1 + third["now"]) * (1 + third["beta"] * qq[w["start"]]) - 1 for w in ours]
    ar = bars_mv["arnav"]
    gate_ours = [w["ret"] > (1 + ar["now"]) * (1 + ar["beta"] * qq[w["start"]]) - 1 for w in ours]
    gate_qqq = [qq[w["start"]] > (1 + ar["now"]) * (1 + ar["beta"] * qq[w["start"]]) - 1 for w in ours]
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("agent_regime", ROOT / "agent.py"); _A = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_A)
    att = [_A.regime([b["close"] for b in m.before(w["start"], 80)["QQQ"]]) == _A.ATTACK for w in ours]
    res["attack_start"] = {"n": sum(att),
                           "agent": stats([w["ret"] for w, a in zip(ours, att) if a]),
                           "qqq_buy_hold": stats([qq[w["start"]] for w, a in zip(ours, att) if a])}
    res["moving_prize_bar"] = {"arnav_beta": ar["beta"], "p_agent_above": sum(gate_ours) / len(gate_ours),
                               "p_qqq_above": sum(gate_qqq) / len(gate_qqq)}
    ours13 = rolling(m, fresh, "2022-03-01", "2026-10-09", n=13)
    qqq13 = rolling(m, lambda: buy_hold("QQQ"), "2022-03-01", "2026-10-09", n=13, enforce_limits=False)
    res["S6_rolling_13"] = {"agent": stats([w["ret"] for w in ours13]), "qqq_buy_hold": stats([w["ret"] for w in qqq13])}
    res["moving_bar"] = {"entrants": bars_mv, "p_above_current_1st_moved": sum(beat1) / len(beat1),
                         "p_above_current_3rd_moved": sum(beat3) / len(beat3),
                         "note": "ignores other entrants and late entrants; a bar model, not a forecast"}
    # Continuous replay 2022-03 .. 2026-10 (one account), and a data sanity check
    cont = run_live(fresh(), m, "2022-03-01", "2026-10-09", history=80)
    dr = [cont["curve"][i] / cont["curve"][i - 1] - 1 for i in range(1, len(cont["curve"]))]
    yrs = len(cont["curve"]) / 252
    res["continuous_2022_2026"] = {"sessions": len(cont["curve"]), "total_ret": cont["ret"],
                                   "cagr": (1 + cont["ret"]) ** (1 / yrs) - 1, "max_drawdown": max_drawdown(cont["curve"]),
                                   "worst_day": min(dr), "best_day": max(dr)}
    jumps = []
    for t, rows in bars.items():
        for a, b in zip(rows, rows[1:]):
            r = b["close"] / a["close"] - 1
            if abs(r) > (0.45 if t in ("SOXL", "TQQQ", "UPRO", "SPXL") else 0.30):
                jumps.append([t, b["ts"], round(r, 4)])
    res["data_check_large_daily_moves"] = jumps
    hm = json.load(open(HISTORY))
    qb = {r["ts"]: r for r in bars["QQQ"]}
    o = qb[hm["dates"][0]]["open"] * 1.0005
    res["mirror_check_qqq_vs_official_market_curve_max_rel_err"] = max(
        abs(100000 / o * qb[d]["close"] - v) / v for d, v in zip(hm["dates"], hm["market"]["curve"]))
    res["qqq_official_round2_ret"] = hm["market"]["curve"][-1] / 100000 - 1
    # last-2-years subset (2024-10 .. 2026-10)
    recent = [w["ret"] for w in ours if w["start"] >= "2024-10-01"]
    res["S6_rolling_15_last_2y"] = stats(recent)
    # S7 — same period as the Round 1 winner's official Round 2 curve
    off = json.load(open(OFFICIAL))
    hist = json.load(open(HISTORY))
    dates = hist["dates"]
    arnav = off["arnav"]["curve"]
    full = run_live(fresh(), m, dates[0], dates[-1], history=80)
    sub = []
    for i in range(0, len(dates) - WINDOW + 1):
        a_prev = 100000.0 if i == 0 else arnav[i - 1]
        a_ret = arnav[i + WINDOW - 1] / a_prev - 1
        o = run_live(fresh(), m, dates[i], dates[i + WINDOW - 1], history=80)["ret"]
        sub.append({"start": dates[i], "agent": o, "arnav": a_ret})
    res["S7_round2_same_period"] = {
        "window": [dates[0], dates[-1]], "agent_ret": full["ret"], "agent_mdd": max_drawdown(full["curve"]),
        "arnav_official_ret": off["arnav"]["ret"], "leader_official_ret": max(v["ret"] for v in off.values()),
        "note": "prize rule = entrant return > Round 1 winner's FULL Round 2 return (live_runner qualified); sub-window shares are reference only",
        "subwindows": len(sub), "agent_beats_arnav_share": sum(s["agent"] > s["arnav"] for s in sub) / len(sub),
        "agent_sub_median": statistics.median(s["agent"] for s in sub),
        "arnav_sub_median": statistics.median(s["arnav"] for s in sub),
        "agent_sub_p_ge_6pct": sum(s["agent"] >= 0.06 for s in sub) / len(sub),
        "agent_curve": [round(x, 2) for x in full["curve"]],
    }
    # Round 1 window: the 16 sessions that closed on 2026-07-02 (official winner +5.91%)
    ds = [d for d in m.dates if d <= "2026-07-02"][-16:]
    r1 = run_live(fresh(), m, ds[0], ds[-1], history=80)
    res["round1_window"] = {"window": [ds[0], ds[-1]], "agent_ret": r1["ret"], "arnav_official_ret": 0.0591,
                            "qqq_buy_hold": run_live(buy_hold("QQQ"), m, ds[0], ds[-1], enforce_limits=False)["ret"]}
    # S1 — admission mirror: 3 public windows + 2 stress windows
    import gzip
    raw = json.loads(gzip.open(ROOT / "sample_regimes.json.gz", "rb").read())
    adm = {}
    for k, v in raw.items():
        bb = {t: [{"ts": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in rows]
              for t, rows in v["bars"].items()}
        adm[k] = run_admission(fresh(), Market(bb), v["eval_start"], v["eval_end"])
    for k, (a, b) in {"stress_2022_rate_selloff": ("2022-03-01", "2022-06-30"),
                      "stress_2025_tariff_crash": ("2025-02-18", "2025-05-30")}.items():
        adm[k] = run_admission(fresh(), m, a, b, history=260)
    res["S1_admission_mirror"] = adm
    # Sensitivity: each parameter +/-20%, rolling 15 over the full span
    sens = {}
    grid = {"VOL_LIMIT": (0.32, 0.48), "BRAKE_DROP": (-0.048, -0.072), "LEADER_WEIGHT": (0.20, 0.27),
            "BETA_TARGET": (1.04, 1.40), "CONFIRM": (2, 4), "KEEP_RANK": (5, 7)}
    for name, vals in grid.items():
        for val in vals:
            rr = rolling(m, lambda: fresh(**{name: val}), "2022-03-01", "2026-10-09")
            sens[f"{name}={val}"] = {k: round(v, 4) for k, v in stats([w["ret"] for w in rr]).items()}
    res["sensitivity"] = sens
    (ROOT / "results").mkdir(exist_ok=True)
    json.dump(res, open(ROOT / "results" / "backtest.json", "w"), indent=1)
    short = {k: v for k, v in res.items() if k != "S7_round2_same_period"}
    s7 = {k: v for k, v in res["S7_round2_same_period"].items() if k != "agent_curve"}
    print(json.dumps(short, indent=1, default=str)[:6000])
    print(json.dumps(s7, indent=1))


if __name__ == "__main__":
    main()
