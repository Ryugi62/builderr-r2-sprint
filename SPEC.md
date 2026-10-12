# SPEC — Convex Sprint (Builderr Trading Round 2 agent)

## Purpose
A single-file, standard-library `decide()` agent for the Builderr Trading Round 2 paper account.
Round 2 ranks entrants by **raw percentage return from each bot's first scored session**, and a
prize requires beating the Round 1 winner's Round 2 forward return. An entry submitted on
2026-10-12 has 13–15 scored sessions (Oct 12–14 start, last session Oct 30; about 10 if loading is delayed). The agent is built for that
situation: it puts as much *within-rules* variance as possible behind the strongest trend, and it
has explicit, numeric rules for when it must stop being aggressive.

## Ubiquitous language (same words in code)
| Term | Meaning |
|---|---|
| **session** | one US market day; orders decided on prior closes fill at that session's open |
| **regime** | `ATTACK`, `LEADERS` or `CASH`, decided from QQQ closes only |
| **leaders** | up to 3 single stocks (or 1x index ETFs as fallback) in an uptrend, ranked by momentum |
| **sleeve** | one 3x ETF (SOXL when semis lead, else TQQQ) used only in `ATTACK` |
| **beta gross** | sum(weight x beta), beta = 3 for 3x ETFs, 2 for 2x ETFs, 1 otherwise (the challenge's "Beta multiples" table) |
| **return** | account value at the last session's close / $100,000 - 1, counted from the first scored session (the board's definition) |
| **brake** | QQQ 5-session return <= -6% on any of the last 3 sessions |
| **governor** | account equity <= 90% of the $100,000 start -> sleeve removed |

## Rules the code implements
- Trend tests use **2 of the last 3 closes** above the average (hysteresis), so a one-day poke through an average does not flip the regime.
- `ATTACK`: QQQ above SMA20 and SMA50 (2-of-3), QQQ 10-session realized vol <= 40% annualized, no brake.
  Book = 3 leaders x 25% + sleeve sized so beta gross = 1.25 (sleeve <= 20%).
- `LEADERS`: QQQ above SMA50 (2-of-3) but not `ATTACK`, no brake. Book = 3 leaders x 25%, no sleeve (beta gross <= 0.75).
- `CASH`: QQQ not above SMA50 (2-of-3), or brake, or < 53 sessions of history. Book = all cash.
- Leaders: close > SMA20, close > SMA50, 63-session return > 0; score = 63-session return + 21-session return.
  A held leader is kept while it still qualifies and ranks in the top 6 (less churn); empty slots go to the best new names, then to 1x ETFs (SMH, QQQ, XLK, SPY).
- Governor: equity <= 90% of the $100,000 start -> no sleeve (stateless; read from cash + positions).
- Trading band: a held target is re-traded only when |weight - target| > 3 points; any weight > 28% is trimmed back to target;
  if beta gross > 1.35, every line is reset to target.

