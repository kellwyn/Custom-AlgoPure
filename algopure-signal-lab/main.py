"""
AlgoPure — Signal Lab
Usage: python main.py XAUUSD 3M
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()


def main():
    symbol   = sys.argv[1] if len(sys.argv) > 1 else os.getenv("SYMBOL", "XAUUSD")
    duration = sys.argv[2] if len(sys.argv) > 2 else "3M"

    import MetaTrader5 as mt5
    from config          import LabConfig
    from fetcher         import fetch_ohlcv
    from strategy_scan   import scan_setups
    from tp_analysis     import evaluate_outcomes, summary_stats
    from report          import print_summary, print_setups

    cfg = LabConfig(symbol=symbol)

    if not mt5.initialize():
        print(f"MT5 init failed: {mt5.last_error()}")
        return

    try:
        print(f"Fetching {symbol} {cfg.analysis_tf} — {duration}...")
        df = fetch_ohlcv(cfg, duration)
        print(f"  {len(df)} bars loaded.")

        setups  = scan_setups(df, cfg)
        results = evaluate_outcomes(df, setups)
        stats   = summary_stats(results)

        print_summary(stats, symbol, duration)
        print_setups(results)

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
