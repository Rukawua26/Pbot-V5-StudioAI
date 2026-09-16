from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class Structure5MResult:
    valid_setup: bool
    mss_confirmed: bool
    pullback_touched: bool
    ema50_5m: float
    suggested_sl: float
    swing_high: float
    swing_low: float
    reason: str


def compute_ema(series: pd.Series, span: int = 50) -> pd.Series:
    clean_series = series.ffill().bfill()
    return clean_series.ewm(span=span, adjust=False).mean()


def evaluate_structure_5m(
    df_5m: pd.DataFrame | None,
    bias_1h: str,
    lookback_mss: int = 10,
    lookback_pullback: int = 5,
    touch_tolerance_pct: float = 0.0015,
    recent_touch_lookback: int = 4,
) -> Structure5MResult:
    """Evalúa el marco intermedio (5 Minutos / 5M) para Cambio de Estructura (MSS) y Pullback a EMA 50.

    Para Venta (SHORT):
    1. MSS: Cierre reciente < mínimo estructural de las N velas previas.
    2. Pullback: El precio reciente testea la EMA 50 de 5M (High >= EMA50 - tolerancia).
    3. Stop Loss: Máximo relevante de las últimas velas del retroceso.

    Para Compra (LONG):
    1. MSS: Cierre reciente > máximo estructural de las N velas previas.
    2. Pullback: El precio reciente testea la EMA 50 de 5M (Low <= EMA50 + tolerancia).
    3. Stop Loss: Mínimo relevante de las últimas velas del retroceso.

    Args:
        recent_touch_lookback: Número de velas más recientes (dentro de lookback_pullback) donde
            se verifica el toque a EMA 50. Garantiza que el retroceso es activo y reciente.
            Por defecto 4 (80% de lookback_pullback=5), equilibrio entre recencia y cobertura.
    """
    if df_5m is None or len(df_5m) < max(50, lookback_mss + lookback_pullback + 2):
        return Structure5MResult(
            valid_setup=False,
            mss_confirmed=False,
            pullback_touched=False,
            ema50_5m=0.0,
            suggested_sl=0.0,
            swing_high=0.0,
            swing_low=0.0,
            reason="DATA_INSUFFICIENT_5M",
        )

    if bias_1h not in {"BUY", "SELL"}:
        return Structure5MResult(
            valid_setup=False,
            mss_confirmed=False,
            pullback_touched=False,
            ema50_5m=0.0,
            suggested_sl=0.0,
            swing_high=0.0,
            swing_low=0.0,
            reason="BIAS_1H_NOT_DIRECTIONAL",
        )

    closes = df_5m["close"].astype(float)
    highs = df_5m["high"].astype(float)
    lows = df_5m["low"].astype(float)

    ema50_series = compute_ema(closes, span=50)
    current_ema = float(ema50_series.iloc[-1])

    # Ventana previa para MSS (excluyendo las últimas velas que forman el pullback actual)
    prior_highs = highs.iloc[-(lookback_mss + lookback_pullback) : -lookback_pullback]
    prior_lows = lows.iloc[-(lookback_mss + lookback_pullback) : -lookback_pullback]

    recent_highs = highs.iloc[-lookback_pullback:]
    recent_lows = lows.iloc[-lookback_pullback:]
    recent_closes = closes.iloc[-lookback_pullback:]

    swing_high = (
        float(prior_highs.max()) if len(prior_highs) > 0 else float(highs.max())
    )
    swing_low = float(prior_lows.min()) if len(prior_lows) > 0 else float(lows.min())

    pullback_swing_high = float(recent_highs.max())
    pullback_swing_low = float(recent_lows.min())

    if bias_1h == "SELL":
        # 1. MSS en SHORT: hubo ruptura por debajo del swing low previo
        mss_confirmed = (
            any(float(c) < swing_low for c in recent_closes)
            or float(closes.iloc[-2]) < swing_low
        )

        # 2. Pullback a EMA 50 en 5M: retroceso activo en las últimas velas hacia la EMA 50
        touch_boundary = current_ema * (1.0 - touch_tolerance_pct)
        pullback_touched = any(
            float(h) >= touch_boundary
            for h in recent_highs.iloc[-recent_touch_lookback:]
        )

        valid_highs = [
            float(v)
            for v in [pullback_swing_high, current_ema * 1.002]
            if float(v) > 0.0
        ]
        suggested_sl = max(valid_highs) if valid_highs else float(current_ema * 1.002)

        valid = mss_confirmed and pullback_touched
        reason = (
            "5M_SHORT_SETUP_CONFIRMED"
            if valid
            else (
                "5M_SHORT_MSS_FAILED"
                if not mss_confirmed
                else "5M_SHORT_PULLBACK_NOT_TOUCHED"
            )
        )

        return Structure5MResult(
            valid_setup=valid,
            mss_confirmed=mss_confirmed,
            pullback_touched=pullback_touched,
            ema50_5m=current_ema,
            suggested_sl=suggested_sl,
            swing_high=pullback_swing_high,
            swing_low=swing_low,
            reason=reason,
        )

    else:  # BUY
        # 1. MSS en LONG: hubo ruptura por encima del swing high previo
        mss_confirmed = (
            any(float(c) > swing_high for c in recent_closes)
            or float(closes.iloc[-2]) > swing_high
        )

        # 2. Pullback a EMA 50 en 5M: retroceso activo en las últimas velas hacia la EMA 50
        touch_boundary = current_ema * (1.0 + touch_tolerance_pct)
        pullback_touched = any(
            float(low_val) <= touch_boundary
            for low_val in recent_lows.iloc[-recent_touch_lookback:]
        )

        valid_lows = [
            float(v)
            for v in [pullback_swing_low, current_ema * 0.998]
            if float(v) > 0.0
        ]
        suggested_sl = min(valid_lows) if valid_lows else float(current_ema * 0.998)

        valid = mss_confirmed and pullback_touched
        reason = (
            "5M_LONG_SETUP_CONFIRMED"
            if valid
            else (
                "5M_LONG_MSS_FAILED"
                if not mss_confirmed
                else "5M_LONG_PULLBACK_NOT_TOUCHED"
            )
        )

        return Structure5MResult(
            valid_setup=valid,
            mss_confirmed=mss_confirmed,
            pullback_touched=pullback_touched,
            ema50_5m=current_ema,
            suggested_sl=suggested_sl,
            swing_high=swing_high,
            swing_low=pullback_swing_low,
            reason=reason,
        )
