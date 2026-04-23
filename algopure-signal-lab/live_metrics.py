"""
Pure calculation functions for live position risk metrics.
No MT5 calls — takes raw position/account data and returns dicts/DataFrames.
"""
from __future__ import annotations

from typing import Optional
import pandas as pd


# ── P&L primitives ────────────────────────────────────────────────────────────

def _pnl(price_diff: float, lots: float, tick_size: float, tick_value: float) -> float:
    if tick_size == 0:
        return 0.0
    return (price_diff / tick_size) * tick_value * lots


def signed_pnl(entry: float, price: float, lots: float, direction: str,
               tick_size: float, tick_value: float) -> float:
    diff = (price - entry) if direction == "LONG" else (entry - price)
    return _pnl(diff, lots, tick_size, tick_value)


def price_diff_pnl(price_diff: float, lots: float, tick_size: float, tick_value: float) -> float:
    return _pnl(price_diff, lots, tick_size, tick_value)


# ── Per-position risk metrics ─────────────────────────────────────────────────

def position_risk_row(
    label: str, price: Optional[float], entry: float, lots: float,
    direction: str, balance: float, tick_size: float, tick_value: float,
) -> dict:
    """Build one row for the risk metrics table."""
    if price is None:
        return {"Level": label, "Price": "—", "Δ Price": "—",
                "Δ Pts": "—", "Δ %": "—", "P&L $": "—", "% Account": "—"}

    diff  = (price - entry) if direction == "LONG" else (entry - price)
    pts   = diff / tick_size if tick_size else 0
    pct   = diff / entry * 100 if entry else 0
    pnl   = _pnl(diff, lots, tick_size, tick_value)
    pct_a = pnl / balance * 100 if balance else 0

    return {
        "Level":     label,
        "Price":     f"{price:.5f}",
        "Δ Price":   f"{diff:+.2f}",
        "Δ Pts":     f"{pts:+.0f}",
        "Δ %":       f"{pct:+.3f}%",
        "P&L $":     f"${pnl:+,.2f}",
        "% Account": f"{pct_a:+.3f}%",
    }


def build_risk_metrics_table(
    entry: float, current: float, sl: Optional[float], tp: Optional[float],
    lots: float, direction: str, balance: float,
    tick_size: float, tick_value: float,
    daily_loss_limit: float = 8000.0,
    drawdown_limit:   float = 5000.0,
    max_loss_limit:   float = 0.0,
    realized_daily_pnl: float = 0.0,
) -> pd.DataFrame:
    """
    Build the main risk metrics table for one position.
    Returns a DataFrame with rows: TP, Current, Entry, SL, Daily Limit, Drawdown, Max Loss.
    """
    rows = []
    if tp is not None:
        rows.append(position_risk_row("Take Profit", tp, entry, lots, direction,
                                      balance, tick_size, tick_value))

    # Current P&L
    cur_diff  = (current - entry) if direction == "LONG" else (entry - current)
    cur_pnl   = _pnl(cur_diff, lots, tick_size, tick_value)
    cur_pts   = cur_diff / tick_size if tick_size else 0
    cur_pct   = cur_diff / entry * 100 if entry else 0
    cur_pct_a = cur_pnl / balance * 100 if balance else 0
    status    = "✓ IN PROFIT" if cur_pnl > 0 else ("▶ AT ENTRY" if cur_pnl == 0 else "⚠ IN LOSS")
    rows.append({
        "Level": f"▶ Current  [{status}]",
        "Price": f"{current:.5f}",
        "Δ Price": f"{cur_diff:+.2f}",
        "Δ Pts":  f"{cur_pts:+.0f}",
        "Δ %":    f"{cur_pct:+.3f}%",
        "P&L $":  f"${cur_pnl:+,.2f}",
        "% Account": f"{cur_pct_a:+.3f}%",
    })

    rows.append(position_risk_row("Entry", entry, entry, lots, direction,
                                  balance, tick_size, tick_value))
    if sl is not None:
        rows.append(position_risk_row("Stop Loss", sl, entry, lots, direction,
                                      balance, tick_size, tick_value))

    # Account-level limits
    daily_used   = abs(realized_daily_pnl) + max(0, -cur_pnl)
    daily_remain = daily_loss_limit - daily_used
    rows.append({
        "Level":  "Daily Loss Limit",
        "Price":  "—",
        "Δ Price": "—",
        "Δ Pts":  "—",
        "Δ %":    "—",
        "P&L $":  f"-${daily_loss_limit:,.2f}",
        "% Account": f"-{daily_loss_limit/balance*100:.2f}%  "
                     f"(${daily_remain:,.0f} remain)",
    })
    dd_remain = drawdown_limit - max(0, -cur_pnl)
    rows.append({
        "Level":  "Drawdown Limit",
        "Price":  "—",
        "Δ Price": "—",
        "Δ Pts":  "—",
        "Δ %":    "—",
        "P&L $":  f"-${drawdown_limit:,.2f}",
        "% Account": f"-{drawdown_limit/balance*100:.2f}%  "
                     f"(${dd_remain:,.0f} remain)",
    })
    if max_loss_limit > 0:
        ml_remain = max_loss_limit - max(0, -cur_pnl)
        rows.append({
            "Level":  "Max Loss Limit",
            "Price":  "—",
            "Δ Price": "—",
            "Δ Pts":  "—",
            "Δ %":    "—",
            "P&L $":  f"-${max_loss_limit:,.2f}",
            "% Account": f"-{max_loss_limit/balance*100:.2f}%  "
                         f"(${ml_remain:,.0f} remain)",
        })

    return pd.DataFrame(rows)


