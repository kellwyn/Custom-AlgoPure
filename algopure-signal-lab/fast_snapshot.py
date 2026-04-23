"""
Fast live-position snapshot — no historical fetch, runs in < 500ms.
Called in a background thread immediately after order execution so the
signal lab context is available without blocking the REPL.
"""
from __future__ import annotations

import MetaTrader5 as mt5
from datetime import datetime


_SEP = "─" * 64


def run(symbol: str | None = None) -> None:
    """
    Print live position risk summary to stdout.
    Expects MT5 to already be initialized (shares the bot's connection).
    """
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if not positions:
        return

    acct = mt5.account_info()
    ts   = datetime.now().strftime("%H:%M:%S")

    print(f"\n  {_SEP}")
    print(f"  SIGNAL LAB SNAPSHOT  {ts}")
    if acct:
        print(f"  Balance: ${acct.balance:,.2f}   Equity: ${acct.equity:,.2f}   "
              f"Free margin: ${acct.margin_free:,.2f}")
    print(f"  {_SEP}")

    for pos in positions:
        direction = "SHORT" if pos.type == mt5.ORDER_TYPE_SELL else "LONG"
        tick = mt5.symbol_info_tick(pos.symbol)
        info = mt5.symbol_info(pos.symbol)

        if tick is None or info is None:
            continue

        current   = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        tick_sz   = info.trade_tick_size
        tick_v    = info.trade_tick_value
        pv_per_pt = tick_v / tick_sz if tick_sz else 0

        pnl_now = pos.volume * ((current - pos.price_open) / tick_sz * tick_v
                                if pos.type == mt5.ORDER_TYPE_BUY
                                else (pos.price_open - current) / tick_sz * tick_v)

        sl_dist = abs(current - pos.sl) if pos.sl > 0 else None
        tp_dist = abs(pos.tp - current) if pos.tp > 0 else None
        pnl_sl  = pos.volume * sl_dist * pv_per_pt if sl_dist is not None else None
        pnl_tp  = pos.volume * tp_dist * pv_per_pt if tp_dist is not None else None

        rr = (tp_dist / sl_dist) if (sl_dist and tp_dist and sl_dist > 0) else None

        print(f"\n  #{pos.ticket}  {pos.symbol}  {direction}  {pos.volume} lots")
        print(f"    Entry   : {pos.price_open:.5f}")
        print(f"    Current : {current:.5f}   P&L: ${pnl_now:+,.2f}")
        if pos.sl > 0 and sl_dist is not None:
            pts_to_sl = sl_dist / tick_sz
            print(f"    SL      : {pos.sl:.5f}   dist: {sl_dist:.2f} pts ({pts_to_sl:.0f})   "
                  f"risk: -${pnl_sl:,.2f}")
        if pos.tp > 0 and tp_dist is not None:
            pts_to_tp = tp_dist / tick_sz
            print(f"    TP      : {pos.tp:.5f}   dist: {tp_dist:.2f} pts ({pts_to_tp:.0f})   "
                  f"target: +${pnl_tp:,.2f}")
        if rr is not None:
            print(f"    R:R     : 1:{rr:.2f}")
        if acct:
            risk_pct = pnl_sl / acct.balance * 100 if pnl_sl else 0
            print(f"    % Acct  : {risk_pct:.3f}% at risk")

    print(f"\n  {_SEP}\n")
