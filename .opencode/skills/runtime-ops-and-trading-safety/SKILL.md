---
name: runtime-ops-and-trading-safety
description: Use ONLY when changes touch Binance Futures runtime execution, orders, positions, PAPER/SHADOW/REAL mode behavior, reconciliation, wallet sync, watchdog, recovery, HALT, stop loss, core/bot_app.py, core/bot_facade.py, core/bot_connection.py, or core/execution_adapters.py.
---

# Runtime Ops And Trading Safety

Treat this as runtime-critical work.

Required checks:

- Preserve separation between `PAPER`, `SHADOW`, and `REAL`.
- The exchange is authoritative for real exposure, orders, and positions.
- Never leave a real position without `HARD SL` coverage.
- Avoid non-idempotent retries that could duplicate exposure.
- If live state is ambiguous, prefer `HALT` and reconciliation before continuing.
- In `REAL`, auth or permission failures must abort; do not silently degrade.
- Keep live execution behind `core/execution_adapters.py` boundaries.
- Do not add silent `pass` statements in `core/`.

Before finishing, identify whether focused runtime tests, `scripts/smoke_modular_imports.sh`, or `tools/regression_contracts.py` are required.
