import unittest

from tools.promotion_gate import (
    evaluate_fidelity,
    evaluate_promotion_gate,
    evaluate_risk_decision_summary,
    evaluate_strategy_report_doc,
)


class PromotionGateTests(unittest.TestCase):
    def test_evaluate_risk_decision_summary_passes_when_within_thresholds(self):
        failures = evaluate_risk_decision_summary(
            {
                "actions": {"BLOCK": 2, "HALT": 0, "QUARANTINE": 1},
                "risk_decision_per_intent": 1.2,
            },
            max_halt_actions=0,
            max_quarantine_actions=3,
            max_risk_decision_per_intent=2.0,
        )
        self.assertEqual(failures, [])

    def test_evaluate_risk_decision_summary_fails_when_thresholds_exceeded(self):
        failures = evaluate_risk_decision_summary(
            {
                "actions": {"HALT": 1, "QUARANTINE": 5},
                "risk_decision_per_intent": 3.1,
            },
            max_halt_actions=0,
            max_quarantine_actions=3,
            max_risk_decision_per_intent=2.0,
        )
        self.assertEqual(len(failures), 3)

    def test_evaluate_strategy_report_doc_uses_embedded_verdict(self):
        failures = evaluate_strategy_report_doc(
            {
                "verdict": {
                    "passed": False,
                    "failures": ["walk_forward weak", "regime range negative"],
                }
            },
            require_strategy_report=True,
        )
        self.assertIn("strategy validation verdict failed", failures)
        self.assertIn("strategy: walk_forward weak", failures)

    def test_evaluate_fidelity_passes_with_sufficient_data(self):
        failures = evaluate_fidelity(
            {"fidelity": {"summary": {"weighted_fidelity_score": 0.95, "total_samples": 50}}},
            min_fidelity_score=0.80,
            min_fidelity_samples=20,
        )
        self.assertEqual(failures, [])

    def test_evaluate_fidelity_fails_when_below_thresholds(self):
        failures = evaluate_fidelity(
            {"fidelity": {"summary": {"weighted_fidelity_score": 0.75, "total_samples": 10}}},
            min_fidelity_score=0.80,
            min_fidelity_samples=20,
        )
        self.assertEqual(len(failures), 2)
        self.assertIn("fidelity.total_samples 10 < 20", failures)
        self.assertIn("fidelity.weighted_fidelity_score 0.7500 < 0.8000", failures)

    def test_evaluate_strategy_report_doc_reports_missing_fidelity_when_required(self):
        failures = evaluate_strategy_report_doc(
            {"verdict": {"passed": True, "failures": []}},
            require_strategy_report=True,
            require_fidelity_report=True,
        )
        self.assertIn("fidelity report missing or invalid in strategy report", failures)

    def test_evaluate_strategy_report_doc_reports_fidelity_failures_when_required(self):
        failures = evaluate_strategy_report_doc(
            {
                "verdict": {"passed": True, "failures": []},
                "fidelity": {"summary": {"weighted_fidelity_score": 0.70, "total_samples": 5}},
            },
            require_strategy_report=True,
            require_fidelity_report=True,
            min_fidelity_score=0.80,
            min_fidelity_samples=20,
        )
        self.assertEqual(len(failures), 2)
        self.assertIn("fidelity.total_samples 5 < 20", failures)
        self.assertIn("fidelity.weighted_fidelity_score 0.7000 < 0.8000", failures)

    def test_evaluate_strategy_report_doc_skips_fidelity_when_not_required(self):
        failures = evaluate_strategy_report_doc(
            {"verdict": {"passed": True, "failures": []}},
            require_strategy_report=True,
        )
        self.assertEqual(failures, [])

    def test_evaluate_promotion_gate_aggregates_all_failure_sources(self):
        verdict = evaluate_promotion_gate(
            shadow_failures=["too few fills"],
            risk_failures=["too many halts"],
            strategy_failures=["strategy weak"],
            real_failures=["config invalid"],
        )
        self.assertFalse(verdict["passed"])
        self.assertEqual(len(verdict["failures"]), 4)
        self.assertIn("shadow: too few fills", verdict["failures"])


if __name__ == "__main__":
    unittest.main()
