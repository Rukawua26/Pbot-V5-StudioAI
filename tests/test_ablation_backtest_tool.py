import unittest

from tests.test_walk_forward_backtest_tool import _synthetic_candles
from tools.ablation_backtest import run_ablation_backtest
from tools.walk_forward_backtest import BacktestParams


class AblationBacktestToolTest(unittest.TestCase):
    def test_ablation_returns_baseline_and_ranked_rows(self):
        params = BacktestParams(
            alma_offset=0.85,
            alma_sigma=6.0,
            z_score_threshold=1.6,
            entropy_bins=8,
            adx_threshold=25.0,
            stop_loss_pct=1.2,
            take_profit_pct=2.0,
        )

        report = run_ablation_backtest(_synthetic_candles(), params)

        self.assertEqual(report["baseline_mode"], "mt_sr_regime")
        self.assertEqual(len(report["rows"]), 4)
        self.assertIn("profit_factor", report["baseline"])
        self.assertGreaterEqual(report["rows"][0]["objective"], report["rows"][-1]["objective"])

    def test_backtester_rejects_unknown_strategy_mode(self):
        params = BacktestParams(
            alma_offset=0.85,
            alma_sigma=6.0,
            z_score_threshold=1.6,
            entropy_bins=8,
            adx_threshold=25.0,
            stop_loss_pct=1.2,
            take_profit_pct=2.0,
        )

        with self.assertRaises(ValueError):
            run_ablation_backtest(_synthetic_candles(), params, modes=("unknown",))


if __name__ == "__main__":
    unittest.main()
