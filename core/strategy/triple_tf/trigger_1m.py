from dataclasses import dataclass
import pandas as pd

from core.strategy.triple_tf.closed_candles import _to_ms


@dataclass
class Trigger1MResult:
    triggered: bool
    side: str  # "BUY", "SELL", or "WAIT"
    entry_price: float
    ema50_1m: float
    reason: str
    trigger_time: int | None = None


def compute_ema(series: pd.Series, span: int = 50) -> pd.Series:
    clean_series = series.ffill().bfill()
    return clean_series.ewm(span=span, adjust=False).mean()


def evaluate_trigger_1m(
    df_1m: pd.DataFrame | None,
    bias_1h: str,
    setup_5m_valid: bool,
    spread: float = 0.0,
    max_spread_pct: float = 0.0010,
    fvg_zone: object | None = None,
) -> Trigger1MResult:
    """Evalúa el marco menor (1 Minuto / 1M) para el disparo de entrada."""
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

    times = df_1m["time"] if "time" in df_1m.columns else pd.Series(df_1m.index)
    trigger_time_val = _to_ms(times.iloc[-1])

    ema50_series = compute_ema(closes, span=50)
    current_close = float(closes.iloc[-1])
    current_high = float(highs.iloc[-1])
    current_low = float(lows.iloc[-1])
    current_ema = float(ema50_series.iloc[-1])

    # 1. Modo FVG: disparo por toque en zona + rechazo por mecha (wick rejection)
    if fvg_zone is not None:
        fvg_top = getattr(fvg_zone, "fvg_top", 0.0)
        fvg_bot = getattr(fvg_zone, "fvg_bot", 0.0)
        if bias_1h == "BUY":
            touches_fvg = current_low <= fvg_top and current_high >= fvg_bot
            wick_rejection = current_close > fvg_top
            if touches_fvg and wick_rejection:
                return Trigger1MResult(
                    triggered=True,
                    side="BUY",
                    entry_price=current_close,
                    ema50_1m=current_ema,
                    reason="1M_FVG_REJECTION_CONFIRMED",
                    trigger_time=trigger_time_val,
                )
            return Trigger1MResult(
                triggered=False,
                side="WAIT",
                entry_price=current_close,
                ema50_1m=current_ema,
                reason="1M_WAITING_FOR_FVG_REJECTION",
            )
        elif bias_1h == "SELL":
            touches_fvg = current_high >= fvg_bot and current_low <= fvg_top
            wick_rejection = current_close < fvg_bot
            if touches_fvg and wick_rejection:
                return Trigger1MResult(
                    triggered=True,
                    side="SELL",
                    entry_price=current_close,
                    ema50_1m=current_ema,
                    reason="1M_FVG_REJECTION_CONFIRMED",
                    trigger_time=trigger_time_val,
                )
            return Trigger1MResult(
                triggered=False,
                side="WAIT",
                entry_price=current_close,
                ema50_1m=current_ema,
                reason="1M_WAITING_FOR_FVG_REJECTION",
            )

    # 2. Modo Fallback: disparo por cruce de EMA 50 1M
    prev_close = float(closes.iloc[-2])
    prev_ema = float(ema50_series.iloc[-2])

    if bias_1h == "SELL":
        recent_highs = highs.iloc[-min(len(highs), 3) :]
        touched_or_above = prev_close >= prev_ema or any(
            float(h) >= current_ema for h in recent_highs
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
                trigger_time=trigger_time_val,
            )
        return Trigger1MResult(
            triggered=False,
            side="WAIT",
            entry_price=current_close,
            ema50_1m=current_ema,
            reason="1M_WAITING_FOR_EMA50_CROSS_BELOW",
        )

    else:  # BUY
        recent_lows = lows.iloc[-min(len(lows), 3) :]
        touched_or_below = prev_close <= prev_ema or any(
            float(low_val) <= current_ema for low_val in recent_lows
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
                trigger_time=trigger_time_val,
            )
        return Trigger1MResult(
            triggered=False,
            side="WAIT",
            entry_price=current_close,
            ema50_1m=current_ema,
            reason="1M_WAITING_FOR_EMA50_CROSS_ABOVE",
        )
