from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from core.strategy.triple_tf.closed_candles import _to_ms


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
    mss_time: int | None = None
    pullback_time: int | None = None


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
    max_setup_minutes: int = 15,
) -> Structure5MResult:
    """Evalúa el marco intermedio (5 Minutos / 5M) para Cambio de Estructura (MSS) y Pullback a EMA 50."""
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
    times = df_5m["time"] if "time" in df_5m.columns else pd.Series(df_5m.index)

    ema50_series = compute_ema(closes, span=50)
    current_ema = float(ema50_series.iloc[-1])

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

    mss_time = None
    pullback_time = None
    now_ms = _to_ms(times.iloc[-1])
    max_setup_ms = max_setup_minutes * 60 * 1000

    if bias_1h == "SELL":
        mss_confirmed = False
        for i, c in recent_closes.items():
            if float(c) < swing_low:
                mss_confirmed = True
                mss_time = _to_ms(times[i])
                break
        if not mss_confirmed and float(closes.iloc[-2]) < swing_low:
            mss_confirmed = True
            mss_time = _to_ms(times.iloc[-2])

        touch_boundary = current_ema * (1.0 - touch_tolerance_pct)
        pullback_touched = False
        for i, h in recent_highs.iloc[-recent_touch_lookback:].items():
            if float(h) >= touch_boundary:
                cand_time = _to_ms(times[i])
                pullback_touched = True
                pullback_time = cand_time
                if (
                    mss_time is not None
                    and cand_time is not None
                    and cand_time > mss_time
                ):
                    break

        valid_highs = [
            float(v)
            for v in [pullback_swing_high, current_ema * 1.002]
            if float(v) > 0.0
        ]
        suggested_sl = max(valid_highs) if valid_highs else float(current_ema * 1.002)

        valid = mss_confirmed and pullback_touched
        reason = "5M_SHORT_SETUP_CONFIRMED"
        if not mss_confirmed:
            reason = "5M_SHORT_MSS_FAILED"
        elif not pullback_touched:
            reason = "5M_SHORT_PULLBACK_NOT_TOUCHED"

        if valid:
            if (
                mss_time is not None
                and pullback_time is not None
                and pullback_time <= mss_time
            ):
                valid = False
                reason = "5M_PULLBACK_BEFORE_MSS"
            elif (
                pullback_time is not None
                and now_ms is not None
                and (now_ms - pullback_time > max_setup_ms)
            ):
                valid = False
                reason = "5M_SETUP_EXPIRED"

        return Structure5MResult(
            valid_setup=valid,
            mss_confirmed=mss_confirmed,
            pullback_touched=pullback_touched,
            ema50_5m=current_ema,
            suggested_sl=suggested_sl,
            swing_high=pullback_swing_high,
            swing_low=swing_low,
            reason=reason,
            mss_time=mss_time,
            pullback_time=pullback_time,
        )

    else:
        mss_confirmed = False
        for i, c in recent_closes.items():
            if float(c) > swing_high:
                mss_confirmed = True
                mss_time = _to_ms(times[i])
                break
        if not mss_confirmed and float(closes.iloc[-2]) > swing_high:
            mss_confirmed = True
            mss_time = _to_ms(times.iloc[-2])

        touch_boundary = current_ema * (1.0 + touch_tolerance_pct)
        pullback_touched = False
        for i, low_val in recent_lows.iloc[-recent_touch_lookback:].items():
            if float(low_val) <= touch_boundary:
                cand_time = _to_ms(times[i])
                pullback_touched = True
                pullback_time = cand_time
                if (
                    mss_time is not None
                    and cand_time is not None
                    and cand_time > mss_time
                ):
                    break

        valid_lows = [
            float(v)
            for v in [pullback_swing_low, current_ema * 0.998]
            if float(v) > 0.0
        ]
        suggested_sl = min(valid_lows) if valid_lows else float(current_ema * 0.998)

        valid = mss_confirmed and pullback_touched
        reason = "5M_LONG_SETUP_CONFIRMED"
        if not mss_confirmed:
            reason = "5M_LONG_MSS_FAILED"
        elif not pullback_touched:
            reason = "5M_LONG_PULLBACK_NOT_TOUCHED"

        if valid:
            if (
                mss_time is not None
                and pullback_time is not None
                and pullback_time <= mss_time
            ):
                valid = False
                reason = "5M_PULLBACK_BEFORE_MSS"
            elif (
                pullback_time is not None
                and now_ms is not None
                and (now_ms - pullback_time > max_setup_ms)
            ):
                valid = False
                reason = "5M_SETUP_EXPIRED"

        return Structure5MResult(
            valid_setup=valid,
            mss_confirmed=mss_confirmed,
            pullback_touched=pullback_touched,
            ema50_5m=current_ema,
            suggested_sl=suggested_sl,
            swing_high=swing_high,
            swing_low=pullback_swing_low,
            reason=reason,
            mss_time=mss_time,
            pullback_time=pullback_time,
        )
