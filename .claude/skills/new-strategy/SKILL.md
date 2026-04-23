---
name: new-strategy
description: Scaffolds a new strategy repo with the standard three-component structure (mq5-ea, python-bot, signal-lab). Run when starting a new trading strategy project.
disable-model-invocation: true
---

Scaffold a new MetaTrader strategy project named $ARGUMENTS.

Follow these steps exactly:

1. **Confirm the strategy name** — derive a slug (e.g. "SwingBB" → `swingbb`, "80/20 Scalps" → `8020scalps`)

2. **Create repo directory structure**:
```
DEV-<StrategyName>/
├── <slug>-mq5-ea/
├── <slug>-python-bot/
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── signals.py
│   │   ├── strategy.py
│   │   └── trader.py
│   ├── main.py
│   └── requirements.txt
├── <slug>-signal-lab/
│   ├── config.py
│   ├── fetcher.py
│   ├── main.py
│   ├── report.py
│   ├── strategy_scan.py
│   └── tp_analysis.py
├── .env.example
├── .gitignore
├── CLAUDE.md
└── CREDENTIALS.md
```

3. **Create the EA shell** in `<slug>-mq5-ea/<StrategyName>_v1.00.mq5`:
   - Use the MQL5_EA_SHELL from `../Dev-RZY/SKILLS.md`
   - Set `#property version "1.00"`
   - Add strategy name and date to file header comment

4. **Update MAGIC_NUMBER** in `.env.example` — use today's date as YYYYMMDD

5. **Initialise git**:
```bash
git init
git add .
git commit -m "$(cat <<'EOF'
Initial commit — <StrategyName> v1.00 scaffold

Co-Authored-By: KSE
EOF
)"
```

6. **Report** — list all created files and confirm next step: "Implement strategy rules in `<slug>-mq5-ea/<StrategyName>_v1.00.mq5` starting with Rule 1."
