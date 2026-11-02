import unittest
from dataclasses import replace

import numpy as np
import pandas as pd

from core.strategy.mean_reversion import (
    NEVER,
    NS_MIN,
    MRFeatures,
    MRParams,
    adx,
    build_features,
    candidate_mask,
    signal_at,
)
from tests.test_mtf_pullback import candles, frames

NOW = pd.Timestamp("2026-01-01T12:00Z").value


def feat(d=0, **overrides):
    """One 1M bar. Long stretch (d=0) closed 10 min ago, confirmation 5 min ago."""
    pair = lambda a, b: np.array([[a], [b]])  # noqa: E731
    sc = NOW - 10 * NS_MIN
    base = dict(
        close_time_ns=np.array([NOW]),
        close_1m=np.array([100.0]),
        candle_dir_1m=np.array([1 if d == 0 else -1]),
        range_1h=np.array([True]),
        stretch_close_ns=pair(sc, NEVER) if d == 0 else pair(NEVER, sc),
        stretch_open_ns=pair(sc - 15 * NS_MIN, NEVER)
        if d == 0
        else pair(NEVER, sc - 15 * NS_MIN),
        stop_base=pair(99.0, 101.0),
        atr_15m=pair(1.0, 1.0),
        target=pair(102.0, 98.0),
        confirm_close_ns=pair(NOW - 5 * NS_MIN, NOW - 5 * NS_MIN),
        warm=np.array([True]),
    )
    for key, value in overrides.items():
        arr = np.asarray(value)
        base[key] = arr.reshape(2, 1) if base[key].ndim == 2 else arr.reshape(1)
    return MRFeatures(**base)


class MRRuleTests(unittest.TestCase):
    def test_long_reversion_targets_middle_band(self):
        s = signal_at(feat(), 0, symbol="SOLUSDT")
        self.assertEqual(s.side, "BUY")
        self.assertAlmostEqual(s.stop, 98.9)  # stop window low - 0.1*ATR
        self.assertEqual(s.target, 102.0)
        self.assertEqual(s.setup_id, ("SOLUSDT", "BUY", NOW - 25 * NS_MIN))

    def test_short_mirrors_long(self):
        s = signal_at(feat(d=1), 0)
        self.assertEqual(s.side, "SELL")
        self.assertAlmostEqual(s.stop, 101.1)
        self.assertEqual(s.target, 98.0)

    def test_each_layer_vetoes(self):
        cases = {
            "WARMUP": dict(warm=[False]),
            "SESSION_OUTSIDE_HOURS": dict(
                close_time_ns=[pd.Timestamp("2026-01-01T22:00Z").value]
            ),
            "REGIME_1H_NOT_RANGE": dict(range_1h=[False]),
            "STRETCH_15M_NONE": dict(stretch_close_ns=[[NEVER], [NEVER]]),
            "CONFIRM_5M_NONE": dict(confirm_close_ns=[[NOW - 11 * NS_MIN], [NEVER]]),
            "ENTRY_1M_NONE": dict(candle_dir_1m=[-1]),
            "TARGET_TOO_CLOSE": dict(target=[[100.5], [98.0]]),
            "STOP_INVALID": dict(atr_15m=[[np.nan], [1.0]]),
        }
        for reason, override in cases.items():
            with self.subTest(reason=reason):
                s = signal_at(feat(**override), 0)
                self.assertEqual((s.side, s.reason), ("WAIT", reason))

    def test_window_boundaries(self):
        sc = NOW - 30 * NS_MIN
        ok = feat(stretch_close_ns=[[sc], [NEVER]], confirm_close_ns=[[NOW], [NEVER]])
        self.assertEqual(signal_at(ok, 0).side, "BUY")  # 30 min inclusive
        late = feat(
            stretch_close_ns=[[sc - NS_MIN], [NEVER]], confirm_close_ns=[[NOW], [NEVER]]
        )
        self.assertEqual(signal_at(late, 0).reason, "STRETCH_15M_NONE")
        same = feat(confirm_close_ns=[[NOW - 10 * NS_MIN], [NEVER]])  # == stretch close
        self.assertEqual(signal_at(same, 0).reason, "CONFIRM_5M_NONE")

    def test_stop_and_target_boundaries(self):
        # stop = base - 0.1*ATR(1.0); stop pct valid in [0.4, 2.5]; target >= 1.0R.
        def run(base, target):
            return signal_at(
                feat(stop_base=[[base], [101.0]], target=[[target], [98.0]]), 0
            )

        self.assertEqual(run(99.65, 101.0).side, "BUY")  # 0.45%
        self.assertEqual(run(99.75, 101.0).reason, "STOP_OUT_OF_RANGE")  # 0.35%
        self.assertEqual(run(97.7, 103.0).side, "BUY")  # 2.4%
        self.assertEqual(run(97.3, 103.0).reason, "STOP_OUT_OF_RANGE")  # 2.8%
        # risk 1.1 (stop 98.9): 1.05R vetoed, 1.15R allowed
        self.assertEqual(run(99.0, 101.05).reason, "TARGET_TOO_CLOSE")
        self.assertEqual(run(99.0, 101.15).side, "BUY")

    def test_candidate_mask_never_misses_a_signal(self):
        f = build_features(*frames(candles(minutes=60 * 24 * 20, drift=0.0)))
        mask = candidate_mask(f)
        sig = np.array(
            [signal_at(f, i).side in {"BUY", "SELL"} for i in range(len(f.warm))]
        )
        self.assertTrue(sig.any(), "fixture must produce signals")
        self.assertFalse((sig & ~mask).any())

    def test_params_are_respected(self):
        p = replace(MRParams(), min_target_r=0.4)
        self.assertEqual(signal_at(feat(target=[[100.5], [98.0]]), 0, p).side, "BUY")


