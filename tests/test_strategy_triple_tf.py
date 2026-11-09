import unittest
import numpy as np
import pandas as pd

from core.strategy.triple_tf.bias_1h import evaluate_bias_1h
from core.strategy.triple_tf.structure_5m import evaluate_structure_5m
from core.strategy.triple_tf.trigger_1m import evaluate_trigger_1m
from core.strategy.triple_tf.trailing_1m import evaluate_trailing_1m
from core.strategy.triple_tf.engine import TripleTFEngine


import time


def generate_mock_ohlcv(n: int, base_price: float, trend: float = 0.0) -> pd.DataFrame:
    np.random.seed(42)
    prices = [base_price]
    for i in range(1, n):
        prices.append(prices[-1] * (1.0 + trend + np.random.normal(0, 0.001)))

    opens = [p * 0.9995 if trend >= 0 else p * 1.0005 for p in prices]
    closes = [p * 1.0005 if trend >= 0 else p * 0.9995 for p in prices]
    highs = [max(o, c) * 1.001 for o, c in zip(opens, closes)]
    lows = [min(o, c) * 0.999 for o, c in zip(opens, closes)]

    now_ms = int(time.time() * 1000)
    times = [now_ms - ((n - i) * 60000) for i in range(n)]

    df = pd.DataFrame(
        {
            "time": times,
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
        # Generate 5M data with range around 100
        df_5m = generate_mock_ohlcv(60, 100.0, trend=0.0)
        ema = float(df_5m["close"].ewm(span=50, adjust=False).mean().iloc[-1])

        # Ensure prior low is clearly defined
        df_5m.loc[df_5m.index[-15:-5], "low"] = 99.0
        # Ensure candles before MSS are above prior low and below EMA touch
        df_5m.loc[df_5m.index[-5:-3], "close"] = 99.5
        df_5m.loc[df_5m.index[-5:-3], "high"] = ema * 0.99
        df_5m.loc[df_5m.index[-5:-3], "low"] = 99.2
        # Force MSS on index -3 (close breaks below 99.0)
        df_5m.loc[df_5m.index[-3], "close"] = 97.0
        df_5m.loc[df_5m.index[-3], "high"] = 98.0
        df_5m.loc[df_5m.index[-3], "low"] = 96.5
        # Force pullback later on index -1 (high touches EMA)
        df_5m.loc[df_5m.index[-1], "high"] = ema * 1.001
        df_5m.loc[df_5m.index[-1], "low"] = ema * 0.998
        df_5m.loc[df_5m.index[-1], "close"] = ema * 0.999

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
        # Contrato T1: el bypass TTF exige signal_close_time (identidad por vela
        # 1M cerrada) y gate REAL; en PAPER sigue pasando con TTF_PASSED.
        from unittest.mock import MagicMock, patch
        from config import Config
        from core.signals.filters import _apply_entry_filters_and_adjust_prob

        bot = MagicMock()
        bot._get_market_regime.return_value = "RANGE"
        bot._ttf_last_signal_keys = {}
        ctx = {
            "ttf_metrics": {"bias_1h": {"bias": "BUY"}},
            "rsi": 80.0,
            "adx": 10.0,
            "signal_close_time": 1_770_030_400_000,
        }
        df_mock = generate_mock_ohlcv(20, 100.0)
        with patch.object(Config, "PAPER_MODE", True):
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
