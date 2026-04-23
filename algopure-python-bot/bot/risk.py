"""
Position sizing, Kelly criterion, and P&L utilities.
All functions are pure (no MT5 calls) except where noted.
"""
from __future__ import annotations

import math
from typing import Optional


# ── P&L helpers ───────────────────────────────────────────────────────────────

def pnl_per_lot(price_diff: float, tick_size: float, tick_value: float) -> float:
    """Dollar P&L for 1 lot given a price move of price_diff."""
    if tick_size == 0:
        return 0.0
    return (price_diff / tick_size) * tick_value


def position_pnl(price_diff: float, lots: float, tick_size: float, tick_value: float) -> float:
    return pnl_per_lot(price_diff, tick_size, tick_value) * lots


def price_to_pnl(
    entry: float, price: float, lots: float,
    direction: str, tick_size: float, tick_value: float
) -> float:
    """Signed P&L at a given price for a LONG or SHORT position."""
    diff = (price - entry) if direction == "LONG" else (entry - price)
    return position_pnl(diff, lots, tick_size, tick_value)


def sl_to_price(entry: float, sl_value: float, sl_unit: str, direction: str,
                tick_size: float, pip_size: Optional[float] = None) -> float:
    """
    Convert a SL specification to an absolute price.
    sl_unit: 'price' | 'points' | 'pips' | 'pct' | 'dollars'
    'points' = tick units  |  'pips' = 10 ticks (common convention)
    'dollars' = dollar distance (treated as price_diff via pnl_per_lot inverse)
    """
    if sl_unit == "price":
        return sl_value
    sign = -1 if direction == "LONG" else 1
    if sl_unit == "points":
        return entry + sign * sl_value * tick_size
    if sl_unit == "pips":
        ps = pip_size if pip_size else tick_size * 10
        return entry + sign * sl_value * ps
    if sl_unit == "pct":
        return entry * (1 + sign * sl_value / 100.0)
    if sl_unit == "dollars":
        return entry + sign * sl_value * tick_size
    return sl_value


def tp_to_price(entry: float, tp_value: float, tp_unit: str, direction: str,
                tick_size: float, pip_size: Optional[float] = None) -> float:
    """Convert a TP specification to an absolute price (mirror of sl_to_price)."""
    if tp_unit == "price":
        return tp_value
    sign = 1 if direction == "LONG" else -1
    if tp_unit == "points":
        return entry + sign * tp_value * tick_size
    if tp_unit == "pips":
        ps = pip_size if pip_size else tick_size * 10
        return entry + sign * tp_value * ps
    if tp_unit == "pct":
        return entry * (1 + sign * tp_value / 100.0)
    if tp_unit == "dollars":
        return entry + sign * tp_value * tick_size
    return tp_value


# ── Position sizing ───────────────────────────────────────────────────────────

def risk_based_lots(
    balance: float, risk_pct: float, entry: float, sl_price: float,
    tick_size: float, tick_value: float,
    vol_min: float = 0.01, vol_max: float = 100.0, vol_step: float = 0.01,
    max_lots: float = 2.0,
) -> float:
    """Size a position so that loss to SL = risk_pct% of balance."""
    risk_amt = balance * risk_pct / 100.0
    sl_dist  = abs(entry - sl_price)
    if sl_dist == 0 or tick_size == 0 or tick_value == 0:
        return vol_min
    dollar_per_lot = (sl_dist / tick_size) * tick_value
    lot = risk_amt / dollar_per_lot
    lot = max(vol_min, min(min(vol_max, max_lots), lot))
    if vol_step > 0:
        lot = round(round(lot / vol_step) * vol_step, 8)
    return lot


def kelly_lots(
    balance: float, win_rate: float, rr_ratio: float, kelly_fraction: float,
    entry: float, sl_price: float,
    tick_size: float, tick_value: float,
    vol_min: float = 0.01, vol_max: float = 100.0, vol_step: float = 0.01,
    max_lots: float = 2.0,
) -> float:
    """
    Kelly criterion lot sizing.
    f* = p - q/b  where p=win_rate, q=1-p, b=rr_ratio
    Applied to account balance to get dollar risk, then converted to lots.
    """
    if rr_ratio <= 0 or win_rate <= 0 or win_rate >= 1:
        return vol_min
    q  = 1.0 - win_rate
    f  = win_rate - q / rr_ratio          # full Kelly fraction of capital
    f  = max(0.0, f) * kelly_fraction      # scale down (quarter-Kelly etc.)
    risk_amt = balance * f
    sl_dist  = abs(entry - sl_price)
    if sl_dist == 0 or tick_size == 0 or tick_value == 0:
        return vol_min
    dollar_per_lot = (sl_dist / tick_size) * tick_value
    lot = risk_amt / dollar_per_lot
    lot = max(vol_min, min(min(vol_max, max_lots), lot))
    if vol_step > 0:
        lot = round(round(lot / vol_step) * vol_step, 8)
    return lot


# ── Scenario helpers ─────────────────────────────────────────────────────────

def hedge_breakeven_price(
    entry: float, lots: float, direction: str,
    current_price: float, hedge_lots: float,
) -> Optional[float]:
    """
    Price at which (original position + hedge) combined P&L = 0.
    Original: LONG @ entry, hedge: SHORT @ current_price (or vice-versa).
    Returns None if lots == hedge_lots (parallel — never converges).
    """
    if abs(lots - hedge_lots) < 1e-9:
        return None
    if direction == "LONG":
        # long_pnl = (P - entry) * lots
        # short_pnl = (current_price - P) * hedge_lots
        # sum = 0  →  P(lots - hedge_lots) = entry*lots - current_price*hedge_lots
        return (entry * lots - current_price * hedge_lots) / (lots - hedge_lots)
    else:
        # short_pnl = (entry - P) * lots
        # long_pnl  = (P - current_price) * hedge_lots
        # sum = 0  →  P(hedge_lots - lots) = entry*lots - current_price*hedge_lots   [signs flip]
        denom = hedge_lots - lots
        if abs(denom) < 1e-9:
            return None
        return (entry * lots - current_price * hedge_lots) / denom
