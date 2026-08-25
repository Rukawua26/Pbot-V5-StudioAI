import unittest

from tools.real_readiness_check import (
    evaluate_config_readiness,
    evaluate_walk_forward_report,
)


class RealReadinessCheckTest(unittest.TestCase):
    def test_rejects_real_without_explicit_guardrails(self):
        failures = evaluate_config_readiness(
            {
                "PAPER_MODE": False,
                "ALLOW_REAL_TRADING": False,
                "USE_TESTNET": False,
                "BINANCE_API_KEY": "k",
                "BINANCE_API_SECRET": "s",
                "TELEGRAM_TOKEN": "t",
                "TELEGRAM_CHAT_ID": "c",
                "MAX_OPEN_TRADES": 1,
                "MAX_RISK_USD": 5,
                "RISK_PER_TRADE_PERCENT": 0.25,
            }
        )

        self.assertIn("ALLOW_REAL_TRADING=true is required", failures)

    def test_accepts_conservative_real_config(self):
        failures = evaluate_config_readiness(
            {
                "PAPER_MODE": False,
                "ALLOW_REAL_TRADING": True,
                "USE_TESTNET": False,
                "BINANCE_API_KEY": "k",
                "BINANCE_API_SECRET": "s",
                "TELEGRAM_TOKEN": "t",
                "TELEGRAM_CHAT_ID": "c",
                "MAX_OPEN_TRADES": 1,
                "MAX_RISK_USD": 5,
                "RISK_PER_TRADE_PERCENT": 0.25,
            }
        )

        self.assertEqual(failures, [])

    def test_rejects_weak_walk_forward_report(self):
        failures = evaluate_walk_forward_report(
            {
                "summary": {
                    "windows": 2,
                    "positive_validation_windows": 0,
                    "avg_validation_profit_factor": 0.9,
                    "max_validation_drawdown": 0.35,
                    "total_validation_trades": 0,
                }
            },
            min_profit_factor=1.2,
            max_drawdown=0.2,
        )

        self.assertGreaterEqual(len(failures), 3)


if __name__ == "__main__":
    unittest.main()