## Success conditions (fixed before the backtest was run)
| # | Condition | Threshold |
|---|---|---|
| S1 | Local admission mirror (`engine/sim.py::run_admission`, same checks as the template's `preview.py`) on the 3 public sample windows + 2 extra stress windows (2022-03-01..2022-06-30, 2025-02-18..2025-05-30) | PASS on all: errors 0, peak beta gross <= 1.5 at every close, no >=30% weight held > 5 sessions, max drawdown < 50% |
| S2 | No lookahead | the order list for session *d* is identical when every bar after *d-1* is deleted or randomized |
| S3 | Caps | target weight <= 25% per name, trim above 28%, target beta gross <= 1.25, reset above 1.35; over 2022-2026 real data replay (live mirror) the highest close beta gross < 1.5 and no >= 30% weight for 2 consecutive closes |
| S4 | Runtime | `decide()` <= 0.5 s per call on 42 tickers x 500 bars (limit is 5 s) |
| S5 | Determinism, no I/O | same input -> same output; the agent imports only `math` (AST test) |
| S6 | Tournament fitness, every 15-session window 2022-03..2026-10 (live mirror) | P(return >= +6%) >= 20%; P(return > -2.99%) >= 65% |
| S7 | Same period as the Round 1 winner's official Round 2 curve (2026-07-07..10-09) — the prize rule compares an entrant's return with the Round 1 winner's **full-round** return (`qualified = ret > benchmark_ret`) | full-window return > -2.99% |

## Given / When / Then
- **Given** QQQ closed above its SMA20 and SMA50 with calm volatility, **when** `decide()` runs with no positions, **then** it buys 3 leaders and one 3x sleeve, and the projected beta gross is <= 1.25.
- **Given** QQQ fell 7% over 5 sessions, **when** `decide()` runs holding a full book, **then** it returns sell orders for every position.
- **Given** a held leader drifted to 29% of equity, **when** `decide()` runs, **then** it sells that leader back to 25%.
- **Given** bars after the decision date are changed, **when** `decide()` runs, **then** the orders do not change.
- **Given** a ticker is missing from `market_state` (admission windows carry ~21 tickers), **when** `decide()` runs, **then** it skips that ticker without error.

## Non-goals
- No ML model training, no LLM, no network, no external data.
- No intraday logic (the engine is daily).
- Not a fit to any single window. Parameters started as round numbers set before the first backtest; the beta target was later lowered twice for cap room, and the two churn rules added after v0 were added after seeing the Round 2 window (see change log), so the Round 2 number in S7 is in-sample and is reported as such.
- Not a recommendation to trade real money.

## Architecture note
The host loads one Python file (`agent.py`) by path, so the agent ships as a single stdlib file.
Inside it the layers are kept apart: **domain** (pure math and rules, no I/O) -> **application**
(`decide()` turns portfolio + market into orders). The backtest engine, research scripts and
tests are separate packages that import the agent; the agent imports nothing from them.

## Change log against these conditions
- v0 (first run): S1–S6 passed; **S7 failed** (Round 2 window −4.78%, beat the Round 1 winner in 44% of sub-windows).
  Cause found in the daily log: the regime flipped between ATTACK and LEADERS almost daily around SMA20 and the
  leader list churned daily. Fix: 2-of-3 confirmation and the keep-rank rule (both generic churn controls).
  The fix also raised P(return >= +6%) on the 2022-03..2024-09 windows that S7 does not touch (137/650 = 21.1% -> 149/650 = 22.9% in v2),
  so it is not only a fit to the Round 2 window. The S7 thresholds were not changed.
- v1 -> v2: beta target 1.35 -> 1.30 and drift reset 1.42 -> 1.40, to keep the highest close beta gross in the
  4.5-year replay at 1.43 instead of 1.49 (more room under the 1.5x admission cap).
- Red-team fix (before submission): S7 originally also asked to beat the Round 1 winner in >= 55% of 15-session
  sub-windows. The board's rule compares with the winner's full-round return, so that sub-window share is kept in
  `results/backtest.json` as reference only and is no longer a condition. The prize-relevant number is S6's
  P(return > -2.99%).

## Caveats on S6 numbers
- The 1,144 windows overlap; non-overlapping 15-session blocks and per-year splits are in `results/backtest.json`.
- The single-stock list is the live board's fetch list (2026). It contains names that later led (PLTR, MU, MRVL,
  AVGO), which flatters 2022-2024 windows; a run without those four is in `results/backtest.json`.
- v2 -> v3 (mock review): beta target 1.30 -> 1.25 and reset 1.35, after a synthetic +40% overnight gap in the
  3x sleeve took the admission-style close gross to 1.478 (`tests/test_caps.py::test_sleeve_gap_up_40pct_stays_under_cap_at_close`).
  A held name with no price is now sold when it is not a target; above the reset level every line is re-traded.
- Rule ideas from reviewers that were tested and **not** adopted (results/variants.jsonl): at most 2 semis
  leaders; TQQQ instead of SOXL when 2+ leaders are semis; sleeve off below 97% of start; sleeve off after a
  -3%/-4% sleeve-index day; sleeve off when SMH 10-session vol > 35%; QQQ vol limit 30%. None raised both
  P(return >= +6%) and P(return > -2.99%); all lowered the first by 0.2-1.9 points.
- v3 -> v4 (second review): rule-variant switches moved out of the scored file into `research/agent_research.py`
  (defaults trade identically — tested); one bad bar is skipped instead of dropping the ticker; malformed portfolio
  entries are ignored. Trading behaviour unchanged (same backtest numbers). Two more variants tested and not adopted:
  SMH brake for SOXL (+0.3 pt prize-bar odds, 0 pt top-3 odds) and QLD in LEADERS (+0.2/+0.3 pt) — inside the noise.
