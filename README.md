# Convex Sprint — a Builderr Trading Round 2 agent

**What only this entry has:** exposure sized for the window a late Round 2 entry actually gets. Rank is raw return from the first scored session and 13–15 sessions are left, so the book runs at beta-adjusted gross 1.30 (3 leaders + a 3x sleeve) only while three numeric conditions hold — and the README publishes how often that plan cleared a top-3-sized bar in past 15-session windows, including the windows where it lost.

`agent.py` is one standard-library file (`import math` only): no network, no files, no clock, no LLM.

## When is it aggressive, and what forces it to stop?

| State | When (QQQ closes only; "above" = on 2 of the last 3 closes) | Book |
|---|---|---|
| **ATTACK** | QQQ above its 20- and 50-session averages, 10-session realized vol <= 40%/yr, no brake | 3 strongest uptrending stocks x 25% + one 3x sleeve (SOXL when semis lead QQQ over 21 sessions, else TQQQ) sized to **beta-adjusted gross 1.30** |
| **LEADERS** | QQQ above its 50-session average but not ATTACK | the same 3 leaders x 25%, **no sleeve** (gross <= 0.75) |
| **CASH** | QQQ not above its 50-session average, **or** QQQ fell >= 6% over 5 sessions on any of the last 3 sessions | **all cash** |

Also: if the account falls to 90% of its $100,000 start, the sleeve is not used again until it recovers. A leader is kept while it still trends and ranks in the top 6 (no daily churn). Any line above 28% is cut back to target; if beta gross drifts above 1.40 the leveraged line is reset.

## Results (simulation)

All numbers are **backtests** on daily Yahoo bars (split/dividend adjusted, as the board uses) run through `engine/sim.py`, a mirror of the board's `run_bot` fill model: decide on prior closes, fill at the open with 5/10 bps slippage, sells first, buys clamped to cash, 30% per name and 1.5x beta gross, marked at the close. Check of the mirror: QQQ buy-and-hold over 2026-07-07..10-09 matches the official market curve within 0.07% on every day.

**Return** below always means: account value at the last session's close / $100,000 − 1, counted from the first scored session (the board's definition).

**Every 15-session window, 2022-03-01 .. 2026-10-09** (1,144 windows; they overlap, so they are not 1,144 independent tries):

| | P(return >= +6%) | P(return >= +8.5%) | P(return > −2.99%) | median | 10th pct | 90th pct | worst |
|---|---|---|---|---|---|---|---|
| This agent | **28.8%** | **18.6%** | 76.6% | 0.0% | −6.4% | +12.1% | −23.0% |
| QQQ buy and hold | 13.8% | 6.5% | 80.7% | +1.6% | −5.6% | +7.2% | −15.5% |

+6% and +8.5% are roughly the current #3 and #1 returns on the Round 2 board (2026-10-09). −2.99% is the Round 1 winner's full Round 2 return — the prize bar is an entrant's return above that number (it will move until Oct 30).

How much to trust these probabilities:
- Non-overlapping 15-session blocks (77): P(>= +6%) 31.2% ± 5.3% (one standard error), P(>= +8.5%) 19.5%.
- By start year, P(>= +6%): 2022 4.7% · 2023 30.4% · 2024 36.9% · 2025 35.2% · 2026 34.4%. In a falling market (2022) the bot mostly sits in cash, so it rarely reaches the bar.
- The stock list is the board's 2026 fetch list, which includes later leaders. Without PLTR, MU, MRVL and AVGO: P(>= +6%) 23.1%, P(>= +8.5%) 15.5%.

**Same period as the Round 1 winner's official Round 2 curve** (2026-07-07 .. 2026-10-09, 68 sessions):

![equity curves](docs/round2_window.svg)

| | Full window (68 sessions) | Max drawdown |
|---|---|---|
| This agent (backtest) | **+3.37%** | 8.1% |
| Round 1 winner (official) | −2.99% | — |
| QQQ buy and hold (official) | +5.32% | — |

Over the full window QQQ alone did better: the agent was in cash for 25 of the 68 sessions (13 in a row from Jul 20) and missed part of the August recovery.

