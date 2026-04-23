"""
Command executor — maps ParsedCommand → MT5 actions.
Handles confirmation display, SL/TP resolution, and dispatch.
"""
from __future__ import annotations

import logging
from typing import Optional

import MetaTrader5 as mt5

from .commands      import ParsedCommand
from .config        import ExecutionConfig
from .order_manager import OrderManager
from .risk          import (
    sl_to_price, tp_to_price, price_to_pnl,
    risk_based_lots, kelly_lots,
)
from .signals       import TradeOrder
from .trader        import (
    get_symbol_info, get_tick, get_account,
    get_open_positions, get_pending_orders,
    send_market_order, send_limit_order, send_stop_order,
    modify_position, modify_pending_order,
    close_position, close_all_positions, cancel_pending_order,
    pip_value_per_lot,
)

log = logging.getLogger("algopure-bot")

_SEP = "─" * 64


class Executor:
    def __init__(self, cfg: ExecutionConfig, mgr: OrderManager):
        self.cfg = cfg
        self.mgr = mgr

    # ── Public dispatch ───────────────────────────────────────────────────────

    def process(self, cmd: ParsedCommand):
        if cmd.error:
            print(f"  ✗ {cmd.error}")
            return

        dispatch = {
            "order":       self._handle_order,
            "close":       self._handle_close,
            "close_all":   self._handle_close_all,
            "modify_sl":   self._handle_modify_sl,
            "modify_tp":   self._handle_modify_tp,
            "modify_both": self._handle_modify_both,
            "hedge":       self._handle_hedge,
            "trailing":    self._handle_trailing,
            "status":      self._handle_status,
            "config":      self._handle_config,
            "kelly":       self._handle_kelly,
            "help":        self._handle_help,
            "exit":        self._handle_exit,
            "unknown":     self._handle_unknown,
        }
        handler = dispatch.get(cmd.action, self._handle_unknown)
        handler(cmd)

    # ── Order entry ───────────────────────────────────────────────────────────

    def _handle_order(self, cmd: ParsedCommand):
        symbol    = cmd.symbol or self.cfg.default_symbol
        direction = cmd.direction or "LONG"
        info      = get_symbol_info(symbol)
        tick      = get_tick(symbol)
        acct      = get_account()

        if info is None or tick is None:
            print(f"  ✗ Cannot get symbol info for {symbol}")
            return

        # Resolve entry price
        entry = cmd.limit_price if cmd.order_type != "MARKET" else (
            tick.ask if direction == "LONG" else tick.bid
        )

        # Resolve SL price
        sl_price = self._resolve_level(
            cmd.sl, cmd.sl_unit, direction, entry, info.trade_tick_size, "SL",
            self.cfg.default_sl_points,
        )

        # Resolve TP price
        tp_price = self._resolve_level(
            cmd.tp, cmd.tp_unit, direction, entry, info.trade_tick_size, "TP",
            self.cfg.default_tp_points,
        )

        # Lots
        lots = cmd.lots if cmd.lots is not None else self.cfg.default_lots
        lots_capped = min(lots, self.cfg.max_lots)
        if lots_capped < lots:
            print(f"  ⚠ Lots capped at max {self.cfg.max_lots}")
            lots = lots_capped

        # Build order object
        order = TradeOrder(
            symbol    = symbol,
            direction = direction,
            lots      = lots,
            order_type  = cmd.order_type,
            limit_price = cmd.limit_price if cmd.order_type != "MARKET" else None,
            stop_loss   = sl_price,
            take_profit = tp_price,
        )

        self._print_order_confirmation(order, entry, acct)

        if not self._confirm("Execute?"):
            print("  Order skipped.")
            return

        if cmd.order_type == "MARKET":
            ok, msg, ticket = send_market_order(order, self.cfg)
        elif cmd.order_type == "LIMIT":
            ok, msg, ticket = send_limit_order(order, self.cfg)
        else:
            ok, msg, ticket = send_stop_order(order, self.cfg)

        if ok:
            print(f"\n  ✓ ORDER EXECUTED  Ticket #{ticket}  {msg}")
            log.info("Order placed: ticket=%s symbol=%s dir=%s lots=%s", ticket, symbol, direction, lots)
        else:
            print(f"\n  ✗ {msg}")

    def _handle_hedge(self, cmd: ParsedCommand):
        """Open an opposite position to hedge an existing one."""
        symbol = cmd.symbol or self.cfg.default_symbol

        # Determine direction from existing position if not specified
        existing = get_open_positions(symbol=symbol)
        if existing and cmd.direction is None:
            ex = existing[0]
            hedge_dir = "SHORT" if ex.type == mt5.ORDER_TYPE_BUY else "LONG"
        else:
            hedge_dir = cmd.direction or "SHORT"

        hedge_cmd = ParsedCommand(
            action    = "order",
            symbol    = symbol,
            direction = hedge_dir,
            lots      = cmd.lots or self.cfg.default_lots,
            order_type= "MARKET" if cmd.limit_price is None else "LIMIT",
            limit_price = cmd.limit_price,
            raw       = cmd.raw,
        )
        print(f"  Hedging {symbol} with {hedge_dir} {hedge_cmd.lots} lots")
        self._handle_order(hedge_cmd)

    # ── Close ────────────────────────────────────────────────────────────────

    def _handle_close(self, cmd: ParsedCommand):
        if cmd.ticket:
            pos_list = [p for p in get_open_positions() if p.ticket == cmd.ticket]
            if not pos_list:
                # Try pending
                ok, msg = cancel_pending_order(cmd.ticket)
                print(f"  {'✓' if ok else '✗'} {msg}")
                return
            pos = pos_list[0]
            direction = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
            print(f"\n  Closing #{cmd.ticket}  {pos.symbol} {direction} {pos.volume} lots")
            if not self._confirm("Confirm close?"):
                print("  Close cancelled.")
                return
            ok, msg = close_position(cmd.ticket, self.cfg)
            print(f"  {'✓' if ok else '✗'} {msg}")
        elif cmd.symbol:
            positions = [p for p in get_open_positions() if p.symbol == cmd.symbol]
            if not positions:
                print(f"  No open positions for {cmd.symbol}")
                return
            print(f"\n  Closing {len(positions)} position(s) for {cmd.symbol}")
            if not self._confirm("Confirm?"):
                return
            for p in positions:
                ok, msg = close_position(p.ticket, self.cfg)
                print(f"  {'✓' if ok else '✗'} {msg}")

    def _handle_close_all(self, cmd: ParsedCommand):
        positions = get_open_positions()
        if not positions:
            print("  No open positions.")
            return
        print(f"\n  Closing ALL {len(positions)} position(s):")
        for p in positions:
            direction = "LONG" if p.type == mt5.ORDER_TYPE_BUY else "SHORT"
            print(f"    #{p.ticket}  {p.symbol} {direction} {p.volume} lots  P&L: ${p.profit:,.2f}")
        if not self._confirm("Confirm close all?"):
            print("  Cancelled.")
            return
        msgs = close_all_positions(self.cfg)
        for m in msgs:
            print(m)

    # ── Modify SL / TP ────────────────────────────────────────────────────────

    def _handle_modify_sl(self, cmd: ParsedCommand):
        ticket = self._resolve_ticket(cmd.ticket)
        if ticket is None:
            return
        pos = self._get_pos_or_warn(ticket)
        if pos is None:
            return

        direction = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
        entry     = pos.price_open
        info      = get_symbol_info(pos.symbol)
        new_sl    = self._resolve_level(
            cmd.sl, cmd.sl_unit, direction, entry,
            info.trade_tick_size if info else 0.01, "SL", 0,
        )
        if new_sl is None:
            print("  ✗ Could not resolve SL price")
            return

        print(f"\n  #{ticket}  {pos.symbol}  SL: {pos.sl:.5f} → {new_sl:.5f}")
        if not self._confirm("Confirm modify?"):
            return
        ok, msg = modify_position(ticket, sl=new_sl)
        print(f"  {'✓' if ok else '✗'} {msg}")

    def _handle_modify_tp(self, cmd: ParsedCommand):
        ticket = self._resolve_ticket(cmd.ticket)
        if ticket is None:
            return
        pos = self._get_pos_or_warn(ticket)
        if pos is None:
            return

        direction = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
        entry     = pos.price_open
        info      = get_symbol_info(pos.symbol)
        new_tp    = self._resolve_level(
            cmd.tp, cmd.tp_unit, direction, entry,
            info.trade_tick_size if info else 0.01, "TP", 0,
        )
        if new_tp is None:
            print("  ✗ Could not resolve TP price")
            return

        print(f"\n  #{ticket}  {pos.symbol}  TP: {pos.tp:.5f} → {new_tp:.5f}")
        if not self._confirm("Confirm modify?"):
            return
        ok, msg = modify_position(ticket, tp=new_tp)
        print(f"  {'✓' if ok else '✗'} {msg}")

    def _handle_modify_both(self, cmd: ParsedCommand):
        ticket = self._resolve_ticket(cmd.ticket)
        if ticket is None:
            return
        pos = self._get_pos_or_warn(ticket)
        if pos is None:
            return

        direction = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
        info      = get_symbol_info(pos.symbol)
        tick_size = info.trade_tick_size if info else 0.01

        new_sl = self._resolve_level(cmd.sl, cmd.sl_unit, direction, pos.price_open, tick_size, "SL", 0)
        new_tp = self._resolve_level(cmd.tp, cmd.tp_unit, direction, pos.price_open, tick_size, "TP", 0)

        print(f"\n  #{ticket}  {pos.symbol}")
        if new_sl is not None: print(f"  SL: {pos.sl:.5f} → {new_sl:.5f}")
        if new_tp is not None: print(f"  TP: {pos.tp:.5f} → {new_tp:.5f}")
        if not self._confirm("Confirm?"):
            return
        ok, msg = modify_position(ticket, sl=new_sl, tp=new_tp)
        print(f"  {'✓' if ok else '✗'} {msg}")

    # ── Trailing stop ────────────────────────────────────────────────────────

    def _handle_trailing(self, cmd: ParsedCommand):
        if cmd.trailing_pts is None:
            print("  ✗ Specify trailing distance, e.g.: trail 20 points")
            return
        ticket = self._resolve_ticket(cmd.ticket)
        if ticket is None:
            return
        self.mgr.set_trailing_stop(ticket, cmd.trailing_pts)
        print(f"  ✓ Trailing stop active on #{ticket}  distance={cmd.trailing_pts:.5f} pts")

    # ── Status ───────────────────────────────────────────────────────────────

    def _handle_status(self, _cmd: ParsedCommand):
        acct = get_account()
        positions = get_open_positions()
        pending   = get_pending_orders()

        print()
        if acct:
            print(f"  Account : {acct.name}  #{acct.login}  [{acct.server}]")
            print(f"  Balance : ${acct.balance:,.2f}  Equity: ${acct.equity:,.2f}  "
                  f"Margin: ${acct.margin:,.2f}")
        print()

        if not positions and not pending:
            print("  No open positions or pending orders.")
            return

        if positions:
            print(f"  OPEN POSITIONS ({len(positions)}):")
            print(f"  {'Ticket':>8}  {'Symbol':<10} {'Side':<6} {'Lots':>6} "
                  f"{'Entry':>10} {'Current':>10} {'SL':>10} {'TP':>10} {'P&L':>10}")
            print(f"  {_SEP}")
            for p in positions:
                side   = "LONG" if p.type == mt5.ORDER_TYPE_BUY else "SHORT"
                pnl    = f"${p.profit:+,.2f}"
                tick   = get_tick(p.symbol)
                cur    = f"{tick.bid:.5f}" if tick and p.type == mt5.ORDER_TYPE_BUY else \
                         f"{tick.ask:.5f}" if tick else "—"
                trail  = " [T]" if p.ticket in self.mgr.active_trailing_tickets() else ""
                print(f"  #{p.ticket:<7}  {p.symbol:<10} {side:<6} {p.volume:>6.2f} "
                      f"{p.price_open:>10.5f} {cur:>10}  {p.sl:>10.5f} {p.tp:>10.5f} {pnl:>10}{trail}")

        if pending:
            print()
            print(f"  PENDING ORDERS ({len(pending)}):")
            for o in pending:
                otype = {
                    mt5.ORDER_TYPE_BUY_LIMIT: "BUY LIMIT",
                    mt5.ORDER_TYPE_SELL_LIMIT: "SELL LIMIT",
                    mt5.ORDER_TYPE_BUY_STOP: "BUY STOP",
                    mt5.ORDER_TYPE_SELL_STOP: "SELL STOP",
                }.get(o.type, str(o.type))
                print(f"  #{o.ticket:<7}  {o.symbol:<10} {otype:<12} {o.volume:>6.2f} @ {o.price_open:.5f}  "
                      f"sl={o.sl:.5f}  tp={o.tp:.5f}")
        print()

        # Risk warnings
        warnings = self.mgr.check_risk_limits()
        for w in warnings:
            print(w)

    # ── Config ───────────────────────────────────────────────────────────────

    def _handle_config(self, cmd: ParsedCommand):
        if cmd.config_key is None or cmd.config_val is None:
            print("  ✗ Incomplete config command.")
            return
        setattr(self.cfg, cmd.config_key, cmd.config_val)
        print(f"  ✓ {cmd.config_key} = {cmd.config_val}"
              + (f" [{cmd.config_unit}]" if cmd.config_unit else ""))

    # ── Kelly sizing preview ──────────────────────────────────────────────────

    def _handle_kelly(self, cmd: ParsedCommand):
        symbol = cmd.symbol or self.cfg.default_symbol
        acct   = get_account()
        if acct is None:
            print("  ✗ No account info")
            return
        info = get_symbol_info(symbol)
        if info is None:
            print(f"  ✗ No symbol info for {symbol}")
            return

        balance   = acct.balance
        win_rate  = self.cfg.kelly_win_rate
        rr        = 1.5  # assumed if not known

        # Without a position, show sizing table for common RR ratios
        print(f"\n  Kelly Sizing  [{symbol}]  Win Rate={win_rate*100:.0f}%  "
              f"Quarter-Kelly ({self.cfg.kelly_fraction*100:.0f}%)")
        print(f"  {'R:R':>6}  {'Full Kelly %':>13}  {'Quarter Kelly %':>16}  {'Lots (1% risk SL=20pts)':>24}")
        print(f"  {_SEP}")
        for rr in [0.5, 1.0, 1.5, 2.0, 3.0]:
            q  = 1 - win_rate
            fk = max(0.0, win_rate - q / rr) * 100
            qk = fk * self.cfg.kelly_fraction
            # Example lot size at 1:RR with 20-point SL
            ex_sl_dist = 20 * info.trade_tick_size
            ex_lots = kelly_lots(
                balance, win_rate, rr, self.cfg.kelly_fraction,
                3200.0, 3200.0 - ex_sl_dist,
                info.trade_tick_size, info.trade_tick_value,
                info.volume_min, info.volume_max, info.volume_step, self.cfg.max_lots,
            )
            print(f"  {rr:>4.1f}:1  {fk:>12.1f}%  {qk:>15.1f}%  {ex_lots:>24.2f}")
        print()

    # ── Help ─────────────────────────────────────────────────────────────────

    def _handle_help(self, _cmd: ParsedCommand):
        help_text = f"""
  {_SEP}
  AlgoPure Execution Bot — Command Reference
  {_SEP}
  ORDER ENTRY
    buy/long  [SYMBOL] LOTS [lots] [sl PRICE] [tp PRICE]
    sell/short [SYMBOL] LOTS [lots] [sl PRICE] [tp PRICE]
    buy SYMBOL LOTS limit at PRICE [sl PRICE] [tp PRICE]   ← limit order
    buy SYMBOL LOTS stop  at PRICE [sl PRICE] [tp PRICE]   ← stop order

  SL / TP UNITS  (append to any sl/tp value)
    price   : absolute price       e.g.  sl 3180
    points  : tick units           e.g.  sl 20 points
    pips    : 10 × tick            e.g.  sl 5 pips
    %       : % from entry         e.g.  sl 0.5%

  MANAGE POSITIONS
    set sl 3180 [on ticket 12345]    — move stop loss
    set tp 3250 [on ticket 12345]    — move take profit
    modify ticket 12345 sl 3175 tp 3260
    trail[ing] 15 points [on ticket 12345]   — trailing stop
    close ticket 12345               — close by ticket
    close all                        — close everything
    hedge [SYMBOL] 0.1 lots          — open opposite position

  INFO
    status  /  positions             — show open positions & account
    kelly [for SYMBOL]               — Kelly criterion sizing table

  SETTINGS  (runtime, resets on exit)
    set default lots 0.2
    set max lots 1.0
    set default sl 25 points
    set default tp 50 points
    set risk 1.5%
    set daily limit 5000
    set drawdown limit 3000

  SYSTEM
    exit / quit
  {_SEP}"""
        print(help_text)

    # ── Exit ─────────────────────────────────────────────────────────────────

    def _handle_exit(self, _cmd: ParsedCommand):
        raise SystemExit(0)

    def _handle_unknown(self, cmd: ParsedCommand):
        print(f"  ✗ {cmd.error or 'Unknown command — type help for reference.'}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_level(
        self, value, unit: str, direction: str, entry: float,
        tick_size: float, label: str, default_pts: float,
    ) -> Optional[float]:
        """Convert a raw SL/TP value (and unit) to an absolute price."""
        if value is None:
            if default_pts <= 0:
                return None
            value = default_pts
            unit  = "points"

        if unit == "auto":
            # Heuristic: if value looks like a price, treat as price
            unit = "price" if value > 100 else "points"

        if label == "SL":
            return sl_to_price(entry, value, unit, direction, tick_size)
        else:
            return tp_to_price(entry, value, unit, direction, tick_size)

    def _resolve_ticket(self, ticket: Optional[int]) -> Optional[int]:
        """If ticket is None and only one position is open, use that."""
        if ticket is not None:
            return ticket
        positions = get_open_positions()
        if len(positions) == 1:
            return positions[0].ticket
        if not positions:
            print("  ✗ No open positions.")
        else:
            print("  ✗ Multiple positions open — specify ticket number.")
            for p in positions:
                print(f"    #{p.ticket}  {p.symbol}")
        return None

    def _get_pos_or_warn(self, ticket: int):
        positions = mt5.positions_get(ticket=ticket)
        if positions:
            return positions[0]
        print(f"  ✗ No open position with ticket #{ticket}")
        return None

    def _confirm(self, prompt: str) -> bool:
        if not self.cfg.manual_confirm:
            return True
        try:
            ans = input(f"  {prompt}  [y / n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return ans in ("y", "yes")

    def _print_order_confirmation(self, order: TradeOrder, entry: float, acct):
        balance  = acct.balance  if acct else 0.0
        currency = acct.currency if acct else "USD"

        info    = get_symbol_info(order.symbol)
        tick_sz = info.trade_tick_size  if info else 0.01
        tick_v  = info.trade_tick_value if info else 1.0

        def level_str(price: Optional[float]) -> str:
            if price is None:
                return "none"
            diff  = price - entry if order.direction == "LONG" else entry - price
            pts   = diff / tick_sz
            pct   = diff / entry * 100
            sign  = "+" if diff >= 0 else ""
            return f"{price:.5f}  ({sign}{pts:.0f} pts / {sign}{pct:.3f}%)"

        sl_str  = level_str(order.stop_loss)
        tp_str  = level_str(order.take_profit)

        # Risk $ and potential $
        risk_usd = pot_usd = "—"
        if order.stop_loss:
            sl_dist  = abs(entry - order.stop_loss)
            risk_usd = f"${(sl_dist / tick_sz) * tick_v * order.lots:,.2f}"
            risk_pct_str = f" ({(sl_dist / tick_sz * tick_v * order.lots / balance * 100):.2f}% of balance)" if balance else ""
            risk_usd += risk_pct_str if balance else ""
        if order.take_profit:
            tp_dist = abs(order.take_profit - entry)
            pot_usd = f"${(tp_dist / tick_sz) * tick_v * order.lots:,.2f}"

        rr_str = "—"
        if order.stop_loss and order.take_profit:
            sl_d = abs(entry - order.stop_loss)
            tp_d = abs(order.take_profit - entry)
            rr   = tp_d / sl_d if sl_d > 0 else 0
            rr_str = f"1:{rr:.2f}"

        print(f"""
  ┌{_SEP}┐
  │  PENDING ORDER — Review Before Executing               │
  │  Symbol    : {order.symbol:<48} │
  │  Direction : {order.direction} ({order.order_type}){' '*(43 - len(order.direction) - len(order.order_type))}│
  │  Lots      : {order.lots:<48} │
  │  Entry     : {entry:<48.5f} │
  │  Stop Loss : {sl_str:<48} │
  │  Take Prof : {tp_str:<48} │
  │  Risk:Rew  : {rr_str:<48} │
  │  Risk $    : {risk_usd:<48} │
  │  Potential : {pot_usd:<48} │
  │                                                              │
  │  ⚠  ORDER IS LIVE — will execute at market price            │
  │     SL fires at {order.stop_loss or 'none'!s:<46} │
  │     TP fires at {order.take_profit or 'none'!s:<46} │
  └{_SEP}┘""")
