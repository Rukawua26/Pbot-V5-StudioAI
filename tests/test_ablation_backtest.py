import unittest
from unittest.mock import patch

from core.backtester import VectorBacktestResult
from tools.ablation_backtest import run_ablation_backtest
from tools.walk_forward_backtest import BacktestParams


class AblationBacktestTests(unittest.TestCase):
    def test_run_ablation_backtest_adds_deltas_vs_baseline(self):
        params = BacktestParams(0.85, 6.0, 1.6, 8, 25.0, 1.2, 2.0)
        fake_results = {
            "equal_weight": VectorBacktestResult(
                objective=1.0,
                profit_factor=1.1,
                max_drawdown=0.2,
                net_return_pct=5.0,
                trades=10,
                gross_profit=1.0,
                gross_loss=0.9,
            ),
            "mt_sr_regime": VectorBacktestResult(
                objective=1.5,
                profit_factor=1.3,
                max_drawdown=0.15,
                net_return_pct=8.0,
                trades=12,
                gross_profit=1.5,
                gross_loss=0.8,
            ),
        }

        class FakeBacktester:
            def __init__(self, candles):
                self.candles = candles

            def evaluate(self, **kwargs):
                return fake_results[kwargs["strategy_mode"]]

        with patch("tools.ablation_backtest.VectorBacktester", FakeBacktester):
            report = run_ablation_backtest(
                candles="dummy",
                params=params,
                modes=("mt_sr_regime", "equal_weight"),
                baseline_mode="equal_weight",
                candidate_mode="mt_sr_regime",
            )

        self.assertEqual(report["baseline_mode"], "equal_weight")
        self.assertEqual(report["candidate"]["mode"], "mt_sr_regime")
        self.assertAlmostEqual(report["candidate"]["delta_vs_baseline"]["objective"], 0.5)


if __name__ == "__main__":
    unittest.main()
