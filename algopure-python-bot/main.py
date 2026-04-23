"""
AlgoPure — Python Trading Bot
Version : 1.0.0
Date    : 2026-04-23
Author  : kellwyn

Strategy rules are TBD — implement find_setup() in bot/strategy.py.
"""

import argparse
import os
import time
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("algopure-bot")


def _resolve_profile(profile: str):
    """Apply PROFILE_<NAME>_* env vars, overriding base .env values."""
    prefix = f"PROFILE_{profile.upper().replace('-', '_')}_"
    for key, val in os.environ.items():
        if key.startswith(prefix):
            override = key[len(prefix):]
            os.environ[override] = val
            log.info("Profile %s: %s = %s", profile, override, val)


def main():
    parser = argparse.ArgumentParser(description="AlgoPure trading bot")
    parser.add_argument("--profile", help="Broker profile (e.g. metaquotes, blackbull-spot)")
    parser.add_argument("--symbol",  help="Override symbol (e.g. XAUUSD, XAUUSDp, GOLD.f)")
    args = parser.parse_args()

    if args.profile:
        _resolve_profile(args.profile)
    if args.symbol:
        os.environ["SYMBOL"] = args.symbol

    from bot.connection import connect, disconnect
    from bot.strategy   import load_config

    cfg = load_config()
    log.info("AlgoPure v1.0.0 starting — symbol=%s  manual_confirm=%s",
             cfg.symbol, cfg.manual_confirm)

    connect()

    try:
        run_loop(cfg)
    finally:
        disconnect()


def run_loop(cfg):
    import MetaTrader5 as mt5
    from bot.strategy import find_setup
    from bot.trader   import execute_setup

    last_bar = None

    while True:
        try:
            bars = mt5.copy_rates_from_pos(cfg.symbol, cfg.timeframe, 0, 5)
            if bars is None or len(bars) < 2:
                time.sleep(1)
                continue

            current_bar_time = bars[-1]["time"]
            if current_bar_time == last_bar:
                time.sleep(0.5)
                continue
            last_bar = current_bar_time

            setup = find_setup(cfg)
            if setup:
                log.info("Setup detected: %s %s  entry=%.5f  sl=%.5f  tp=%.5f",
                         setup.direction, setup.symbol,
                         setup.entry, setup.stop_loss, setup.target)
                execute_setup(setup, cfg)

        except KeyboardInterrupt:
            log.info("Interrupted by user.")
            break
        except Exception as exc:
            log.exception("Loop error: %s", exc)
            time.sleep(2)


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    main()
