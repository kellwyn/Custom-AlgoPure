"""
AlgoPure Signal Lab — Streamlit Web Dashboard
Run: streamlit run dashboard_web.py -- --symbol XAUUSDp [--profile metaquotes]

All timestamps are UTC.
ICT RTH for gold = 13:30–20:00 UTC (COMEX / NY session, 09:30–16:00 US/Eastern).
48-slot chart time labels are UTC clock hours.
"""

import argparse
import os
import sys
import time
from datetime import datetime

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── parse CLI args passed after '--' in streamlit run ────────────────────────
def _parse_args():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--symbol",  default=None)
    p.add_argument("--profile", default=None)
    args, _ = p.parse_known_args()
    return args

_cli = _parse_args()

# ── MT5 connection (cached per session) ──────────────────────────────────────
@st.cache_resource(show_spinner="Connecting to MT5…")
def _mt5_connect(profile: str | None):
    import keyring
    if profile:
        prefix = f"PROFILE_{profile.upper().replace('-', '_')}_"
        for k, v in os.environ.items():
            if k.startswith(prefix):
                os.environ[k[len(prefix):]] = v

    p     = os.getenv("KEYRING_PROFILE", "algopure")
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
        st.error(f"MT5 init failed: {mt5.last_error()}")
        st.stop()
    return True


# ── Historical data cache (5-min TTL) ────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner="Fetching 3M of M30 bars…")
def _get_hist(symbol: str) -> pd.DataFrame:
    sys.path.insert(0, os.path.dirname(__file__))
    from config  import LabConfig
    from fetcher import fetch_ohlcv
    # Ensure MT5 is initialised in this thread (cache_data runs in its own context)
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed in data fetch: {mt5.last_error()}")
    mt5.symbol_select(symbol, True)
    return fetch_ohlcv(LabConfig(symbol=symbol), "3M")


# ── Live MT5 data (no cache — always fresh) ───────────────────────────────────
def _live_data(symbol: str):
    acct      = mt5.account_info()
    positions = mt5.positions_get() or []
    pending   = mt5.orders_get()   or []
    tick      = mt5.symbol_info_tick(symbol)
    return acct, positions, pending, tick


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title = "AlgoPure Signal Lab",
    page_icon  = "📊",
    layout     = "wide",
    initial_sidebar_state = "expanded",
)

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.title("AlgoPure Signal Lab")
    st.caption("All times UTC · ICT RTH = 13:30–20:00 UTC")
    st.divider()

    symbol = st.text_input("Symbol", value=_cli.symbol or os.getenv("SYMBOL", "XAUUSDp"))
    profile = st.text_input("Profile", value=_cli.profile or os.getenv("KEYRING_PROFILE", "algopure"))

    st.divider()
    daily_loss_limit = st.number_input("Daily Loss Limit ($)", value=8000.0, step=500.0)
    drawdown_limit   = st.number_input("Drawdown Limit ($)",   value=5000.0, step=500.0)
    max_loss_limit   = st.number_input("Max Loss Limit ($, 0=off)", value=0.0, step=1000.0)

    st.divider()
    auto_refresh = st.toggle("Auto-refresh", value=False)
    refresh_secs = st.slider("Refresh interval (s)", 5, 120, 15) if auto_refresh else 15

    st.divider()
    rth_only = st.checkbox("Slot chart: RTH only", value=False)
    st.caption("RTH = 13:30–20:00 UTC (COMEX gold / NY)")

# ── Connect ───────────────────────────────────────────────────────────────────
_mt5_connect(profile if profile else None)

# ── Fetch data ────────────────────────────────────────────────────────────────
acct, positions, pending, tick = _live_data(symbol)

# ── Header ────────────────────────────────────────────────────────────────────
ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
st.markdown(f"## AlgoPure Signal Lab &nbsp;·&nbsp; `{symbol}` &nbsp;·&nbsp; <small>{ts}</small>",
            unsafe_allow_html=True)

