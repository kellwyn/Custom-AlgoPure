---
name: diagnostic-scan
description: Runs a one-shot filter diagnostic on the AlgoPure bot to identify which rules are passing or blocking. Use when the bot reports "No setup detected" and you need to know why.
---

Run a filter-by-filter diagnostic scan on the bot for symbol $ARGUMENTS (default: XAUUSD).

1. Determine the symbol — use $ARGUMENTS if provided, otherwise check the running bot's config or default to `XAUUSD`

2. Find the bot directory in the current repo:
```bash
BOT_DIR=$(find /c/Users/kellw/OneDrive/Custom-AlgoPure -maxdepth 1 -type d -name "*-python-bot" | head -1)
echo "Bot dir: $BOT_DIR"
```

3. Run the following diagnostic from that directory:

```bash
cd "$BOT_DIR" && python -u -c "
import os; os.environ['SYMBOL'] = 'SYMBOL_HERE'
from dotenv import load_dotenv; load_dotenv()
from bot.connection import connect; connect()
import MetaTrader5 as mt5
from bot.strategy import find_setup, StrategyConfig
from main import cfg
tick = mt5.symbol_info_tick(cfg.symbol)
print(f'Symbol  : {cfg.symbol}  |  bid/ask: {tick.bid:.2f}/{tick.ask:.2f}')
setup = find_setup(cfg)
print(f'Setup   : {setup if setup else \"No setup detected\"}')
mt5.shutdown()
"
```

4. Interpret the output:
   - **No setup detected** — strategy rules not yet implemented or conditions not met
   - **Connection error** — check keyring credentials with `python -c "import keyring; print(keyring.get_password('mt5','algopure_login'))"`
   - **Symbol None** — wrong symbol for connected broker; check `.env` SYMBOL setting
