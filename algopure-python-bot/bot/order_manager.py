"""
Position tracker and trailing stop manager.
Tracks which positions have active trailing stops and updates them each cycle.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Dict, Optional

import MetaTrader5 as mt5

from .config import ExecutionConfig
from .trader import get_open_positions, modify_position, get_tick

log = logging.getLogger("algopure-bot")


class OrderManager:
    def __init__(self, cfg: ExecutionConfig):
        self.cfg = cfg
        # ticket → trailing distance in price points
        self._trailing: Dict[int, float] = {}
        # ticket → best price seen (for trailing logic)
        self._trail_high: Dict[int, float] = {}

    # ── Trailing stop management ──────────────────────────────────────────────

    def set_trailing_stop(self, ticket: int, points: float):
        """Register a trailing stop for a live position."""
        self._trailing[ticket] = points
        pos = self._get_pos(ticket)
        if pos:
            # Initialise high-water with current price
            if pos.type == mt5.ORDER_TYPE_BUY:
                self._trail_high[ticket] = pos.price_current
            else:
                self._trail_high[ticket] = pos.price_current
        log.info("Trailing stop set: ticket=%d  distance=%.5f pts", ticket, points)

    def remove_trailing_stop(self, ticket: int):
        self._trailing.pop(ticket, None)
        self._trail_high.pop(ticket, None)

    def update_trailing_stops(self):
        """Called every second from the background monitor thread."""
        for ticket, trail_pts in list(self._trailing.items()):
            pos = self._get_pos(ticket)
            if pos is None:
                # Position closed externally — clean up
                self.remove_trailing_stop(ticket)
                continue

            tick = get_tick(pos.symbol)
            if tick is None:
                continue

            if pos.type == mt5.ORDER_TYPE_BUY:
                current = tick.bid
                high    = self._trail_high.get(ticket, pos.price_open)
                if current > high:
                    self._trail_high[ticket] = current
                    new_sl = current - trail_pts
                    if new_sl > pos.sl:
                        ok, msg = modify_position(ticket, sl=new_sl)
                        if ok:
                            log.info("Trail SL moved: #%d  sl=%.5f", ticket, new_sl)
            else:
                current = tick.ask
                low     = self._trail_high.get(ticket, pos.price_open)
                if current < low:
                    self._trail_high[ticket] = current
                    new_sl = current + trail_pts
                    if new_sl < pos.sl or pos.sl == 0:
                        ok, msg = modify_position(ticket, sl=new_sl)
                        if ok:
                            log.info("Trail SL moved: #%d  sl=%.5f", ticket, new_sl)

    # ── Risk / daily-loss monitoring ──────────────────────────────────────────

    def daily_pnl(self) -> float:
        """Sum of today's closed-trade profits + current unrealized P&L."""
        acct = mt5.account_info()
        if acct is None:
            return 0.0
        today = date.today()
        from_ts = int(mt5.datetime_to_time(
            mt5.datetime(today.year, today.month, today.day, 0, 0, 0)
        ))
        history = mt5.history_deals_get(from_ts, int(mt5.datetime_to_time(
            mt5.datetime(today.year, today.month, today.day, 23, 59, 59)
        )))
        closed_pnl = sum(d.profit for d in (history or []) if d.entry == mt5.DEAL_ENTRY_OUT)
        unrealized = sum(p.profit for p in get_open_positions())
        return closed_pnl + unrealized

    def check_risk_limits(self) -> list[str]:
        """Return list of warning strings for any limit breaches."""
        warnings = []
        acct = mt5.account_info()
        if acct is None:
            return warnings
        balance = acct.balance

        # Floating drawdown
        unrealized = sum(p.profit for p in get_open_positions())
        if unrealized < 0 and abs(unrealized) >= self.cfg.drawdown_limit:
            warnings.append(
                f"  ⚠ DRAWDOWN ALERT  unrealized=${unrealized:,.2f}  "
                f"limit=${self.cfg.drawdown_limit:,.2f}"
            )

        # Max loss limit (if set)
        if self.cfg.max_loss_limit > 0:
            if unrealized < -self.cfg.max_loss_limit:
                warnings.append(
                    f"  ⛔ MAX LOSS EXCEEDED  unrealized=${unrealized:,.2f}  "
                    f"limit=${self.cfg.max_loss_limit:,.2f}"
                )
        return warnings

    # ── Utility ───────────────────────────────────────────────────────────────

    def _get_pos(self, ticket: int):
        positions = mt5.positions_get(ticket=ticket)
        return positions[0] if positions else None

    def active_trailing_tickets(self) -> list[int]:
        return list(self._trailing.keys())
