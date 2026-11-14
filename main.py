"""Selective burst-momentum cbBTC bot for the make.fun BTC race
(agent-fun/bars-replay/v1), competition btc-race-24h-20261113-2314.

Strategy, in one paragraph: the bot sits in cash almost all of the time and
only buys on a genuine short-horizon momentum burst (the latest close at
least 0.9% above the close 30 bars ago), because a full round trip costs
about 26 bps in fees, slippage and price impact while a typical one-minute
bar moves only about 8 bps -- so only a real burst is worth chasing. It
buys with all of its cash, banks half the position once it is up 1.0% over
cost, banks half of the remainder at +1.2% if the rally extends that far,
and then lets the rest ride until the close falls back below its 48-bar
exponential moving average (the slow-trend exit), behind a 2.0% trailing
stop, a 1.0% stop-loss and a 720-bar maximum hold. At most two entries per
window, with a 240-bar cooldown after an exit, so a choppy decline cannot
grind it down through repeated re-entries (the failure mode of the
previous race's bot: 7 trades, -1.21% on this window). If it has still
never traded by bar 1200 it takes one small (30% of equity) fallback trade
on a weaker +0.4% 30-minute burst, and if it has still never traded by bar
1400 it buys 30% unconditionally, so the entry always meets the race's
minimum-one-trade guardrail even in a window with no burst at all. It
never holds into the end on purpose: the replay flattens anything left at
the last close.

Everything is a pure function of the bars received so far: no clock, no
environment, no files, no network, no randomness. The same bars always give
the same orders, so the two graded executions agree byte for byte.

Wire protocol: the vendored kit shim (vendor/makefun_bars.py, a byte-identical
copy of the kit's sdk/makefun_bars.py) owns stdin/stdout; this file only
decides orders in on_batch().
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters (chosen on the new dev window, see NOTES.md) ---
LOOKBACK_BARS = 30        # momentum window, in bars (minutes)
BURST_PCT = 0.009         # entry: close >= 0.9% above the close LOOKBACK bars ago
EMA_SLOW = 48             # slow EMA for the post-take-profit trend exit
FALLBACK_PCT = 0.0040     # weaker burst that arms the late-window fallback entry
FALLBACK_BAR = 1200       # fallback only once this many closes have been seen
FALLBACK_SIZE = 0.30      # fallback buys 30% of equity
FORCE_BAR = 1400          # unconditional fallback buy if still never traded
FORCE_SIZE = 0.30         # forced buy is 30% of equity
TAKE_PROFIT_PCT = 0.010   # once per position: sell half when value/cost is +1.0%
TAKE_PROFIT_FRAC = 0.5    # fraction of the position the take-profit sells
TAKE_PROFIT2_PCT = 0.012  # second tier: sell half of the remainder at +1.2% over cost
TRAIL_PCT = 0.020         # sell all when value falls 2.0% below its peak since entry
STOP_LOSS_PCT = 0.010     # sell all when value/cost falls to -1.0%
MAX_HOLD_BARS = 720       # sell all this many bars after the entry decision
MAX_ENTRIES = 2           # at most two entries per window
COOLDOWN_BARS = 240       # bars to wait after an exit before a new entry
MAX_SLIPPAGE_BPS = 100    # 1% past the latest close; fills here cost ~10 bps total

# --- per-run state (all derived from the bars + fills, nothing else) ---
closes = []               # closes seen so far, as ints (raw price units)
ema_slow = None           # EMA(48) of closes, float64 (IEEE 754, deterministic)
filled_buys = 0           # buys the harness reported as filled
entries = 0               # entries taken this window
last_exit_bar = -10 ** 9  # index into closes of the last full exit, for cooldown
entry_bar = -1            # index into closes of the entry decision, -1 when flat
peak_close = 0            # highest close since entry (raw price units)
took_profit = False       # whether this position already took its partial profit
took_profit2 = False      # whether this position already took its second partial profit
forced = False            # whether the unconditional fallback buy already fired


def _position_value(state):
    """(qty, value, cost) of the CBBTC position, from the harness account."""
    held = state.positions.get(SYMBOL)
    if held is None or held.qty <= 0:
        return 0, 0, 0
    return held.qty, state.value(SYMBOL, held.qty), held.cost


def on_batch(state, batch):
    global filled_buys, entries, last_exit_bar, entry_bar, peak_close
    global took_profit, took_profit2, forced, ema_slow

    for fill in batch.get("fills", []):
        if fill.get("status") == "filled" and fill.get("side") == "buy":
            filled_buys += 1

    for bar in batch.get("bars", []):
        if bar.get("symbol") == SYMBOL:
            closes.append(int(bar["c"]))

    if state.warming_up:
        return []

    n = len(closes)
    if n == 0:
        return []
    # Slow EMA, seeded at the first close (same rule as the kit's EMA baseline).
    close_f = float(closes[-1])
    if ema_slow is None:
        ema_slow = close_f
    else:
        k = 2.0 / (EMA_SLOW + 1)
        ema_slow = close_f * k + ema_slow * (1.0 - k)

    qty, value, cost = _position_value(state)

    if qty > 0:
        # --- manage an open position ---
        if entry_bar < 0:
            # Position arrived without our entry record (should not happen);
            # adopt it so the exits below still protect it.
            entry_bar = n - 1
            peak_close = closes[-1]
            took_profit = True
        peak_close = max(peak_close, closes[-1])
        peak_value = state.value(SYMBOL, qty, peak_close)

        # 1. Take half the profit once, at +1.0% over cost.
        if not took_profit and cost > 0 and value * 1000 >= cost * 1010:
            took_profit = True
            half = qty // 2
            if half > 0 and state.value(SYMBOL, half) >= 1_000_000:
                return [{"side": "sell", "symbol": SYMBOL, "qty": half,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        # 1b. Take half of the remainder once, at +1.2% over cost.
        if took_profit and not took_profit2 and cost > 0 and value * 1000 >= cost * 1012:
            took_profit2 = True
            half = qty // 2
            if half > 0 and state.value(SYMBOL, half) >= 1_000_000:
                return [{"side": "sell", "symbol": SYMBOL, "qty": half,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        # 2. Trend exit: once the first take-profit has fired, sell the rest
        # when the close falls back below its 48-bar EMA -- the slow grind
        # is over. (Before any take-profit, the trailing stop below is the
        # only trend guard, so a fresh entry is not shaken out by noise.)
        if took_profit and close_f < ema_slow:
            last_exit_bar = n - 1
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        # 3. Trailing stop: 2.0% below the peak value since entry.
        if peak_value > 0 and value * 1000 < peak_value * 980:
            last_exit_bar = n - 1
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        # 4. Stop-loss: 1.0% under cost.
        if cost > 0 and value * 1000 <= cost * 990:
            last_exit_bar = n - 1
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        # 5. Maximum hold: 720 bars after the entry decision.
        if n - 1 - entry_bar >= MAX_HOLD_BARS:
            last_exit_bar = n - 1
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    # --- flat: look for an entry ---
    entry_bar = -1
    # Forced fallback: guarantee at least one trade for the race guardrail,
    # even in a window with no burst at all. 30% of equity, 40 bars before
    # the end, so the worst case is a small drift loss on a third of the book.
    if not forced and filled_buys == 0 and n - 1 >= FORCE_BAR:
        forced = True
        entries += 1
        entry_bar = n - 1
        peak_close = closes[-1]
        took_profit = False
        took_profit2 = False
        spend = state.weight_room(SYMBOL) * 30 // 100
        spend = min(spend, state.cash)
        if spend >= int(state.hello["fees"]["min_notional_quote_units"]):
            return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": spend,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []
    if entries >= MAX_ENTRIES:
        return []
    if n - 1 - last_exit_bar < COOLDOWN_BARS:
        return []
    if n <= LOOKBACK_BARS:
        return []
    now = closes[-1]
    then = closes[-LOOKBACK_BARS - 1]
    burst = (now - then) * 10000 >= then * 90  # now/then - 1 >= 0.9%, integers only
    fallback = (filled_buys == 0 and n >= FALLBACK_BAR
                and (now - then) * 10000 >= then * 40)  # >= 0.40%
    if not (burst or fallback):
        return []

    frac = FALLBACK_SIZE if (fallback and not burst) else 1.0
    spend = state.weight_room(SYMBOL)
    if frac < 1.0:
        spend = spend * 30 // 100
    spend = min(spend, state.cash)
    if spend < int(state.hello["fees"]["min_notional_quote_units"]):
        return []
    entries += 1
    entry_bar = n - 1
    peak_close = now
    took_profit = False
    took_profit2 = False
    return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": spend,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


makefun_bars.run(on_batch)
