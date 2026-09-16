from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class Bias1HResult:
    bias: str  # "BUY", "SELL", "NEUTRAL"
    ema50: float
    slope_pct: float
    deceleration: bool
    rejection_side: str | None  # "UPPER_WICK", "LOWER_WICK", or None
    wick_ratio: float
    reason: str


def compute_ema(series: pd.Series, span: int = 50) -> pd.Series:
    clean_series = series.ffill().bfill()
    return clean_series.ewm(span=span, adjust=False).mean()


def evaluate_bias_1h(
    df_1h: pd.DataFrame | None,
    deceleration_threshold: float = 0.50,
    slope_lookback: int = 3,
) -> Bias1HResult:
    """Evalúa el marco temporal de 1 Hora (1H) para determinar el sesgo direccional.

    Reglas:
    1. Calcula la EMA 50 en 1H.
    2. Evalúa desaceleración/rechazo en las últimas velas (mecha superior >= 50% para SELL,
       mecha inferior >= 50% para BUY).
    3. Evalúa la relación del precio de cierre con la EMA 50 y la pendiente de la EMA 50.
    """
    if df_1h is None or len(df_1h) < 50:
        return Bias1HResult(
            bias="NEUTRAL",
            ema50=0.0,
            slope_pct=0.0,
            deceleration=False,
            rejection_side=None,
            wick_ratio=0.0,
            reason="DATA_INSUFFICIENT_1H",
        )

    closes = df_1h["close"].astype(float)
    highs = df_1h["high"].astype(float)
    lows = df_1h["low"].astype(float)
    opens = df_1h["open"].astype(float)

    ema50_series = compute_ema(closes, span=50)
    current_close = float(closes.iloc[-1])
    current_ema = float(ema50_series.iloc[-1])
    prev_ema = float(ema50_series.iloc[-min(len(ema50_series), slope_lookback + 1)])

    slope_pct = ((current_ema - prev_ema) / prev_ema * 100.0) if prev_ema > 0 else 0.0

    # Analizar últimas 3 velas para detectar mechas de desaceleración / rechazo
    recent_rejection = None
    max_wick_ratio = 0.0
    has_upper_rejection = False
    has_lower_rejection = False

    for idx in range(-1, -4, -1):
        if abs(idx) > len(df_1h):
            break
        close_val = float(closes.iloc[idx])
        open_val = float(opens.iloc[idx])
        high_val = float(highs.iloc[idx])
        low_val = float(lows.iloc[idx])

        total_range = high_val - low_val
        if total_range <= 0:
            continue

        body_top = max(close_val, open_val)
        body_bottom = min(close_val, open_val)

        upper_wick = high_val - body_top
        lower_wick = body_bottom - low_val

        upper_ratio = upper_wick / total_range
        lower_ratio = lower_wick / total_range

        if upper_ratio >= deceleration_threshold:
            has_upper_rejection = True
            if upper_ratio > max_wick_ratio:
                max_wick_ratio = upper_ratio
                recent_rejection = "UPPER_WICK"
        if lower_ratio >= deceleration_threshold:
            has_lower_rejection = True
            if lower_ratio > max_wick_ratio:
                max_wick_ratio = lower_ratio
                recent_rejection = "LOWER_WICK"

    has_deceleration = max_wick_ratio >= deceleration_threshold

    # Lógica de decisión del Bias
    # COMPRA (BUY):
    # - Precio >= EMA 50 en 1H con pendiente positiva o plana (>= -0.05%)
    # - Sin mecha de rechazo superior (UPPER_WICK)
    if current_close >= current_ema:
        if slope_pct < -0.05:
            return Bias1HResult(
                bias="NEUTRAL",
                ema50=current_ema,
                slope_pct=slope_pct,
                deceleration=has_deceleration,
                rejection_side=recent_rejection,
                wick_ratio=max_wick_ratio,
                reason="1H_SLOPE_BEARISH_ABOVE_EMA",
            )
        if has_upper_rejection:
            # Trampa / rechazo en resistencia
            return Bias1HResult(
                bias="NEUTRAL",
                ema50=current_ema,
                slope_pct=slope_pct,
                deceleration=has_deceleration,
                rejection_side="UPPER_WICK",
                wick_ratio=max_wick_ratio,
                reason="1H_RESISTANCE_REJECTION_ABOVE_EMA",
            )
        return Bias1HResult(
            bias="BUY",
            ema50=current_ema,
            slope_pct=slope_pct,
            deceleration=has_deceleration,
            rejection_side=recent_rejection,
            wick_ratio=max_wick_ratio,
            reason="1H_PRICE_ABOVE_EMA50",
        )
    else:
        # VENTA (SELL):
        # - Precio < EMA 50 en 1H con pendiente negativa o plana (<= 0.05%)
        # - Sin mecha de rechazo inferior (LOWER_WICK)
        if slope_pct > 0.05:
            return Bias1HResult(
                bias="NEUTRAL",
                ema50=current_ema,
                slope_pct=slope_pct,
                deceleration=has_deceleration,
                rejection_side=recent_rejection,
                wick_ratio=max_wick_ratio,
                reason="1H_SLOPE_BULLISH_BELOW_EMA",
            )
        if has_lower_rejection:
            # Trampa / rechazo en soporte
            return Bias1HResult(
                bias="NEUTRAL",
                ema50=current_ema,
                slope_pct=slope_pct,
                deceleration=has_deceleration,
                rejection_side="LOWER_WICK",
                wick_ratio=max_wick_ratio,
                reason="1H_SUPPORT_REJECTION_BELOW_EMA",
            )
        return Bias1HResult(
            bias="SELL",
            ema50=current_ema,
            slope_pct=slope_pct,
            deceleration=has_deceleration,
            rejection_side=recent_rejection,
            wick_ratio=max_wick_ratio,
            reason="1H_PRICE_BELOW_EMA50",
        )
