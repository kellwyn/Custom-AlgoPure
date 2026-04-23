"""
Signal lab configuration — AlgoPure.
"""

from dataclasses import dataclass, field

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

    # Session definition (server time hours)
    session_start_h: int   = 9
    session_start_m: int   = 30
    session_end_h:   int   = 16
    session_end_m:   int   = 0
    rth_start_h:     int   = 9
    rth_end_h:       int   = 16

    # Candle thresholds
    big_move_pct:    float = 0.3
    tight_range_pct: float = 0.05

    # TODO: add strategy-specific scan parameters here
