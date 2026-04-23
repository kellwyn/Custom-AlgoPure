"""
Historical strategy scan — AlgoPure.
Implement scan_setups() to detect historical entry signals from OHLCV data.
"""
from __future__ import annotations

from typing import List, Dict, Any

import pandas as pd

from config import LabConfig


def scan_setups(df: pd.DataFrame, cfg: LabConfig) -> List[Dict[str, Any]]:
    """
    Scan historical bars for entry signals.
    Returns a list of setup dicts with keys: time, direction, entry, stop_loss, target.

    TODO: implement strategy rules here.
    """
    setups = []

    # for i in range(lookback, len(df)):
    #     # Rule 1: ...
    #     pass

    return setups
