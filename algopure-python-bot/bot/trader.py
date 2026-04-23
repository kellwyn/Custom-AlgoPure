"""
Low-level MT5 order dispatch — market, limit, stop, modify, close.
All functions return (success: bool, message: str).
"""
from __future__ import annotations

import MetaTrader5 as mt5
from typing import Optional, Tuple

from .signals import TradeOrder
from .config  import ExecutionConfig


# ── Symbol info helpers ───────────────────────────────────────────────────────

def get_symbol_info(symbol: str):
    info = mt5.symbol_info(symbol)
    if info is None:
        mt5.symbol_select(symbol, True)
        info = mt5.symbol_info(symbol)
    return info


def get_tick(symbol: str):
    return mt5.symbol_info_tick(symbol)


def pip_value_per_lot(symbol: str) -> float:
    """Dollar P&L per 1 price unit per 1 lot."""
    info = get_symbol_info(symbol)
    if info is None or info.trade_tick_size == 0:
        return 0.0
    return info.trade_tick_value / info.trade_tick_size


def normalize_lots(lots: float, symbol: str, max_lots: float) -> float:
    info = get_symbol_info(symbol)
    if info is None:
        return round(lots, 2)
    lo, hi, step = info.volume_min, min(info.volume_max, max_lots), info.volume_step
    lots = max(lo, min(hi, lots))
    if step > 0:
        lots = round(round(lots / step) * step, 8)
    return lots


# ── Market order ──────────────────────────────────────────────────────────────

def send_market_order(order: TradeOrder, cfg: ExecutionConfig) -> Tuple[bool, str, Optional[int]]:
    """
    Place a market BUY or SELL order.
    Returns (success, message, ticket_or_None).
    """
    tick = get_tick(order.symbol)
    if tick is None:
        return False, f"No tick for {order.symbol}: {mt5.last_error()}", None

    info = get_symbol_info(order.symbol)
    if info is None:
        return False, f"Symbol info unavailable for {order.symbol}", None

    otype = mt5.ORDER_TYPE_BUY  if order.direction == "LONG" else mt5.ORDER_TYPE_SELL
    price = tick.ask             if order.direction == "LONG" else tick.bid

    lots = normalize_lots(order.lots, order.symbol, cfg.max_lots)

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       order.symbol,
        "volume":       lots,
        "type":         otype,
        "price":        price,
        "deviation":    cfg.slippage,
        "magic":        cfg.magic,
        "comment":      cfg.comment,
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    if order.stop_loss  is not None: request["sl"] = order.stop_loss
    if order.take_profit is not None: request["tp"] = order.take_profit

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code    = result.retcode if result else mt5.last_error()
        comment = result.comment if result else ""
        return False, f"Order failed  retcode={code}  {comment}", None

    return True, f"Executed @ {result.price:.5f}", result.order


# ── Limit order ───────────────────────────────────────────────────────────────

def send_limit_order(order: TradeOrder, cfg: ExecutionConfig) -> Tuple[bool, str, Optional[int]]:
    """Place a pending LIMIT order."""
    if order.limit_price is None:
        return False, "Limit price required for LIMIT order", None

    otype = mt5.ORDER_TYPE_BUY_LIMIT  if order.direction == "LONG" else mt5.ORDER_TYPE_SELL_LIMIT
    lots  = normalize_lots(order.lots, order.symbol, cfg.max_lots)

    request = {
        "action":       mt5.TRADE_ACTION_PENDING,
        "symbol":       order.symbol,
        "volume":       lots,
        "type":         otype,
        "price":        order.limit_price,
        "deviation":    cfg.slippage,
        "magic":        cfg.magic,
        "comment":      cfg.comment,
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }
    if order.stop_loss  is not None: request["sl"] = order.stop_loss
    if order.take_profit is not None: request["tp"] = order.take_profit

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code    = result.retcode if result else mt5.last_error()
        comment = result.comment if result else ""
        return False, f"Limit order failed  retcode={code}  {comment}", None

    return True, f"Limit order placed @ {order.limit_price:.5f}", result.order


# ── Stop order ────────────────────────────────────────────────────────────────

