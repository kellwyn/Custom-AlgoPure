"""
AlgoPure — Execution Algorithm Bot  v2.0
Natural language REPL for manual-decision trade execution via MetaTrader 5.

Usage:
  python main.py [--profile PROFILE] [--symbol SYMBOL] [--no-confirm]

Examples:
  python main.py --profile metaquotes
  python main.py --symbol XAUUSDp --profile blackbull-spot
"""

import argparse
import logging
import os
import sys
import threading
import time

from dotenv import load_dotenv

load_dotenv()

os.makedirs("logs", exist_ok=True)   # must exist before FileHandler opens it

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    handlers= [
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("algopure-bot")


# ── Profile resolution ────────────────────────────────────────────────────────

def _apply_profile(profile: str):
    prefix = f"PROFILE_{profile.upper().replace('-', '_')}_"
    for key, val in os.environ.items():
        if key.startswith(prefix):
            override = key[len(prefix):]
            os.environ[override] = val


# ── Background trailing-stop monitor ─────────────────────────────────────────

def _trailing_monitor(mgr, stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            mgr.update_trailing_stops()
        except Exception as exc:
            log.debug("Trailing monitor error: %s", exc)
        stop_event.wait(1.0)


# ── REPL ──────────────────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║         AlgoPure  —  Execution Algorithm Bot  v2.0          ║
║  Type 'help' for commands.  Type 'exit' to quit.            ║
╚══════════════════════════════════════════════════════════════╝
"""

def repl(executor, mgr, default_symbol: str):
    from bot.commands import parse_command

    print(BANNER)
    print(f"  Default symbol : {default_symbol}")
    print(f"  Manual confirm : {executor.cfg.manual_confirm}")
    print(f"  Max lots       : {executor.cfg.max_lots}")
    print(f"  Daily limit    : ${executor.cfg.daily_loss_limit:,.2f}")
    print()

    while True:
        try:
            raw = input("algopure> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Interrupted — type 'exit' to quit cleanly.")
            continue

        if not raw:
            continue

        try:
            cmd = parse_command(raw, default_symbol=default_symbol)
            executor.process(cmd)
        except SystemExit:
            print("  Disconnecting and shutting down...")
            break
        except Exception as exc:
            log.exception("REPL error: %s", exc)
            print(f"  ✗ Unexpected error: {exc}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AlgoPure execution bot")
    parser.add_argument("--profile",    help="Broker profile (e.g. metaquotes, blackbull-spot)")
    parser.add_argument("--symbol",     help="Default symbol (e.g. XAUUSD, XAUUSDp, GOLD.f)")
    parser.add_argument("--no-confirm", action="store_true",
                        help="Disable manual confirmation (auto-execute — use with care)")
    args = parser.parse_args()

    if args.profile:
        _apply_profile(args.profile)
    if args.symbol:
        os.environ["SYMBOL"] = args.symbol

    # ── Lazy imports after env vars are resolved ───────────────────────────────
    from bot.connection  import connect, disconnect
    from bot.config      import load_exec_config
    from bot.order_manager import OrderManager
    from bot.executor    import Executor

    cfg = load_exec_config()
    if args.no_confirm:
        cfg.manual_confirm = False
        log.warning("Manual confirmation disabled — orders will execute automatically.")

    connect()

    # Pre-cache symbol info so the first order has zero lookup overhead
    from bot.trader import warm_symbol
    if warm_symbol(cfg.default_symbol):
        log.info("Symbol cache warmed: %s", cfg.default_symbol)

    mgr      = OrderManager(cfg)
    executor = Executor(cfg, mgr)

    stop_ev  = threading.Event()
    monitor  = threading.Thread(
        target  = _trailing_monitor,
        args    = (mgr, stop_ev),
        daemon  = True,
        name    = "trailing-monitor",
    )
    monitor.start()

    try:
        repl(executor, mgr, cfg.default_symbol)
    finally:
        stop_ev.set()
        monitor.join(timeout=2)
        disconnect()


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    main()
