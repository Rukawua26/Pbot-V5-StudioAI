# Repo Summary

This repository is a Binance Futures trading bot with `PAPER`, `SHADOW`, and `REAL` modes.

Core truths:

- `main.py` is the real entrypoint and should only import `run_entrypoint` from `core.bot_app`.
- Heavy bootstrap belongs in `core/bot_app.py`, not `main.py`.
- `config.py` is a legacy proxy; real configuration is in `core/config/manager.py` and `core/config/operational.py`.
- `.env` is loaded by importing `core/config/operational.py`.
- `core/bot_facade.py` is the public runtime contract.
- `core/bot_connection.py` separates connection behavior by mode.
- `core/execution_adapters.py` defines live and shadow-live execution boundaries.
- `core/trade_entry.py` is the entry-point for trade execution (SHADOW/PAPER/REAL); builds `trade_state` with confidence, similarity boost, and context snapshot.
- `learning.py` and `tools/learning.py` both define `Brain` with a Trade Context Vault: `save_trade_context_snapshot`, `find_similar_contexts`, `cleanup_stale_snapshots`. The bot uses `tools/learning.Brain` at runtime.
- The DB table `trade_context_snapshots` stores market fingerprints (derived features, ~1 KB) for cosine-similarity search against historical winners.
- Startup migrations in `core/bot_models_startup.py` handle stale snapshot cleanup and features_version migration.

Keep changes small. Do not mix broad refactors with functional fixes.