# ── Scenario analysis — 5 hypothetical price points ──────────────────────────

def scenario_table(
    entry: float, current: float, sl: Optional[float], tp: Optional[float],
    lots: float, direction: str, balance: float,
    tick_size: float, tick_value: float,
) -> pd.DataFrame:
    """
    5 hypothetical price points evenly spanning [SL-buffer, TP+buffer].
    Shows pips, % move, P&L $, % account, win/loss label.
    """
    # Define 5 scenario prices
    sl_price = sl if sl else (entry * 0.995 if direction == "LONG" else entry * 1.005)
    tp_price = tp if tp else (entry * 1.01  if direction == "LONG" else entry * 0.99)

    sl_dist = abs(entry - sl_price)
    tp_dist = abs(tp_price - entry)

    if direction == "LONG":
        prices = [
            sl_price - sl_dist * 0.25,   # Beyond SL
            sl_price,                     # At SL
            entry,                        # Entry
            entry + tp_dist * 0.5,        # Halfway to TP
            tp_price,                     # At TP
        ]
        labels = ["Beyond SL (–25%)", "At SL", "At Entry", "Halfway to TP", "At TP"]
    else:
        prices = [
            tp_price,
            entry - tp_dist * 0.5,
            entry,
            sl_price - sl_dist * 0.25,
            sl_price,
        ]
        labels = ["At TP", "Halfway to TP", "At Entry", "Beyond SL (–25%)", "At SL"]

    rows = []
    for price, label in zip(prices, labels):
        diff    = (price - entry) if direction == "LONG" else (entry - price)
        pnl     = _pnl(diff, lots, tick_size, tick_value)
        pts     = diff / tick_size if tick_size else 0
        pct     = diff / entry * 100 if entry else 0
        pct_a   = pnl / balance * 100 if balance else 0
        wl      = "WIN" if pnl > 0 else ("FLAT" if pnl == 0 else "LOSS")
        rows.append({
            "Scenario":  label,
            "Price":     f"{price:.5f}",
            "Δ Pts":     f"{pts:+.0f}",
            "Δ %":       f"{pct:+.3f}%",
            "P&L $":     f"${pnl:+,.2f}",
            "% Account": f"{pct_a:+.3f}%",
            "Outcome":   wl,
        })

    return pd.DataFrame(rows)


# ── SL / TP optimization — 3 alternatives each ───────────────────────────────

def sl_alternatives(
    entry: float, sl: Optional[float], lots: float, direction: str,
    balance: float, tick_size: float, tick_value: float,
) -> pd.DataFrame:
    """Return 3 SL alternatives: tight (0.5×), current, wide (2×)."""
    if sl is None:
        sl = (entry * 0.995 if direction == "LONG" else entry * 1.005)

    sl_dist = abs(entry - sl)
    if direction == "LONG":
        options = [
            ("Tight  (0.5×)", entry - sl_dist * 0.5),
            ("Current",       sl),
            ("Wide   (2.0×)", entry - sl_dist * 2.0),
        ]
    else:
        options = [
            ("Tight  (0.5×)", entry + sl_dist * 0.5),
            ("Current",       sl),
            ("Wide   (2.0×)", entry + sl_dist * 2.0),
        ]

    rows = []
    for label, price in options:
        diff  = abs(entry - price)
        risk  = _pnl(diff, lots, tick_size, tick_value)
        pts   = diff / tick_size if tick_size else 0
        pct   = diff / entry * 100 if entry else 0
        pct_a = risk / balance * 100 if balance else 0
        rows.append({
            "Option":    label,
            "SL Price":  f"{price:.5f}",
            "Distance":  f"{diff:.2f}",
            "Pts":       f"{pts:.0f}",
            "Risk %":    f"{pct:.3f}%",
            "Risk $":    f"${risk:,.2f}",
            "% Account": f"{pct_a:.3f}%",
        })

    return pd.DataFrame(rows)


