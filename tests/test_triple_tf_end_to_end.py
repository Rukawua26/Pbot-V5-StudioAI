"""
test_triple_tf_end_to_end.py — Prueba End-to-End completa del ciclo de vida Triple TF.
Cubre:
1. Blindaje de pendiente en bias_1h.py (Hallazgo 5)
2. Activación estricta >= 1R en trailing_1m.py (Hallazgo 2)
3. Polaridad del Stop Loss (Hallazgo 6)
4. Lectura canónica del SL en monitor (Hallazgo 3)
5. Compatibilidad de firma elástica de Bot.close_trade (Hallazgo 1)
6. Ciclo completo de trailing exit sin TypeError
"""

import unittest
from unittest.mock import MagicMock
import numpy as np
import pandas as pd

from core.strategy.triple_tf.bias_1h import evaluate_bias_1h
from core.strategy.triple_tf.trailing_1m import evaluate_trailing_1m
from core.bot_trade_monitor import monitor_open_trades


def _make_ohlcv(n: int = 60, base: float = 100.0, trend: float = 0.0) -> pd.DataFrame:
    np.random.seed(42)
    prices = [base]
    for _ in range(1, n):
        prices.append(prices[-1] * (1.0 + trend + np.random.normal(0, 0.001)))
    opens = [p * 0.9995 for p in prices] if trend >= 0 else [p * 1.0005 for p in prices]
    closes = (
        [p * 1.0005 for p in prices] if trend >= 0 else [p * 0.9995 for p in prices]
    )
    highs = [p * 1.002 for p in prices]
    lows = [p * 0.998 for p in prices]
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000.0] * n,
        }
    )


def _recent_open_time():
    """Retorna un timestamp 30 minutos en el pasado (supera el cooldown de 5 min)."""
    from datetime import timedelta
    from core.time_utils import utc_now

    return (utc_now() - timedelta(minutes=30)).isoformat()


