"""Mean Reversion v3: 1H range regime, 15M Bollinger stretch, 5M confirmation, 1M entry.

Pure and causal. Callers pass CLOSED candles only (``time`` = bar open, UTC).
Indicators are computed per timeframe and aligned to each 1M bar through the
close time of the latest higher-timeframe bar that had already closed. Rules are
pre-registered in ``odd/tasks/mean-reversion-v3.md``.

Interpretation fixed with the code (pre-registration wording):
* Bollinger uses population std (ddof=0).
* The structural stop window is the 4 15M bars ending at the stretch bar, and
  ATR/target are read at the stretch bar.
* The 5M confirmation must close strictly after the stretch bar closed and no
  later than 30 minutes after it; the 1M entry bar closes at or after the
  confirmation and inside the same window.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.strategy.mtf_pullback import _closes, _ema, _latest_closed, _ns

NS_MIN = 60_000_000_000
NEVER = np.iinfo(np.int64).min


@dataclass(frozen=True)
class MRParams:
    adx_period_1h: int = 14
    adx_max_1h: float = 20.0
    ema_1h: int = 50
    ema_flat_lookback_1h: int = 6
    ema_flat_max_pct: float = 0.5
    bb_period_15m: int = 20
    bb_std_15m: float = 2.0
    stop_bars_15m: int = 4
    atr_period_15m: int = 14
    stop_atr_buffer: float = 0.1
    window_minutes: int = 30
    min_stop_pct: float = 0.4
    max_stop_pct: float = 2.5
    min_target_r: float = 1.0
    max_hold_minutes: int = 240
    session_start_utc: int = 7
    session_end_utc: int = 22


@dataclass
class MRSignal:
    side: str  # BUY, SELL or WAIT
    reason: str
    entry_ref: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    setup_id: tuple | None = None


@dataclass
class MRFeatures:
    close_time_ns: np.ndarray
    close_1m: np.ndarray
    candle_dir_1m: np.ndarray  # +1 close>open, -1 close<open, 0 doji
    range_1h: np.ndarray  # bool: 1H range regime
    stretch_close_ns: (
        np.ndarray
    )  # [2, n] latest long/short stretch close (NEVER if none)
    stretch_open_ns: np.ndarray  # [2, n]
    stop_base: np.ndarray  # [2, n] min low (long) / max high (short) of the stop window
    atr_15m: np.ndarray  # [2, n] ATR at the stretch bar
    target: np.ndarray  # [2, n] SMA20 at the stretch bar
    confirm_close_ns: np.ndarray  # [2, n] latest 5M confirmation close (NEVER if none)
    warm: np.ndarray


def _wilder(values: pd.Series, period: int) -> pd.Series:
    return values.ewm(alpha=1.0 / period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(
        axis=1
    )
    atr = _wilder(tr, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * _wilder(plus_dm, period) / atr
        minus_di = 100.0 * _wilder(minus_dm, period) / atr
        dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return _wilder(dx.fillna(0.0), period).to_numpy(float)


def _last_index(mask: np.ndarray) -> np.ndarray:
    idx = np.where(mask, np.arange(len(mask)), -1)
    return np.maximum.accumulate(idx) if len(idx) else idx


def build_features(
    df_1h: pd.DataFrame,
    df_15m: pd.DataFrame,
    df_5m: pd.DataFrame,
    df_1m: pd.DataFrame,
    params: MRParams | None = None,
) -> MRFeatures:
    p = params or MRParams()

    # 1H range regime
    c1h = df_1h["close"].astype(float)
    ema = _ema(c1h, p.ema_1h)
    lb = p.ema_flat_lookback_1h
    ema_prev = (
        np.concatenate([np.full(lb, np.nan), ema[:-lb]])
        if len(ema) > lb
        else np.full(len(ema), np.nan)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        flat = np.abs(ema / ema_prev - 1.0) * 100.0 < p.ema_flat_max_pct
    range_h = (adx(df_1h, p.adx_period_1h) < p.adx_max_1h) & flat

    # 15M Bollinger stretch, stop window, ATR and target at the stretch bar
    h15 = df_15m["high"].astype(float).to_numpy()
    l15 = df_15m["low"].astype(float).to_numpy()
    c15s = df_15m["close"].astype(float)
    c15 = c15s.to_numpy()
    sma = c15s.rolling(p.bb_period_15m).mean().to_numpy()
    std = c15s.rolling(p.bb_period_15m).std(ddof=0).to_numpy()
    stretch_long = c15 < sma - p.bb_std_15m * std
    stretch_short = c15 > sma + p.bb_std_15m * std
    w = p.stop_bars_15m
    low_win = pd.Series(l15).rolling(w).min().to_numpy()
    high_win = pd.Series(h15).rolling(w).max().to_numpy()
    prev_c = np.concatenate([[np.nan], c15[:-1]])
    tr = np.nanmax(
        np.vstack([h15 - l15, np.abs(h15 - prev_c), np.abs(l15 - prev_c)]), axis=0
    )
    atr15 = pd.Series(tr).rolling(p.atr_period_15m).mean().to_numpy()
    close15 = _closes(df_15m, "15min")
    open15 = _ns(df_15m["time"])

    # 5M confirmation: close beyond the previous bar's extreme
    h5 = df_5m["high"].astype(float).to_numpy()
    l5 = df_5m["low"].astype(float).to_numpy()
    c5 = df_5m["close"].astype(float).to_numpy()
    conf_long = c5 > np.concatenate([[np.inf], h5[:-1]])
    conf_short = c5 < np.concatenate([[-np.inf], l5[:-1]])
    close5 = _closes(df_5m, "5min")

    # 1M
    o1 = df_1m["open"].astype(float).to_numpy()
    c1 = df_1m["close"].astype(float).to_numpy()
    now = _closes(df_1m, "1min")
    n = len(now)

    i1h = _latest_closed(_closes(df_1h, "1h"), now)
    i15 = _latest_closed(close15, now)
    i5 = _latest_closed(close5, now)

    stretch_close = np.full((2, n), NEVER, dtype=np.int64)
    stretch_open = np.full((2, n), NEVER, dtype=np.int64)
    stop_base = np.full((2, n), np.nan)
    atr_at = np.full((2, n), np.nan)
    target = np.full((2, n), np.nan)
    confirm = np.full((2, n), NEVER, dtype=np.int64)
    for d, (smask, base, cmask) in enumerate(
        ((stretch_long, low_win, conf_long), (stretch_short, high_win, conf_short))
    ):
        last_s = _last_index(smask)
        ok = i15 >= 0
        s = np.where(ok, last_s[np.maximum(i15, 0)], -1)
        has = s >= 0
        sv = np.maximum(s, 0)
        stretch_close[d] = np.where(has, close15[sv], NEVER)
        stretch_open[d] = np.where(has, open15[sv], NEVER)
        stop_base[d] = np.where(has, base[sv], np.nan)
        atr_at[d] = np.where(has, atr15[sv], np.nan)
        target[d] = np.where(has, sma[sv], np.nan)
        last_c = _last_index(cmask)
        cidx = np.where(i5 >= 0, last_c[np.maximum(i5, 0)], -1)
        confirm[d] = np.where(cidx >= 0, close5[np.maximum(cidx, 0)], NEVER)

    warm = (
        (i1h >= max(p.ema_1h, 3 * p.adx_period_1h) + lb)
        & (i15 >= max(p.bb_period_15m, p.atr_period_15m, w))
        & (i5 >= 1)
    )
    return MRFeatures(
        close_time_ns=now,
        close_1m=c1,
        candle_dir_1m=np.sign(c1 - o1).astype(int),
        range_1h=np.where(i1h >= 0, range_h[np.maximum(i1h, 0)], False),
        stretch_close_ns=stretch_close,
        stretch_open_ns=stretch_open,
        stop_base=stop_base,
        atr_15m=atr_at,
        target=target,
        confirm_close_ns=confirm,
        warm=warm,
    )


def candidate_mask(feat: MRFeatures, params: MRParams | None = None) -> np.ndarray:
    """Cheap vectorised prefilter; ``signal_at`` remains the source of truth."""
    p = params or MRParams()
    window = p.window_minutes * NS_MIN
    out = np.zeros(len(feat.warm), dtype=bool)
    for d, direction in ((0, 1), (1, -1)):
        sc = feat.stretch_close_ns[d]
        cc = feat.confirm_close_ns[d]
        out |= (
            (sc != NEVER)
            & (cc > sc)
            & (cc <= sc + window)
            & (feat.close_time_ns <= sc + window)
            & (feat.candle_dir_1m == direction)
        )
    return out & feat.warm & feat.range_1h


def signal_at(
    feat: MRFeatures, i: int, params: MRParams | None = None, symbol: str = "Asset"
) -> MRSignal:
    """Decision on closed 1M bar ``i``. Pure: never consumes the setup."""
    p = params or MRParams()
    if not feat.warm[i]:
        return MRSignal("WAIT", "WARMUP")
    hour = int((int(feat.close_time_ns[i]) // 3_600_000_000_000) % 24)
    if not p.session_start_utc <= hour < p.session_end_utc:
        return MRSignal("WAIT", "SESSION_OUTSIDE_HOURS")
    if not feat.range_1h[i]:
        return MRSignal("WAIT", "REGIME_1H_NOT_RANGE")
    now = int(feat.close_time_ns[i])
    window = p.window_minutes * NS_MIN
    # Prefer the most recent stretch when both directions are inside the window.
    order = sorted((0, 1), key=lambda d: -int(feat.stretch_close_ns[d][i]))
    reason = "STRETCH_15M_NONE"
    for d in order:
        sc = int(feat.stretch_close_ns[d][i])
        if sc == NEVER or now > sc + window:
            continue
        direction = 1 if d == 0 else -1
        cc = int(feat.confirm_close_ns[d][i])
        if not sc < cc <= sc + window:
            reason = "CONFIRM_5M_NONE"
            continue
        if int(feat.candle_dir_1m[i]) != direction:
            reason = "ENTRY_1M_NONE"
            continue
        ref = float(feat.close_1m[i])
        buffer = p.stop_atr_buffer * float(feat.atr_15m[d][i])
        stop = float(feat.stop_base[d][i]) - direction * buffer
        target = float(feat.target[d][i])
        if not all(np.isfinite(v) for v in (ref, stop, target)) or ref <= 0:
            return MRSignal("WAIT", "STOP_INVALID")
        risk = (ref - stop) * direction
        stop_pct = risk / ref * 100.0
        if not p.min_stop_pct <= stop_pct <= p.max_stop_pct:
            return MRSignal("WAIT", "STOP_OUT_OF_RANGE", ref, stop, target)
        if (target - ref) * direction < p.min_target_r * risk:
            return MRSignal("WAIT", "TARGET_TOO_CLOSE", ref, stop, target)
        side = "BUY" if direction == 1 else "SELL"
        setup_id = (symbol, side, int(feat.stretch_open_ns[d][i]))
        return MRSignal(side, "MR_REVERSION_CONFIRMED", ref, stop, target, setup_id)
    return MRSignal("WAIT", reason)
