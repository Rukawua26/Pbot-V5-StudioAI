from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class Trigger1MResult:
    triggered: bool
    side: str  # "BUY", "SELL", or "WAIT"
    entry_price: float
    ema50_1m: float
    reason: str


def compute_ema(series: pd.Series, span: int = 50) -> pd.Series:
    clean_series = series.ffill().bfill()
    return clean_series.ewm(span=span, adjust=False).mean()


def evaluate_trigger_1m(
    df_1m: pd.DataFrame | None,
    bias_1h: str,
    setup_5m_valid: bool,
    spread: float = 0.0,
    max_spread_pct: float = 0.0010,
) -> Trigger1MResult:
    """Evalúa el marco menor (1 Minuto / 1M) para el disparo de entrada.

    Reglas:
    - Solo evalúa si bias_1h es direccional y setup_5m_valid es True.
    - SHORT: La última vela confirmada de 1M (o cierre actual) cruza o cierra por debajo de la EMA 50 de 1M.
    - LONG: La última vela confirmada de 1M cruza o cierra por encima de la EMA 50 de 1M.
    - Filtro de spread para evitar ejecuciones con slippage excesivo.
    """
    if not setup_5m_valid or bias_1h not in {"BUY", "SELL"}:
        return Trigger1MResult(
            triggered=False,
            side="WAIT",
            entry_price=0.0,
            ema50_1m=0.0,
            reason="SETUP_5M_NOT_VALID",
        )

    if spread > max_spread_pct:
        return Trigger1MResult(
            triggered=False,
            side="WAIT",
            entry_price=0.0,
            ema50_1m=0.0,
            reason="SPREAD_TOO_HIGH_FOR_1M_TRIGGER",
        )

    if df_1m is None or len(df_1m) < 50:
        return Trigger1MResult(
            triggered=False,
            side="WAIT",
            entry_price=0.0,
            ema50_1m=0.0,
            reason="DATA_INSUFFICIENT_1M",
        )

    closes = df_1m["close"].astype(float)
    highs = df_1m["high"].astype(float) if "high" in df_1m.columns else closes
    lows = df_1m["low"].astype(float) if "low" in df_1m.columns else closes

    ema50_series = compute_ema(closes, span=50)
    current_close = float(closes.iloc[-1])
    current_ema = float(ema50_series.iloc[-1])

    # Revisamos confirmación de cruce o rebote reciente (últimas 2-3 velas)
    prev_close = float(closes.iloc[-2])
    prev_ema = float(ema50_series.iloc[-2])

    if bias_1h == "SELL":
        # Disparo en venta: cierre actual por debajo de EMA 50 de 1M
        # habiendo testeado o cruzado la EMA 50 en las últimas velas (sin sobreextensión)
        recent_highs = highs.iloc[-min(len(highs), 3) :]
        touched_or_above = prev_close >= (prev_ema * 0.9995) or any(
            float(h) >= (current_ema * 0.9995) for h in recent_highs
        )
        not_overextended = current_close >= (current_ema * 0.994)
        crossed_below = (
            current_close < current_ema and touched_or_above and not_overextended
        )

        if crossed_below:
            return Trigger1MResult(
                triggered=True,
                side="SELL",
                entry_price=current_close,
                ema50_1m=current_ema,
                reason="1M_EMA50_CROSS_BELOW_CONFIRMED",
            )
        return Trigger1MResult(
            triggered=False,
            side="WAIT",
            entry_price=current_close,
            ema50_1m=current_ema,
            reason="1M_WAITING_FOR_EMA50_CROSS_BELOW",
        )

    else:  # BUY
        # Disparo en compra: cierre actual por encima de EMA 50 de 1M
        # habiendo testeado o cruzado la EMA 50 en las últimas velas (sin sobreextensión)
        recent_lows = lows.iloc[-min(len(lows), 3) :]
        touched_or_below = prev_close <= (prev_ema * 1.0005) or any(
            float(low_val) <= (current_ema * 1.0005) for low_val in recent_lows
        )
        not_overextended = current_close <= (current_ema * 1.006)
        crossed_above = (
            current_close > current_ema and touched_or_below and not_overextended
        )

        if crossed_above:
            return Trigger1MResult(
                triggered=True,
                side="BUY",
                entry_price=current_close,
                ema50_1m=current_ema,
                reason="1M_EMA50_CROSS_ABOVE_CONFIRMED",
            )
        return Trigger1MResult(
            triggered=False,
            side="WAIT",
            entry_price=current_close,
            ema50_1m=current_ema,
            reason="1M_WAITING_FOR_EMA50_CROSS_ABOVE",
        )
