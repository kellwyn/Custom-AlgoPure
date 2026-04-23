"""
Low-level MT5 order dispatch — market, limit, stop, modify, close.

Speed design:
  - _cached_sym_info() caches static symbol data (tick_size, filling_mode,
    vol constraints) for 5 minutes so the critical order path makes exactly
    1 MT5 call (fresh tick) + order_send, instead of 6+.
  - warm_symbol() pre-populates the cache on bot startup so the first order
    has zero lookup overhead.
  - All functions accept an optional _info kwarg to share one cached lookup
    across the whole order lifecycle.
"""
from __future__ import annotations

import time
from threading import Lock
from typing import Optional, Tuple

import MetaTrader5 as mt5

from .signals import TradeOrder
from .config  import ExecutionConfig


# ── Symbol info cache ─────────────────────────────────────────────────────────

_sym_cache: dict = {}   # symbol → (info_obj, cached_at_monotonic)
_sym_lock  = Lock()
_SYM_TTL   = 300.0      # seconds — static info (tick_size, filling_mode, vol) is stable


def _cached_sym_info(symbol: str):
    """Return cached symbol_info, refreshing if TTL expired."""
    now = time.monotonic()
    with _sym_lock:
        entry = _sym_cache.get(symbol)
        if entry and (now - entry[1]) < _SYM_TTL:
            return entry[0]

    mt5.symbol_select(symbol, True)
    info = mt5.symbol_info(symbol)
    if info:
        with _sym_lock:
            _sym_cache[symbol] = (info, now)
    return info


def warm_symbol(symbol: str) -> bool:
    """
    Pre-cache symbol info and warm the MT5 internal price feed.
    Call on bot startup for every default symbol so the first order
    has zero lookup overhead.
    """
    info = _cached_sym_info(symbol)
    if info is None:
        return False
    mt5.symbol_info_tick(symbol)   # warms MT5's internal tick cache
    return True


def invalidate_sym_cache(symbol: str = None):
    """Force re-fetch on next use. Pass None to clear all."""
    with _sym_lock:
        if symbol:
            _sym_cache.pop(symbol, None)
        else:
            _sym_cache.clear()


# ── Filling mode (computed from cached info) ──────────────────────────────────

def _filling_mode(info) -> int:
    """
    Map symbol.filling_mode bitmask to ORDER_FILLING_* constant.
    Bitmask: bit0=FOK, bit1=IOC.  Constants: FOK=0, IOC=1, RETURN=2.
    """
    fm = info.filling_mode
    if fm & 1: return mt5.ORDER_FILLING_FOK
    if fm & 2: return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


# ── Public helpers ────────────────────────────────────────────────────────────

def get_symbol_info(symbol: str):
    """Public accessor — returns cached info."""
    return _cached_sym_info(symbol)


def get_tick(symbol: str):
    """Always-fresh bid/ask tick."""
    return mt5.symbol_info_tick(symbol)


def get_account():
    return mt5.account_info()


def get_open_positions(symbol: Optional[str] = None):
    return mt5.positions_get(symbol=symbol) or []


def get_pending_orders(symbol: Optional[str] = None):
    return mt5.orders_get(symbol=symbol) or []


def pip_value_per_lot(symbol: str) -> float:
    info = _cached_sym_info(symbol)
    if info is None or info.trade_tick_size == 0:
        return 0.0
    return info.trade_tick_value / info.trade_tick_size


def normalize_lots(lots: float, symbol: str, max_lots: float,
                   _info=None) -> float:
    info = _info or _cached_sym_info(symbol)
    if info is None:
        return round(lots, 2)
    lo, hi, step = info.volume_min, min(info.volume_max, max_lots), info.volume_step
    lots = max(lo, min(hi, lots))
    if step > 0:
        lots = round(round(lots / step) * step, 8)
    return lots


# ── Market order ──────────────────────────────────────────────────────────────

def send_market_order(order: TradeOrder, cfg: ExecutionConfig,
                      _info=None) -> Tuple[bool, str, Optional[int]]:
    """
    Fast path: uses cached info + one fresh tick call → order_send.
    Total MT5 calls: 2 (tick + order_send).
    Pass _info to share a cached lookup already held by the caller.
    """
    info = _info or _cached_sym_info(order.symbol)
    if info is None:
        return False, f"Symbol info unavailable for {order.symbol}", None

    tick = mt5.symbol_info_tick(order.symbol)   # always fresh at execution
    if tick is None:
        return False, f"No tick for {order.symbol}: {mt5.last_error()}", None

    otype = mt5.ORDER_TYPE_BUY if order.direction == "LONG" else mt5.ORDER_TYPE_SELL
    price = tick.ask             if order.direction == "LONG" else tick.bid

    lo, hi, step = info.volume_min, min(info.volume_max, cfg.max_lots), info.volume_step
    lots = max(lo, min(hi, order.lots))
    if step > 0:
        lots = round(round(lots / step) * step, 8)

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
        "type_filling": _filling_mode(info),
    }
    if order.stop_loss   is not None: request["sl"] = order.stop_loss
    if order.take_profit is not None: request["tp"] = order.take_profit

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code    = result.retcode if result else mt5.last_error()
        comment = result.comment if result else ""
        return False, f"Order failed  retcode={code}  {comment}", None

    return True, f"Executed @ {result.price:.5f}", result.order