if acct:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Balance",     f"${acct.balance:,.2f}")
    c2.metric("Equity",      f"${acct.equity:,.2f}",
              delta=f"{acct.equity - acct.balance:+,.2f}")
    c3.metric("Free Margin", f"${acct.margin_free:,.2f}")
    c4.metric("Account",     f"#{acct.login} · {acct.server}")

if tick:
    st.caption(f"Current bid/ask: **{tick.bid:.5f} / {tick.ask:.5f}**  ·  "
               f"Spread: {(tick.ask-tick.bid)*100:.1f} pts")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_pos, tab_mkt, tab_ict = st.tabs([
    "📋 Live Positions & Risk",
    "📊 48-Slot Market Character",
    "🕐 ICT RTH Session Analysis",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Live Positions & Risk
# ═══════════════════════════════════════════════════════════════════════════════
with tab_pos:
    from live_metrics import (
        build_risk_metrics_table, scenario_table,
        sl_alternatives, tp_alternatives, hedge_breakeven_table,
    )
    from config import LabConfig

    # ── Positions summary ──────────────────────────────────────────────────
    st.subheader("Open Positions")
    if not positions:
        st.info("No open positions.")
    else:
        rows = []
        for p in positions:
            t = mt5.symbol_info_tick(p.symbol)
            cur = (t.bid if p.type == mt5.ORDER_TYPE_BUY else t.ask) if t else p.price_current
            rows.append({
                "Ticket":  p.ticket,
                "Symbol":  p.symbol,
                "Side":    "LONG" if p.type == mt5.ORDER_TYPE_BUY else "SHORT",
                "Lots":    p.volume,
                "Entry":   p.price_open,
                "Current": round(cur, 5),
                "SL":      p.sl,
                "TP":      p.tp,
                "P&L $":   round(p.profit, 2),
            })
        pos_df = pd.DataFrame(rows)

        def _pnl_color(val):
            color = "#4ade80" if val > 0 else ("#f87171" if val < 0 else "inherit")
            return f"color: {color}; font-weight: bold"

        styled = (
            pos_df.style
            .map(_pnl_color, subset=["P&L $"])
            .format({"Entry": "{:.5f}", "Current": "{:.5f}", "SL": "{:.5f}",
                     "TP": "{:.5f}", "P&L $": "${:+,.2f}", "Lots": "{:.2f}"})
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)

    if pending:
        st.subheader("Pending Orders")
        prows = []
        for o in pending:
            otype = {
                mt5.ORDER_TYPE_BUY_LIMIT: "BUY LIMIT", mt5.ORDER_TYPE_SELL_LIMIT: "SELL LIMIT",
                mt5.ORDER_TYPE_BUY_STOP:  "BUY STOP",  mt5.ORDER_TYPE_SELL_STOP:  "SELL STOP",
            }.get(o.type, str(o.type))
            prows.append({"Ticket": o.ticket, "Symbol": o.symbol, "Type": otype,
                          "Lots": o.volume, "Price": o.price_open, "SL": o.sl, "TP": o.tp})
        st.dataframe(pd.DataFrame(prows), use_container_width=True, hide_index=True)

    # ── Per-position risk tables ────────────────────────────────────────────
    for pos in positions:
        direction = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
        info      = mt5.symbol_info(pos.symbol)
        if info is None:
            continue

        tick_sz = info.trade_tick_size
        tick_v  = info.trade_tick_value
        t2      = mt5.symbol_info_tick(pos.symbol)
        current = (t2.bid if pos.type == mt5.ORDER_TYPE_BUY else t2.ask) if t2 else pos.price_current
        sl      = pos.sl if pos.sl > 0 else None
        tp      = pos.tp if pos.tp > 0 else None
        balance = acct.balance if acct else 1.0

        pnl_sign = "+" if pos.profit >= 0 else ""
        st.markdown(
            f"---\n#### Ticket #{pos.ticket} · {pos.symbol} · **{direction}** · "
            f"{pos.volume} lots @ {pos.price_open:.5f}  "
            f"&nbsp;|&nbsp; Current: **{current:.5f}**  "
            f"&nbsp;|&nbsp; P&L: **{pnl_sign}${pos.profit:,.2f}**"
        )

        col_risk, col_scen = st.columns([1, 1])

        with col_risk:
            st.markdown("**Risk Thresholds**")
            risk_df = build_risk_metrics_table(
                entry=pos.price_open, current=current, sl=sl, tp=tp,
                lots=pos.volume, direction=direction, balance=balance,
                tick_size=tick_sz, tick_value=tick_v,
                daily_loss_limit=daily_loss_limit,
                drawdown_limit=drawdown_limit,
                max_loss_limit=max_loss_limit,
            )

            def _risk_color(row):
                styles = [""] * len(row)
                pnl_col = list(risk_df.columns).index("P&L $") if "P&L $" in risk_df.columns else -1
                if pnl_col >= 0:
                    val = row.iloc[pnl_col]
                    if isinstance(val, str) and val.startswith("$+"):
                        styles[pnl_col] = "color: #4ade80"
                    elif isinstance(val, str) and val.startswith("$-"):
                        styles[pnl_col] = "color: #f87171"
                return styles

            st.dataframe(
                risk_df.style.apply(_risk_color, axis=1),
                use_container_width=True, hide_index=True,
            )

        with col_scen:
            st.markdown("**5 Hypothetical Scenarios**")
            sc_df = scenario_table(
                entry=pos.price_open, current=current, sl=sl, tp=tp,
                lots=pos.volume, direction=direction, balance=balance,
                tick_size=tick_sz, tick_value=tick_v,
            )

            def _sc_color(row):
                styles = [""] * len(row)
                oc = list(sc_df.columns).index("Outcome") if "Outcome" in sc_df.columns else -1
                if oc >= 0:
                    if "WIN" in str(row.iloc[oc]):   styles = ["color: #4ade80"] * len(row)
                    elif "LOSS" in str(row.iloc[oc]): styles = ["color: #f87171"] * len(row)
                return styles

            st.dataframe(
                sc_df.style.apply(_sc_color, axis=1),
                use_container_width=True, hide_index=True,
            )

        col_sl, col_tp, col_hg = st.columns(3)

        with col_sl:
            st.markdown("**SL Alternatives (3)**")
            sl_df = sl_alternatives(pos.price_open, sl, pos.volume, direction,
                                    balance, tick_sz, tick_v)
            st.dataframe(sl_df, use_container_width=True, hide_index=True)

        with col_tp:
            st.markdown("**TP Alternatives (3)**")
            tp_df = tp_alternatives(pos.price_open, sl, tp, pos.volume, direction,
                                    balance, tick_sz, tick_v)
            st.dataframe(tp_df, use_container_width=True, hide_index=True)

        with col_hg:
            st.markdown("**Hedge Break-Even**")
            hg_df = hedge_breakeven_table(pos.price_open, current, pos.volume,
                                          direction, tick_sz, tick_v)
            st.dataframe(hg_df, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — 48-Slot Market Character
# ═══════════════════════════════════════════════════════════════════════════════
with tab_mkt:
    from market_analysis import compute_slot_char
    from config import LabConfig

    st.subheader("48-Slot Market Character (M30, 3-Month Lookback)")
    st.caption(
        "Slot time labels are **UTC** clock hours.  "
        "ICT RTH slots (gold): **13:30–20:00 UTC** = 09:30–16:00 US/Eastern (COMEX).  "
        "Sorted by avg tick volume (most active first)."
    )

    hist_df = _get_hist(symbol)
    cfg     = LabConfig(symbol=symbol)
    slot_df = compute_slot_char(
        hist_df,
        big_move_pct    = cfg.big_move_pct,
        tight_range_pct = cfg.tight_range_pct,
        rth_only        = rth_only,
        rth_start_h     = cfg.rth_start_h,
        rth_end_h       = cfg.rth_end_h,
    )

    display_cols = ["time_label", "n_bars", "pct_buy", "pct_sell", "bias",
                    "volat_lbl", "avg_rsi", "vol_lbl", "avg_vol",
                    "ict_vol_pct", "daily_vol_pct", "pct_big", "pct_tight", "money_spent"]
    col_labels = {
        "time_label":    "Time (UTC)",
        "n_bars":        "N Bars",
        "pct_buy":       "% Buy",
        "pct_sell":      "% Sell",
        "bias":          "Bias",
        "volat_lbl":     "Volatility",
        "avg_rsi":       "RSI",
        "vol_lbl":       "Vol Label",
        "avg_vol":       "Avg Tick Vol",
        "ict_vol_pct":   "% ICT Vol",
        "daily_vol_pct": "% Daily Vol",
        "pct_big":       "% Big",
        "pct_tight":     "% Tight",
        "money_spent":   "Money Spent",
    }

    slot_out = (
        slot_df[display_cols]
        .sort_values("avg_vol", ascending=False)
        .rename(columns=col_labels)
        .reset_index(drop=True)
    )

    def _slot_style(df):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        if "Bias" in df.columns:
            styles["Bias"] = df["Bias"].apply(
                lambda v: "color: #4ade80; font-weight:bold" if v > 10
                else ("color: #f87171; font-weight:bold" if v < -10 else "")
            )
        if "Volatility" in df.columns:
            styles["Volatility"] = df["Volatility"].apply(
                lambda v: "color: #f87171" if v == "HIGH"
                else ("color: #60a5fa" if v == "LOW" else "")
            )
        if "Vol Label" in df.columns:
            styles["Vol Label"] = df["Vol Label"].apply(
                lambda v: "color: #f87171" if v == "HIGH"
                else ("color: #60a5fa" if v == "LOW" else "")
            )
        return styles

    st.dataframe(
        slot_out.style
            .apply(_slot_style, axis=None)
            .format({
                "% Buy": "{:.1f}%", "% Sell": "{:.1f}%",
                "Bias": "{:+.1f}", "RSI": "{:.1f}",
                "Avg Tick Vol": "{:,.0f}", "% ICT Vol": "{:.0f}%",
                "% Daily Vol": "{:.0f}%", "% Big": "{:.1f}%",
                "% Tight": "{:.1f}%", "Money Spent": "{:,.0f}",
            }),
        use_container_width=True,
        hide_index=True,
        height=600,
    )

    # Top 10 by directional bias
    st.markdown("---")
    st.markdown("**Top 10 Slots by Directional Bias Strength** (min 10 bars)")
    top10 = (
        slot_df[slot_df["n_bars"] >= 10]
        .sort_values("bias_score", ascending=False)
        .head(10)[display_cols]
        .rename(columns=col_labels)
        .reset_index(drop=True)
    )
    st.dataframe(
        top10.style
            .apply(_slot_style, axis=None)
            .format({
                "% Buy": "{:.1f}%", "% Sell": "{:.1f}%",
                "Bias": "{:+.1f}", "RSI": "{:.1f}",
                "Avg Tick Vol": "{:,.0f}", "% ICT Vol": "{:.0f}%",
                "% Daily Vol": "{:.0f}%", "% Big": "{:.1f}%",
                "% Tight": "{:.1f}%", "Money Spent": "{:,.0f}",
            }),
        use_container_width=True,
        hide_index=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ICT RTH Session Analysis
# ═══════════════════════════════════════════════════════════════════════════════
with tab_ict:
    from market_analysis import compute_ict_sessions
    from config import LabConfig

    cfg = LabConfig(symbol=symbol)

    st.subheader("ICT RTH Session — Last 20 Days")
    st.caption(
        f"**RTH window: {cfg.rth_start_h:02d}:{cfg.rth_start_m:02d}–"
        f"{cfg.rth_end_h:02d}:{cfg.rth_end_m:02d} UTC**  "
        f"(= 09:30–16:00 US/Eastern / COMEX gold floor)  ·  "
        f"30-day rolling baselines.  Rows marked ⚠ have at least one anomaly (>1.5σ)."
    )

    hist_df = _get_hist(symbol)
    ict_df  = compute_ict_sessions(
        hist_df,
        rth_start_h  = cfg.rth_start_h,
        rth_start_m  = cfg.rth_start_m,
        rth_end_h    = cfg.rth_end_h,
        rth_end_m    = cfg.rth_end_m,
        n_days       = 20,
        rolling_days = 30,
    )

    # Build display frame
    ict_display = ict_df[[
        "date", "sess_vol", "sess_baseline", "vs_sess_pct",
        "daily_vol", "daily_baseline", "vs_daily_pct",
        "money_spent", "pct_buy", "pct_sell", "avg_rsi",
        "volat_lbl", "anomaly",
    ]].copy()
    ict_display.columns = [
        "Date", "Sess Vol", "30d Sess Baseline", "% vs Sess",
        "Daily Vol", "30d Daily Baseline", "% vs Daily",
        "Money Spent", "% Buy", "% Sell", "Avg RSI",
        "Volatility", "Anomalies",
    ]
    ict_display["Date"] = ict_display["Date"].astype(str)
    # Prefix anomaly rows
    ict_display["Date"] = ict_display.apply(
        lambda r: f"! {r['Date']}" if r["Anomalies"] else r["Date"], axis=1
    )

    def _ict_row_style(row):
        is_anom  = bool(row["Anomalies"])
        # Anomaly rows: very subtle warm tint — no dark background
        row_bg   = "background-color: #fffbea; " if is_anom else ""
        styles   = [row_bg] * len(row)
        col_list = list(ict_display.columns)
        for col, val in zip(col_list, row):
            idx = col_list.index(col)
            if col == "% vs Sess":
                try:
                    v = float(str(val).replace("%",""))
                    if v >= 130:  styles[idx] = row_bg + "color: #16a34a; font-weight:bold"
                    elif v <= 70: styles[idx] = row_bg + "color: #dc2626; font-weight:bold"
                except: pass
            elif col == "% vs Daily":
                try:
                    v = float(str(val).replace("%",""))
                    if v >= 130:  styles[idx] = row_bg + "color: #16a34a; font-weight:bold"
                    elif v <= 70: styles[idx] = row_bg + "color: #dc2626; font-weight:bold"
                except: pass
            elif col == "Volatility":
                if str(val) == "HIGH":   styles[idx] = row_bg + "color: #dc2626"
                elif str(val) == "LOW":  styles[idx] = row_bg + "color: #2563eb"
            elif col == "Anomalies" and val:
                styles[idx] = row_bg + "color: #b45309; font-weight:bold"
            elif col == "Date" and is_anom:
                styles[idx] = row_bg + "font-weight:bold"
        return styles

    fmt = {
        "Sess Vol": "{:,.0f}", "30d Sess Baseline": "{:,.0f}",
        "% vs Sess": "{:.0f}%", "Daily Vol": "{:,.0f}",
        "30d Daily Baseline": "{:,.0f}", "% vs Daily": "{:.0f}%",
        "Money Spent": "{:,.0f}", "% Buy": "{:.1f}%",
        "% Sell": "{:.1f}%", "Avg RSI": "{:.1f}",
    }
    st.dataframe(
        ict_display.style.apply(_ict_row_style, axis=1).format(fmt, na_rep="—"),
        use_container_width=True,
        hide_index=True,
        height=500,
    )

    # Anomaly digest
    anomalous = ict_df[ict_df["anomaly"].str.len() > 0]
    if not anomalous.empty:
        st.markdown("---")
        st.markdown("**Anomaly Digest**")
        for _, row in anomalous.iterrows():
            st.warning(f"**{row['date']}** → {row['anomaly']}")
    else:
        st.success("No anomalies detected in the last 20 days.")


# ── Auto-refresh ──────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(refresh_secs)
    st.rerun()
