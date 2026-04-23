"""
TradeSetup dataclass — populated by find_setup() in strategy.py.
Add fields as the strategy rules are defined.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TradeSetup:
    symbol:     str
    timeframe:  str
    direction:  str            # "LONG" or "SHORT"
    entry:      float
    stop_loss:  float
    target:     float
    session:    str = ""
    risk_reward: float = 0.0
    # Add strategy-specific fields here as rules are implemented
    notes:      str = ""

    def __post_init__(self):
        if self.stop_loss != self.entry:
            sl_dist = abs(self.entry - self.stop_loss)
            tp_dist = abs(self.target - self.entry)
            self.risk_reward = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0.0
