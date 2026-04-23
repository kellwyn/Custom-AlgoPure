"""
Signal lab configuration — AlgoPure.

ALL time fields are UTC hours/minutes.
MT5 Unix timestamps are converted to UTC in fetcher.py — every hour reference here
must be expressed in UTC, not broker server time or local time.

ICT RTH reference times (UTC):
  Gold / XAUUSD / XAUUSDp / GOLD.f
    COMEX floor + NY session:  13:30 – 20:00 UTC  (= 09:30–16:00 US/Eastern)
  NQ / ES / US equities
    NYSE/CME RTH:              14:30 – 21:00 UTC  (= 09:30–16:00 US/Eastern)
  London equities / FTSE
    LSE session:               08:00 – 16:30 UTC

The 48-slot chart covers all 24 UTC hours; slot N labels are UTC clock times.
"""

from dataclasses import dataclass

DURATIONS = {
    "1W":  7,
    "1M":  30,
    "3M":  90,
    "6M":  180,
    "1Y":  365,
    "3Y":  1095,
}


@dataclass
class LabConfig:
    symbol:          str   = "XAUUSD"
    analysis_tf:     str   = "M30"

    # ── Broad "active session" tag applied to every bar in fetcher.py ─────────
    # For gold: London + NY overlap + full NY = 08:00–20:00 UTC
    # (used only for is_session flag; not the ICT RTH window)
    session_start_h: int   = 8
    session_start_m: int   = 0
    session_end_h:   int   = 20
    session_end_m:   int   = 0

    # ── ICT RTH window used for RTH-only slot chart and session daily analysis ─
    # Gold / XAUUSDp / GOLD.f  →  COMEX RTH = 13:30–20:00 UTC
    rth_start_h:     int   = 13
    rth_start_m:     int   = 30
    rth_end_h:       int   = 20
    rth_end_m:       int   = 0

    # ── Candle thresholds ─────────────────────────────────────────────────────
    big_move_pct:    float = 0.3
    tight_range_pct: float = 0.05
