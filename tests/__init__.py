"""
Test isolation note:
- SNIPER_DISABLE_FILE_TELEMETRY prevents telemetry side effects at import time.
- Top 3 priorities for better isolation:
  1. test_execution_service_methods.py — defer `import ccxt` to test methods
  2. test_reconciliation.py — use @patch instead of mutating Config directly
  3. test_config_precedence.py — replace save/restore with @patch.object
"""

import os

os.environ.setdefault("SNIPER_DISABLE_FILE_TELEMETRY", "1")
