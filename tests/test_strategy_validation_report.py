import unittest

from tools.strategy_validation_report import evaluate_strategy_report


class StrategyValidationReportTests(unittest.TestCase):
    def test_evaluate_strategy_report_passes_with_strong_inputs(self):
        verdict = evaluate_strategy_report(
            walk_forward={
                "summary": {
                    "windows": 4,
                    "positive_validation_windows": 3,
                    "avg_validation_profit_factor": 1.35,
                    "max_validation_drawdown": 0.12,
                    "total_validation_trades": 40,
                }
            },
            ablation={
                "candidate": {
                    "delta_vs_baseline": {
                        "profit_factor": 0.10,
                        "net_return_pct": 3.0,
                    }
                }
            },
            regime_rows=[
                {"regime": "BULL_TREND", "trades": 20, "expectancy_pct": 0.2},
                {"regime": "RANGE", "trades": 12, "expectancy_pct": 0.1},
            ],
            min_profit_factor=1.2,
            max_drawdown=0.20,
            min_positive_windows_ratio=0.5,
            min_candidate_delta_pf=0.0,
            min_candidate_delta_return_pct=0.0,
            min_regime_trades=10,
            min_regime_expectancy_pct=0.0,
        )

        self.assertTrue(verdict["passed"])
        self.assertEqual(verdict["failures"], [])

    def test_evaluate_strategy_report_fails_on_weak_inputs(self):
        verdict = evaluate_strategy_report(
            walk_forward={
                "summary": {
                    "windows": 2,
                    "positive_validation_windows": 0,
                    "avg_validation_profit_factor": 0.9,
                    "max_validation_drawdown": 0.30,
                    "total_validation_trades": 0,
                }
            },
            ablation={
                "candidate": {
                    "delta_vs_baseline": {
                        "profit_factor": -0.2,
                        "net_return_pct": -4.0,
                    }
                }
            },
            regime_rows=[
                {"regime": "BULL_TREND", "trades": 12, "expectancy_pct": -0.1},
            ],
            min_profit_factor=1.2,
            max_drawdown=0.20,
            min_positive_windows_ratio=0.5,
            min_candidate_delta_pf=0.0,
            min_candidate_delta_return_pct=0.0,
            min_regime_trades=10,
            min_regime_expectancy_pct=0.0,
        )

        self.assertFalse(verdict["passed"])
        self.assertGreaterEqual(len(verdict["failures"]), 5)

    def test_evaluate_strategy_report_includes_fidelity_gate_when_provided(self):
        verdict = evaluate_strategy_report(
            walk_forward={
                "summary": {
                    "windows": 4,
                    "positive_validation_windows": 3,
                    "avg_validation_profit_factor": 1.35,
                    "max_validation_drawdown": 0.12,
                    "total_validation_trades": 40,
                }
            },
            ablation={
                "candidate": {
                    "delta_vs_baseline": {
                        "profit_factor": 0.10,
                        "net_return_pct": 3.0,
                    }
                }
            },
            regime_rows=[{"regime": "RANGE", "trades": 12, "expectancy_pct": 0.1}],
            fidelity={"summary": {"weighted_fidelity_score": 0.75, "total_samples": 10}},
            min_profit_factor=1.2,
            max_drawdown=0.20,
            min_positive_windows_ratio=0.5,
            min_candidate_delta_pf=0.0,
            min_candidate_delta_return_pct=0.0,
            min_regime_trades=10,
            min_regime_expectancy_pct=0.0,
            min_fidelity_score=0.80,
            min_fidelity_samples=20,
        )

        self.assertFalse(verdict["passed"])
        self.assertIn("fidelity.total_samples 10 < 20", verdict["failures"])
        self.assertIn(
            "fidelity.weighted_fidelity_score 0.7500 < 0.8000",
            verdict["failures"],
        )


if __name__ == "__main__":
    unittest.main()
