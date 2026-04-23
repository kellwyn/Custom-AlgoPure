"""
Console reporting — AlgoPure signal lab.
"""
from __future__ import annotations

from typing import List, Dict, Any


def print_summary(stats: Dict[str, Any], symbol: str, duration: str):
    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  AlgoPure — Signal Lab Results")
    print(f"  Symbol: {symbol}   Duration: {duration}")
    print(sep)
    print(f"  Total setups : {stats['total']}")
    print(f"  Wins         : {stats.get('wins', 0)}")
    print(f"  Losses       : {stats.get('losses', 0)}")
    print(f"  Win rate     : {stats['win_rate']}%")
    print(f"  Avg P&L pts  : {stats['avg_pnl']}")
    print(f"  Expectancy   : {stats['expectancy']} pts/trade")
    print(sep)


def print_setups(setups: List[Dict[str, Any]], limit: int = 20):
    if not setups:
        print("  No setups found.")
        return
    print(f"\n  Last {min(limit, len(setups))} setups:")
    for s in setups[-limit:]:
        print(f"  {s.get('time','')}  {s.get('direction','?'):5s}  "
              f"entry={s.get('entry',0):.5f}  outcome={s.get('outcome','?')}")
