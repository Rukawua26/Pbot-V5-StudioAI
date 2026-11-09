"""Guardrails T1 (Bloque 1): velas cerradas, gate REAL TTF y dedup por vela 1M."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from config import Config
from core.signals.filters import _apply_entry_filters_and_adjust_prob
from core.strategy.triple_tf.closed_candles import closed_candles, last_close_ms
from tools.strategy import Strategy

# Ancla fija de tiempo para los tests de helper (2026-02-02T12:00:00Z)
BASE_MS = 1_770_030_400_000

_MISSING = object()


def _candles(n: int, duration_ms: int, last_open_ms: int = BASE_MS) -> pd.DataFrame:
    opens = [last_open_ms - (n - 1 - i) * duration_ms for i in range(n)]
    return pd.DataFrame(
        {
            "time": opens,
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.5] * n,
            "volume": [1000.0] * n,
        }
    )


def _mock_ohlcv(n: int, trend: float = 0.0) -> pd.DataFrame:
    """Mismo generador sembrado que los tests TTF existentes (seed 42)."""
    np.random.seed(42)
    prices = [100.0]
    for _ in range(1, n):
        prices.append(prices[-1] * (1.0 + trend + np.random.normal(0, 0.001)))

    opens = [p * 0.9995 if trend >= 0 else p * 1.0005 for p in prices]
    closes = [p * 1.0005 if trend >= 0 else p * 0.9995 for p in prices]
    highs = [max(o, c) * 1.001 for o, c in zip(opens, closes)]
    lows = [min(o, c) * 0.999 for o, c in zip(opens, closes)]

    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000.0 + np.random.uniform(0, 500) for _ in range(len(prices))],
        }
    )


class TestClosedCandles(unittest.TestCase):
    def test_open_candle_excluded(self):
        # Evaluamos en mitad de la última vela: esa vela sigue abierta
        df = _candles(3, 60_000)
        out = closed_candles(df, "1m", evaluation_time=BASE_MS + 30_000)
        self.assertEqual(len(out), 2)
        self.assertEqual(int(out["time"].iloc[-1]), BASE_MS - 60_000)

    def test_boundary_exact_counts_as_closed(self):
        # open + duracion == evaluation_time cuenta como cerrada
        df = _candles(3, 60_000)
        out = closed_candles(df, "1m", evaluation_time=BASE_MS + 60_000)
        self.assertEqual(len(out), 3)
        self.assertEqual(int(out["time"].iloc[-1]), BASE_MS)

    def test_int_microseconds_supported(self):
        df = _candles(2, 60_000)
        df["time"] = df["time"] * 1000  # microsegundos
        out = closed_candles(df, "1m", evaluation_time=BASE_MS + 60_000)
        self.assertEqual(len(out), 2)
        self.assertEqual(int(out["time"].iloc[-1]), BASE_MS * 1000)

    def test_datetime_tz_aware(self):
        base = datetime.fromtimestamp(BASE_MS / 1000, tz=timezone.utc)
        df = _candles(2, 60_000)
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        out = closed_candles(df, "1m", evaluation_time=base)
        # en el instante exacto de apertura de la última: solo la anterior cerró
        self.assertEqual(len(out), 1)
        out_all = closed_candles(
            df, "1m", evaluation_time=base + pd.Timedelta(minutes=1)
        )
        self.assertEqual(len(out_all), 2)

    def test_datetime_naive_assumed_utc(self):
        base = datetime.fromtimestamp(BASE_MS / 1000, tz=timezone.utc)
        df = _candles(2, 60_000)
        df["time"] = pd.to_datetime(df["time"], unit="ms").dt.tz_localize(None)
        eval_naive = (base + pd.Timedelta(minutes=1)).replace(tzinfo=None)
        out = closed_candles(df, "1m", evaluation_time=eval_naive)
        self.assertEqual(len(out), 2)

    def test_missing_time_column_returns_empty(self):
        df = _candles(3, 60_000).drop(columns=["time"])
        out = closed_candles(df, "1m", evaluation_time=BASE_MS + 60_000)
        self.assertTrue(out.empty)

    def test_unreadable_time_returns_empty(self):
        df = _candles(3, 60_000)
        df["time"] = df["time"].astype(object)
        df.loc[1, "time"] = "no-es-un-timestamp"
        out = closed_candles(df, "1m", evaluation_time=BASE_MS + 60_000)
        self.assertTrue(out.empty)

    def test_none_time_returns_empty(self):
        df = _candles(3, 60_000)
        df["time"] = df["time"].astype(object)
        df.loc[0, "time"] = None
        out = closed_candles(df, "1m", evaluation_time=BASE_MS + 60_000)
        self.assertTrue(out.empty)

    def test_timeframes_1m_5m_1h(self):
        for timeframe, duration_ms in (
            ("1m", 60_000),
            ("5m", 300_000),
            ("1h", 3_600_000),
        ):
            with self.subTest(timeframe=timeframe):
                df = _candles(2, duration_ms)
                # falta 1ms para el cierre de la última: sigue abierta
                almost = closed_candles(
                    df, timeframe, evaluation_time=BASE_MS + duration_ms - 1
                )
                self.assertEqual(len(almost), 1)
                # cierre exacto: ambas cerradas
                exact = closed_candles(
                    df, timeframe, evaluation_time=BASE_MS + duration_ms
                )
                self.assertEqual(len(exact), 2)

    def test_unknown_timeframe_returns_empty(self):
        df = _candles(3, 60_000)
        out = closed_candles(df, "7m", evaluation_time=BASE_MS + 60_000)
        self.assertTrue(out.empty)

    def test_default_evaluation_time_is_now(self):
        # velas de hace 10 días: todas cerradas con el default (ahora UTC)
        old_ms = BASE_MS - 10 * 24 * 3_600_000
        df = _candles(3, 60_000, last_open_ms=old_ms)
        out = closed_candles(df, "1m")
        self.assertEqual(len(out), 3)

    def test_none_df_returns_empty(self):
        self.assertTrue(closed_candles(None, "1m").empty)


class TestLastCloseMs(unittest.TestCase):
    def test_returns_open_plus_duration(self):
        df = _candles(3, 60_000)
        self.assertEqual(last_close_ms(df, "1m"), BASE_MS + 60_000)

    def test_none_when_no_time_column(self):
        df = _candles(3, 60_000).drop(columns=["time"])
        self.assertIsNone(last_close_ms(df, "1m"))

    def test_none_when_empty_unknown_tf_or_none(self):
        df = _candles(3, 60_000)
        self.assertIsNone(last_close_ms(df.iloc[0:0], "1m"))
        self.assertIsNone(last_close_ms(df, "7m"))
        self.assertIsNone(last_close_ms(None, "1m"))


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot._get_market_regime.return_value = "RANGE"
    bot._ttf_last_signal_keys = {}
    return bot


def _ttf_ctx(close_time=_MISSING) -> dict:
    ctx = {"ttf_metrics": {"bias_1h": {"bias": "BUY"}}, "rsi": 50.0, "adx": 20.0}
    if close_time is not _MISSING:
        ctx["signal_close_time"] = close_time
    return ctx


def _apply(bot: MagicMock, ctx: dict, audit_signal: str = "BUY", prob: float = 85.0):
    return _apply_entry_filters_and_adjust_prob(
        bot=bot,
        symbol="BTC/USDT",
        symbol_raw="BTCUSDT",
        df_main=None,
        audit_signal=audit_signal,
        prob_final=prob,
        ctx=ctx,
        vol_rel=1.0,
    )


class TestTtfRealGate(unittest.TestCase):
    def test_real_without_flag_is_blocked(self):
        bot = _make_bot()
        with (
            patch.object(Config, "PAPER_MODE", False),
            patch.object(Config, "TTF_REAL_ENABLED", False),
            patch("core.signals.filters.append_execution_event") as mock_event,
        ):
            _prob, passed, reason, _ctx = _apply(bot, _ttf_ctx(BASE_MS))
        self.assertFalse(passed)
        self.assertEqual(reason, "TTF_REAL_BLOCKED")
        self.assertTrue(bot.log.called)
        mock_event.assert_called_once()
        self.assertEqual(mock_event.call_args.args[1], "TTF_REAL_BLOCKED")

    def test_real_with_flag_passes(self):
        bot = _make_bot()
        with (
            patch.object(Config, "PAPER_MODE", False),
            patch.object(Config, "TTF_REAL_ENABLED", True),
        ):
            _prob, passed, reason, _ctx = _apply(bot, _ttf_ctx(BASE_MS))
        self.assertTrue(passed)
        self.assertEqual(reason, "TTF_PASSED")

    def test_paper_mode_passes_without_flag(self):
        bot = _make_bot()
        with (
            patch.object(Config, "PAPER_MODE", True),
            patch.object(Config, "TTF_REAL_ENABLED", False),
        ):
            _prob, passed, reason, _ctx = _apply(bot, _ttf_ctx(BASE_MS))
        self.assertTrue(passed)
        self.assertEqual(reason, "TTF_PASSED")


class TestTtfDedup(unittest.TestCase):
    def setUp(self):
        paper = patch.object(Config, "PAPER_MODE", True)
        paper.start()
        self.addCleanup(paper.stop)
        flag = patch.object(Config, "TTF_REAL_ENABLED", False)
        flag.start()
        self.addCleanup(flag.stop)

    def test_same_symbol_side_close_time_is_duplicate(self):
        bot = _make_bot()
        _prob, passed, _reason, _ctx = _apply(bot, _ttf_ctx(BASE_MS))
        self.assertTrue(passed)
        # close_time float se normaliza a int: sigue siendo la misma identidad
        _prob, passed2, reason2, _ctx = _apply(bot, _ttf_ctx(float(BASE_MS)))
        self.assertFalse(passed2)
        self.assertEqual(reason2, "TTF_DUPLICATE_SIGNAL")
        self.assertTrue(bot.log.called)

    def test_different_close_time_passes(self):
        bot = _make_bot()
        _apply(bot, _ttf_ctx(BASE_MS))
        _prob, passed, reason, _ctx = _apply(bot, _ttf_ctx(BASE_MS + 60_000))
        self.assertTrue(passed)
        self.assertEqual(reason, "TTF_PASSED")

    def test_missing_close_time_is_blocked(self):
        bot = _make_bot()
        _prob, passed, reason, _ctx = _apply(bot, _ttf_ctx())
        self.assertFalse(passed)
        self.assertEqual(reason, "TTF_SIGNAL_IDENTITY_MISSING")
        self.assertTrue(bot.log.called)


class TestClosedCandlesAtStrategyFrontier(unittest.TestCase):
    """La frontera TTF decide con velas cerradas dentro de Strategy.analyze."""

    @staticmethod
    def _fixtures(n_1m: int):
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        anchors = {
            "last_1h": (now_ms // 3_600_000) * 3_600_000 - 3_600_000,
            "last_5m": (now_ms // 300_000) * 300_000 - 300_000,
            "last_1m": (now_ms // 60_000) * 60_000 - 60_000,
        }

        df_1h = _mock_ohlcv(60, trend=-0.005)
        df_1h["time"] = _candles(60, 3_600_000, anchors["last_1h"])["time"]

        df_5m = _mock_ohlcv(60, trend=-0.002)
        ema = df_5m["close"].ewm(span=50, adjust=False).mean().iloc[-1]

        # force MSS on index -3
        df_5m.loc[df_5m.index[-3], "close"] = df_5m["low"].min() - 10
        # force pullback on index -1
        df_5m.loc[df_5m.index[-1], "high"] = ema * 1.001
        df_5m.loc[df_5m.index[-1], "low"] = ema * 0.998
        df_5m["time"] = _candles(60, 300_000, anchors["last_5m"])["time"]

        df_1m = _mock_ohlcv(n_1m, trend=-0.001)
        df_1m["time"] = _candles(n_1m, 60_000, anchors["last_1m"])["time"]
        return df_1h, df_5m, df_1m, anchors

    @staticmethod
    def _analyze(df_1h, df_5m, df_1m):
        with (
            patch.object(Config, "STRATEGY_ENGINE", "triple_tf"),
            patch.object(Config, "TRIAGE_ADAPTIVE_RVOL_ENABLED", False),
        ):
            return Strategy.analyze(
                df_1h,
                df_1h,
                MagicMock(),
                symbol="TTF_GUARDRAIL_TEST",
                df_5m=df_5m,
                df_1m=df_1m,
            )

    def test_lt_50_closed_1m_falls_to_wait_data_insufficient(self):
        df_1h, df_5m, df_1m, anchors = self._fixtures(n_1m=49)
        sig, _mode, _price, _conf, telemetry, _votos = self._analyze(
            df_1h, df_5m, df_1m
        )
        self.assertEqual(sig, "WAIT")
        self.assertEqual(
            telemetry["ttf_metrics"]["trigger_1m"]["reason"],
            "DATA_INSUFFICIENT_1M",
        )
        # identidad tomada de la última vela 1M cerrada, no de una vela abierta
        self.assertEqual(telemetry["signal_close_time"], anchors["last_1m"] + 60_000)

    def test_sell_signal_carries_closed_1m_identity(self):
        df_1h, df_5m, df_1m, anchors = self._fixtures(n_1m=60)
        # Cruce forzado bajo EMA50 en las dos últimas velas cerradas (SELL)
        ema_series = df_1m["close"].ewm(span=50, adjust=False).mean()
        df_1m.loc[df_1m.index[-2], "close"] = float(ema_series.iloc[-2]) * 1.003
        df_1m.loc[df_1m.index[-1], "close"] = float(ema_series.iloc[-1]) * 0.997


class TestTtfSessionAndMacroFilters(unittest.TestCase):
    def setUp(self):
        paper = patch.object(Config, "PAPER_MODE", True)
        paper.start()
        self.addCleanup(paper.stop)
        flag = patch.object(Config, "TTF_REAL_ENABLED", False)
        flag.start()
        self.addCleanup(flag.stop)

    def test_session_filter_blocks_outside_hours(self):
        bot = _make_bot()
        # 03:00 UTC (outside 07:00-22:00)
        outside_ms = 1_770_000_000_000
        _prob, passed, reason, _ctx = _apply(bot, _ttf_ctx(outside_ms))
        self.assertFalse(passed)
        self.assertEqual(reason, "TTF_SESSION_OUTSIDE_HOURS")

    def test_session_filter_passes_inside_hours(self):
        bot = _make_bot()
        # 12:00 UTC (inside 07:00-22:00)
        inside_ms = BASE_MS
        _prob, passed, reason, _ctx = _apply(bot, _ttf_ctx(inside_ms))
        self.assertTrue(passed)
        self.assertEqual(reason, "TTF_PASSED")

    def test_macro_filter_blocks_bear_regime_for_buy(self):
        bot = _make_bot()
        bot._get_market_regime.return_value = "BEAR_TREND"
        _prob, passed, reason, _ctx = _apply(bot, _ttf_ctx(BASE_MS), audit_signal="BUY")
        self.assertFalse(passed)
        self.assertEqual(reason, "TTF_MACRO_REGIME_BEAR")


if __name__ == "__main__":
    unittest.main()
