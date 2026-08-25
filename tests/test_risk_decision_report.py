import unittest

from tools.risk_decision_report import summarize_risk_decisions


class RiskDecisionReportTests(unittest.TestCase):
    def test_summarize_risk_decisions_counts_actions_reasons_and_rates(self):
        rows = [
            {"event": "ORDER_INTENT_CREATED", "payload": {"symbol": "BTC/USDT"}},
            {"event": "ORDER_INTENT_CREATED", "payload": {"symbol": "ETH/USDT"}},
            {"event": "ORDER_FILLED", "payload": {"symbol": "BTC/USDT"}},
            {
                "event": "RISK_DECISION",
                "payload": {
                    "action": "BLOCK",
                    "reason": "GLOBAL_COOLDOWN",
                    "source": "runtime_entry_guard",
                    "symbol": "BTC/USDT",
                },
            },
            {
                "event": "RISK_DECISION",
                "payload": {
                    "action": "HALT",
                    "reason": "DAILY_DRAWDOWN_LIMIT_REACHED",
                    "source": "daily_drawdown_breaker",
                    "symbol": "UNKNOWN",
                },
            },
        ]

        summary = summarize_risk_decisions(rows)

        self.assertEqual(summary["total_risk_decisions"], 2)
        self.assertEqual(summary["actions"]["BLOCK"], 1)
        self.assertEqual(summary["actions"]["HALT"], 1)
        self.assertEqual(summary["reasons"]["GLOBAL_COOLDOWN"], 1)
        self.assertEqual(summary["sources"]["runtime_entry_guard"], 1)
        self.assertEqual(summary["symbols"]["BTC/USDT"], 1)
        self.assertEqual(summary["order_intents"], 2)
        self.assertEqual(summary["order_filled"], 1)
        self.assertAlmostEqual(summary["risk_decision_per_intent"], 1.0)

    def test_summarize_risk_decisions_handles_missing_payload_fields(self):
        rows = [{"event": "RISK_DECISION", "payload": {}}]

        summary = summarize_risk_decisions(rows)

        self.assertEqual(summary["actions"]["UNKNOWN"], 1)
        self.assertEqual(summary["reasons"]["UNKNOWN"], 1)
        self.assertEqual(summary["sources"]["UNKNOWN"], 1)
        self.assertEqual(summary["symbols"]["UNKNOWN"], 1)


if __name__ == "__main__":
    unittest.main()
