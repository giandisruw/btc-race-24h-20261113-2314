# NOTES — strategy, parameters, and measured results

## Kit (new, fetched for this race)

- Competition: `btc-race-24h-20261113-2314`, kit downloaded from
  `https://make.fun/c/btc-race-24h-20261113-2314/kit` with the stored
  make.fun API key (never printed or stored in any file).
- `kit.json`: bundle_sha256
  `30594725ff09bc87af1c57506fe177c927581e0435020a09253cae09083ffa3c`,
  dataset_sha256
  `a5af740915c2328ea14e28ba6deca6bee873f797dd0538d640caade502027cf3`,
  harness `harness@3f9d6dc6…`, scorer `scorer@3afea00b…`.
- Dev window: **2026-11-12 23:14 UTC → 2026-11-13 23:14 UTC**, 1,440 bars,
  0 gaps (cut.json `window.start_ms` 1794525240000, `end_ms` 1794611640000).
  Bars file sha256
  `995528635f7a4d0f5cfe5dcf3d8c64a64e6f908c39b9485b2bf21ff725c296bb`.
- Same rules as the last race: $1,000 start, 4 bps fee, 2 bps slippage,
  constant-product price impact, latency 1 bar, long only, max 16 orders
  per reply, min notional 1 USDC, race guardrails ≥1 trade and max
  drawdown ≤25%.

## The new dev window (what the bot had to survive)

- First close $71,408.76, last close $67,900.67: **−4.91%** total.
  Buy-and-hold: −52.59 USDC (−5.26%), max DD 5.10%.
  House EMA-cross (8/21): −99.38 USDC (−9.94%), 58 trades.
- 1-minute return stdev 7.9 bps (vs 5.1 bps on the old window), 77 flat bars.
- The only clean up-move: best 60-minute return **+1.79% at bar 467**
  (2026-11-13 07:02 UTC); worst 60-minute move −2.23% at bar 288.
- The old race's bot (burst 60-min +0.75%, TP +0.6%/+0.9%, trail 0.8%,
  max hold 360) scores **−12.07 USDC (−1.21%), 7 trades** on this window:
  it re-entered repeatedly in the decline. It was NOT re-submitted.

## Strategy search (exact-integer simulator, BigInt port of the harness fill model)

A simulator implementing the harness's exact integer fill model
(`BarsPool` constant-product impact, 4 bps fee, 2 bps slippage, latency-1
fills, decision checks, end-of-window flatten) was used to search
strategies on the new window, cross-checked on the old window, and
stress-tested on 20 block-bootstrap (1-hour blocks) copies of the new
window. Calibration of the simulator: old buy-and-hold −25.97 USDC
(exactly the official `grade-local` figure) and old EMA-cross −92.26 vs
official −95.88 (within 0.37 pp).

Findings that shaped the design:

- **Pure EMA trend-following loses on both windows.** Best EMA grid
  entry (8/21, 20 bps gap, +0.4% burst filter): −14.25 USDC on the new
  window, −14.99 on the old. Unfiltered EMA-cross: −109 to −134. The
  last race's winner was an EMA trend bot (+$9.19 on its race window),
  but no EMA variant clears the dev gate on this window, so pure EMA is out.
- **Burst entries work, but only with few trades.** The best plain-burst
  configs catch the single rally at bars ~432–920 and make +3 to +7 USDC
  in 3 trades. More trades = more losses in the decline.
- **Entry caps matter most.** Capping entries at 2 per window with a
  240-bar cooldown after an exit is what separates the finalists
  (stress median +2.8 to +7.4) from the old bot (stress median −99.05,
  20/20 losing copies).
- **Exit structure matters more than the entry.** A fixed trailing stop
  is a knife-edge on this window (trail 1.0% → −18.52, 1.2% → +7.30,
  1.6% → +4.52). Exiting the remainder on a close below EMA(48) after
  the first take-profit — letting the slow grind ride and exiting when
  the trend breaks — gives +10.52 with the best stress median (+2.84,
  10/20 losses) of any single-exit variant, and +11.91/+11.95 with the
  second take-profit tier (stress median +7.40, 9/20 losses).
- **The forced fallback is cheap insurance.** With the primary disabled,
  buying 30% at bar 1400 and flattening at the end loses only −1.46 to
  −3.23 USDC on the two known windows, and it guarantees the ≥1-trade
  race guardrail in a window with no burst at all. The signal-based
  fallback (30-min ≥ +0.4% after bar 1200) never fires on the new window
  even with the primary disabled — the window's late 30-minute returns
  never reach +0.4% — which is why the unconditional buy at bar 1400
  exists.

## Final parameters (all in `main.py`)

| Parameter | Value | Why |
|---|---|---|
| Momentum lookback | 30 bars | 30/45/60 all in the +5.5–+7.3 plateau; 30 is least lagged |
| Burst threshold | +0.9% | 0.7–0.9% plateau at +7.30; 1.0–1.3% gives +6.22 (flat region, not knife-edge) |
| Position size | 100% of equity | Full size on a selective entry |
| Take profit 1 | sell 50% at +1.0% over cost | TP 1.0–1.2% identical on dev; 0.8% gives +4.92, 1.5% +8.23 |
| Take profit 2 | sell 50% of remainder at +1.2% over cost | +11.95 vs +10.52 without it; stress median +7.40 vs +2.84 |
| Trend exit | sell rest when close < EMA(48), after TP1 | Best stress median of any exit tested; rides the grind |
| Trailing stop | 2.0% below peak value | Wide safety net; 1.6–2.5% all give +10.52 on dev |
| Stop-loss | −1.0% vs cost | Safety net; never binds on the new window |
| Max hold | 720 bars | 480–1440 all give +10.52 on dev |
| Max entries | 2 per window | The single biggest robustness win (see above) |
| Cooldown | 240 bars after an exit | Cooldown 0 flips the same config to −3.19 |
| Fallback entry | bar ≥1200, no filled buy yet, 30-min ≥ +0.4%, 30% size | Guardrail insurance for a quiet race window |
| Forced buy | bar ≥1400, no filled buy yet, 30% size, unconditional | Guarantees ≥1 trade; worst case ≈ −$1.5–$3.2 |
| Max slippage | 100 bps | Fills cost ~10 bps; cap only guards freak opens |

