"""
Natural language command parser for the AlgoPure execution bot.

Supported command forms (case-insensitive):

  buy/long  [SYMBOL] LOTS [lots] [limit|stop at PRICE] [sl SL_VAL [unit]] [tp TP_VAL [unit]]
  sell/short [SYMBOL] LOTS [lots] [limit|stop at PRICE] [sl SL_VAL [unit]] [tp TP_VAL [unit]]
  close [all | SYMBOL | ticket N | #N]
  set sl [to] VALUE [unit] [on ticket N | on #N]
  set tp [to] VALUE [unit] [on ticket N | on #N]
  modify ticket N [sl VALUE] [tp VALUE]
  hedge [SYMBOL] LOTS [lots] [at PRICE]
  trail[ing] [stop] VALUE [points|pips] [on ticket N]
  status | positions | account
  set default lots N
  set max lots N
  set default sl N [unit]
  set default tp N [unit]
  set risk N%
  set daily limit N
  set drawdown limit N
  kelly [for SYMBOL]
  help | ?
  exit | quit
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedCommand:
    action:     str                        # see module docstring
    symbol:     Optional[str]  = None
    direction:  Optional[str]  = None      # "LONG" | "SHORT"
    lots:       Optional[float] = None
    order_type: str            = "MARKET"  # "MARKET" | "LIMIT" | "STOP"
    limit_price: Optional[float] = None
    sl:         Optional[float] = None
    sl_unit:    str            = "auto"    # "price"|"points"|"pips"|"pct"|"auto"
    tp:         Optional[float] = None
    tp_unit:    str            = "auto"
    ticket:     Optional[int]  = None
    trailing_pts: Optional[float] = None
    config_key:  Optional[str]  = None
    config_val:  Optional[float] = None
    config_unit: Optional[str]  = None
    error:       Optional[str]  = None
    raw:         str           = ""


# ── Unit detection ─────────────────────────────────────────────────────────────

_UNIT_PAT = r"(%|points?|pts?|pips?|dollars?|\$)"

def _detect_unit(s: str) -> str:
    s = s.lower().strip()
    if s in ("%",):                  return "pct"
    if s in ("point", "points", "pt", "pts"): return "points"
    if s in ("pip", "pips"):         return "pips"
    if s in ("dollar", "dollars", "$"): return "dollars"
    return "price"

def _sl_tp_unit_and_val(val_str: str, unit_str: Optional[str]) -> tuple[float, str]:
    v = float(val_str)
    if unit_str:
        return v, _detect_unit(unit_str)
    # heuristic: small values without a unit are treated as price-distance in $
    # large values (>100) are absolute prices
    return v, "auto"


# ── Ticket extraction ──────────────────────────────────────────────────────────

def _extract_ticket(text: str) -> tuple[Optional[int], str]:
    """Pull 'on ticket N' or 'on #N' from text, return (ticket, remaining_text)."""
    m = re.search(r'\bon\s+(?:ticket|#)\s*(\d+)', text, re.I)
    if m:
        return int(m.group(1)), text[:m.start()].strip()
    m = re.search(r'\b(?:ticket|#)\s*(\d+)', text, re.I)
    if m:
        return int(m.group(1)), (text[:m.start()] + text[m.end():]).strip()
    return None, text


# ── SL / TP extraction from order string ──────────────────────────────────────

def _extract_sl_tp(text: str) -> tuple[Optional[float], str, Optional[float], str, str]:
    """
    Extract sl / tp from text like 'sl 3180 tp 3250' or 'sl 20 points tp 30 pips'.
    Returns (sl_val, sl_unit, tp_val, tp_unit, remaining_text).
    """
    sl_val = sl_unit = tp_val = tp_unit = None
    remaining = text

    # TP first so we can trim it before matching SL (avoids greedy overlap)
    m = re.search(
        r'\btp\s+([\d.]+)\s*(' + _UNIT_PAT + r')?', remaining, re.I
    )
    if m:
        tp_val, raw_unit = float(m.group(1)), m.group(2)
        tp_unit = _detect_unit(raw_unit) if raw_unit else "auto"
        remaining = (remaining[:m.start()] + remaining[m.end():]).strip()

    m = re.search(
        r'\bsl\s+([\d.]+)\s*(' + _UNIT_PAT + r')?', remaining, re.I
    )
    if m:
        sl_val, raw_unit = float(m.group(1)), m.group(2)
        sl_unit = _detect_unit(raw_unit) if raw_unit else "auto"
        remaining = (remaining[:m.start()] + remaining[m.end():]).strip()

    return sl_val, sl_unit or "auto", tp_val, tp_unit or "auto", remaining


# ── Symbol extraction ─────────────────────────────────────────────────────────

_SYMBOL_CANDIDATES = re.compile(
    r'\b(XAUUSD|XAUUSDp|GOLD\.f|GOLD\.F|XAUUSD[pP]?|gold|xauusd|auusd|xau|goldf)\b',
    re.I,
)

def _extract_symbol(text: str, default: str) -> tuple[str, str]:
    m = _SYMBOL_CANDIDATES.search(text)
    if m:
        raw = m.group(0)
        aliases = {
            "gold": "XAUUSD", "xau": "XAUUSD", "xauusd": "XAUUSD",
            "auusd": "XAUUSD", "xauusdp": "XAUUSDp", "goldf": "GOLD.f",
            "gold.f": "GOLD.f",
        }
        sym = aliases.get(raw.lower(), raw.upper())
        remaining = (text[:m.start()] + text[m.end():]).strip()
        return sym, remaining
    return default, text


# ── Main parser ───────────────────────────────────────────────────────────────

def parse_command(text: str, default_symbol: str = "XAUUSD") -> ParsedCommand:
    raw = text
    t   = text.strip()

    # ── exit / quit ──────────────────────────────────────────────────────────
    if re.match(r'^(exit|quit|bye|q)$', t, re.I):
        return ParsedCommand(action="exit", raw=raw)

    # ── help ─────────────────────────────────────────────────────────────────
    if re.match(r'^(help|\?|h|commands?)$', t, re.I):
        return ParsedCommand(action="help", raw=raw)

    # ── status ───────────────────────────────────────────────────────────────
    if re.match(r'^(status|positions?|pos|show|orders?|open|account|balance|info|p)$', t, re.I):
        return ParsedCommand(action="status", raw=raw)

    # ── kelly sizing ─────────────────────────────────────────────────────────
    m = re.match(r'^kelly(?:\s+(?:for|size)?\s*(\w[\w.]*))?\s*$', t, re.I)
    if m:
        sym, _ = _extract_symbol(m.group(1) or "", default_symbol)
        return ParsedCommand(action="kelly", symbol=sym, raw=raw)

    # ── close ────────────────────────────────────────────────────────────────
    m = re.match(r'^(close|exit|kill|flatten|flat)\b(.*)$', t, re.I)
    if m:
        rest = m.group(2).strip()
        cmd  = ParsedCommand(action="close", raw=raw)
        if re.match(r'^(all|everything|everything)$', rest, re.I) or rest == "":
            cmd.action = "close_all"
        elif re.match(r'^(?:ticket\s*|#)\s*(\d+)$', rest, re.I):
            n = re.search(r'(\d+)', rest)
            cmd.ticket = int(n.group(1)) if n else None
        else:
            sym, _ = _extract_symbol(rest, default_symbol)
            cmd.symbol = sym
        return cmd

    # ── hedge ────────────────────────────────────────────────────────────────
    m = re.match(r'^(hedge|opposite)\b(.*)$', t, re.I)
    if m:
        rest = m.group(2).strip()
        cmd = ParsedCommand(action="hedge", symbol=default_symbol, raw=raw)
        sym, rest = _extract_symbol(rest, default_symbol)
        cmd.symbol = sym
        lm = re.search(r'([\d.]+)\s*(?:lots?|l)?\b', rest, re.I)
        if lm:
            cmd.lots = float(lm.group(1))
            rest = (rest[:lm.start()] + rest[lm.end():]).strip()
        pm = re.search(r'(?:at|@)\s*([\d.]+)', rest, re.I)
        if pm:
            cmd.limit_price = float(pm.group(1))
        return cmd

    # ── trailing stop ────────────────────────────────────────────────────────
    m = re.match(r'^trail(?:ing)?\s*(?:stop)?\b(.*)$', t, re.I)
    if m:
        rest = m.group(1).strip()
        cmd  = ParsedCommand(action="trailing", raw=raw)
        ticket, rest = _extract_ticket(rest)
        cmd.ticket = ticket
        vm = re.search(r'([\d.]+)', rest)
        if vm:
            cmd.trailing_pts = float(vm.group(1))
        return cmd

    # ── modify / set SL / set TP ─────────────────────────────────────────────
    if re.match(r'^(set|move|modify|update|change|adjust)\b', t, re.I):
        rest = re.sub(r'^(set|move|modify|update|change|adjust)\s+', '', t, flags=re.I)

        # "default lots N" / "max lots N" / "risk N%" / "daily limit N" etc.
        cfg = _try_parse_config(rest, raw)
        if cfg:
            return cfg

        # "sl [to] VALUE [unit] [on ticket N]"
        m = re.match(
            r'^(?:stop\s*loss|stop|sl)\s+(?:to\s+)?([\d.]+)\s*(' + _UNIT_PAT + r')?\s*(.*)$',
            rest, re.I
        )
        if m:
            val, unit_str, tail = m.group(1), m.group(2), m.group(3).strip() if m.lastindex >= 3 else ""
            sl_val, sl_unit = float(val), _detect_unit(unit_str) if unit_str else "auto"
            ticket, _ = _extract_ticket(tail)
            return ParsedCommand(action="modify_sl", sl=sl_val, sl_unit=sl_unit,
                                 ticket=ticket, raw=raw)

        # "tp [to] VALUE [unit] [on ticket N]"
        m = re.match(
            r'^(?:take\s*profit|target|tp)\s+(?:to\s+)?([\d.]+)\s*(' + _UNIT_PAT + r')?\s*(.*)$',
            rest, re.I
        )
        if m:
            val, unit_str, tail = m.group(1), m.group(2), m.group(3).strip() if m.lastindex >= 3 else ""
            tp_val, tp_unit = float(val), _detect_unit(unit_str) if unit_str else "auto"
            ticket, _ = _extract_ticket(tail)
            return ParsedCommand(action="modify_tp", tp=tp_val, tp_unit=tp_unit,
                                 ticket=ticket, raw=raw)

        # "ticket N sl VALUE tp VALUE"
        m = re.match(r'^ticket\s*(\d+)\s+(.*)', rest, re.I)
        if m:
            tkt = int(m.group(1))
            body = m.group(2).strip()
            sl_val, sl_unit, tp_val, tp_unit, _ = _extract_sl_tp(body)
            return ParsedCommand(action="modify_both", ticket=tkt,
                                 sl=sl_val, sl_unit=sl_unit or "auto",
                                 tp=tp_val, tp_unit=tp_unit or "auto", raw=raw)

        return ParsedCommand(action="unknown", error=f"Unrecognised modify command: '{text}'", raw=raw)

    # ── buy / sell order ─────────────────────────────────────────────────────
    dir_m = re.match(r'^(buy|long|b|sell|short|s)\b(.*)$', t, re.I)
    if dir_m:
        direction = "LONG" if dir_m.group(1).lower() in ("buy", "long", "b") else "SHORT"
        rest      = dir_m.group(2).strip()

        cmd = ParsedCommand(action="order", direction=direction,
                            symbol=default_symbol, raw=raw)

        # Symbol
        sym, rest = _extract_symbol(rest, default_symbol)
        cmd.symbol = sym

        # SL / TP (strip before other parsing to avoid confusion)
        sl_val, sl_unit, tp_val, tp_unit, rest = _extract_sl_tp(rest)
        cmd.sl, cmd.sl_unit = sl_val, sl_unit
        cmd.tp, cmd.tp_unit = tp_val, tp_unit

        # Limit / stop price
        lm = re.search(r'\b(limit|lmt|stop|stp)\s+(?:at\s+)?([\d.]+)', rest, re.I)
        if lm:
            kw = lm.group(1).lower()
            cmd.order_type  = "LIMIT" if kw in ("limit", "lmt") else "STOP"
            cmd.limit_price = float(lm.group(2))
            rest = (rest[:lm.start()] + rest[lm.end():]).strip()

        # Lots
        lm2 = re.search(r'([\d.]+)\s*(?:lots?|l)?\b', rest, re.I)
        if lm2:
            cmd.lots = float(lm2.group(1))

        return cmd

    return ParsedCommand(action="unknown", error=f"Unknown command: '{text}'", raw=raw)


# ── Config sub-parser ─────────────────────────────────────────────────────────

def _try_parse_config(rest: str, raw: str) -> Optional[ParsedCommand]:
    """Try to parse 'default|max|risk|daily|drawdown ...' config commands."""
    # "default lots N"  |  "default size N"
    m = re.match(r'^default\s+(?:lots?|size|position\s*size)\s+(?:to\s+)?([\d.]+)', rest, re.I)
    if m:
        return ParsedCommand(action="config", config_key="default_lots",
                             config_val=float(m.group(1)), raw=raw)

    # "max lots N"  |  "max size N"
    m = re.match(r'^max(?:imum)?\s+(?:lots?|size|position\s*size)\s+(?:to\s+)?([\d.]+)', rest, re.I)
    if m:
        return ParsedCommand(action="config", config_key="max_lots",
                             config_val=float(m.group(1)), raw=raw)

    # "default sl N [unit]"
    m = re.match(r'^default\s+(?:sl|stop|stop\s*loss)\s+(?:to\s+)?([\d.]+)\s*(' + _UNIT_PAT + r')?', rest, re.I)
    if m:
        unit = _detect_unit(m.group(2)) if m.group(2) else "points"
        return ParsedCommand(action="config", config_key="default_sl_points",
                             config_val=float(m.group(1)), config_unit=unit, raw=raw)

    # "default tp N [unit]"
    m = re.match(r'^default\s+(?:tp|take\s*profit|target)\s+(?:to\s+)?([\d.]+)\s*(' + _UNIT_PAT + r')?', rest, re.I)
    if m:
        unit = _detect_unit(m.group(2)) if m.group(2) else "points"
        return ParsedCommand(action="config", config_key="default_tp_points",
                             config_val=float(m.group(1)), config_unit=unit, raw=raw)

    # "risk N%"
    m = re.match(r'^risk\s+(?:to\s+)?([\d.]+)\s*%?', rest, re.I)
    if m:
        return ParsedCommand(action="config", config_key="risk_pct",
                             config_val=float(m.group(1)), raw=raw)

    # "daily limit N"
    m = re.match(r'^daily\s+(?:loss\s+)?limit\s+(?:to\s+)?([\d.,]+)', rest, re.I)
    if m:
        return ParsedCommand(action="config", config_key="daily_loss_limit",
                             config_val=float(m.group(1).replace(",", "")), raw=raw)

    # "drawdown limit N"
    m = re.match(r'^drawdown\s+(?:limit\s+)?(?:to\s+)?([\d.,]+)', rest, re.I)
    if m:
        return ParsedCommand(action="config", config_key="drawdown_limit",
                             config_val=float(m.group(1).replace(",", "")), raw=raw)

    # "win rate N%"  /  "kelly win rate N%"
    m = re.match(r'^(?:kelly\s+)?win\s*rate\s+(?:to\s+)?([\d.]+)', rest, re.I)
    if m:
        return ParsedCommand(action="config", config_key="kelly_win_rate",
                             config_val=float(m.group(1)) / 100.0, raw=raw)

    return None
