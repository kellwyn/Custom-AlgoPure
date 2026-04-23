"""
Strategy logic — AlgoPure.
Implement find_setup() to return a TradeSetup when entry conditions are met, or None.
Mirror each rule 1-for-1 with the MQL5 EA.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from .signals import TradeSetup


# ── Strategy configuration ────────────────────────────────────────────────────

@dataclass
class StrategyConfig:
    symbol:        str   = "XAUUSD"
    timeframe:     int   = mt5.TIMEFRAME_M5
    candle_count:  int   = 100
    magic:         int   = 20260423
    slippage:      int   = 10

    # Risk
    risk_pct:      float = 1.0
    sl_points:     float = 20.0
    tp_points:     float = 30.0
    max_lots:      float = 2.0

    # Session filter
    use_session:   bool  = True
    session_start: tuple = field(default_factory=lambda: (9, 30))   # (hour, minute) server time
    session_end:   tuple = field(default_factory=lambda: (16, 0))

    # Execution gate
    manual_confirm: bool = True    # set False only after demo validation


def load_config() -> StrategyConfig:
    """Build StrategyConfig from environment variables."""
    return StrategyConfig(
        symbol       = os.getenv("SYMBOL",    "XAUUSD"),
        risk_pct     = float(os.getenv("RISK_PCT",   "1.0")),
        sl_points    = float(os.getenv("SL_POINTS",  "20.0")),
        tp_points    = float(os.getenv("TP_POINTS",  "30.0")),
        max_lots     = float(os.getenv("MAX_LOTS",   "2.0")),
        manual_confirm = os.getenv("MANUAL_CONFIRM", "true").lower() == "true",
    )


# ── Data fetch ────────────────────────────────────────────────────────────────

def _fetch(symbol: str, timeframe: int, count: int) -> pd.DataFrame:
    """Fetch OHLCV bars, skipping the forming bar (pos=1)."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No data for {symbol}: {mt5.last_error()}")
    df = pd.DataFrame(rates)
    df.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"}, inplace=True)
    return df


# ── Session filter ────────────────────────────────────────────────────────────

def is_in_trading_session(cfg: StrategyConfig) -> bool:
    if not cfg.use_session:
        return True
    import MetaTrader5 as mt5
    from datetime import datetime
    server_time = datetime.fromtimestamp(mt5.symbol_info_tick(cfg.symbol).time)
    mins  = server_time.hour * 60 + server_time.minute
    start = cfg.session_start[0] * 60 + cfg.session_start[1]
    end   = cfg.session_end[0]   * 60 + cfg.session_end[1]
    return start <= mins < end


# ── Main entry point ──────────────────────────────────────────────────────────

def find_setup(cfg: StrategyConfig) -> Optional[TradeSetup]:
    """
    Scan the most recent bars and return a TradeSetup if all entry conditions pass.
    Returns None if no valid setup is found.

    TODO: implement strategy rules here.
    """
    if not is_in_trading_session(cfg):
        return None

    # df = _fetch(cfg.symbol, cfg.timeframe, cfg.candle_count)
    # Rule 1: ...
    # Rule 2: ...

    return None   # placeholder — no strategy implemented yet
