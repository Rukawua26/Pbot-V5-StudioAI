import unittest
from dataclasses import replace

import numpy as np
import pandas as pd

from core.strategy.mtf_pullback import (
    MTFFeatures,
    MTFParams,
    build_features,
    signal_at,
)
from tools.ttf_backtest import resample_closed


def candles(minutes=60 * 24 * 12, seed=7, drift=0.00004):
    rng = np.random.default_rng(seed)
    t = pd.date_range("2026-01-01", periods=minutes, freq="min", tz="UTC")
    steps = drift + 0.0012 * rng.standard_normal(minutes)
    close = 100 * np.exp(np.cumsum(steps))
    open_ = np.concatenate([[100.0], close[:-1]])
    spread = np.abs(rng.standard_normal(minutes)) * 0.0006 * close
    return pd.DataFrame(
        {
            "time": t,
            "open": open_,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
            "close": close,
            "volume": 1000.0,
        }
    )


def frames(df):
    return (
        resample_closed(df, "1h"),
        resample_closed(df, "15min"),
        resample_closed(df, "5min"),
        df,
    )


def feat(**overrides):
    base = dict(
        close_time_ns=np.array([pd.Timestamp("2026-01-01T12:00Z").value]),
        close_1m=np.array([100.0]),
        ctx=np.array([1]),
        setup=np.array([1]),
        swing=np.array([99.0]),
        swing_time_ns=np.array([123]),
        atr_15m=np.array([1.0]),
        confirm_age_long_ns=np.array([5 * 60_000_000_000]),
        confirm_age_short_ns=np.array([np.iinfo(np.int64).max]),
        trigger=np.array([1]),
        idx_1h=np.array([300]),
        idx_15m=np.array([300]),
        idx_5m=np.array([300]),
        warm=np.array([True]),
    )
    for key, value in overrides.items():
        base[key] = np.array([value])
    return MTFFeatures(**base)


class MTFSignalRulesTests(unittest.TestCase):
    def test_long_signal_with_structural_stop(self):
        s = signal_at(feat(), 0, symbol="SOLUSDT")
        self.assertEqual(s.side, "BUY")
        self.assertEqual(s.reason, "MTF_PULLBACK_CONFIRMED")
        self.assertAlmostEqual(s.stop, 99.0 - 0.1)  # swing - 0.1*ATR
        self.assertEqual(s.setup_id, ("SOLUSDT", "BUY", 123))

    def test_short_signal_mirrors_long(self):
        s = signal_at(
            feat(
                ctx=-1,
                setup=-1,
                swing=101.0,
                trigger=-1,
                confirm_age_long_ns=np.iinfo(np.int64).max,
                confirm_age_short_ns=60_000_000_000,
            ),
            0,
        )
        self.assertEqual(s.side, "SELL")
        self.assertAlmostEqual(s.stop, 101.1)

    def test_each_layer_vetoes(self):
        cases = {
            "WARMUP": dict(warm=False),
            "CONTEXT_1H_NONE": dict(ctx=0),
            "SETUP_15M_NONE": dict(setup=-1),
            "CONFIRM_5M_NONE": dict(confirm_age_long_ns=16 * 60_000_000_000),
            "TRIGGER_1M_NONE": dict(trigger=-1),
            "SESSION_OUTSIDE_HOURS": dict(
                close_time_ns=pd.Timestamp("2026-01-01T22:00Z").value
            ),
        }
        for reason, override in cases.items():
            with self.subTest(reason=reason):
                s = signal_at(feat(**override), 0)
                self.assertEqual((s.side, s.reason), ("WAIT", reason))

    def test_confirmation_age_boundary_is_inclusive(self):
        self.assertEqual(
            signal_at(feat(confirm_age_long_ns=15 * 60_000_000_000), 0).side, "BUY"
        )

    def test_stop_range_boundaries(self):
        # stop pct = (100 - (swing - 0.1)) / 100 * 100
        self.assertEqual(signal_at(feat(swing=99.6), 0).side, "BUY")  # 0.5%
        self.assertEqual(signal_at(feat(swing=97.6), 0).side, "BUY")  # 2.5%
        self.assertEqual(
            signal_at(feat(swing=99.7), 0).reason, "STOP_OUT_OF_RANGE"
        )  # 0.4%
        self.assertEqual(
            signal_at(feat(swing=97.5), 0).reason, "STOP_OUT_OF_RANGE"
        )  # 2.6%
        self.assertEqual(signal_at(feat(atr_15m=np.nan), 0).reason, "STOP_INVALID")

    def test_session_start_is_inclusive(self):
        s = signal_at(feat(close_time_ns=pd.Timestamp("2026-01-01T07:00Z").value), 0)
        self.assertEqual(s.side, "BUY")


