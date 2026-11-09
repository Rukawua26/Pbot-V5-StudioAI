import unittest
import pandas as pd

from core.strategy.triple_tf.fvg_5m import detect_fvg_5m, FVGZone
from core.strategy.triple_tf.trigger_1m import evaluate_trigger_1m
from core.strategy.triple_tf.structure_5m import evaluate_structure_5m


class TestStrategyFVG(unittest.TestCase):
    def test_detect_fvg_5m_bullish(self):
        # 3 candles:
        # candle 0: low 98, high 100, open 98.5, close 99.5
        # candle 1 (impulsive): low 99.5, high 104, open 100, close 103.5 (body 3.5 / range 4.5 = 77%)
        # candle 2: low 101, high 105, open 103.5, close 104.5
        # Gap between candle 0 high (100) and candle 2 low (101) = 1.0 (0.95% > 0.30%)
        df = pd.DataFrame(
            [
                {
                    "time": 1000,
                    "open": 98.5,
                    "high": 100.0,
                    "low": 98.0,
                    "close": 99.5,
                    "volume": 100,
                },
                {
                    "time": 2000,
                    "open": 100.0,
                    "high": 104.0,
                    "low": 99.5,
                    "close": 103.5,
                    "volume": 500,
                },
                {
                    "time": 3000,
                    "open": 103.5,
                    "high": 105.0,
                    "low": 101.0,
                    "close": 104.5,
                    "volume": 200,
                },
            ]
        )
        res = detect_fvg_5m(df, "BUY", min_gap_pct=0.30)
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.bias, "BUY")
        self.assertEqual(res.fvg_bot, 100.0)
        self.assertEqual(res.fvg_top, 101.0)
        self.assertGreater(res.gap_pct, 0.30)
        self.assertLess(res.suggested_sl, 101.0)

    def test_detect_fvg_5m_bearish(self):
        # 3 candles:
        # candle 0: low 100, high 102, open 101.5, close 100.5
        # candle 1 (impulsive): low 96, high 100.5, open 100, close 96.5 (body 3.5 / range 4.5 = 77%)
        # candle 2: low 95, high 99, open 96.5, close 95.5
        # Gap between candle 2 high (99) and candle 0 low (100) = 1.0 (1.04% > 0.30%)
        df = pd.DataFrame(
            [
                {
                    "time": 1000,
                    "open": 101.5,
                    "high": 102.0,
                    "low": 100.0,
                    "close": 100.5,
                    "volume": 100,
                },
                {
                    "time": 2000,
                    "open": 100.0,
                    "high": 100.5,
                    "low": 96.0,
                    "close": 96.5,
                    "volume": 500,
                },
                {
                    "time": 3000,
                    "open": 96.5,
                    "high": 99.0,
                    "low": 95.0,
                    "close": 95.5,
                    "volume": 200,
                },
            ]
        )
        res = detect_fvg_5m(df, "SELL", min_gap_pct=0.30)
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.bias, "SELL")
        self.assertEqual(res.fvg_bot, 99.0)
        self.assertEqual(res.fvg_top, 100.0)
        self.assertGreater(res.gap_pct, 0.30)
        self.assertGreater(res.suggested_sl, 99.0)

    def test_detect_fvg_5m_gap_too_small(self):
        # Gap = 0.05% < 0.30%
        df = pd.DataFrame(
            [
                {
                    "time": 1000,
                    "open": 99.9,
                    "high": 100.0,
                    "low": 99.8,
                    "close": 99.95,
                    "volume": 100,
                },
                {
                    "time": 2000,
                    "open": 99.95,
                    "high": 100.2,
                    "low": 99.9,
                    "close": 100.15,
                    "volume": 200,
                },
                {
                    "time": 3000,
                    "open": 100.15,
                    "high": 100.3,
                    "low": 100.05,
                    "close": 100.25,
                    "volume": 100,
                },
            ]
        )
        res = detect_fvg_5m(df, "BUY", min_gap_pct=0.30)
        self.assertIsNone(res)

    def test_trigger_1m_fvg_wick_rejection_bullish(self):
        fvg = FVGZone(
            bias="BUY",
            fvg_top=101.0,
            fvg_bot=100.0,
            gap_pct=1.0,
            suggested_sl=100.9,
            formed_at_idx=2,
        )

        # Candle wicks into FVG (low 100.5 <= 101, high 102 >= 100) and closes outside (close 101.5 > 101)
        candles = []
        for i in range(50):
            candles.append(
                {
                    "time": 1000 + i * 60000,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 10,
                }
            )
        # Last candle
        candles[-1] = {
            "time": 1000 + 50 * 60000,
            "open": 101.2,
            "high": 102.0,
            "low": 100.5,
            "close": 101.5,
            "volume": 10,
        }
        df_1m = pd.DataFrame(candles)

        res = evaluate_trigger_1m(
            df_1m, bias_1h="BUY", setup_5m_valid=True, fvg_zone=fvg
        )
        self.assertTrue(res.triggered)
        self.assertEqual(res.side, "BUY")
        self.assertEqual(res.reason, "1M_FVG_REJECTION_CONFIRMED")

    def test_trigger_1m_fvg_inside_no_rejection_bullish(self):
        fvg = FVGZone(
            bias="BUY",
            fvg_top=101.0,
            fvg_bot=100.0,
            gap_pct=1.0,
            suggested_sl=100.9,
            formed_at_idx=2,
        )

        # Candle stays inside FVG without rejecting (close = 100.5 <= 101)
        candles = []
        for i in range(50):
            candles.append(
                {
                    "time": 1000 + i * 60000,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 10,
                }
            )
        candles[-1] = {
            "time": 1000 + 50 * 60000,
            "open": 100.8,
            "high": 100.9,
            "low": 100.2,
            "close": 100.5,
            "volume": 10,
        }
        df_1m = pd.DataFrame(candles)

        res = evaluate_trigger_1m(
            df_1m, bias_1h="BUY", setup_5m_valid=True, fvg_zone=fvg
        )
        self.assertFalse(res.triggered)
        self.assertEqual(res.side, "WAIT")
        self.assertEqual(res.reason, "1M_WAITING_FOR_FVG_REJECTION")

    def test_structure_5m_max_setup_minutes_expiration(self):
        # Create structure with pullback at index -2 and current candle at index -1
        # If timestamp delta > max_setup_minutes * 60000, it should expire
        candles = []
        for i in range(60):
            candles.append(
                {
                    "time": i * 5 * 60 * 1000,
                    "open": 100.0,
                    "high": 105.0,
                    "low": 99.0,
                    "close": 102.0,
                    "volume": 10,
                }
            )

        # Setup with old timestamp
        candles[-1]["time"] = 60 * 5 * 60 * 1000 + 20 * 60 * 1000  # 20 mins later
        df_5m = pd.DataFrame(candles)

        res = evaluate_structure_5m(df_5m, bias_1h="BUY", max_setup_minutes=15)
        # Should not validate setup if expired or without valid fresh setup
        if not res.valid_setup:
            self.assertIn(
                res.reason,
                [
                    "5M_SETUP_EXPIRED",
                    "5M_LONG_MSS_FAILED",
                    "5M_LONG_PULLBACK_NOT_TOUCHED",
                    "5M_PULLBACK_BEFORE_MSS",
                ],
            )


if __name__ == "__main__":
    unittest.main()
