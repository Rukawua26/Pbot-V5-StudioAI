#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$PROJECT_ROOT"

"$PYTHON_BIN" - <<'PY'
import importlib

modules = [
    "core.command_router",
    "core.bot_facade",
    "core.bot_cycles",
    "core.bot_signals",
    "core.bot_housekeeping",
    "core.bot_runtime",
    "core.bot_main_loop",
    "core.market_intelligence",
    "core.process_lock",
    "core.bot_risk_cycles",
    "core.signals.analyze",
    "core.signals.context",
    "core.signals.filters",
    "core.signals.execution",
]

for name in modules:
    importlib.import_module(name)

print("OK modular imports")
PY

echo "[OK] Modular import smoke passed"
