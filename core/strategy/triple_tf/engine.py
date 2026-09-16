from __future__ import annotations

from typing import Any
import pandas as pd

from core.strategy.triple_tf.bias_1h import evaluate_bias_1h
from core.strategy.triple_tf.structure_5m import evaluate_structure_5m
from core.strategy.triple_tf.trigger_1m import evaluate_trigger_1m


class TripleTFEngine:
    """Motor de Estrategia Triple Timeframe (1H / 5M / 1M).

    Pipeline:
    1. 1H: Determina Sesgo Direccional (BUY / SELL / NEUTRAL) con EMA 50 y Mechas de Desaceleración.
    2. 5M: Valida Cambio de Estructura (MSS) y Toque de Retroceso (Pullback) a la EMA 50 de 5M.
    3. 1M: Detecta Gatillo de Disparo por Cruce/Cierre de Vela sobre la EMA 50 de 1M.
    """

    @classmethod
    def analyze(
        cls,
        df_1h: pd.DataFrame | None,
        df_5m: pd.DataFrame | None,
        df_1m: pd.DataFrame | None = None,
        symbol: str = "Asset",
        spread: float = 0.0,
        deceleration_threshold: float = 0.50,
        lookback_mss: int = 10,
        lookback_pullback: int = 5,
        touch_tolerance_pct: float = 0.0015,
        max_spread_pct: float = 0.0010,
    ) -> dict[str, Any]:
        # 1. Evaluar Sesgo en 1H
        bias_res = evaluate_bias_1h(
            df_1h=df_1h,
            deceleration_threshold=deceleration_threshold,
        )

        # 2. Evaluar Estructura y Pullback en 5M
        struct_res = evaluate_structure_5m(
            df_5m=df_5m,
            bias_1h=bias_res.bias,
            lookback_mss=lookback_mss,
            lookback_pullback=lookback_pullback,
            touch_tolerance_pct=touch_tolerance_pct,
        )

        # Si no tenemos DF de 1M (por ejemplo en escaneo previo de radar), retornamos el estado del setup 5M
        if df_1m is None or df_1m.empty:
            signal = "WAIT"
            confidence = 60.0 if struct_res.valid_setup else 0.0
            return {
                "signal": signal,
                "confidence": confidence,
                "bias_1h": bias_res.bias,
                "setup_5m_valid": struct_res.valid_setup,
                "trigger_1m_ready": False,
                "stop_loss": struct_res.suggested_sl,
                "entry_price": float(df_5m["close"].iloc[-1])
                if df_5m is not None and len(df_5m) > 0
                else 0.0,
                "market_regime": f"TTF_{bias_res.bias}",
                "reason": f"1H:{bias_res.reason} | 5M:{struct_res.reason} | 1M:WAITING_DATA",
                "ttf_metrics": {
                    "bias_1h": bias_res.__dict__,
                    "structure_5m": struct_res.__dict__,
                },
            }

        # 3. Evaluar Gatillo en 1M
        trigger_res = evaluate_trigger_1m(
            df_1m=df_1m,
            bias_1h=bias_res.bias,
            setup_5m_valid=struct_res.valid_setup,
            spread=spread,
            max_spread_pct=max_spread_pct,
        )

        if trigger_res.triggered and trigger_res.side in {"BUY", "SELL"}:
            signal = trigger_res.side
            confidence = 85.0
            reason = f"TTF_ENTRY_CONFIRMED: 1H={bias_res.bias}, 5M=MSS+Pullback, 1M={trigger_res.reason}"
        else:
            signal = "WAIT"
            confidence = 50.0 if struct_res.valid_setup else 0.0
            reason = f"1H:{bias_res.reason} | 5M:{struct_res.reason} | 1M:{trigger_res.reason}"

        return {
            "signal": signal,
            "confidence": confidence,
            "bias_1h": bias_res.bias,
            "setup_5m_valid": struct_res.valid_setup,
            "trigger_1m_ready": trigger_res.triggered,
            "stop_loss": struct_res.suggested_sl,
            "entry_price": trigger_res.entry_price,
            "market_regime": f"TTF_{bias_res.bias}",
            "reason": reason,
            "ttf_metrics": {
                "bias_1h": bias_res.__dict__,
                "structure_5m": struct_res.__dict__,
                "trigger_1m": trigger_res.__dict__,
            },
        }