class MTFFeatureCausalityTests(unittest.TestCase):
    def test_future_candles_never_change_past_features(self):
        df = candles()
        cut = len(df) - 60 * 24 * 2
        full = build_features(*frames(df))
        past = build_features(*frames(df.iloc[:cut].reset_index(drop=True)))
        # Exclude bars whose higher-TF aggregate is still forming in the truncated set.
        safe = cut - 60
        for name in (
            "ctx",
            "setup",
            "swing",
            "atr_15m",
            "confirm_age_long_ns",
            "confirm_age_short_ns",
            "trigger",
            "warm",
        ):
            with self.subTest(name=name):
                np.testing.assert_array_equal(
                    getattr(full, name)[:safe], getattr(past, name)[:safe]
                )

    def test_higher_timeframes_only_use_closed_bars(self):
        df = candles(minutes=60 * 24 * 10)
        h1, m15, m5, m1 = frames(df)
        f = build_features(h1, m15, m5, m1)
        now = f.close_time_ns
        close_1h = (
            h1["time"].dt.tz_localize(None).to_numpy("datetime64[ns]").astype(np.int64)
            + pd.Timedelta("1h").value
        )
        close_15 = (
            m15["time"].dt.tz_localize(None).to_numpy("datetime64[ns]").astype(np.int64)
            + pd.Timedelta("15min").value
        )
        ok = f.idx_1h >= 0
        self.assertTrue((close_1h[f.idx_1h[ok]] <= now[ok]).all())
        nxt = np.minimum(f.idx_1h[ok] + 1, len(close_1h) - 1)
        self.assertTrue(
            ((close_1h[nxt] > now[ok]) | (f.idx_1h[ok] == len(close_1h) - 1)).all()
        )
        ok15 = f.idx_15m >= 0
        self.assertTrue((close_15[f.idx_15m[ok15]] <= now[ok15]).all())

    def test_trending_market_produces_only_trend_side_signals(self):
        # Moderate uptrend: pullbacks to EMA20(15M) exist (a parabolic trend has none).
        up = build_features(*frames(candles(drift=0.00008)))
        sides = {signal_at(up, i).side for i in range(len(up.warm)) if up.warm[i]}
        self.assertIn("BUY", sides)
        self.assertNotIn("SELL", sides)
        down = build_features(*frames(candles(drift=-0.00008)))
        sides = {signal_at(down, i).side for i in range(len(down.warm)) if down.warm[i]}
        self.assertIn("SELL", sides)
        self.assertNotIn("BUY", sides)

    def test_1h_context_requires_rising_ema_slope(self):
        # Long uptrend then a flat-but-above-EMA200 drift lower: EMA50 slope turns
        # negative while close/EMA50 stay above EMA200 -> context must drop to 0.
        up = candles(minutes=60 * 24 * 14, drift=0.00008)
        last = float(up["close"].iloc[-1])
        down = candles(minutes=60 * 24 * 2, seed=3, drift=-0.00005)
        scale = last / float(down["open"].iloc[0])
        for col in ("open", "high", "low", "close"):
            down[col] = down[col] * scale
        down["time"] = (
            down["time"]
            + (up["time"].iloc[-1] - down["time"].iloc[0])
            + pd.Timedelta(minutes=1)
        )
        df = pd.concat([up, down], ignore_index=True)
        h1, m15, m5, m1 = frames(df)
        f = build_features(h1, m15, m5, m1)
        c = h1["close"].astype(float)
        e50 = c.ewm(span=50, adjust=False).mean()
        e200 = c.ewm(span=200, adjust=False).mean()
        falling_above = ((c > e200) & (e50 > e200) & (e50.diff(3) < 0)).to_numpy()
        rows = np.isin(f.idx_1h, np.where(falling_above)[0]) & f.warm
        self.assertTrue(rows.any(), "fixture must contain falling-slope bars")
        self.assertTrue((f.ctx[rows] == 0).all())

    def test_5m_confirmation_requires_break_of_previous_extreme(self):
        t = pd.date_range("2026-01-01", periods=40, freq="5min", tz="UTC")
        close = np.full(40, 100.0)
        close[-1] = 100.5  # above EMA20 but NOT above previous high (101)
        df5 = pd.DataFrame(
            {
                "time": t,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": close,
                "volume": 1.0,
            }
        )
        m1 = pd.DataFrame(
            {
                "time": [t[-1] + pd.Timedelta(minutes=5)],
                "open": 100.5,
                "high": 100.6,
                "low": 100.4,
                "close": 100.5,
                "volume": 1.0,
            }
        )
        f = build_features(df5.iloc[:1], df5, df5, m1)
        self.assertEqual(f.confirm_age_long_ns[0], np.iinfo(np.int64).max)
        df5.loc[df5.index[-1], "close"] = 101.5  # now breaks previous high
        f = build_features(df5.iloc[:1], df5, df5, m1)
        # 1M bar closes one minute after the confirming 5M close.
        self.assertEqual(f.confirm_age_long_ns[0], 60_000_000_000)

    def test_15m_setup_requires_trend_alignment(self):
        # Flat 15M closes: EMA20 == EMA50, lows touch EMA20, no close below EMA50.
        # Only the trend condition (EMA20 > EMA50) is false -> no long setup.
        t = pd.date_range("2026-01-01", periods=80, freq="15min", tz="UTC")
        m15 = pd.DataFrame(
            {
                "time": t,
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": 100.0,
                "volume": 1.0,
            }
        )
        m1 = pd.DataFrame(
            {
                "time": [t[-1] + pd.Timedelta(minutes=15)],
                "open": 100.0,
                "high": 100.1,
                "low": 99.9,
                "close": 100.0,
                "volume": 1.0,
            }
        )
        f = build_features(m15.iloc[:1], m15, m15, m1)
        self.assertEqual(int(f.setup[0]), 0)
        closes = np.linspace(95.0, 100.0, 80)
        rising = m15.assign(close=closes, low=closes - 1.0)  # lows reach EMA20
        f = build_features(rising.iloc[:1], rising, rising, m1)
        self.assertEqual(int(f.setup[0]), 1)

    def test_params_are_respected(self):
        p = replace(MTFParams(), min_stop_pct=0.2)
        self.assertEqual(signal_at(feat(swing=99.7), 0, p).side, "BUY")


if __name__ == "__main__":
    unittest.main()
