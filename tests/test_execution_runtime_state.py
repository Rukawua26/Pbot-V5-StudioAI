import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.execution_runtime_state import (
    EXECUTION_RUNTIME_META_KEY,
    load_execution_runtime_state,
    persist_execution_runtime_state,
)
from core.execution_service import ExecutionService


class _MemoryBrain:
    def __init__(self):
        self._meta = {}

    def set_metadata_json(self, key, value):
        self._meta[key] = value

    def get_metadata_json(self, key, default=None):
        return self._meta.get(key, default)


class _NoOpExchange:
    def __init__(self):
        self.timeout = 9000


class ExecutionRuntimeStateTest(unittest.TestCase):
    def test_persist_and_load_runtime_state_roundtrip(self):
        brain = _MemoryBrain()

        service_a = ExecutionService("k", "s")
        service_a.exchange = _NoOpExchange()

        with patch("core.execution_service.time.time", return_value=100.0):
            service_a._symbol_quarantine_until = {"BTC/USDT": 200.0}
            service_a._no_price_exit_daily_metrics = {
                service_a._active_no_price_day_key(): {"BTC/USDT": 2}
            }

        bot_a = SimpleNamespace(brain=brain, execution=service_a, log=lambda *_: None)
        with patch("core.execution_service.time.time", return_value=100.0):
            persist_execution_runtime_state(bot_a)

        self.assertIn(EXECUTION_RUNTIME_META_KEY, brain._meta)

        service_b = ExecutionService("k", "s")
        service_b.exchange = _NoOpExchange()
        bot_b = SimpleNamespace(brain=brain, execution=service_b, log=lambda *_: None)

        with patch("core.execution_service.time.time", return_value=120.0):
            load_execution_runtime_state(bot_b)
            self.assertTrue(service_b.is_symbol_quarantined("BTC/USDT"))
            self.assertEqual(service_b.get_no_price_market_exit_count("BTC/USDT"), 2)

    def test_import_ignores_expired_quarantine(self):
        service = ExecutionService("k", "s")
        service.exchange = _NoOpExchange()

        with patch("core.execution_service.time.time", return_value=500.0):
            service.import_runtime_state(
                {
                    "quarantines": {"ETH/USDT": 400.0},
                    "no_price_exit_daily": {},
                }
            )

        self.assertFalse(service.is_symbol_quarantined("ETH/USDT"))


if __name__ == "__main__":
    unittest.main()
