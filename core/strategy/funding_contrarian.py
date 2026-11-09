"""Funding-Rate Contrarian v5: extreme 8h funding as a contrarian signal.

Pure and causal. Funding rate is a market-microstructure signal, not a price
pattern. High positive funding = overleveraged longs -> short bias.
High negative funding = overleveraged shorts -> long bias.
Rules pre-registered in odd/tasks/funding-contrarian-v5.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FCParams:
    funding_threshold: float = 0.0001  # 0.01% in decimal (0.05% produced <1% of bars)
    atr_period_1h: int = 14
    stop_atr_mult: float = 1.5
    min_stop_pct: float = 0.5
    max_stop_pct: float = 5.0
    take_profit_r: float = 1.0
    max_hold_hours: int = 24
    session_start_utc: int = 7
    session_end_utc: int = 22


@dataclass
class FCSignal:
    side: str  # BUY, SELL or WAIT
    reason: str
    entry_ref: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    setup_id: tuple | None = None
    max_hold_minutes: int | None = None


@dataclass
class FCFeatures:
    close_time_ns: np.ndarray
    close_1h: np.ndarray
    atr_1h: np.ndarray
    funding: np.ndarray  # funding rate aligned to each 1H bar
    funding_extreme: (
        np.ndarray
    )  # +1 short bias (high positive), -1 long bias (high negative), 0 none
    warm: np.ndarray


def _atr(df: pd.DataFrame, period: int) -> np.ndarray:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(
        axis=1
    )
    return tr.rolling(period).mean().to_numpy(float)


def build_features(
    df_1h: pd.DataFrame,
    funding_df: pd.DataFrame,
    params: FCParams | None = None,
) -> FCFeatures:
    """Align 8h funding rates to 1H bars. A funding entry applies to all 1H bars
    whose close time is >= the funding time and < the next funding time."""
    p = params or FCParams()
    close = df_1h["close"].astype(float).to_numpy()
    close_time = pd.to_datetime(df_1h["time"], utc=True)
    close_ns = (
        close_time.dt.tz_localize(None).to_numpy("datetime64[ns]").astype(np.int64)
    )

    # ATR on 1H
    atr = _atr(df_1h, p.atr_period_1h)

    # Align funding: each funding rate applies from its timestamp forward
    funding = np.full(len(df_1h), np.nan)
    if funding_df is not None and not funding_df.empty:
        fdf = funding_df.copy()
        fdf["time"] = pd.to_datetime(fdf["fundingTime"], unit="ms", utc=True)
        fdf = fdf.sort_values("time").reset_index(drop=True)
        f_times = (
            fdf["time"].dt.tz_localize(None).to_numpy("datetime64[ns]").astype(np.int64)
        )
        f_rates = fdf["fundingRate"].astype(float).to_numpy()
        # For each 1H bar, find the latest funding with time <= bar close
        idx = np.searchsorted(f_times, close_ns, side="right") - 1
        valid = idx >= 0
        funding[valid] = f_rates[idx[valid]]

    # Extreme detection
    extreme = np.zeros(len(df_1h), dtype=int)
    valid_mask = np.isfinite(funding)
    extreme[valid_mask & (funding > p.funding_threshold)] = 1  # short bias
    extreme[valid_mask & (funding < -p.funding_threshold)] = -1  # long bias

    warm = (
        np.isfinite(atr)
        & np.isfinite(funding)
        & (np.arange(len(df_1h)) >= p.atr_period_1h)
    )

    return FCFeatures(
        close_time_ns=close_ns,
        close_1h=close,
        atr_1h=atr,
        funding=funding,
        funding_extreme=extreme,
        warm=warm,
    )


def signal_at(
    feat: FCFeatures, i: int, params: FCParams | None = None, symbol: str = "Asset"
) -> FCSignal:
    p = params or FCParams()
    if not feat.warm[i]:
        return FCSignal("WAIT", "WARMUP")
    hour = int((int(feat.close_time_ns[i]) // 3_600_000_000_000) % 24)
    if not p.session_start_utc <= hour < p.session_end_utc:
        return FCSignal("WAIT", "SESSION_OUTSIDE_HOURS")
    extreme = int(feat.funding_extreme[i])
    if extreme == 0:
        return FCSignal("WAIT", "FUNDING_NOT_EXTREME")
    ref = float(feat.close_1h[i])
    atr = float(feat.atr_1h[i])
    if not (np.isfinite(ref) and ref > 0 and np.isfinite(atr) and atr > 0):
        return FCSignal("WAIT", "INVALID_ATR")
    direction = -1 if extreme == 1 else 1  # contrarian: high positive funding -> short
    stop = (
        ref - direction * p.stop_atr_mult * atr
    )  # for long: ref - mult*atr; for short: ref + mult*atr
    # Actually: long stop = ref - mult*atr, short stop = ref + mult*atr
    if direction == 1:
        stop = ref - p.stop_atr_mult * atr
    else:
        stop = ref + p.stop_atr_mult * atr
    risk = (ref - stop) * direction
    stop_pct = risk / ref * 100.0
    if not p.min_stop_pct <= stop_pct <= p.max_stop_pct:
        return FCSignal("WAIT", "STOP_OUT_OF_RANGE", ref, stop)
    target = ref + direction * p.take_profit_r * risk
    setup_id = (symbol, "BUY" if direction == 1 else "SELL", int(feat.close_time_ns[i]))
    side = "BUY" if direction == 1 else "SELL"
    return FCSignal(
        side, "FC_FUNDING_EXTREME", ref, stop, target, setup_id, p.max_hold_hours * 60
    )
