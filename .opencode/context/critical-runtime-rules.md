# Critical Runtime Rules

Treat changes as runtime-critical when they touch execution, reconciliation, wallet sync, watchdog, recovery, Binance Futures auth, order state, position state, or mode handling.

Operational invariants:

- The exchange is the source of truth for real exposure and live order/position state.
- Never leave a real position without `HARD SL` coverage.
- Do not add non-idempotent retries that can duplicate exposure.
- If live state is ambiguous, prefer `HALT` and reconciliation before continuing.
- Keep `PAPER`, `SHADOW`, and `REAL` behavior separated.
- In `REAL`, auth or permission failures must abort rather than degrade silently.
- Do not introduce silent `pass` statements in `core/`.

Critical files include:

- `core/bot_app.py`
- `core/bot_facade.py`
- `core/bot_connection.py`
- `core/execution_adapters.py`
- `core/config/`
- watchdog, recovery, reconciliation, wallet sync, and runtime safety tools.
