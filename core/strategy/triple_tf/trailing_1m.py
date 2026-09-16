from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class Trailing1MResult:
    should_exit: bool
    current_ema50_1m: float
    current_close_1m: float
    current_r_multiple: float
    reason: str
    is_activated: bool = False


def compute_ema(series: pd.Series, span: int = 50) -> pd.Series:
    clean_series = series.ffill().bfill()
    return clean_series.ewm(span=span, adjust=False).mean()


def evaluate_trailing_1m(
    df_1m: pd.DataFrame | None,
    side: str,
    entry_price: float,
    sl_price: float,
    current_price: float,
    activation_r: float = 1.0,
    min_profit_pct: float = 0.002,
    trailing_already_activated: bool = False,
) -> Trailing1MResult:
    """Evalúa la salida dinámica por Trailing Stop de la EMA 50 en 1M.

    Reglas:
    1. Si el trade aún no alcanza el beneficio mínimo de activación (>= 1.0 R o >= min_profit_pct),
       no activa el trailing de 1M para evitar cortes por micro-ruido inicial.
    2. Una vez activado (o si ya venía activo por memoria de estado trailing_already_activated=True):
       - SHORT: Si la vela de 1M cierra por encima de la EMA 50 en 1M -> Cierre de posición.
       - LONG: Si la vela de 1M cierra por debajo de la EMA 50 en 1M -> Cierre de posición.
    """
    if df_1m is None or len(df_1m) < 50 or entry_price <= 0:
        return Trailing1MResult(
            should_exit=False,
            current_ema50_1m=0.0,
            current_close_1m=current_price,
            current_r_multiple=0.0,
            reason="DATA_INSUFFICIENT_1M_TRAILING",
            is_activated=bool(trailing_already_activated),
        )

    normalized_side = "BUY" if str(side).upper() in {"BUY", "LONG"} else "SELL"
    risk_distance = (
        abs(entry_price - sl_price) if sl_price > 0 else (entry_price * 0.02)
    )
    if risk_distance <= 0:
        risk_distance = entry_price * 0.01

    if normalized_side == "BUY":
        profit_distance = current_price - entry_price
        r_multiple = profit_distance / risk_distance
        profit_pct = (current_price - entry_price) / entry_price
    else:
        profit_distance = entry_price - current_price
        r_multiple = profit_distance / risk_distance
        profit_pct = (entry_price - current_price) / entry_price

    closes = df_1m["close"].astype(float)
    ema50_series = compute_ema(closes, span=50)
    current_close_1m = float(closes.iloc[-1])
    current_ema50_1m = float(ema50_series.iloc[-1])

    # Condición de activación: se activa al alcanzar al menos 1R de ganancia,
    # o bien permanece activo si ya se activó previamente (memoria de estado).
    was_already_activated = bool(trailing_already_activated)
    is_now_activated = r_multiple >= activation_r and profit_pct >= min_profit_pct
    is_activated = was_already_activated or is_now_activated

    if not is_activated:
        return Trailing1MResult(
            should_exit=False,
            current_ema50_1m=current_ema50_1m,
            current_close_1m=current_close_1m,
            current_r_multiple=r_multiple,
            reason="TRAILING_1M_NOT_YET_ACTIVATED",
            is_activated=False,
        )

    if normalized_side == "BUY":
        if current_close_1m < current_ema50_1m:
            return Trailing1MResult(
                should_exit=True,
                current_ema50_1m=current_ema50_1m,
                current_close_1m=current_close_1m,
                current_r_multiple=r_multiple,
                reason="TRAILING_1M_EMA50_CLOSE_BELOW",
                is_activated=True,
            )
    else:  # SELL
        if current_close_1m > current_ema50_1m:
            return Trailing1MResult(
                should_exit=True,
                current_ema50_1m=current_ema50_1m,
                current_close_1m=current_close_1m,
                current_r_multiple=r_multiple,
                reason="TRAILING_1M_EMA50_CLOSE_ABOVE",
                is_activated=True,
            )

    return Trailing1MResult(
        should_exit=False,
        current_ema50_1m=current_ema50_1m,
        current_close_1m=current_close_1m,
        current_r_multiple=r_multiple,
        reason="TRAILING_1M_POSITION_HEALTHY",
        is_activated=True,
    )