def send_stop_order(order: TradeOrder, cfg: ExecutionConfig) -> Tuple[bool, str, Optional[int]]:
    """Place a pending STOP order."""
    if order.limit_price is None:
        return False, "Stop price required for STOP order", None

    otype = mt5.ORDER_TYPE_BUY_STOP  if order.direction == "LONG" else mt5.ORDER_TYPE_SELL_STOP
    lots  = normalize_lots(order.lots, order.symbol, cfg.max_lots)

    request = {
        "action":       mt5.TRADE_ACTION_PENDING,
        "symbol":       order.symbol,
        "volume":       lots,
        "type":         otype,
        "price":        order.limit_price,
        "deviation":    cfg.slippage,
        "magic":        cfg.magic,
        "comment":      cfg.comment,
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }
    if order.stop_loss  is not None: request["sl"] = order.stop_loss
    if order.take_profit is not None: request["tp"] = order.take_profit

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code    = result.retcode if result else mt5.last_error()
        comment = result.comment if result else ""
        return False, f"Stop order failed  retcode={code}  {comment}", None

    return True, f"Stop order placed @ {order.limit_price:.5f}", result.order


# ── Modify position SL / TP ───────────────────────────────────────────────────

def modify_position(ticket: int, sl: Optional[float] = None,
                    tp: Optional[float] = None) -> Tuple[bool, str]:
    """Modify SL and/or TP on a live position by ticket."""
    pos = _get_position(ticket)
    if pos is None:
        return False, f"No open position with ticket #{ticket}"

    request = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol":   pos.symbol,
        "sl":       sl if sl is not None else pos.sl,
        "tp":       tp if tp is not None else pos.tp,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code    = result.retcode if result else mt5.last_error()
        comment = result.comment if result else ""
        return False, f"Modify failed  retcode={code}  {comment}"

    parts = []
    if sl is not None: parts.append(f"SL → {sl:.5f}")
    if tp is not None: parts.append(f"TP → {tp:.5f}")
    return True, "  ".join(parts)


def modify_pending_order(ticket: int, price: Optional[float] = None,
                         sl: Optional[float] = None,
                         tp: Optional[float] = None) -> Tuple[bool, str]:
    """Modify a pending limit/stop order."""
    orders = mt5.orders_get(ticket=ticket)
    if not orders:
        return False, f"No pending order with ticket #{ticket}"
    o = orders[0]
    request = {
        "action":  mt5.TRADE_ACTION_MODIFY,
        "order":   ticket,
        "price":   price if price is not None else o.price_open,
        "sl":      sl    if sl    is not None else o.sl,
        "tp":      tp    if tp    is not None else o.tp,
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code = result.retcode if result else mt5.last_error()
        return False, f"Modify pending failed  retcode={code}"
    return True, f"Pending order #{ticket} modified"


# ── Close position ────────────────────────────────────────────────────────────

def close_position(ticket: int, cfg: ExecutionConfig) -> Tuple[bool, str]:
    """Close a live position by ticket (full close)."""
    pos = _get_position(ticket)
    if pos is None:
        return False, f"No open position with ticket #{ticket}"

    tick = get_tick(pos.symbol)
    if tick is None:
        return False, f"No tick for {pos.symbol}"

    close_type  = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    close_price = tick.bid             if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "position":     ticket,
        "symbol":       pos.symbol,
        "volume":       pos.volume,
        "type":         close_type,
        "price":        close_price,
        "deviation":    cfg.slippage,
        "magic":        cfg.magic,
        "comment":      f"close {cfg.comment}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code    = result.retcode if result else mt5.last_error()
        comment = result.comment if result else ""
        return False, f"Close failed  retcode={code}  {comment}"

    direction = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
    profit    = pos.profit
    pnl_str   = f"+${profit:,.2f}" if profit >= 0 else f"-${abs(profit):,.2f}"
    return True, f"#{ticket} {pos.symbol} {direction} {pos.volume} lots  P&L: {pnl_str}"


def close_all_positions(cfg: ExecutionConfig, symbol: Optional[str] = None) -> list[str]:
    """Close all open positions, optionally filtered by symbol."""
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if not positions:
        return ["No open positions to close."]
    results = []
    for pos in positions:
        ok, msg = close_position(pos.ticket, cfg)
        tag = "✓" if ok else "✗"
        results.append(f"  {tag} {msg}")
    return results


def cancel_pending_order(ticket: int) -> Tuple[bool, str]:
    """Cancel a pending limit/stop order."""
    request = {"action": mt5.TRADE_ACTION_REMOVE, "order": ticket}
    result  = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code = result.retcode if result else mt5.last_error()
        return False, f"Cancel failed  retcode={code}"
    return True, f"Pending order #{ticket} cancelled"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_position(ticket: int):
    positions = mt5.positions_get(ticket=ticket)
    return positions[0] if positions else None


def get_open_positions(symbol: Optional[str] = None):
    return mt5.positions_get(symbol=symbol) or []


def get_pending_orders(symbol: Optional[str] = None):
    return mt5.orders_get(symbol=symbol) or []


def get_account() -> Optional[object]:
    return mt5.account_info()
