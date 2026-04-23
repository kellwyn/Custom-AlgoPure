"""
Execution bot configuration — defaults and hard limits.
All values can be overridden via environment variables or runtime commands.
"""
import os
from dataclasses import dataclass, field


@dataclass
class ExecutionConfig:
    # ── Identity ──────────────────────────────────────────────────────────────
    magic:   int = 20260423
    comment: str = "AlgoPure_v1.00"
    slippage: int = 10

    # ── Default position parameters ───────────────────────────────────────────
    default_lots: float = 0.10
    max_lots:     float = 2.0         # hard ceiling — never exceeded

    # ── Default SL / TP (0 = no default, user must specify) ──────────────────
    default_sl_points: float = 0.0    # in price points (tick units)
    default_tp_points: float = 0.0

    # ── Risk / account limits ─────────────────────────────────────────────────
    risk_pct:          float = 1.0    # % of balance per trade (Kelly override)
    daily_loss_limit:  float = 8000.0  # stop trading if daily loss ≥ this
    drawdown_limit:    float = 5000.0  # alert at this floating drawdown
    max_loss_limit:    float = 0.0    # 0 = no additional hard cap

    # ── Kelly criterion ───────────────────────────────────────────────────────
    kelly_win_rate:    float = 0.55   # assumed win rate for Kelly sizing
    kelly_fraction:    float = 0.25   # fraction of full Kelly to use (quarter-Kelly)

    # ── Execution gate ────────────────────────────────────────────────────────
    manual_confirm: bool = True       # always confirm before executing

    # ── Defaults ─────────────────────────────────────────────────────────────
    default_symbol: str = "XAUUSD"

    # ── Symbol aliases (lower-case input → canonical MT5 symbol) ─────────────
    symbol_aliases: dict = field(default_factory=lambda: {
        "gold":         "XAUUSD",
        "xau":          "XAUUSD",
        "xauusd":       "XAUUSD",
        "auusd":        "XAUUSD",
        "xauusdp":      "XAUUSDp",
        "goldf":        "GOLD.f",
        "gold.f":       "GOLD.f",
        "goldfutures":  "GOLD.f",
    })

    def resolve_symbol(self, raw: str) -> str:
        return self.symbol_aliases.get(raw.lower(), raw.upper())


def load_exec_config() -> ExecutionConfig:
    return ExecutionConfig(
        default_lots      = float(os.getenv("DEFAULT_LOTS",      "0.10")),
        max_lots          = float(os.getenv("MAX_LOTS",          "2.0")),
        default_sl_points = float(os.getenv("DEFAULT_SL_POINTS", "0")),
        default_tp_points = float(os.getenv("DEFAULT_TP_POINTS", "0")),
        risk_pct          = float(os.getenv("RISK_PCT",          "1.0")),
        daily_loss_limit  = float(os.getenv("DAILY_LOSS_LIMIT",  "8000")),
        drawdown_limit    = float(os.getenv("DRAWDOWN_LIMIT",    "5000")),
        max_loss_limit    = float(os.getenv("MAX_LOSS_LIMIT",    "0")),
        kelly_win_rate    = float(os.getenv("KELLY_WIN_RATE",    "0.55")),
        kelly_fraction    = float(os.getenv("KELLY_FRACTION",    "0.25")),
        manual_confirm    = os.getenv("MANUAL_CONFIRM", "true").lower() == "true",
        default_symbol    = os.getenv("SYMBOL", "XAUUSD"),
    )
