"""MTF Pullback v2: 1H context, 15M pullback setup, 5M confirmation, 1M entry.

Pure and causal. Callers pass CLOSED candles only (``time`` = bar open, UTC).
Every indicator is computed per timeframe and aligned to each 1M bar through the
close time of the latest higher-timeframe bar that had already closed, so the
same code serves the offline backtest (every 1M bar) and a live caller (last
bar). Rules are pre-registered in ``odd/tasks/mtf-pullback-v2.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TIMEFRAMES = {"1h": "1h", "15m": "15min", "5m": "5min", "1m": "1min"}


@dataclass(frozen=True)
class MTFParams:
    ema_fast_1h: int = 50
    ema_slow_1h: int = 200
    slope_lookback_1h: int = 3
    ema_fast_15m: int = 20
    ema_slow_15m: int = 50
    pullback_bars_15m: int = 4
    atr_period_15m: int = 14
    stop_atr_buffer: float = 0.1
    ema_5m: int = 20
    confirm_max_age_minutes: int = 15
    ema_1m: int = 9
    min_stop_pct: float = 0.5
    max_stop_pct: float = 2.5
    take_profit_r: float = 1.5
    max_hold_minutes: int = 480
    session_start_utc: int = 7
    session_end_utc: int = 22


@dataclass
class MTFSignal:
    side: str  # BUY, SELL or WAIT
    reason: str
    entry_ref: float = 0.0
    stop: float = 0.0
    setup_id: tuple | None = None


@dataclass
class MTFFeatures:
    """Per-1M-bar aligned arrays. Index ``i`` is a closed 1M bar."""

    close_time_ns: np.ndarray
    close_1m: np.ndarray
    ctx: np.ndarray  # +1 long, -1 short, 0 none
    setup: np.ndarray  # +1 long setup, -1 short setup, 0 none (latest closed 15M)
    swing: np.ndarray  # swing low (long) / swing high (short) of the pullback
    swing_time_ns: np.ndarray
    atr_15m: np.ndarray
    confirm_age_long_ns: np.ndarray  # now - close of latest long 5M confirmation
    confirm_age_short_ns: np.ndarray
    trigger: np.ndarray  # +1 close>EMA9, -1 close<EMA9 on the 1M bar
    idx_1h: np.ndarray
    idx_15m: np.ndarray
    idx_5m: np.ndarray
    warm: np.ndarray  # enough history on every timeframe


def _ns(times: pd.Series) -> np.ndarray:
    t = pd.to_datetime(times, utc=True)
    return t.dt.tz_localize(None).to_numpy("datetime64[ns]").astype(np.int64)


def _ema(values: pd.Series, span: int) -> np.ndarray:
    return values.ewm(span=span, adjust=False).mean().to_numpy(float)


def _closes(df: pd.DataFrame, rule: str) -> np.ndarray:
    return _ns(df["time"]) + pd.Timedelta(rule).value


def _latest_closed(close_ns: np.ndarray, now_ns: np.ndarray) -> np.ndarray:
    """Index of the latest bar with close <= now (-1 if none)."""
    return np.searchsorted(close_ns, now_ns, side="right") - 1


def build_features(
    df_1h: pd.DataFrame,
    df_15m: pd.DataFrame,
    df_5m: pd.DataFrame,
    df_1m: pd.DataFrame,
    params: MTFParams | None = None,
) -> MTFFeatures:
    p = params or MTFParams()

    # 1H context
    c1h = df_1h["close"].astype(float)
    e_fast = _ema(c1h, p.ema_fast_1h)
    e_slow = _ema(c1h, p.ema_slow_1h)
    slope = e_fast - np.concatenate(
        [np.full(p.slope_lookback_1h, np.nan), e_fast[: -p.slope_lookback_1h]]
    )
    c1 = c1h.to_numpy(float)
    ctx_1h = np.where(
        (c1 > e_slow) & (e_fast > e_slow) & (slope > 0),
        1,
        np.where((c1 < e_slow) & (e_fast < e_slow) & (slope < 0), -1, 0),
    )

    # 15M setup: trend + pullback to EMA20 without closing beyond EMA50
    h15 = df_15m["high"].astype(float)
    l15 = df_15m["low"].astype(float)
    c15 = df_15m["close"].astype(float)
    e20 = _ema(c15, p.ema_fast_15m)
    e50 = _ema(c15, p.ema_slow_15m)
    w = p.pullback_bars_15m

    def _all(mask: np.ndarray) -> np.ndarray:
        return pd.Series(mask.astype(float)).rolling(w).min().to_numpy() == 1.0

    def _any(mask: np.ndarray) -> np.ndarray:
        return pd.Series(mask.astype(float)).rolling(w).max().to_numpy() == 1.0

    hv, lv, cv = h15.to_numpy(float), l15.to_numpy(float), c15.to_numpy(float)
    long_setup = (e20 > e50) & _any(lv <= e20) & _all(cv >= e50)
    short_setup = (e20 < e50) & _any(hv >= e20) & _all(cv <= e50)
    setup_15 = np.where(long_setup, 1, np.where(short_setup, -1, 0))
    n15 = len(df_15m)
    swing_low = np.full(n15, np.nan)
    swing_high = np.full(n15, np.nan)
    low_pos = np.zeros(n15, dtype=np.int64)
    high_pos = np.zeros(n15, dtype=np.int64)
    if n15 >= w:
        lw = np.lib.stride_tricks.sliding_window_view(lv, w)
        hw = np.lib.stride_tricks.sliding_window_view(hv, w)
        swing_low[w - 1 :] = lw.min(axis=1)
        swing_high[w - 1 :] = hw.max(axis=1)
        low_pos[w - 1 :] = np.arange(n15 - w + 1) + lw.argmin(axis=1)
        high_pos[w - 1 :] = np.arange(n15 - w + 1) + hw.argmax(axis=1)
    prev_c = np.concatenate([[np.nan], cv[:-1]])
    tr = np.nanmax(
        np.vstack([hv - lv, np.abs(hv - prev_c), np.abs(lv - prev_c)]), axis=0
    )
    atr = pd.Series(tr).rolling(p.atr_period_15m).mean().to_numpy()
    open15_ns = _ns(df_15m["time"])

    # 5M confirmation: break of the previous bar's extreme, on the trend side of EMA20
    h5 = df_5m["high"].astype(float).to_numpy()
    l5 = df_5m["low"].astype(float).to_numpy()
    c5s = df_5m["close"].astype(float)
    c5 = c5s.to_numpy()
    e5 = _ema(c5s, p.ema_5m)
    prev_h = np.concatenate([[np.inf], h5[:-1]])
    prev_l = np.concatenate([[-np.inf], l5[:-1]])
    conf_long = (c5 > prev_h) & (c5 > e5)
    conf_short = (c5 < prev_l) & (c5 < e5)
    close5_ns = _closes(df_5m, TIMEFRAMES["5m"])

    def _last_true_close(mask: np.ndarray) -> np.ndarray:
        idx = np.where(mask, np.arange(len(mask)), -1)
        idx = np.maximum.accumulate(idx) if len(idx) else idx
        return np.where(idx >= 0, close5_ns[np.maximum(idx, 0)], np.iinfo(np.int64).min)

    last_long_ns = _last_true_close(conf_long)
    last_short_ns = _last_true_close(conf_short)

    # 1M trigger
    c1ms = df_1m["close"].astype(float)
    c1m = c1ms.to_numpy()
    e9 = _ema(c1ms, p.ema_1m)
    trig = np.where(c1m > e9, 1, np.where(c1m < e9, -1, 0))
    now = _closes(df_1m, TIMEFRAMES["1m"])

    i1h = _latest_closed(_closes(df_1h, TIMEFRAMES["1h"]), now)
    i15 = _latest_closed(_closes(df_15m, TIMEFRAMES["15m"]), now)
    i5 = _latest_closed(close5_ns, now)
    warm = (
        (i1h >= p.ema_slow_1h)
        & (i15 >= max(p.ema_slow_15m, p.atr_period_15m, w))
        & (i5 >= p.ema_5m)
        & (np.arange(len(now)) >= p.ema_1m)
    )
    s1h, s15, s5 = np.maximum(i1h, 0), np.maximum(i15, 0), np.maximum(i5, 0)
    setup = np.where(i15 >= 0, setup_15[s15], 0)
    swing = np.where(setup == 1, swing_low[s15], swing_high[s15])
    swing_pos = np.where(setup == 1, low_pos[s15], high_pos[s15])
    with np.errstate(over="ignore"):
        age_long = np.where(i5 >= 0, now - last_long_ns[s5], np.iinfo(np.int64).max)
        age_short = np.where(i5 >= 0, now - last_short_ns[s5], np.iinfo(np.int64).max)
    age_long = np.where(age_long < 0, np.iinfo(np.int64).max, age_long)
    age_short = np.where(age_short < 0, np.iinfo(np.int64).max, age_short)
    return MTFFeatures(
        close_time_ns=now,
        close_1m=c1m,
        ctx=np.where(i1h >= 0, ctx_1h[s1h], 0),
        setup=setup,
        swing=swing,
        swing_time_ns=open15_ns[swing_pos] if n15 else np.zeros(len(now), np.int64),
        atr_15m=np.where(i15 >= 0, atr[s15], np.nan),
        confirm_age_long_ns=age_long,
        confirm_age_short_ns=age_short,
        trigger=trig,
        idx_1h=i1h,
        idx_15m=i15,
        idx_5m=i5,
        warm=warm,
    )


def signal_at(
    feat: MTFFeatures, i: int, params: MTFParams | None = None, symbol: str = "Asset"
) -> MTFSignal:
    """Decision on closed 1M bar ``i``. Pure: never consumes the setup."""
    p = params or MTFParams()
    if not feat.warm[i]:
        return MTFSignal("WAIT", "WARMUP")
    hour = int((int(feat.close_time_ns[i]) // 3_600_000_000_000) % 24)
    if not p.session_start_utc <= hour < p.session_end_utc:
        return MTFSignal("WAIT", "SESSION_OUTSIDE_HOURS")
    ctx = int(feat.ctx[i])
    if ctx == 0:
        return MTFSignal("WAIT", "CONTEXT_1H_NONE")
    if int(feat.setup[i]) != ctx:
        return MTFSignal("WAIT", "SETUP_15M_NONE")
    age = feat.confirm_age_long_ns[i] if ctx == 1 else feat.confirm_age_short_ns[i]
    if age > p.confirm_max_age_minutes * 60_000_000_000:
        return MTFSignal("WAIT", "CONFIRM_5M_NONE")
    if int(feat.trigger[i]) != ctx:
        return MTFSignal("WAIT", "TRIGGER_1M_NONE")
    ref = float(feat.close_1m[i])
    buffer = p.stop_atr_buffer * float(feat.atr_15m[i])
    stop = float(feat.swing[i]) - buffer if ctx == 1 else float(feat.swing[i]) + buffer
    if not (np.isfinite(stop) and np.isfinite(ref) and ref > 0):
        return MTFSignal("WAIT", "STOP_INVALID")
    stop_pct = (ref - stop) / ref * 100.0 * ctx
    if not p.min_stop_pct <= stop_pct <= p.max_stop_pct:
        return MTFSignal("WAIT", "STOP_OUT_OF_RANGE", ref, stop)
    side = "BUY" if ctx == 1 else "SELL"
    setup_id = (symbol, side, int(feat.swing_time_ns[i]))
    return MTFSignal(side, "MTF_PULLBACK_CONFIRMED", ref, stop, setup_id)
