"""
48-slot market character and ICT RTH session daily analysis.
Implements the same logic as slot-market-char and ict-session-analysis skills,
inline for use in the signal lab dashboard.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional


# ── RSI ──────────────────────────────────────────────────────────────────────

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta.clip(upper=0))
    avg_g = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_l = loss.ewm(com=period - 1, min_periods=period).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _volat_label(val: float, series: pd.Series) -> str:
    p25, p75 = series.quantile(0.25), series.quantile(0.75)
    if val >= p75: return "HIGH"
    if val <= p25: return "LOW"
    return "NORM"


def _vol_label_threshold(val: float, daily_mean: float) -> str:
    if val >= daily_mean * 1.5: return "HIGH"
    if val <= daily_mean * 0.5: return "LOW"
    return "NORM"


# ── 48-slot market character ──────────────────────────────────────────────────

def compute_slot_char(df: pd.DataFrame, big_move_pct: float = 0.3,
                      tight_range_pct: float = 0.05,
                      rth_only: bool = False,
                      rth_start_h: int = 13, rth_end_h: int = 20) -> pd.DataFrame:
    """
    Aggregate M30 bars into 48 time slots per 24h.
    slot = hour*2 + (minute>=30).
    """
    df = df.copy()
    df["rsi"] = compute_rsi(df["c"])
    df["slot"] = df["time"].dt.hour * 2 + (df["time"].dt.minute >= 30).astype(int)

    if rth_only:
        df = df[(df["time"].dt.hour >= rth_start_h) & (df["time"].dt.hour < rth_end_h)]

    # ICT session average volume (for % comparison)
    ict_mask  = (df["time"].dt.hour >= rth_start_h) & (df["time"].dt.hour < rth_end_h)
    ict_avg_v = df.loc[ict_mask, "tick_volume"].mean() if ict_mask.any() else 1
    daily_avg_v = df["tick_volume"].mean()

    agg = df.groupby("slot").agg(
        n_bars   = ("c", "count"),
        pct_buy  = ("is_buy", "mean"),
        pct_sell = ("is_sell", "mean"),
        avg_rsi  = ("rsi", "mean"),
        avg_vol  = ("tick_volume", "mean"),
        avg_range= ("range_pct", "mean"),
        pct_big  = ("is_big", "mean"),
        pct_tight= ("is_tight", "mean"),
        avg_close= ("c", "mean"),
    ).reset_index()

    agg["bias"]       = (agg["pct_buy"] - agg["pct_sell"]) * 100
    agg["bias_score"] = agg["bias"].abs()
    agg["money_spent"]= agg["avg_vol"] * agg["avg_close"]
    agg["ict_vol_pct"]= agg["avg_vol"] / ict_avg_v * 100
    agg["daily_vol_pct"] = agg["avg_vol"] / daily_avg_v * 100

    agg["volat_lbl"] = agg["avg_range"].apply(lambda v: _volat_label(v, agg["avg_range"]))
    agg["vol_lbl"]   = agg["avg_vol"].apply(lambda v: _vol_label_threshold(v, daily_avg_v))

    # Slot → HH:MM label
    def slot_to_hhmm(s):
        h = s // 2
        m = 30 * (s % 2)
        return f"{h:02d}:{m:02d}"

    agg["time_label"] = agg["slot"].apply(slot_to_hhmm)
    agg["pct_buy"]   = (agg["pct_buy"]  * 100).round(1)
    agg["pct_sell"]  = (agg["pct_sell"] * 100).round(1)
    agg["pct_big"]   = (agg["pct_big"]  * 100).round(1)
    agg["pct_tight"] = (agg["pct_tight"]* 100).round(1)

    return agg.sort_values("slot").reset_index(drop=True)


# ── ICT RTH session daily analysis ───────────────────────────────────────────

def compute_ict_sessions(
    df: pd.DataFrame,
    rth_start_h: int = 13, rth_start_m: int = 30,
    rth_end_h: int = 20,   rth_end_m: int = 0,
    n_days: int = 20,
    rolling_days: int = 30,
) -> pd.DataFrame:
    """
    Per-day ICT RTH session metrics for the last n_days, with 30-day rolling baselines.
    Flags anomalies (> 1.5σ from rolling mean).
    """
    df = df.copy()
    df["rsi"]  = compute_rsi(df["c"])
    df["date"] = df["time"].dt.date

    # RTH filter (in minutes since midnight UTC)
    rth_start_min = rth_start_h * 60 + rth_start_m
    rth_end_min   = rth_end_h   * 60 + rth_end_m
    df["mins"] = df["time"].dt.hour * 60 + df["time"].dt.minute
    rth_df     = df[(df["mins"] >= rth_start_min) & (df["mins"] < rth_end_min)].copy()

    # Daily total volume (all sessions)
    daily_all = df.groupby("date").agg(
        daily_vol = ("tick_volume", "sum"),
    ).reset_index()

    # RTH session per day
    daily_rth = rth_df.groupby("date").agg(
        sess_vol    = ("tick_volume", "sum"),
        money_spent = ("tick_volume", lambda x: (x * rth_df.loc[x.index, "c"]).sum()),
        pct_buy     = ("is_buy",  "mean"),
        pct_sell    = ("is_sell", "mean"),
        avg_rsi     = ("rsi",     "mean"),
        avg_range   = ("range_pct", "mean"),
    ).reset_index()

    merged = daily_rth.merge(daily_all, on="date", how="left")
    merged = merged.sort_values("date").reset_index(drop=True)

    # 30-day rolling baselines
    merged["sess_baseline"]  = merged["sess_vol"].rolling(rolling_days, min_periods=5).mean()
    merged["daily_baseline"] = merged["daily_vol"].rolling(rolling_days, min_periods=5).mean()
    merged["range_baseline"] = merged["avg_range"].rolling(rolling_days, min_periods=5).mean()
    merged["range_std"]      = merged["avg_range"].rolling(rolling_days, min_periods=5).std()
    merged["sess_std"]       = merged["sess_vol"].rolling(rolling_days, min_periods=5).std()

    merged["vs_sess_pct"]   = merged["sess_vol"]  / merged["sess_baseline"]  * 100
    merged["vs_daily_pct"]  = merged["daily_vol"] / merged["daily_baseline"] * 100

    # Volatility label (range_pct vs rolling ± 1.5σ)
    def _vl(row):
        if pd.isna(row["range_baseline"]) or pd.isna(row["range_std"]):
            return "NORM"
        hi = row["range_baseline"] + 1.5 * row["range_std"]
        lo = row["range_baseline"] - 1.5 * row["range_std"]
        if row["avg_range"] >= hi: return "HIGH"
        if row["avg_range"] <= lo: return "LOW"
        return "NORM"

    merged["volat_lbl"] = merged.apply(_vl, axis=1)

    # Anomaly flags
    def _anomalies(row):
        flags = []
        if not pd.isna(row.get("sess_std")) and row["sess_std"] > 0:
            z = (row["sess_vol"] - row["sess_baseline"]) / row["sess_std"]
            if z > 1.5:  flags.append(f"sess_vol↑(+{z:.1f}σ)")
            if z < -1.5: flags.append(f"sess_vol↓({z:.1f}σ)")
        if row["pct_buy"] >= 0.70:  flags.append("BUYER_DOM")
        if row["pct_sell"] >= 0.70: flags.append("SELLER_DOM")
        if row["avg_rsi"] >= 70:    flags.append(f"RSI↑({row['avg_rsi']:.0f})")
        if row["avg_rsi"] <= 30:    flags.append(f"RSI↓({row['avg_rsi']:.0f})")
        if row["volat_lbl"] == "HIGH": flags.append("VOL↑")
        if row["volat_lbl"] == "LOW":  flags.append("VOL↓")
        return ", ".join(flags)

    merged["anomaly"] = merged.apply(_anomalies, axis=1)

    # Limit to last n_days
    all_dates = sorted(merged["date"].unique())
    recent_dates = all_dates[-n_days:]
    result = merged[merged["date"].isin(recent_dates)].copy()

    result["pct_buy"]  = (result["pct_buy"]  * 100).round(1)
    result["pct_sell"] = (result["pct_sell"] * 100).round(1)

    return result.reset_index(drop=True)
