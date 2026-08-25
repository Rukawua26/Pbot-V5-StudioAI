import unittest

from core.execution_service import ExecutionService
from core.trade_manager import _clamp_leverage_1_to_10


class _DummyExchange:
    def __init__(self):
        self.calls = []

    def set_leverage(self, leverage, symbol):
        self.calls.append((leverage, symbol))
        return {"leverage": leverage, "symbol": symbol}


class LeverageGuardrailsTest(unittest.TestCase):
    def test_trade_manager_clamps_leverage_between_1_and_10(self):
        self.assertEqual(_clamp_leverage_1_to_10(25), 10)
        self.assertEqual(_clamp_leverage_1_to_10(0), 1)
        self.assertEqual(_clamp_leverage_1_to_10(7), 7)
        self.assertEqual(_clamp_leverage_1_to_10("9"), 9)

    def test_execution_service_set_leverage_applies_guardrail(self):
        svc = ExecutionService("k", "s")
        svc.exchange = _DummyExchange()

        svc.set_leverage(50, "BTC/USDT")
        svc.set_leverage(-2, "ETH/USDT")
        svc.set_leverage(6, "SOL/USDT")

        self.assertEqual(svc.exchange.calls[0], (10, "BTC/USDT"))
        self.assertEqual(svc.exchange.calls[1], (1, "ETH/USDT"))
        self.assertEqual(svc.exchange.calls[2], (6, "SOL/USDT"))


if __name__ == "__main__":
    unittest.main()
