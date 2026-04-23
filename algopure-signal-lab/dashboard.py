"""
AlgoPure Signal Lab — Live Position Dashboard
Usage:
  python dashboard.py [SYMBOL] [--profile PROFILE] [--watch N]

Options:
  SYMBOL      Symbol to pull historical analysis for (default: XAUUSD)
  --profile   Broker profile (e.g. metaquotes, blackbull-spot)
  --watch N   Auto-refresh every N seconds (default: single snapshot)
  --rth       Restrict slot market chart to RTH bars only
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import MetaTrader5 as mt5
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich import box
from rich.panel import Panel
from rich.columns import Columns

console = Console(width=220, force_terminal=True, highlight=False)


# ── MT5 utilities ─────────────────────────────────────────────────────────────

def _sym_info(symbol: str):
    info = mt5.symbol_info(symbol)
    if info is None:
        mt5.symbol_select(symbol, True)
        info = mt5.symbol_info(symbol)
    return info


def _connect(profile: Optional[str] = None):
    import keyring
    if profile:
        prefix = f"PROFILE_{profile.upper().replace('-', '_')}_"
        for k, v in os.environ.items():
            if k.startswith(prefix):
                os.environ[k[len(prefix):]] = v

    p    = os.getenv("KEYRING_PROFILE", "algopure")
    login = keyring.get_password("mt5", f"{p}_login")    or os.getenv("MT5_LOGIN")
    pw    = keyring.get_password("mt5", f"{p}_password") or os.getenv("MT5_PASSWORD")
    srv   = keyring.get_password("mt5", f"{p}_server")   or os.getenv("MT5_SERVER")

    kwargs = {}
    mt5_path = os.getenv("MT5_PATH")
    if mt5_path: kwargs["path"] = mt5_path
    if login and pw and srv:
        kwargs.update(login=int(login), password=pw, server=srv)

    ok = mt5.initialize(**kwargs) if kwargs else mt5.initialize()
    if not ok:
        console.print(f"[red]MT5 init failed: {mt5.last_error()}[/red]")
        sys.exit(1)


# ── Historical data cache ─────────────────────────────────────────────────────

_hist_cache: dict = {"df": None, "ts": 0}
_CACHE_TTL = 300  # 5 min


def _get_hist(symbol: str, duration: str = "3M") -> Optional[pd.DataFrame]:
    now = time.time()
    if _hist_cache["df"] is None or (now - _hist_cache["ts"]) > _CACHE_TTL:
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from config  import LabConfig
            from fetcher import fetch_ohlcv
            cfg = LabConfig(symbol=symbol)
            _hist_cache["df"] = fetch_ohlcv(cfg, duration)
            _hist_cache["ts"] = now
        except Exception as exc:
            console.print(f"[yellow]Historical data unavailable: {exc}[/yellow]")
            return None
    return _hist_cache["df"]


# ── Rich table builders ───────────────────────────────────────────────────────

def _style_pnl(val_str: str) -> str:
    if val_str.startswith("$+") or (val_str.startswith("+") and "$" in val_str):
        return f"[green]{val_str}[/green]"
    if val_str.startswith("$-") or (val_str.startswith("-") and "$" in val_str):
        return f"[red]{val_str}[/red]"
    return val_str


def build_positions_table(positions) -> Table:
    t = Table(
        title="LIVE POSITIONS", box=box.ROUNDED,
        title_style="bold white on dark_blue",
        header_style="bold cyan",
    )
    for col in ["Ticket", "Symbol", "Side", "Lots", "Entry", "Current", "SL", "TP", "P&L $", "Trail"]:
        t.add_column(col, justify="right" if col not in ("Symbol", "Side", "Trail") else "center")

    for p in positions:
        side  = "[green]LONG[/green]" if p.type == mt5.ORDER_TYPE_BUY else "[red]SHORT[/red]"
        tick  = mt5.symbol_info_tick(p.symbol)
        cur   = (f"{tick.bid:.5f}" if p.type == mt5.ORDER_TYPE_BUY else f"{tick.ask:.5f}") if tick else "—"
        pnl   = f"${p.profit:+,.2f}"
        pnl_s = f"[green]{pnl}[/green]" if p.profit >= 0 else f"[red]{pnl}[/red]"
        trail = "[yellow]●[/yellow]" if False else ""   # trailing flag handled by executor
        t.add_row(
            str(p.ticket), p.symbol, side, f"{p.volume:.2f}",
            f"{p.price_open:.5f}", cur, f"{p.sl:.5f}", f"{p.tp:.5f}", pnl_s, trail,
        )

    if not positions:
        t.add_row(*["—"] * 10)

    return t


def build_risk_metrics_table_rich(df: pd.DataFrame, title: str) -> Table:
    t = Table(title=title, box=box.SIMPLE_HEAVY, header_style="bold yellow")
    for col in df.columns:
        t.add_column(col)
    for _, row in df.iterrows():
        cells = []
        for col, val in row.items():
            val_s = str(val)
            if col in ("P&L $", "% Account"):
                if "+" in val_s and val_s not in ("—",):
                    val_s = f"[green]{val_s}[/green]"
                elif any(c in val_s for c in ["-$", "-0.", "-1", "-2", "-3", "-4", "-5", "-6", "-7", "-8", "-9"]):
                    val_s = f"[red]{val_s}[/red]"
            cells.append(val_s)
        t.add_row(*cells)
    return t


def build_scenario_table_rich(df: pd.DataFrame, title: str) -> Table:
    t = Table(title=title, box=box.SIMPLE_HEAVY, header_style="bold magenta")
    for col in df.columns:
        t.add_column(col)
    for _, row in df.iterrows():
        cells = []
        for col, val in row.items():
            val_s = str(val)
            if col == "Outcome":
                if val_s == "WIN":   val_s = "[green]WIN[/green]"
                elif val_s == "LOSS": val_s = "[red]LOSS[/red]"
            elif col in ("P&L $",):
                val_s = f"[green]{val_s}[/green]" if "+" in val_s else f"[red]{val_s}[/red]"
            cells.append(val_s)
        t.add_row(*cells)
    return t


def build_generic_table(df: pd.DataFrame, title: str,
                        title_style: str = "bold white") -> Table:
    t = Table(title=title, box=box.ROUNDED, title_style=title_style, header_style="bold cyan")
    for col in df.columns:
        t.add_column(str(col), overflow="fold")
    for _, row in df.iterrows():
        t.add_row(*[str(v) for v in row])
    return t


def build_slot_char_table(df: pd.DataFrame, top_n: int = 48) -> Table:
    t = Table(
        title="48-SLOT MARKET CHARACTER  [ALL SESSIONS]",
        box=box.ROUNDED, title_style="bold white on dark_green",
        header_style="bold green",
    )
    col_defs = [
        ("Time",       5, "center"),
        ("N",          4, "right"),
        ("%Buy",       6, "right"),
        ("%Sell",      6, "right"),
        ("Bias",       6, "right"),
        ("VolatLbl",   6, "center"),
        ("RSI",        5, "right"),
        ("VolLbl",     5, "center"),
        ("AvgTickVol", 10, "right"),
        ("%ICTVol",    7, "right"),
        ("%DayVol",    7, "right"),
        ("%Big",       5, "right"),
        ("%Tight",     6, "right"),
        ("MoneySpent", 12, "right"),
    ]
    for name, width, just in col_defs:
        t.add_column(name, min_width=width, justify=just, no_wrap=True)

    df_s = df.sort_values("avg_vol", ascending=False).head(top_n)
    for _, row in df_s.iterrows():
        vl_style = {"HIGH": "[red]HIGH[/red]", "LOW": "[blue]LOW[/blue]", "NORM": "NORM"}
        bias_s = f"{row['bias']:+.1f}"
        bias_c = f"[green]{bias_s}[/green]" if row["bias"] > 5 else (
                 f"[red]{bias_s}[/red]" if row["bias"] < -5 else bias_s)
        t.add_row(
            row["time_label"],
            str(int(row["n_bars"])),
            f"{row['pct_buy']:.1f}%",
            f"{row['pct_sell']:.1f}%",
            bias_c,
            vl_style.get(row["volat_lbl"], row["volat_lbl"]),
            f"{row['avg_rsi']:.1f}",
            vl_style.get(row["vol_lbl"], row["vol_lbl"]),
            f"{row['avg_vol']:,.0f}",
            f"{row['ict_vol_pct']:.0f}%",
            f"{row['daily_vol_pct']:.0f}%",
            f"{row['pct_big']:.1f}%",
            f"{row['pct_tight']:.1f}%",
            f"{row['money_spent']:,.0f}",
        )
    return t


def build_ict_session_table(df: pd.DataFrame) -> Table:
    t = Table(
        title="ICT RTH SESSION ANALYSIS  [LAST 20 DAYS]",
        box=box.ROUNDED, title_style="bold white on dark_red",
        header_style="bold red",
    )
    cols = [
        ("Date",       10, "left"),
        ("SessVol",    10, "right"),
        ("30dSess",    10, "right"),
        ("%vSess",      7, "right"),
        ("DailyVol",   10, "right"),
        ("30dDaily",   10, "right"),
        ("%vDaily",     8, "right"),
        ("MoneySpent", 13, "right"),
        ("%Buy",        6, "right"),
        ("%Sell",       6, "right"),
        ("AvgRSI",      7, "right"),
        ("Volat",       5, "center"),
        ("Anomalies",  40, "left"),
    ]
    for name, width, just in cols:
        t.add_column(name, min_width=width, max_width=width if name != "Anomalies" else 50,
                     justify=just, no_wrap=True)

    for _, row in df.iterrows():
        anom  = str(row.get("anomaly", ""))
        flag  = "! " if anom else "  "
        date_s = f"{flag}{row['date']}"
        vl_style = {"HIGH": "[red]HIGH[/red]", "LOW": "[blue]LOW[/blue]", "NORM": "NORM"}
        vs_s = f"{row['vs_sess_pct']:.0f}%"  if not pd.isna(row.get("vs_sess_pct")) else "—"
        vd_s = f"{row['vs_daily_pct']:.0f}%" if not pd.isna(row.get("vs_daily_pct")) else "—"
        t.add_row(
            date_s,
            f"{row['sess_vol']:,.0f}",
            f"{row['sess_baseline']:,.0f}" if not pd.isna(row.get("sess_baseline")) else "—",
            vs_s,
            f"{row['daily_vol']:,.0f}",
            f"{row['daily_baseline']:,.0f}" if not pd.isna(row.get("daily_baseline")) else "—",
            vd_s,
            f"{row['money_spent']:,.0f}",
            f"{row['pct_buy']:.1f}%",
            f"{row['pct_sell']:.1f}%",
            f"{row['avg_rsi']:.1f}",
            vl_style.get(row["volat_lbl"], row["volat_lbl"]),
            f"[yellow]{anom}[/yellow]" if anom else "",
        )
    return t


# ── Full dashboard snapshot ───────────────────────────────────────────────────

def render_dashboard(symbol: str, rth_only: bool = False):
    from live_metrics import (
        build_risk_metrics_table, scenario_table,
        sl_alternatives, tp_alternatives, hedge_breakeven_table,
    )
    from market_analysis import compute_slot_char, compute_ict_sessions

    acct = mt5.account_info()
    if acct is None:
        console.print("[red]Cannot retrieve account info[/red]")
        return

    balance  = acct.balance
    currency = acct.currency
    ts_str   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    console.rule(f"[bold white]AlgoPure Signal Lab  ·  {ts_str}[/bold white]")
    console.print(
        f"  Account: [bold]{acct.name}[/bold]  #{acct.login}  |  "
        f"Balance: [green]${balance:,.2f} {currency}[/green]  |  "
        f"Equity: [cyan]${acct.equity:,.2f}[/cyan]  |  "
        f"Margin: ${acct.margin:,.2f}  |  "
        f"Free Margin: ${acct.margin_free:,.2f}"
    )
    console.print()

    # ── Live positions ─────────────────────────────────────────────────────
    positions = mt5.positions_get() or []
    console.print(build_positions_table(positions))
    console.print()

    # ── Per-position risk tables ───────────────────────────────────────────
    for pos in positions:
        direction = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
        info      = _sym_info(pos.symbol)
        if info is None:
            continue

        tick_sz = info.trade_tick_size
        tick_v  = info.trade_tick_value
        tick    = mt5.symbol_info_tick(pos.symbol)
        current = (tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask) if tick else pos.price_current
        sl      = pos.sl if pos.sl > 0 else None
        tp      = pos.tp if pos.tp > 0 else None

        header = (
            f"#{pos.ticket}  {pos.symbol}  {direction}  "
            f"{pos.volume} lots @ {pos.price_open:.5f}  |  "
            f"Current: {current:.5f}  |  P&L: ${pos.profit:+,.2f}"
        )
        console.print(Panel(header, style="bold white on grey23"))

        # Risk metrics
        risk_df = build_risk_metrics_table(
            entry=pos.price_open, current=current, sl=sl, tp=tp,
            lots=pos.volume, direction=direction, balance=balance,
            tick_size=tick_sz, tick_value=tick_v,
            daily_loss_limit=8000.0, drawdown_limit=5000.0,
        )
        console.print(build_risk_metrics_table_rich(risk_df, f"RISK METRICS — #{pos.ticket}"))
        console.print()

        # Scenario analysis
        sc_df = scenario_table(
            entry=pos.price_open, current=current, sl=sl, tp=tp,
            lots=pos.volume, direction=direction, balance=balance,
            tick_size=tick_sz, tick_value=tick_v,
        )
        console.print(build_scenario_table_rich(sc_df, "HYPOTHETICAL SCENARIOS (5 price points)"))
        console.print()

        # SL / TP optimization
        sl_df = sl_alternatives(pos.price_open, sl, pos.volume, direction, balance, tick_sz, tick_v)
        tp_df = tp_alternatives(pos.price_open, sl, tp, pos.volume, direction, balance, tick_sz, tick_v)
        console.print(Columns([
            build_generic_table(sl_df, "STOP LOSS OPTIONS (3 alternatives)", "bold red"),
            build_generic_table(tp_df, "TAKE PROFIT OPTIONS (3 alternatives)", "bold green"),
        ]))
        console.print()

        # Hedge break-even
        hg_df = hedge_breakeven_table(pos.price_open, current, pos.volume, direction, tick_sz, tick_v)
        console.print(build_generic_table(hg_df, "HEDGE BREAK-EVEN ANALYSIS", "bold magenta"))
        console.print()

    # ── Market character (historical) ──────────────────────────────────────
    hist_df = _get_hist(symbol)
    if hist_df is not None and not hist_df.empty:
        from config import LabConfig
        cfg = LabConfig(symbol=symbol)
        slot_df = compute_slot_char(
            hist_df,
            big_move_pct   = cfg.big_move_pct,
            tight_range_pct= cfg.tight_range_pct,
            rth_only       = rth_only,
            rth_start_h    = cfg.rth_start_h,
            rth_end_h      = cfg.rth_end_h,
        )
        console.print(build_slot_char_table(slot_df))
        console.print()

        # ICT session daily  (all times UTC)
        ict_df = compute_ict_sessions(
            hist_df,
            rth_start_h = cfg.rth_start_h,
            rth_start_m = cfg.rth_start_m,
            rth_end_h   = cfg.rth_end_h,
            rth_end_m   = cfg.rth_end_m,
            n_days      = 20,
            rolling_days= 30,
        )
        console.print(build_ict_session_table(ict_df))
        console.print()

        # Anomaly digest
        anomalous = ict_df[ict_df["anomaly"].str.len() > 0]
        if not anomalous.empty:
            console.print("[bold yellow]  ANOMALY DIGEST:[/bold yellow]")
            for _, row in anomalous.iterrows():
                console.print(f"    [yellow]⚠[/yellow]  {row['date']}  →  {row['anomaly']}")
            console.print()

    console.rule()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AlgoPure Signal Lab Dashboard")
    parser.add_argument("symbol",    nargs="?", default=None, help="Symbol (default: from .env)")
    parser.add_argument("--profile", help="Broker profile")
    parser.add_argument("--watch",   type=int, default=0,
                        help="Auto-refresh interval in seconds (0 = single snapshot)")
    parser.add_argument("--rth",     action="store_true", help="Slot chart: RTH only")
    args = parser.parse_args()

    _connect(args.profile)

    symbol = args.symbol or os.getenv("SYMBOL", "XAUUSD")

    try:
        if args.watch > 0:
            while True:
                console.clear()
                render_dashboard(symbol, rth_only=args.rth)
                console.print(f"  [dim]Auto-refreshing every {args.watch}s — Ctrl+C to stop[/dim]")
                time.sleep(args.watch)
        else:
            render_dashboard(symbol, rth_only=args.rth)
    except KeyboardInterrupt:
        console.print("\n  [dim]Dashboard stopped.[/dim]")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
