"""
TP/SL outcome evaluation — AlgoPure.
Given a list of setups, determines which hit TP, which hit SL, and calculates win rate.
"""
from __future__ import annotations

from typing import List, Dict, Any

import pandas as pd


def evaluate_outcomes(df: pd.DataFrame, setups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    For each setup, scan forward bars to determine if TP or SL was hit first.
    Appends 'outcome' ("TP" | "SL" | "OPEN"), 'bars_held', 'pnl_pts' to each setup dict.

    TODO: implement outcome evaluation.
    """
    results = []
    for setup in setups:
        setup = setup.copy()
        setup["outcome"]   = "OPEN"
        setup["bars_held"] = 0
        setup["pnl_pts"]   = 0.0
        results.append(setup)
    return results


def summary_stats(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute win rate, average R:R, expectancy from evaluated setups."""
    if not results:
        return {"total": 0, "win_rate": 0.0, "avg_rr": 0.0, "expectancy": 0.0}

    total = len(results)
    wins  = sum(1 for r in results if r.get("outcome") == "TP")
    pnl   = [r.get("pnl_pts", 0.0) for r in results]

    return {
        "total":      total,
        "wins":       wins,
        "losses":     total - wins,
        "win_rate":   round(wins / total * 100, 1),
        "avg_pnl":    round(sum(pnl) / total, 2),
        "expectancy": round(sum(pnl) / total, 4),
    }