# ── Limit order ───────────────────────────────────────────────────────────────

def send_limit_order(order: TradeOrder, cfg: ExecutionConfig,
                     _info=None) -> Tuple[bool, str, Optional[int]]:
    if order.limit_price is None:
        return False, "Limit price required for LIMIT order", None

    info  = _info or _cached_sym_info(order.symbol)
    if info is None:
        return False, f"Symbol info unavailable for {order.symbol}", None

    otype = mt5.ORDER_TYPE_BUY_LIMIT  if order.direction == "LONG" else mt5.ORDER_TYPE_SELL_LIMIT
    lo, hi, step = info.volume_min, min(info.volume_max, cfg.max_lots), info.volume_step
    lots = max(lo, min(hi, order.lots))
    if step > 0:
        lots = round(round(lots / step) * step, 8)

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
    if order.stop_loss   is not None: request["sl"] = order.stop_loss
    if order.take_profit is not None: request["tp"] = order.take_profit

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code    = result.retcode if result else mt5.last_error()
        comment = result.comment if result else ""
        return False, f"Limit order failed  retcode={code}  {comment}", None

    return True, f"Limit order placed @ {order.limit_price:.5f}", result.order


# ── Stop order ────────────────────────────────────────────────────────────────

def send_stop_order(order: TradeOrder, cfg: ExecutionConfig,
                    _info=None) -> Tuple[bool, str, Optional[int]]:
    if order.limit_price is None:
        return False, "Stop price required for STOP order", None

    info  = _info or _cached_sym_info(order.symbol)
    if info is None:
        return False, f"Symbol info unavailable for {order.symbol}", None

    otype = mt5.ORDER_TYPE_BUY_STOP  if order.direction == "LONG" else mt5.ORDER_TYPE_SELL_STOP
    lo, hi, step = info.volume_min, min(info.volume_max, cfg.max_lots), info.volume_step
    lots = max(lo, min(hi, order.lots))
    if step > 0:
        lots = round(round(lots / step) * step, 8)

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
    if order.stop_loss   is not None: request["sl"] = order.stop_loss
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
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False, f"No open position with ticket #{ticket}"
    pos = positions[0]
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
    if sl is not None: parts.append(f"SL -> {sl:.5f}")
    if tp is not None: parts.append(f"TP -> {tp:.5f}")
    return True, "  ".join(parts)


def modify_pending_order(ticket: int, price: Optional[float] = None,
                         sl: Optional[float] = None,
                         tp: Optional[float] = None) -> Tuple[bool, str]:
    orders = mt5.orders_get(ticket=ticket)
    if not orders:
        return False, f"No pending order with ticket #{ticket}"
    o = orders[0]
    request = {
        "action":       mt5.TRADE_ACTION_MODIFY,
        "order":        ticket,
        "price":        price if price is not None else o.price_open,
        "sl":           sl    if sl    is not None else o.sl,
        "tp":           tp    if tp    is not None else o.tp,
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code = result.retcode if result else mt5.last_error()
        return False, f"Modify pending failed  retcode={code}"
    return True, f"Pending order #{ticket} modified"


# ── Close position ────────────────────────────────────────────────────────────

def close_position(ticket: int, cfg: ExecutionConfig,
                   _info=None) -> Tuple[bool, str]:
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False, f"No open position with ticket #{ticket}"
    pos = positions[0]

    tick = mt5.symbol_info_tick(pos.symbol)
    if tick is None:
        return False, f"No tick for {pos.symbol}"

    info = _info or _cached_sym_info(pos.symbol)
    fill = _filling_mode(info) if info else mt5.ORDER_FILLING_FOK

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
        "type_filling": fill,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code    = result.retcode if result else mt5.last_error()
        comment = result.comment if result else ""
        return False, f"Close failed  retcode={code}  {comment}"

    direction = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
    pnl_str   = f"+${pos.profit:,.2f}" if pos.profit >= 0 else f"-${abs(pos.profit):,.2f}"
    return True, f"#{ticket} {pos.symbol} {direction} {pos.volume} lots  P&L: {pnl_str}"


def close_all_positions(cfg: ExecutionConfig,
                        symbol: Optional[str] = None) -> list[str]:
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if not positions:
        return ["No open positions to close."]
    results = []
    for pos in positions:
        info = _cached_sym_info(pos.symbol)
        ok, msg = close_position(pos.ticket, cfg, _info=info)
        results.append(f"  {'ok' if ok else 'FAIL'} {msg}")
    return results


def cancel_pending_order(ticket: int) -> Tuple[bool, str]:
    request = {"action": mt5.TRADE_ACTION_REMOVE, "order": ticket}
    result  = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code = result.retcode if result else mt5.last_error()
        return False, f"Cancel failed  retcode={code}"
    return True, f"Pending order #{ticket} cancelled"
