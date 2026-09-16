import unittest
import numpy as np
import pandas as pd

from core.strategy.triple_tf.bias_1h import evaluate_bias_1h
from core.strategy.triple_tf.structure_5m import evaluate_structure_5m
from core.strategy.triple_tf.trigger_1m import evaluate_trigger_1m
from core.strategy.triple_tf.trailing_1m import evaluate_trailing_1m
from core.strategy.triple_tf.engine import TripleTFEngine


def generate_mock_ohlcv(n: int, base_price: float, trend: float = 0.0) -> pd.DataFrame:
    np.random.seed(42)
    prices = [base_price]
    for i in range(1, n):
        prices.append(prices[-1] * (1.0 + trend + np.random.normal(0, 0.001)))

    opens = [p * 0.9995 if trend >= 0 else p * 1.0005 for p in prices]
    closes = [p * 1.0005 if trend >= 0 else p * 0.9995 for p in prices]
    highs = [max(o, c) * 1.001 for o, c in zip(opens, closes)]
    lows = [min(o, c) * 0.999 for o, c in zip(opens, closes)]

    df = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000.0 + np.random.uniform(0, 500) for _ in prices],
        }
    )
    return df


class TestTripleTFStrategy(unittest.TestCase):
    def test_bias_1h_bullish(self):
        # 1H uptrend: closes clearly above EMA 50
        df_1h = generate_mock_ohlcv(60, 100.0, trend=0.005)
        res = evaluate_bias_1h(df_1h)
        self.assertEqual(res.bias, "BUY")
        self.assertGreater(res.ema50, 0.0)

    def test_bias_1h_bearish(self):
        # 1H downtrend: closes clearly below EMA 50
        df_1h = generate_mock_ohlcv(60, 100.0, trend=-0.005)
        res = evaluate_bias_1h(df_1h)
        self.assertEqual(res.bias, "SELL")
        self.assertGreater(res.ema50, 0.0)

    def test_structure_5m_short_mss_and_pullback(self):
        # Generate 5M data with downtrend breakdown and pullback to EMA
        df_5m = generate_mock_ohlcv(60, 100.0, trend=-0.002)
        # Force a pullback touch in the last candle to EMA
        ema = df_5m["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        df_5m.loc[df_5m.index[-1], "high"] = ema * 1.001
        df_5m.loc[df_5m.index[-1], "low"] = ema * 0.998

        res = evaluate_structure_5m(df_5m, bias_1h="SELL")
        self.assertTrue(res.mss_confirmed)
        self.assertTrue(res.pullback_touched)
        self.assertTrue(res.valid_setup)
        self.assertGreater(res.suggested_sl, 0.0)

    def test_trigger_1m_short(self):
        df_1m = generate_mock_ohlcv(60, 100.0, trend=-0.001)
        # Compute EMA 50 from current closes to calibrate placement
        ema_series = df_1m["close"].ewm(span=50, adjust=False).mean()
        prev_ema_approx = float(ema_series.iloc[-2])
        current_ema_approx = float(ema_series.iloc[-1])
        # Force a genuine cross: prev_close clearly above prev_ema, current_close below current_ema
        df_1m.loc[df_1m.index[-2], "close"] = prev_ema_approx * 1.003
        df_1m.loc[df_1m.index[-1], "close"] = current_ema_approx * 0.997

        res = evaluate_trigger_1m(df_1m, bias_1h="SELL", setup_5m_valid=True)
        self.assertTrue(res.triggered)
        self.assertEqual(res.side, "SELL")

    def test_trailing_1m_exit(self):
        df_1m = generate_mock_ohlcv(60, 100.0, trend=-0.001)
        ema = df_1m["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        # Short position entered at 105, current price 98 (profitable >= 1R)
        # Now 1M close crosses above EMA 50
        df_1m.loc[df_1m.index[-1], "close"] = ema * 1.002

        res = evaluate_trailing_1m(
            df_1m=df_1m,
            side="SELL",
            entry_price=105.0,
            sl_price=107.0,
            current_price=98.0,
            activation_r=1.0,
        )
        self.assertTrue(res.should_exit)
        self.assertEqual(res.reason, "TRAILING_1M_EMA50_CLOSE_ABOVE")

    def test_engine_orchestrator(self):
        df_1h = generate_mock_ohlcv(60, 100.0, trend=0.003)
        df_5m = generate_mock_ohlcv(60, 100.0, trend=0.001)
        df_1m = generate_mock_ohlcv(60, 100.0, trend=0.001)

        result = TripleTFEngine.analyze(
            df_1h=df_1h, df_5m=df_5m, df_1m=df_1m, symbol="BTC/USDT"
        )
        self.assertIn("signal", result)
        self.assertIn("confidence", result)
        self.assertIn("bias_1h", result)
        self.assertIn("setup_5m_valid", result)

    def test_trigger_1m_buy(self):
        df_1m = generate_mock_ohlcv(60, 100.0, trend=0.001)
        ema_series = df_1m["close"].ewm(span=50, adjust=False).mean()
        prev_ema_approx = float(ema_series.iloc[-2])
        current_ema_approx = float(ema_series.iloc[-1])
        # Force cross: prev_close below prev_ema, current_close above current_ema
        df_1m.loc[df_1m.index[-2], "close"] = prev_ema_approx * 0.997
        df_1m.loc[df_1m.index[-1], "close"] = current_ema_approx * 1.003

        res = evaluate_trigger_1m(df_1m, bias_1h="BUY", setup_5m_valid=True)
        self.assertTrue(res.triggered)
        self.assertEqual(res.side, "BUY")

    def test_filters_ttf_bypass(self):
        from unittest.mock import MagicMock
        from core.signals.filters import _apply_entry_filters_and_adjust_prob

        bot = MagicMock()
        bot._get_market_regime.return_value = "RANGE"
        ctx = {"ttf_metrics": {"bias_1h": {"bias": "BUY"}}, "rsi": 80.0, "adx": 10.0}
        df_mock = generate_mock_ohlcv(20, 100.0)
        prob, passed, reason, updated_ctx = _apply_entry_filters_and_adjust_prob(
            bot=bot,
            symbol="BTC/USDT",
            symbol_raw="BTCUSDT",
            df_main=df_mock,
            audit_signal="BUY",
            prob_final=85.0,
            ctx=ctx,
            vol_rel=1.0,
        )
        self.assertTrue(passed)
        self.assertEqual(reason, "TTF_PASSED")
        self.assertEqual(prob, 85.0)


if __name__ == "__main__":
    unittest.main()
