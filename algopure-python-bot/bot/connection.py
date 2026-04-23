"""
MT5 connection management.
Supports multiple parallel MT5 terminals via MT5_PATH in .env.
Reads credentials from Windows Credential Manager via keyring.
"""

import os
import keyring
import MetaTrader5 as mt5


def connect():
    path    = os.getenv("MT5_PATH")
    profile = os.getenv("KEYRING_PROFILE", "algopure")

    login    = keyring.get_password("mt5", f"{profile}_login")    or os.getenv("MT5_LOGIN")
    password = keyring.get_password("mt5", f"{profile}_password") or os.getenv("MT5_PASSWORD")
    server   = keyring.get_password("mt5", f"{profile}_server")   or os.getenv("MT5_SERVER")

    kwargs = {}
    if path:
        kwargs["path"] = path
    if login and password and server:
        kwargs.update(login=int(login), password=password, server=server)

    ok = mt5.initialize(**kwargs) if kwargs else mt5.initialize()

    if not ok:
        raise RuntimeError(f"MT5 connection failed: {mt5.last_error()}")

    info = mt5.account_info()
    if info is None:
        raise RuntimeError(f"Could not retrieve account info: {mt5.last_error()}")

    print("\n  Connected to MetaTrader 5")
    print(f"  Account  : {info.name}  (#{info.login})")
    print(f"  Server   : {info.server}")
    print(f"  Balance  : {info.balance:,.2f} {info.currency}")
    print(f"  Leverage : 1:{info.leverage}")


def disconnect():
    mt5.shutdown()
    print("\n  Disconnected from MT5.")
