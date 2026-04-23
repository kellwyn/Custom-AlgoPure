"""
Order and setup dataclasses for the AlgoPure execution bot.
TradeOrder — used by the execution algorithm (manual commands).
TradeSetup — kept for signal-lab / backtesting compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Execution algorithm order ──────────────────────────────────────────────────

@dataclass
class TradeOrder:
    symbol:    str
    direction: str          # "LONG" or "SHORT"
    lots:      float

    order_type:   str = "MARKET"   # "MARKET" | "LIMIT" | "STOP"
    limit_price:  Optional[float] = None   # entry price for LIMIT / STOP orders
    stop_loss:    Optional[float] = None
    take_profit:  Optional[float] = None
    trailing_pts: Optional[float] = None   # trailing stop in price points

    comment:   str = ""
    notes:     str = ""
    ticket:    Optional[int] = None        # populated after execution

    @property
    def entry(self) -> Optional[float]:
        return self.limit_price

    @property
    def risk_reward(self) -> Optional[float]:
        if self.limit_price and self.stop_loss and self.take_profit:
            sl_dist = abs(self.limit_price - self.stop_loss)
            tp_dist = abs(self.take_profit - self.limit_price)
            return round(tp_dist / sl_dist, 2) if sl_dist > 0 else None
        return None


# ── Signal-lab / backtesting setup (backward compat) ──────────────────────────

@dataclass
class TradeSetup:
    symbol:     str
    timeframe:  str
    direction:  str            # "LONG" or "SHORT"
    entry:      float
    stop_loss:  float
    target:     float
    session:    str   = ""
    risk_reward: float = 0.0
    notes:      str   = ""

    def __post_init__(self):
        if self.stop_loss != self.entry:
            sl_dist = abs(self.entry - self.stop_loss)
            tp_dist = abs(self.target - self.entry)
            self.risk_reward = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0.0
