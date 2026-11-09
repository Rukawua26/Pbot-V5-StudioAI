"""Regime-Adaptive v4: route to trend-following in trending, mean-reversion in ranging.

Pure and causal. Callers pass CLOSED candles only. Regime is detected on 1H
(ADX14 + EMA50 slope). Rules pre-registered in odd/tasks/regime-adaptive-v4.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.strategy.mean_reversion import (
    MRParams,
    build_features as build_mr,
    signal_at as mr_signal,
)
from core.strategy.mtf_pullback import (
    MTFParams,
    build_features as build_mtf,
    signal_at as mtf_signal,
)

REGIME_TRENDING = "TRENDING"
REGIME_RANGING = "RANGING"
REGIME_NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class RAParams:
    adx_period_1h: int = 14
    adx_trending: float = 25.0
    adx_ranging: float = 20.0
    ema_1h: int = 50
    slope_lookback_1h: int = 6
    slope_trending_pct: float = 0.3
    slope_ranging_pct: float = 0.3
    mtf: MTFParams | None = None
    mr: MRParams | None = None

    def __post_init__(self):
        object.__setattr__(self, "mtf", self.mtf or MTFParams())
        object.__setattr__(self, "mr", self.mr or MRParams())


@dataclass
class RASignal:
    side: str  # BUY, SELL or WAIT
    reason: str
    regime: str
    entry_ref: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    setup_id: tuple | None = None
    max_hold_minutes: int | None = None


@dataclass
class RAFeatures:
    regime: np.ndarray  # +1 trending, -1 ranging, 0 neutral
    mtf: object  # MTFFeatures
    mr: object  # MRFeatures

    @property
    def close_time_ns(self) -> np.ndarray:
        """1M close times. Both engines are built from the same 1M frame."""
        return self.mtf.close_time_ns


def _ema(values: pd.Series, span: int) -> np.ndarray:
    return values.ewm(span=span, adjust=False).mean().to_numpy(float)


def _adx(df: pd.DataFrame, period: int) -> np.ndarray:
    from core.strategy.mean_reversion import adx as _adx_fn

    return _adx_fn(df, period)


def build_features(
    df_1h: pd.DataFrame,
    df_15m: pd.DataFrame,
    df_5m: pd.DataFrame,
    df_1m: pd.DataFrame,
    params: RAParams | None = None,
) -> RAFeatures:
    p = params or RAParams()
    c1h = df_1h["close"].astype(float)
    ema = _ema(c1h, p.ema_1h)
    lb = p.slope_lookback_1h
    ema_prev = (
        np.concatenate([np.full(lb, np.nan), ema[:-lb]])
        if len(ema) > lb
        else np.full(len(ema), np.nan)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        slope_pct = np.abs(ema / ema_prev - 1.0) * 100.0
    adx_vals = _adx(df_1h, p.adx_period_1h)

    # Align to 1M bars via latest closed 1H
    from core.strategy.mtf_pullback import _closes, _latest_closed

    now = _closes(df_1m, "1min")
    i1h = _latest_closed(_closes(df_1h, "1h"), now)
    safe = np.maximum(i1h, 0)

    a = adx_vals[safe]
    sp = slope_pct[safe]
    ok = (i1h >= p.adx_period_1h + lb) & np.isfinite(a) & np.isfinite(sp)
    trending = ok & (a >= p.adx_trending) & (sp >= p.slope_trending_pct)
    ranging = ok & (a < p.adx_ranging) & (sp < p.slope_ranging_pct)
    regime = np.where(trending, 1, np.where(ranging, -1, 0)).astype(int)

    mtf_feat = build_mtf(df_1h, df_15m, df_5m, df_1m, p.mtf)
    mr_feat = build_mr(df_1h, df_15m, df_5m, df_1m, p.mr)
    return RAFeatures(regime=regime, mtf=mtf_feat, mr=mr_feat)


def signal_at(
    feat: RAFeatures, i: int, params: RAParams | None = None, symbol: str = "Asset"
) -> RASignal:
    """Route by 1H regime. Pure: never consumes the setup."""
    p = params or RAParams()
    r = int(feat.regime[i])
    if r == 1:
        sig = mtf_signal(feat.mtf, i, p.mtf, symbol)
        if sig.side in {"BUY", "SELL"}:
            d = 1.0 if sig.side == "BUY" else -1.0
            target = sig.entry_ref + d * p.mtf.take_profit_r * abs(
                sig.entry_ref - sig.stop
            )
            return RASignal(
                sig.side,
                "RA_TREND_" + sig.reason,
                REGIME_TRENDING,
                sig.entry_ref,
                sig.stop,
                target,
                ("T",) + tuple(sig.setup_id or ()),
                p.mtf.max_hold_minutes,
            )
        return RASignal("WAIT", "RA_TREND_" + sig.reason, REGIME_TRENDING)
    if r == -1:
        sig = mr_signal(feat.mr, i, p.mr, symbol)
        if sig.side in {"BUY", "SELL"}:
            return RASignal(
                sig.side,
                "RA_RANGE_" + sig.reason,
                REGIME_RANGING,
                sig.entry_ref,
                sig.stop,
                sig.target,
                ("R",) + tuple(sig.setup_id or ()),
                p.mr.max_hold_minutes,
            )
        return RASignal("WAIT", "RA_RANGE_" + sig.reason, REGIME_RANGING)
    return RASignal("WAIT", "RA_NEUTRAL_REGIME", REGIME_NEUTRAL)