**Round 1 window** (16 sessions closing 2026-07-02, where the Round 1 winner made +5.91%): this agent **−5.57%** (QQQ +1.6%). Semis fell 9% on 2026-06-05 and the book lost 15.9% that day. That is the cost of the variance above.

**Admission mirror** (`engine/sim.py::run_admission`, the same checks as the template's `preview.py`): PASS on the 3 public sample windows and on two extra stress windows (2022-03..06 rate sell-off, 2025-02..05 tariff crash). Highest close beta gross 1.378, worst drawdown 12.9%, no line >= 30% on any close.

**Sensitivity** (vol limit, brake, leader weight, beta target 1.04–1.40, confirmation 2–4 closes, keep-rank 5–7): P(return >= +6%) stays between 24.0% and 29.3%.

## Pre-submit checklist (from the challenge page)

| Challenge rule | Where it is checked |
|---|---|
| No `.env` and no API keys committed | `.gitignore`; the agent needs no key |
| `preview.py` clears the safety bar | `tests/test_caps.py::test_admission_mirror_passes_public_windows` (same checks, same sample windows) |
| Every position under the 30% cap; gross under 1.5x | targets 25% / gross 1.30; `tests/test_caps.py`; 4.5-year replay highest close gross 1.43, no line >= 30% two closes in a row |
| No external data for the regime dates (lookahead) | agent imports only `math`; `tests/test_lookahead.py` scrambles every future bar and checks the orders and the equity path up to that day do not change |
| Runs with only the bars it is given | `tests/test_contract.py` (missing tickers, bad bars, single file copied alone like `private_agents/`) |

## How it compares

| Strategy | How it works | What this entry does differently |
|---|---|---|
| Round 1 winner ([builderr-ai/builderr-trading-round-1-winner](https://github.com/builderr-ai/builderr-trading-round-1-winner)) | 5 momentum leaders, CASH/NEUTRAL/FULL, QLD/SSO only in FULL, −6%/−10% drawdown taper, 8% trailing stops | 3 leaders and a 3x sleeve: more variance per session for a 15-session window; stops are regime-level, not per-name |
| Template agent "Forward-Return Rotation Hybrid" ([builderr-ai/builderr-trading-template](https://github.com/builderr-ai/builderr-trading-template)) | ETFs + mega-caps ranked by 60/20-day momentum, defensive sector book when risk-off, small QLD/SSO overlay, gross <= 1.35 | goes to cash instead of defensive sectors; leveraged line is 3x and chosen by which index leads |
| ANATOMY.md "AI play" recipe (same repo) | top 4 of NVDA/AMD/MU/MRVL/AVGO/SMH, 25% each, cash when QQQ < 100-day average | wider universe (20 large caps), 2-of-3 hysteresis, 3x sleeve, 6% crash brake |
| Seed dual momentum (same repo, `seed_dual_momentum.py`) | SPY 60-day gate; top 3 sector ETFs when on, XLP + XLU when off; weekly; no leverage | single names and a 3x sleeve; cash (not staples/utilities) when off; checks daily |

## Run it

```bash
python -m pytest -q                 # 26 tests: contract, caps, lookahead, regime
python research/fetch_bars.py       # optional: daily bars for the board's 42 tickers (not committed)
python research/backtest.py         # writes results/backtest.json
python research/chart.py            # writes docs/round2_window.svg
```

`SPEC.md` holds the purpose, the success conditions fixed before the first backtest, Given/When/Then cases, and a change log (v0 failed the same-period condition; what was changed and why).

## Limits

- Backtests are simulations on past data. Live results will differ; nothing here predicts Oct 2026.
- This is a high-variance book on purpose. In about 10% of past 15-session windows it lost more than 6.4%; the worst lost 23.0%.
- Stops are regime-level (QQQ), not per stock: one bad semis day can cost 15%+ before the next decision.
- Caps are checked at daily closes. Intraday leverage is not measured (the engine is daily).
- Parameters are round numbers set before the first backtest; two churn rules were added after the first run (see `SPEC.md` change log).
- Not investment advice. Paper-trading challenge entry only.

`data/sample_regimes.json.gz` is from the MIT-licensed builderr trading template. `data/official_round2_*.json` are the board's published numbers (template repo, 2026-10-09). License: MIT.
