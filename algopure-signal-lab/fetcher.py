"""
Fetch historical OHLCV data from MT5 for a requested duration.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from config import LabConfig, DURATIONS

_TF_MAP = {
    "M1":  mt5.TIMEFRAME_M1,
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
}


def fetch_ohlcv(cfg: LabConfig, duration_key: str) -> pd.DataFrame:
    """
    Fetch bars for the requested duration from MT5.
    Returns a DataFrame with OHLCV + derived columns.
    """
    days = DURATIONS[duration_key]
    tf   = _TF_MAP.get(cfg.analysis_tf.upper(), mt5.TIMEFRAME_M30)

    bars_needed = int(days * 48 * 1.35) + 300

    rates = mt5.copy_rates_from_pos(cfg.symbol, tf, 1, bars_needed)
    if rates is None or len(rates) == 0:
        raise RuntimeError(
            f"No data for {cfg.symbol} {cfg.analysis_tf}: {mt5.last_error()}"
        )

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"}, inplace=True)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    df = df[df["time"] >= cutoff].copy().reset_index(drop=True)

    if df.empty:
        raise RuntimeError(f"No data within last {days} days for {cfg.symbol}.")

    # Session tags
    df["hour"] = df["time"].dt.hour
    df["is_session"] = (
        (df["hour"] >= cfg.session_start_h) & (df["hour"] < cfg.session_end_h)
    )

    # Per-bar derived metrics
    df["move_pct"]  = (df["c"] - df["o"]).abs() / df["o"] * 100.0
    df["range_pct"] = (df["h"] - df["l"]) / df["o"] * 100.0
    df["dir_pct"]   = (df["c"] - df["o"]) / df["o"] * 100.0
    df["is_buy"]    = df["c"] > df["o"]
    df["is_sell"]   = df["c"] < df["o"]
    df["is_big"]    = df["move_pct"] >= cfg.big_move_pct
    df["is_tight"]  = df["range_pct"] < cfg.tight_range_pct
    df["log_ret"]   = np.log(df["c"] / df["c"].shift(1))

    return df