Deliberately NOT used: EMA-cross entries (whipsaw, −9.9% house baseline),
dip-buying / mean reversion (loses in the downtrend), Donchian breakouts
and RSI mean reversion (both deeply negative on the old window's tests).

## Measured results

### A. Exact-integer protocol driver (the real `main.py`, end to end)

The driver (`exact-driver.cjs`, kept outside the entry dir) is a Node port
of the previous race's `driver.py`: it spawns the real `main.py` as a
subprocess, feeds it hello + one batch per dev bar, and applies the
harness's own integer fill model. Validation of the port: run against the
OLD bot on the OLD window it reproduces `driver.py` exactly — +4.2031 USDC,
identical fills (buy bar 91 @ 74,130.71; sells bars 160/451).

**New bot, NEW dev window** (2026-11-12 23:14 UTC → 2026-11-13 23:14 UTC):

- Run 1: net PnL **+11.9502 USDC (+1.195%)**, 4 trades, fees 0.8049 USDC,
  maxDD 1.07%, max position 0.0145 BTC, max decision 53 ms/bar,
  0 rejected orders.
- Run 2: net PnL **+11.9502 USDC (+1.195%)**, 4 trades — identical.
- Determinism: reply bytes identical across both runs (true).
- Fills: BUY 0.01452934 BTC @ 68,798.70560 (decided bar 432, filled bar 433,
  notional 1,000 USDC, fee 0.40 USDC); SELL 50% @ 69,686.94480 (decided bar
  858, filled bar 859); SELL 25% @ 69,843.71988 (decided bar 859, filled
  bar 860 — second take-profit tier, one bar later); SELL rest @ 69,488.83215
  (decided bar 880, filled bar 881 — close fell below EMA(48)). Flat from
  bar 881 of 1,440; nothing left for the end-of-window flatten.
- **Dev gate: +11.95 > $0 — PASSES.**

**New bot, OLD dev window** (cross-check, not the gate): −11.9387 USDC
(−1.194%), 2 trades, maxDD 1.50%, deterministic. The old window's early
rally (buy bar 57 @ 74,425.07) reversed; the stop-loss exited at bar 510
@ 73,595.44 before any take-profit could fire. Honest statement: this bot
loses on the old window, as every burst variant tested does except the old
bot's own tuned parameters (+4.20 there, −12.07 here). No single-window
rule wins on both; the chosen rule is the one with the best stress
profile on the window that actually gates entry.

### B. Stress test (20 block-bootstrap copies of the new window)

- Final bot: median **+7.40 USDC**, 9/20 copies lose.
  (Plain trail-1.2% baseline: median −14.23, 14/20 lose; old bot: median
  −99.05, 20/20 lose.) The bootstrap copies preserve the window's −4.91%
  total return but reorder its hourly blocks, so they are a pessimistic
  spread, not a forecast — but the chosen config is the only one tested
  whose median copy makes money.

### C. Edge tests (`edge_test_new.py`, synthetic series through the real bot)

- Warmup (`warmup_bars=60`): 0 orders during warmup, clean exit rc=0;
  first buy after warmup at seq 82 on a synthetic burst.
- Flat window, no burst at all: exactly one order — the forced buy at
  seq 1400, 30% of equity (300,000,000 quote units) — nothing else.
- Synthetic rally (+1.5% ramp over 30 bars): buy at seq 117, holds (peak
  is only +0.64% over the entry close, so no take-profit fires — correct).

## What was NOT done

- Official `grade-local` could not be run on the new kit in this sandbox:
  exec-spawned processes cannot persist network-downloaded bytes to disk
  (writes of the downloaded kit fail with EPERM / produce 0-byte files,
  while the same processes write locally-authored bytes fine), so the kit
  exists only in memory during a run. The exact-integer driver above is
  the same verification the previous race used, and its port was validated
  to reproduce the previous race's official numbers exactly (see A).
- The `grade-local --driver process` path cannot grade a Python bot
  anyway (Node-only sandbox); no Docker on this VM.
- Target was a robust >$0 on the new dev window with a defensible race
  design, not the maximum dev PnL: the top dev numbers (+10.5–+12.0) all
  come from the window's single rally, and neighbouring parameters move
  the result by a few dollars either way. The chosen config sits in the
  middle of the flat regions (threshold 0.7–0.9%, TP 1.0–1.2%, trail
  1.6–2.5%, max hold 480–1440 all keep it positive), except for TP 0.8%,
  which flips it to −7.42 — the one cliff, documented here so it is not
  re-tuned blindly.

## Discrepancies found (kit vs brief)

1. The brief's escrow address and 6-hour entry window match the kit
   (dev phase 2026-11-13T23:14Z → 2026-11-14T05:14Z, i.e. entries close
   Sat 14 Nov 12:14 WIB).
2. The kit's `competition.yaml` carries no `warmup_bars` in the dev phase;
   the bot still honours `state.warming_up` if the live hello sends one.
