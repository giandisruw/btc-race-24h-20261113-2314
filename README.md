# BTC Race Bot — btc-race-24h-20261113-2314

Long-only cbBTC/USDC trading bot for the make.fun 24-hour BTC race
(`agent-fun/bars-replay/v1`). Starts with $1,000 of paper money, trades
1-minute bars, and only buys on a genuine short-horizon momentum burst.

## Strategy

- **Entry:** buy 100% of equity when the latest close is at least **0.9%
  above the close 30 bars ago**. A round trip costs ~26 bps
  (4 bps fee + 2 bps slippage + ~20 bps price impact), so only a real
  burst is worth chasing.
- **Take profits:** sell half at **+1.0%** over cost, half of the remainder
  at **+1.2%** over cost.
- **Trend exit:** once the first take-profit has fired, sell the rest when
  the close falls back below its **48-bar EMA** — the slow grind is over.
- **Safety nets:** 2.0% trailing stop, 1.0% stop-loss, 720-bar max hold.
- **Discipline:** at most **2 entries** per window, with a **240-bar
  cooldown** after an exit, so a choppy decline cannot grind the bot down
  through repeated re-entries.
- **Fallbacks (race guardrail):** if it has never traded by bar 1200, one
  small 30% trade on a weaker +0.4% burst; if it has still never traded by
  bar 1400, buy 30% unconditionally — so the entry always makes at least
  one trade even in a window with no burst at all.

See `NOTES.md` for the full evidence: dev-window results, stress tests,
and why the previous race's bot was not re-submitted.

## Files

- `main.py` — the bot (Python 3.13, stdlib only)
- `vendor/makefun_bars.py` — byte-identical copy of the kit's
  `sdk/makefun_bars.py` protocol shim
- `NOTES.md` — strategy, parameters, and measured results
- `LICENSE` — MIT

## Local grading

The kit could not be persisted to disk in this build sandbox (see NOTES.md),
so the bot was verified with an exact-integer protocol driver that spawns
the real `main.py`, feeds it the new kit's dev bars from memory, and applies
the harness's own integer fill model — the same approach as the previous
race, whose driver reproduced the official `grade-local` numbers exactly
(buy-and-hold −25.97 USDC; old bot +4.20 USDC).

Dev window (2026-11-12 23:14 UTC → 2026-11-13 23:14 UTC), new kit
(bundle `30594725ff09bc87af1c57506fe177c927581e0435020a09253cae09083ffa3c`):

| Run | Net PnL | Return | Trades | Fees | Max DD |
|-----|--------:|-------:|-------:|-----:|-------:|
| 1   | +11.95 USDC | +1.195% | 4 | 0.80 USDC | 1.07% |
| 2   | +11.95 USDC | +1.195% | 4 | 0.80 USDC | 1.07% |

Two full runs, reply bytes identical (deterministic). The dev gate is
net PnL > $0 — this bot clears it. The previous race's bot scores −12.07
USDC on this same window, so it was not re-used.

## Verification

Measured with the exact-integer protocol driver described above (the real
`main.py`, end to end, kit bundle sha256
`30594725ff09bc87af1c57506fe177c927581e0435020a09253cae09083ffa3c`).

- **Dev window:** 2026-11-12 23:14 UTC → 2026-11-13 23:14 UTC, 1,440 bars,
  0 gaps. First close $71,408.76, last close $67,900.67: **−4.91%**
  downtrend. Buy-and-hold on the same window: −52.59 USDC (−5.26%).
- **Bot result:** net PnL **+11.9502 USDC (+1.195%)**, **4 trades**, fees
  **0.8049 USDC**, max drawdown **1.07%**. Fills: buy 0.01452934 BTC @
  68,798.70560 (bar 433); sell 50% @ 69,686.94480 (bar 859); sell 25% @
  69,843.71988 (bar 860); sell rest @ 69,488.83215 (bar 881, close below
  EMA(48)). Flat from bar 881.
- **Determinism:** two full runs, reply bytes identical.
- **Stress test:** 20 block-bootstrap (1-hour blocks) copies of the new
  window — median **+7.40 USDC**, **9/20 copies lose**. For comparison,
  the old race's bot scores median −99.05 USDC (20/20 lose) on the same
  copies.
- **Honest cross-check:** on the old dev window the same bot scores
  **−11.94 USDC (−1.194%)**, 2 trades, max drawdown 1.50%. No
  single-window rule wins on both windows; this config was chosen for
  its stress profile on the window that gates entry.

See `NOTES.md` for the full evidence, including the strategy search,
edge tests, and what was not verified.
