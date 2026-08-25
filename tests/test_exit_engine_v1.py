import unittest
from datetime import timedelta
from unittest.mock import patch

from core.risk.exit_engine_v1 import ExitEngineV1
from core.time_utils import utc_now


class ExitEngineV1Test(unittest.TestCase):
    def test_bars_elapsed_invalid_time_returns_zero(self):
        engine = ExitEngineV1()
        self.assertEqual(engine._bars_elapsed("bad-time"), 0)

    def test_time_decay_exit_when_slow_after_bars(self):
        engine = ExitEngineV1(time_decay_bars=4, escape_velocity_pct=0.2)
        with patch.object(engine, "_bars_elapsed", return_value=4):
            result = engine.check_time_decay_exit({"pnl": 0.1, "open_time": "x"})
        self.assertTrue(result["should_exit"])
        self.assertEqual(result["reason"], "TIME_DECAY_ESCAPE_VELOCITY")

    def test_time_decay_no_exit_when_fast_enough(self):
        engine = ExitEngineV1(time_decay_bars=4, escape_velocity_pct=0.2)
        with patch.object(engine, "_bars_elapsed", return_value=4):
            self.assertIsNone(engine.check_time_decay_exit({"pnl": 0.3, "open_time": "x"}))

    def test_structural_invalidation_ignores_non_breakout(self):
        engine = ExitEngineV1()
        self.assertIsNone(engine.check_structural_invalidation_exit({}, 100.0, 1.0))

    def test_structural_invalidation_ignores_early_trade(self):
        engine = ExitEngineV1(structural_min_hold_seconds=120)
        trade = {
            "breakout_origin": True,
            "open_time": utc_now().isoformat(),
            "side": "BUY",
            "entry": 100.0,
            "entry_shock_level": 99.0,
        }
        self.assertIsNone(engine.check_structural_invalidation_exit(trade, 98.0, 1.0))

    def test_structural_invalidation_buy_breaks_below_level(self):
        engine = ExitEngineV1(structural_min_hold_seconds=0, structural_min_buffer_pct=0.05)
        trade = {
            "breakout_origin": True,
            "open_time": (utc_now() - timedelta(minutes=5)).isoformat(),
            "side": "BUY",
            "entry": 100.0,
            "entry_shock_level": 99.0,
        }
        result = engine.check_structural_invalidation_exit(trade, 98.0, 1.0)
        self.assertEqual(result["reason"], "STRUCTURAL_INVALIDATION")

    def test_structural_invalidation_sell_breaks_above_level(self):
        engine = ExitEngineV1(structural_min_hold_seconds=0, structural_min_buffer_pct=0.05)
        trade = {
            "breakout_origin": True,
            "open_time": (utc_now() - timedelta(minutes=5)).isoformat(),
            "side": "SELL",
            "entry": 100.0,
            "entry_shock_level": 101.0,
        }
        result = engine.check_structural_invalidation_exit(trade, 102.0, 1.0)
        self.assertEqual(result["reason"], "STRUCTURAL_INVALIDATION")

    def test_atr_trailing_exit_hits(self):
        engine = ExitEngineV1(trailing_activation_pct=0.9, trailing_min_distance_pct=0.3)
        trade = {"pnl": 1.0, "peak_pnl": 2.0, "entry": 100.0, "leverage": 1.0}
        result = engine.check_atr_trailing_exit(trade, current_atr=0.1)
        self.assertEqual(result["reason"], "ATR_TRAILING_HIT")

    def test_atr_trailing_no_exit_before_activation(self):
        engine = ExitEngineV1(trailing_activation_pct=0.9)
        trade = {"pnl": 0.5, "peak_pnl": 2.0, "entry": 100.0}
        self.assertIsNone(engine.check_atr_trailing_exit(trade, current_atr=1.0))

    def test_breakeven_guard_arms_and_tightens_buy(self):
        engine = ExitEngineV1(breakeven_trigger_pct=0.8, breakeven_lock_pct=0.1)
        trade = {"entry": 100.0, "pnl": 1.0, "side": "BUY", "sl": 99.0}
        result = engine.check_breakeven_guard(trade, current_atr=0.0)
        self.assertEqual(result["reason"], "BREAKEVEN_GUARD_ARMED")
        self.assertTrue(trade["exit_be_armed"])
        self.assertGreater(trade["sl"], 100.0)

    def test_breakeven_guard_arms_and_tightens_sell(self):
        engine = ExitEngineV1(breakeven_trigger_pct=0.8, breakeven_lock_pct=0.1)
        trade = {"entry": 100.0, "pnl": 1.0, "side": "SELL", "sl": 101.0}
        result = engine.check_breakeven_guard(trade, current_atr=0.0)
        self.assertEqual(result["reason"], "BREAKEVEN_GUARD_ARMED")
        self.assertLess(trade["sl"], 100.0)

    def test_breakeven_guard_no_result_when_already_armed(self):
        engine = ExitEngineV1(breakeven_trigger_pct=0.8)
        trade = {"entry": 100.0, "pnl": 1.0, "exit_be_armed": True}
        self.assertIsNone(engine.check_breakeven_guard(trade, current_atr=0.0))

    def test_flat_volatility_exit_when_price_barely_moved(self):
        engine = ExitEngineV1(flat_time_decay_bars=3, flat_time_decay_atr_mult=0.5)
        with patch.object(engine, "_bars_elapsed", return_value=3):
            result = engine.check_flat_volatility_exit(
                {"entry": 100.0, "open_time": "x"}, current_price=100.1, current_atr=1.0
            )
        self.assertEqual(result["reason"], "TIME_DECAY_FLAT_VOLATILITY")

    def test_flat_volatility_no_exit_when_atr_invalid(self):
        engine = ExitEngineV1()
        self.assertIsNone(engine.check_flat_volatility_exit({"entry": 100.0}, 100.0, 0.0))

    def test_evaluate_exit_prioritizes_structural_invalidation(self):
        engine = ExitEngineV1(structural_min_hold_seconds=0)
        trade = {
            "breakout_origin": True,
            "open_time": (utc_now() - timedelta(minutes=5)).isoformat(),
            "side": "BUY",
            "entry": 100.0,
            "entry_shock_level": 99.0,
        }
        result = engine.evaluate_exit(trade, current_price=98.0, current_atr=1.0)
        self.assertEqual(result["reason"], "STRUCTURAL_INVALIDATION")

    def test_evaluate_exit_returns_hold(self):
        engine = ExitEngineV1()
        with patch.object(engine, "_bars_elapsed", return_value=0):
            result = engine.evaluate_exit({"entry": 100.0, "pnl": 0.0}, 100.0, 1.0)
        self.assertEqual(result, {"should_exit": False, "reason": "HOLD", "meta": {}})


if __name__ == "__main__":
    unittest.main()