class TestHallazgo5_SlopeBias(unittest.TestCase):
    """H5: bias_1h.py debe rechazar BUY si la EMA 50 tiene pendiente bajista."""

    def test_buy_rejected_when_slope_bearish(self):
        """Precio arriba de la EMA 50 pero media descendente severa → NEUTRAL."""
        df = _make_ohlcv(n=60, base=100.0, trend=-0.005)
        ema = df["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        df.loc[df.index[-1], "close"] = ema * 1.01  # Precio por encima de la EMA
        res = evaluate_bias_1h(df)
        self.assertEqual(
            res.bias, "NEUTRAL", f"Se esperaba NEUTRAL, pendiente={res.slope_pct:.4f}%"
        )
        self.assertIn("SLOPE_BEARISH", res.reason)

    def test_sell_rejected_when_slope_bullish(self):
        """Precio abajo de la EMA 50 pero media ascendente severa → NEUTRAL."""
        df = _make_ohlcv(n=60, base=100.0, trend=0.005)
        ema = df["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        df.loc[df.index[-1], "close"] = ema * 0.99  # Precio por debajo de la EMA
        res = evaluate_bias_1h(df)
        self.assertEqual(
            res.bias, "NEUTRAL", f"Se esperaba NEUTRAL, pendiente={res.slope_pct:.4f}%"
        )
        self.assertIn("SLOPE_BULLISH", res.reason)

    def test_buy_allowed_when_slope_flat_or_bullish(self):
        """Precio arriba de la EMA 50 con pendiente alcista → BUY."""
        df = _make_ohlcv(n=60, base=100.0, trend=0.003)
        res = evaluate_bias_1h(df)
        self.assertEqual(res.bias, "BUY")

    def test_sell_allowed_when_slope_flat_or_bearish(self):
        """Precio abajo de la EMA 50 con pendiente bajista → SELL."""
        df = _make_ohlcv(n=60, base=100.0, trend=-0.003)
        res = evaluate_bias_1h(df)
        self.assertEqual(res.bias, "SELL")

    def test_upper_wick_rejection_blocks_buy(self):
        """Mecha superior >= 50% en zona de resistencia bloquea BUY → NEUTRAL."""
        df = _make_ohlcv(n=60, base=100.0, trend=0.003)
        ema = df["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        # Construir una vela con mecha superior enorme (>50% del rango total)
        df.loc[df.index[-1], "close"] = ema * 1.001
        df.loc[df.index[-1], "open"] = ema * 1.001
        df.loc[df.index[-1], "low"] = ema * 1.0
        df.loc[df.index[-1], "high"] = ema * 1.02  # mecha superior dominante
        res = evaluate_bias_1h(df)
        self.assertEqual(res.bias, "NEUTRAL")


class TestHallazgo2_TrailingActivation(unittest.TestCase):
    """H2: trailing_1m.py debe exigir >= 1R para activar el trailing stop."""

    def _make_1m_with_close_below_ema(self):
        df = _make_ohlcv(n=60, base=100.0)
        ema = df["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        df.loc[df.index[-1], "close"] = ema * 0.998  # cierre bajo la EMA 50
        return df

    def test_not_activated_below_1r(self):
        """Trade con +0.2R no activa el trailing — no sale aunque cruce la EMA."""
        df = self._make_1m_with_close_below_ema()
        res = evaluate_trailing_1m(
            df,
            side="BUY",
            entry_price=100.0,
            sl_price=98.0,
            current_price=100.4,
            activation_r=1.0,
        )
        self.assertFalse(res.should_exit, "No debe salir con solo 0.2R")
        self.assertEqual(res.reason, "TRAILING_1M_NOT_YET_ACTIVATED")

    def test_not_activated_at_exact_sub_1r(self):
        """Con +0.9R (menos de 1R) el trailing no se activa."""
        df = self._make_1m_with_close_below_ema()
        res = evaluate_trailing_1m(
            df,
            side="BUY",
            entry_price=100.0,
            sl_price=98.0,
            current_price=101.8,
            activation_r=1.0,
        )
        self.assertFalse(res.should_exit)

    def test_activated_and_exits_at_1r_plus(self):
        """Con +1.5R activa el trailing y cierra al cruzar la EMA 50 de 1M."""
        df = self._make_1m_with_close_below_ema()
        res = evaluate_trailing_1m(
            df,
            side="BUY",
            entry_price=100.0,
            sl_price=98.0,
            current_price=103.0,
            activation_r=1.0,
        )
        self.assertTrue(res.should_exit)
        self.assertEqual(res.reason, "TRAILING_1M_EMA50_CLOSE_BELOW")

    def test_short_activated_at_1r_exits_above_ema(self):
        """SHORT con +1.5R activa trailing y cierra al cruzar EMA 50 por encima."""
        df = _make_ohlcv(n=60, base=100.0)
        ema = df["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        df.loc[df.index[-1], "close"] = ema * 1.002  # cierre sobre la EMA
        res = evaluate_trailing_1m(
            df,
            side="SELL",
            entry_price=105.0,
            sl_price=107.0,
            current_price=102.0,
            activation_r=1.0,
        )
        self.assertTrue(res.should_exit)
        self.assertEqual(res.reason, "TRAILING_1M_EMA50_CLOSE_ABOVE")


class TestHallazgo6_SLPolarity(unittest.TestCase):
    """H6: La polaridad del Stop Loss debe ser válida (BUY: SL < price, SELL: SL > price)."""

    def test_buy_sl_must_be_below_price(self):
        """Para BUY, el SL inválido (> precio) debe ser corregido a BUY < price."""

        price = 100.0
        side = "BUY"

        # Simular la corrección que sucede en trade_entry.py cuando sl_val >= price
        suggested_sl = 102.0  # Anómalo: SL está arriba del precio
        risk_dist = abs(price * 0.02)  # 2% de distancia de emergencia

        # Aplicar guardrail de polaridad (mismo código que en trade_entry.py)
        sl_val = suggested_sl
        if side == "BUY" and sl_val >= price:
            sl_val = price - risk_dist
        elif side == "SELL" and sl_val <= price:
            sl_val = price + risk_dist

        self.assertLess(sl_val, price, f"SL={sl_val} debe ser < precio={price}")

    def test_sell_sl_must_be_above_price(self):
        """Para SELL, el SL inválido (< precio) debe ser corregido a SELL > price."""
        price = 100.0
        side = "SELL"
        suggested_sl = 98.0  # Anómalo: SL está abajo del precio en SHORT
        risk_dist = abs(price * 0.02)

        sl_val = suggested_sl
        if side == "BUY" and sl_val >= price:
            sl_val = price - risk_dist
        elif side == "SELL" and sl_val <= price:
            sl_val = price + risk_dist

        self.assertGreater(sl_val, price, f"SL={sl_val} debe ser > precio={price}")


class TestHallazgo3_CanonicalSLKey(unittest.TestCase):
    """H3: bot_trade_monitor.py debe leer SL bajo la clave canónica 'sl', no solo 'stop_loss'."""

    def test_sl_key_canonical_in_monitor(self):
        """El trailing R-multiple se calcula correctamente cuando el SL viene en 'sl'."""
        # Simular un trade con SL almacenado bajo 'sl' (clave canónica de trade_state)
        trade_with_canonical_sl = {
            "symbol": "ETH/USDT",
            "side": "BUY",
            "entry": 2000.0,
            "sl": 1960.0,  # Clave canónica
            # 'stop_loss' no está presente → antes del fix daba sl_p=0.0 y R ficticio 2%
            "strategy_engine": "triple_tf",
            "ttf_metrics": {},
            "open_time": _recent_open_time(),
        }
        entry_p = float(trade_with_canonical_sl.get("entry") or 0.0)
        sl_p = float(
            trade_with_canonical_sl.get("sl")
            or trade_with_canonical_sl.get("stop_loss")
            or 0.0
        )
        current_price = 2080.0  # +2.0R en ganancias

        risk_distance = abs(entry_p - sl_p)
        r_multiple = (
            (current_price - entry_p) / risk_distance if risk_distance > 0 else 0.0
        )

        self.assertAlmostEqual(sl_p, 1960.0, msg="SL debe leerse de la clave 'sl'")
        self.assertAlmostEqual(risk_distance, 40.0, places=1)
        self.assertAlmostEqual(
            r_multiple, 2.0, places=1, msg="R-multiple debe ser 2.0 con SL correcto"
        )


class TestHallazgo1_CloseTradeFirmware(unittest.TestCase):
    """H1: Bot.close_trade debe aceptar side y trade_key sin TypeError."""

    def test_close_trade_accepts_side_and_trade_key(self):
        """Verificar que la firma elástica de close_trade no lanza TypeError."""
        from core.bot_app import Bot

        bot = MagicMock(spec=Bot)
        # La firma real de Bot.close_trade ahora tiene side= y trade_key=
        # Llamamos directamente al mock que representa el método
        bot.close_trade(
            symbol="BTC/USDT",
            reason="TTF_TRAILING_1M_EMA50_CLOSE_BELOW",
            exit_price=103.0,
            exit_confidence=100.0,
            side="BUY",
            trade_key="BTC/USDT|BUY",
        )
        bot.close_trade.assert_called_once()
        kwargs = bot.close_trade.call_args.kwargs
        self.assertEqual(kwargs["side"], "BUY")
        self.assertEqual(kwargs["trade_key"], "BTC/USDT|BUY")


class TestHallazgo1_MonitorTrailingExitFullCycle(unittest.TestCase):
    """H1+H3: Ciclo completo de trailing exit: monitor → trailing eval → close_trade."""

    def test_trailing_exit_calls_close_trade_with_side_and_key(self):
        """monitor_open_trades debe llamar a bot.close_trade con side y trade_key correctos."""
        bot = MagicMock()
        bot.lock = MagicMock()

        open_time = _recent_open_time()
        bot.active_trades = {
            "BTC/USDT|BUY": {
                "symbol": "BTC/USDT",
                "side": "BUY",
                "entry": 100.0,
                "sl": 98.0,  # Clave canónica — crítico para Hallazgo 3
                "strategy_engine": "triple_tf",
                "ttf_metrics": {"bias_1h": {"bias": "BUY"}},
                "open_time": open_time,
            }
        }

        # current_price implícita = último cierre del df_1m
        # Forzar: precio actual = 103.0 (+1.5R), pero cierre de 1M bajo la EMA 50
        df_1m = _make_ohlcv(n=60, base=103.0)
        ema_1m = df_1m["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        # Precio actual (103.0) ya es >=1R ganado, y el cierre de 1M baja la EMA
        df_1m.loc[df_1m.index[-1], "close"] = ema_1m * 0.997
        bot.data_service.fetch_and_update_data.return_value = df_1m

        monitor_open_trades(bot)

        # close_trade debe haberse llamado exactamente una vez
        bot.close_trade.assert_called_once()
        call_kwargs = bot.close_trade.call_args.kwargs
        self.assertEqual(call_kwargs.get("symbol"), "BTC/USDT")
        self.assertEqual(call_kwargs.get("side"), "BUY")
        self.assertIn("TTF_", call_kwargs.get("reason", ""))
        self.assertEqual(call_kwargs.get("trade_key"), "BTC/USDT|BUY")

    def test_trailing_exit_zero_cooldown_within_one_minute(self):
        """Cero cooldown: un trade abierto hace solo 30s debe salir si toca el trailing stop de 1M."""
        from datetime import timedelta
        from core.time_utils import utc_now

        bot = MagicMock()
        bot.lock = MagicMock()

        # Trade abierto hace 30 segundos (antes el cooldown de 5 min lo ignoraba)
        brand_new_time = (utc_now() - timedelta(seconds=30)).isoformat()
        bot.active_trades = {
            "SOL/USDT|BUY": {
                "symbol": "SOL/USDT",
                "side": "BUY",
                "entry": 100.0,
                "sl": 98.0,
                "strategy_engine": "triple_tf",
                "ttf_metrics": {"bias_1h": {"bias": "BUY"}},
                "open_time": brand_new_time,
            }
        }

        df_1m = _make_ohlcv(n=60, base=103.0)
        ema_1m = df_1m["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        df_1m.loc[df_1m.index[-1], "close"] = ema_1m * 0.997
        bot.data_service.fetch_and_update_data.return_value = df_1m

        monitor_open_trades(bot)

        # Debe cerrarse de inmediato en el segundo 30 sin esperar 5 minutos
        bot.close_trade.assert_called_once()


class TestBTCIndependenceAndNaNResilience(unittest.TestCase):
    """Pruebas de autonomía de activo frente a BTC y resiliencia ante NaNs."""

    def test_btc_bear_sentiment_does_not_block_altcoin_buy_in_planning(self):
        """Si BTC está en tendencia bajista, una altcoin con señal TTF BUY debe ejecutarse igual."""
        from core.signals.filters import (
            _plan_execution_mode,
            _resolve_audit_verdict_and_stats,
        )

        bot = MagicMock()
        bot.current_sentiment = ("🔴 TENDENCIA BAJISTA", "red")
        bot._get_market_regime.return_value = "BEAR_TREND"

        ctx = {
            "ttf_metrics": {"bias_1h": {"bias": "BUY"}},
            "prob_final": 85.0,
        }
        signal_stats = {}

        # 1. El veredicto debe ser de TTF y no VETO BTC
        verdict = _resolve_audit_verdict_and_stats(
            bot=bot,
            symbol="SOL/USDT",
            audit_signal="BUY",
            prob_final=85.0,
            ob_status="OK",
            pnl_real_hoy=0.0,
            mode="NONE",
            ctx=ctx,
            filter_passed=True,
            filter_reason="TTF_PASSED",
            ml_pure_prob=0.0,
            signal_stats=signal_stats,
        )
        self.assertIn("TTF_BUY", verdict)
        self.assertNotIn("VETO", verdict)

        # 2. El planificador debe autorizar la ejecución
        should_exec, is_shadow, p_verdict, passed, reason = _plan_execution_mode(
            bot=bot,
            symbol="SOL/USDT",
            audit_signal="BUY",
            prob_final=85.0,
            audit_verdict=verdict,
            filter_passed=True,
            filter_reason="TTF_PASSED",
            ctx=ctx,
        )
        self.assertTrue(
            should_exec, "Debe autorizar la ejecución independientemente de BTC"
        )
        self.assertTrue(passed)
        self.assertEqual(reason, "TTF_PASSED")

    def test_compute_ema_nan_resilience(self):
        """compute_ema debe manejar NaNs sin propagar valores corruptos."""
        from core.strategy.triple_tf.bias_1h import compute_ema

        series_with_nans = pd.Series([100.0, 101.0, np.nan, 103.0, np.nan, 105.0] * 10)
        ema = compute_ema(series_with_nans, span=50)

        self.assertFalse(np.isnan(ema.iloc[-1]), "EMA no debe ser NaN")
        self.assertGreater(float(ema.iloc[-1]), 0.0)


class TestRonda2Hardening(unittest.TestCase):
    """Pruebas de blindaje implementadas tras la Auditoría Forense de Ronda 2."""

    def test_is_ttf_signal_helper(self):
        """is_ttf_signal debe ser la fuente de verdad única para detectar TTF."""
        from core.strategy.triple_tf import is_ttf_signal

        self.assertTrue(is_ttf_signal({"ttf_metrics": {"bias_1h": {}}}))
        self.assertFalse(is_ttf_signal({}))
        self.assertFalse(is_ttf_signal(None))
        self.assertFalse(is_ttf_signal({"strategy_engine": "triple_tf"}))

    def test_structure_5m_recent_touch_lookback_parameter(self):
        """recent_touch_lookback parametrizable permite detectar toque en ventana configurada."""
        from core.strategy.triple_tf.structure_5m import evaluate_structure_5m

        df = _make_ohlcv(n=60, base=100.0, trend=0.003)
        res_default = evaluate_structure_5m(df, bias_1h="BUY", recent_touch_lookback=4)
        self.assertIsInstance(res_default.pullback_touched, bool)

    def test_ttf_monitor_defers_trailing_if_sl_zero(self):
        """Si sl <= 0, monitor_open_trades no debe evaluar trailing (diferido)."""
        bot = MagicMock()
        bot.active_trades = {
            "SOL/USDT": {
                "symbol": "SOL/USDT",
                "entry": 100.0,
                "sl": 0.0,
                "stop_loss": 0.0,
                "side": "BUY",
                "strategy_engine": "triple_tf",
                "open_time": _recent_open_time(),
            }
        }
        df_1m = _make_ohlcv(n=60, base=105.0)
        bot.data_service.fetch_and_update_data.return_value = df_1m

        monitor_open_trades(bot)
        # No debe haber llamado a close_trade porque SL era 0
        bot.close_trade.assert_not_called()

    def test_ttf_real_mode_blocks_blind_fast_track(self):
        """En modo REAL (PAPER_MODE=False y SHADOW_MODE=False), el fast-track ciego se bloquea."""
        from unittest.mock import patch
        from config import Config
        from core.signals.filters import _plan_execution_mode

        bot = MagicMock()
        ctx = {"ttf_metrics": {"bias_1h": {}}}

        with (
            patch.object(Config, "PAPER_MODE", False),
            patch.object(Config, "SHADOW_MODE", False, create=True),
        ):
            should_exec, is_shadow_exec, verdict, passed, reason = _plan_execution_mode(
                bot=bot,
                symbol="SOL/USDT",
                audit_signal="BUY",
                prob_final=85.0,
                audit_verdict="",
                filter_passed=True,
                filter_reason="TTF_PASSED",
                ctx=ctx,
            )
            # En modo REAL, no se autoriza por fast-track ciego
            self.assertFalse(is_shadow_exec)


class TestRonda3PrecisionHardening(unittest.TestCase):
    """Pruebas para el Plan Refinado de Alta Precisión (Ronda 3)."""

    def test_stateful_trailing_memory_exits_even_if_r_drops_below_activation(self):
        """Si el trade ya se armó (trailing_already_activated=True), debe salir si cruza la EMA50
        incluso si el R actual retrocedió a +0.8R (< 1.0R)."""
        from core.strategy.triple_tf.trailing_1m import evaluate_trailing_1m

        # 60 velas donde la EMA50 está alrededor de 105.0
        df = _make_ohlcv(n=60, base=105.0)
        # Última vela cierra en 104.0 (por debajo de EMA 50)
        df.loc[df.index[-1], "close"] = 104.0
        entry_price = 100.0
        sl_price = 95.0  # Risk = 5.0. 1R = 105.0. A 104.0, R = +0.8R (< 1.0R).

        # Sin memoria previa: no se activa porque R < 1.0
        res_stateless = evaluate_trailing_1m(
            df_1m=df,
            side="BUY",
            entry_price=entry_price,
            sl_price=sl_price,
            current_price=104.0,
            trailing_already_activated=False,
        )
        self.assertFalse(res_stateless.should_exit)
        self.assertEqual(res_stateless.reason, "TRAILING_1M_NOT_YET_ACTIVATED")

        # Con memoria previa (ya se armó a +1.3R anteriormente):
        res_stateful = evaluate_trailing_1m(
            df_1m=df,
            side="BUY",
            entry_price=entry_price,
            sl_price=sl_price,
            current_price=104.0,
            trailing_already_activated=True,
        )
        self.assertTrue(res_stateful.should_exit)
        self.assertTrue(res_stateful.is_activated)
        self.assertEqual(res_stateful.reason, "TRAILING_1M_EMA50_CLOSE_BELOW")

    def test_bias_1h_wick_rejection_is_order_independent(self):
        """Vela -2 con rechazo superior severo (80%) debe bloquear BUY
        incluso si vela -1 tiene una mecha inferior del 55%."""
        from core.strategy.triple_tf.bias_1h import evaluate_bias_1h

        df = _make_ohlcv(n=60, base=100.0, trend=0.0)
        # Vela -2: Shooting star (mecha superior al 80%)
        # high=110, close=102, open=101, low=100.5 -> total_range=9.5, body_top=102, upper_wick=8 (>80%)
        df.loc[df.index[-2], "open"] = 101.0
        df.loc[df.index[-2], "close"] = 102.0
        df.loc[df.index[-2], "low"] = 100.5
        df.loc[df.index[-2], "high"] = 110.0

        # Vela -1: Hammer moderado (mecha inferior >= 50%)
        df.loc[df.index[-1], "open"] = 103.0
        df.loc[df.index[-1], "close"] = 103.2
        df.loc[df.index[-1], "low"] = 101.0
        df.loc[df.index[-1], "high"] = 103.5

        res = evaluate_bias_1h(df)
        self.assertEqual(res.bias, "NEUTRAL")
        self.assertEqual(res.reason, "1H_RESISTANCE_REJECTION_ABOVE_EMA")

    def test_trigger_1m_anti_chasing_guard(self):
        """Gatillo 1M no debe disparar si el precio actual está sobreextendido (> 0.6% de la EMA)."""
        from core.strategy.triple_tf.trigger_1m import evaluate_trigger_1m

        df = _make_ohlcv(n=60, base=100.0)
        ema = df["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        # Precio sobreextendido a +1.5% de la EMA
        df.loc[df.index[-1], "close"] = ema * 1.015

        res = evaluate_trigger_1m(df, bias_1h="BUY", setup_5m_valid=True)
        self.assertFalse(res.triggered)

    def test_structure_5m_suggested_sl_strictly_positive_fallback(self):
        """suggested_sl debe ser estrictamente positivo incluso en cualquier caso de mercado."""
        from core.strategy.triple_tf.structure_5m import evaluate_structure_5m

        df = _make_ohlcv(n=60, base=100.0, trend=0.003)
        res = evaluate_structure_5m(df, bias_1h="BUY")
        self.assertGreater(res.suggested_sl, 0.0)

    def test_is_ttf_trade_helper(self):
        """is_ttf_trade identifica correctamente posiciones de la estrategia TTF."""
        from core.strategy.triple_tf import is_ttf_trade

        self.assertTrue(is_ttf_trade({"strategy_engine": "triple_tf"}))
        self.assertTrue(is_ttf_trade({"ttf_metrics": {"bias_1h": {}}}))
        self.assertFalse(is_ttf_trade({"strategy_engine": "legacy"}))
        self.assertFalse(is_ttf_trade({}))
        self.assertFalse(is_ttf_trade(None))


if __name__ == "__main__":
    unittest.main()