class MRFeatureTests(unittest.TestCase):
    def test_future_candles_never_change_past_features(self):
        df = candles(minutes=60 * 24 * 20, drift=0.0)
        cut = len(df) - 60 * 24 * 2
        full = build_features(*frames(df))
        past = build_features(*frames(df.iloc[:cut].reset_index(drop=True)))
        safe = cut - 60
        for name in (
            "range_1h",
            "stretch_close_ns",
            "stop_base",
            "atr_15m",
            "target",
            "confirm_close_ns",
            "candle_dir_1m",
            "warm",
        ):
            with self.subTest(name=name):
                np.testing.assert_array_equal(
                    getattr(full, name)[..., :safe], getattr(past, name)[..., :safe]
                )

    def test_strong_trend_is_not_a_range(self):
        f = build_features(*frames(candles(minutes=60 * 24 * 20, drift=0.0003)))
        self.assertFalse(f.range_1h[f.warm].any())

    def test_range_requires_flat_ema(self):
        # Low ADX alone is not enough: a slow steady drift keeps ADX low but moves EMA50 > 0.5%/6h.
        p_loose = replace(MRParams(), ema_flat_max_pct=100.0)
        df = candles(minutes=60 * 24 * 20, drift=0.00002)
        loose = build_features(*frames(df), p_loose)
        strict = build_features(*frames(df))
        self.assertGreater(loose.range_1h.sum(), strict.range_1h.sum())

    def test_range_requires_low_adx(self):
        # Mild drift: EMA50 is flat enough (<0.5%/6h) but ADX is often >= 20.
        df = candles(minutes=60 * 24 * 20, drift=0.00002)
        no_adx = build_features(*frames(df), replace(MRParams(), adx_max_1h=1e9))
        strict = build_features(*frames(df))
        self.assertGreater(no_adx.range_1h.sum(), strict.range_1h.sum())

    def test_stretch_uses_bollinger_band(self):
        t = pd.date_range("2026-01-01", periods=60, freq="15min", tz="UTC")
        close = np.full(60, 100.0) + np.tile([0.5, -0.5], 30)
        close[-1] = 98.0  # far below lower band
        m15 = pd.DataFrame(
            {
                "time": t,
                "open": close,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 1.0,
            }
        )
        m1 = pd.DataFrame(
            {
                "time": [t[-1] + pd.Timedelta(minutes=15)],
                "open": 98.0,
                "high": 98.1,
                "low": 97.9,
                "close": 98.05,
                "volume": 1.0,
            }
        )
        f = build_features(m15.iloc[:1], m15, m15, m1)
        self.assertEqual(
            int(f.stretch_close_ns[0][0]), (t[-1] + pd.Timedelta(minutes=15)).value
        )
        self.assertEqual(int(f.stretch_close_ns[1][0]), NEVER)
        m15.loc[m15.index[-1], ["close", "open"]] = 99.6  # inside the band
        f = build_features(m15.iloc[:1], m15, m15, m1)
        self.assertEqual(int(f.stretch_close_ns[0][0]), NEVER)

    def test_5m_confirmation_requires_break_of_previous_extreme(self):
        t = pd.date_range("2026-01-01", periods=10, freq="5min", tz="UTC")
        m5 = pd.DataFrame(
            {
                "time": t,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1.0,
            }
        )
        m1 = pd.DataFrame(
            {
                "time": [t[-1] + pd.Timedelta(minutes=5)],
                "open": 100.0,
                "high": 100.1,
                "low": 99.9,
                "close": 100.0,
                "volume": 1.0,
            }
        )
        f = build_features(m5.iloc[:1], m5, m5, m1)
        self.assertEqual(int(f.confirm_close_ns[0][0]), NEVER)
        m5.loc[m5.index[-1], "close"] = 101.5
        f = build_features(m5.iloc[:1], m5, m5, m1)
        self.assertEqual(
            int(f.confirm_close_ns[0][0]), (t[-1] + pd.Timedelta(minutes=5)).value
        )

    def test_adx_high_in_trend_low_in_chop(self):
        h_trend = frames(candles(minutes=60 * 24 * 20, drift=0.0004))[0]
        h_chop = frames(candles(minutes=60 * 24 * 20, drift=0.0))[0]
        self.assertGreater(
            np.nanmean(adx(h_trend)[-100:]), np.nanmean(adx(h_chop)[-100:])
        )


if __name__ == "__main__":
    unittest.main()