def tp_alternatives(
    entry: float, sl: Optional[float], tp: Optional[float],
    lots: float, direction: str, balance: float,
    tick_size: float, tick_value: float,
) -> pd.DataFrame:
    """Return 3 TP alternatives: 1:1, current, and 3:1 R:R."""
    sl_dist = abs(entry - sl) if sl else abs(entry * 0.005)
    if tp is None:
        tp = (entry + sl_dist * 2.0 if direction == "LONG" else entry - sl_dist * 2.0)

    tp_dist = abs(tp - entry)
    if direction == "LONG":
        options = [
            ("Conservative (1:1 R:R)", entry + sl_dist),
            ("Current",                tp),
            ("Extended    (3:1 R:R)",  entry + sl_dist * 3.0),
        ]
    else:
        options = [
            ("Conservative (1:1 R:R)", entry - sl_dist),
            ("Current",                tp),
            ("Extended    (3:1 R:R)",  entry - sl_dist * 3.0),
        ]

    rows = []
    for label, price in options:
        diff  = abs(price - entry)
        pot   = _pnl(diff, lots, tick_size, tick_value)
        pts   = diff / tick_size if tick_size else 0
        pct   = diff / entry * 100 if entry else 0
        pct_a = pot / balance * 100 if balance else 0
        rr    = diff / sl_dist if sl_dist else 0
        rows.append({
            "Option":    label,
            "TP Price":  f"{price:.5f}",
            "Distance":  f"{diff:.2f}",
            "Pts":       f"{pts:.0f}",
            "Potential": f"${pot:,.2f}",
            "% Account": f"{pct_a:.3f}%",
            "R:R":       f"1:{rr:.2f}",
        })

    return pd.DataFrame(rows)


# ── Hedge break-even table ────────────────────────────────────────────────────

def hedge_breakeven_table(
    entry: float, current: float, lots: float, direction: str,
    tick_size: float, tick_value: float,
) -> pd.DataFrame:
    """
    For 3 hedge sizes (0.25×, 0.5×, 1.0× of original lots):
    show the break-even price where combined P&L = 0.
    """
    cur_pnl = signed_pnl(entry, current, lots, direction, tick_size, tick_value)
    rows = []

    for factor, label in [(0.25, "0.25× hedge"), (0.50, "0.50× hedge"), (1.00, "1.00× hedge")]:
        h_lots = lots * factor
        h_dir  = "SHORT" if direction == "LONG" else "LONG"

        # Break-even: find price P where long_pnl(P) + short_pnl(P) = 0
        # Inline formula from risk.py
        if direction == "LONG":
            denom = lots - h_lots
            if abs(denom) < 1e-9:
                be_price = None
            else:
                be_price = (entry * lots - current * h_lots) / denom
        else:
            denom = h_lots - lots
            if abs(denom) < 1e-9:
                be_price = None
            else:
                be_price = (entry * lots - current * h_lots) / denom

        if be_price is None or be_price <= 0:
            rows.append({
                "Hedge": label, "H. Lots": f"{h_lots:.2f}", "H. Direction": h_dir,
                "H. Entry": f"{current:.5f}", "Break-Even Price": "—",
                "Price Move Needed": "—", "Combined P&L @ B/E": "—",
            })
            continue

        move_needed = abs(be_price - current)
        rows.append({
            "Hedge":       label,
            "H. Lots":     f"{h_lots:.2f}",
            "H. Direction": h_dir,
            "H. Entry":    f"{current:.5f}",
            "Break-Even Price": f"{be_price:.5f}",
            "Price Move Needed": f"{move_needed:.2f}",
            "Combined P&L @ B/E": "$0.00",
        })

    return pd.DataFrame(rows)
