import unittest
from dataclasses import replace

import numpy as np

from core.strategy.regime_adaptive import (
    RAParams,
    REGIME_NEUTRAL,
    REGIME_RANGING,
    REGIME_TRENDING,
    build_features,
    signal_at,
)
from tests.test_mtf_pullback import candles, frames


class RegimeAdaptiveTests(unittest.TestCase):
    def test_trending_market_routes_to_trend_strategy(self):
        f = build_features(*frames(candles(drift=0.0003)))
        sides = {signal_at(f, i).side for i in range(len(f.regime)) if f.regime[i] == 1}
        self.assertTrue(sides, "trending fixture must produce trend signals")
        self.assertTrue(all(s in {"BUY", "WAIT"} for s in sides))

    def test_ranging_market_routes_to_range_strategy(self):
        f = build_features(*frames(candles(drift=0.0)))
        sides = {
            signal_at(f, i).side for i in range(len(f.regime)) if f.regime[i] == -1
        }
        # Range may or may not produce signals; if it does, they must be BUY/SELL/WAIT
        self.assertTrue(all(s in {"BUY", "SELL", "WAIT"} for s in sides))

    def test_neutral_regime_never_trades(self):
        f = build_features(*frames(candles(drift=0.0001)))
        for i in range(len(f.regime)):
            if f.regime[i] == 0:
                self.assertEqual(signal_at(f, i).side, "WAIT")
                self.assertEqual(signal_at(f, i).regime, REGIME_NEUTRAL)

    def test_regime_values_are_valid(self):
        f = build_features(*frames(candles(drift=0.0002)))
        self.assertTrue(set(f.regime.tolist()).issubset({-1, 0, 1}))

    def test_signal_carries_regime(self):
        f = build_features(*frames(candles(drift=0.0003)))
        for i in range(len(f.regime)):
            sig = signal_at(f, i)
            if sig.side in {"BUY", "SELL"}:
                self.assertIn(sig.regime, {REGIME_TRENDING, REGIME_RANGING})
                break

    def test_causality_no_future_leak(self):
        df = candles(minutes=60 * 24 * 10)
        full = build_features(*frames(df))
        cut = len(df) - 60 * 24 * 2
        past = build_features(*frames(df.iloc[:cut].reset_index(drop=True)))
        safe = cut - 60
        np.testing.assert_array_equal(full.regime[:safe], past.regime[:safe])

    def test_params_respected(self):
        p = replace(RAParams(), adx_trending=100.0)  # never trending
        f = build_features(*frames(candles(drift=0.0003)), p)
        self.assertFalse((f.regime == 1).any())


if __name__ == "__main__":
    unittest.main()


class RegimeRoutingTests(unittest.TestCase):
    """Routing and thresholds pinned directly (each rule false alone)."""

    def _feat(self, regime):
        from types import SimpleNamespace

        return SimpleNamespace(regime=np.array([regime]), mtf=object(), mr=object())

    def test_trending_uses_trend_engine_with_1_5r_target(self):
        from unittest.mock import patch

        from core.strategy.mtf_pullback import MTFSignal

        trend = MTFSignal("BUY", "MTF_PULLBACK_CONFIRMED", 100.0, 99.0, ("S", "BUY", 1))
        with (
            patch("core.strategy.regime_adaptive.mtf_signal", return_value=trend) as t,
            patch("core.strategy.regime_adaptive.mr_signal") as m,
        ):
            sig = signal_at(self._feat(1), 0)
        t.assert_called_once()
        m.assert_not_called()
        self.assertEqual((sig.side, sig.regime), ("BUY", REGIME_TRENDING))
        self.assertAlmostEqual(sig.target, 101.5)
        self.assertEqual(sig.max_hold_minutes, 480)
        self.assertEqual(sig.setup_id[0], "T")

    def test_ranging_uses_range_engine(self):
        from unittest.mock import patch

        from core.strategy.mean_reversion import MRSignal

        rng = MRSignal(
            "SELL", "MR_REVERSION_CONFIRMED", 100.0, 101.0, 98.0, ("S", "SELL", 1)
        )
        with (
            patch("core.strategy.regime_adaptive.mr_signal", return_value=rng) as m,
            patch("core.strategy.regime_adaptive.mtf_signal") as t,
        ):
            sig = signal_at(self._feat(-1), 0)
        m.assert_called_once()
        t.assert_not_called()
        self.assertEqual(
            (sig.side, sig.regime, sig.target), ("SELL", REGIME_RANGING, 98.0)
        )
        self.assertEqual(sig.max_hold_minutes, 240)
        self.assertEqual(sig.setup_id[0], "R")

    def test_neutral_calls_no_engine(self):
        from unittest.mock import patch

        with (
            patch("core.strategy.regime_adaptive.mtf_signal") as t,
            patch("core.strategy.regime_adaptive.mr_signal") as m,
        ):
            sig = signal_at(self._feat(0), 0)
        t.assert_not_called()
        m.assert_not_called()
        self.assertEqual((sig.side, sig.reason), ("WAIT", "RA_NEUTRAL_REGIME"))

    def _regime_with(self, adx_value, slope_pct):
        """Build features with ADX and EMA slope forced through patches."""
        from unittest.mock import patch

        df = candles(minutes=60 * 24 * 12, drift=0.0)
        h1 = frames(df)[0]
        n = len(h1)
        ema = np.full(n, 100.0)
        # ema now vs 6 bars ago changes by slope_pct
        ema[6:] = 100.0 * (1 + slope_pct / 100.0)
        ema = (
            np.cumprod(np.r_[np.ones(6), np.full(n - 6, 1 + slope_pct / 100.0)]) * 100.0
        )
        with (
            patch(
                "core.strategy.regime_adaptive._adx", return_value=np.full(n, adx_value)
            ),
            patch("core.strategy.regime_adaptive._ema", return_value=ema),
        ):
            f = build_features(*frames(df))
        return set(f.regime[f.regime != 0].tolist()) or {0}

    def test_regime_thresholds(self):
        # 6-bar compounded change of a per-bar rate r is ~6r; pick r so 6r crosses 0.3%.
        self.assertEqual(
            self._regime_with(30.0, 0.1), {1}
        )  # ADX>=25, change ~0.6% -> trending
        self.assertEqual(
            self._regime_with(30.0, 0.01), {0}
        )  # ADX>=25 but flat -> neutral
        self.assertEqual(
            self._regime_with(15.0, 0.01), {-1}
        )  # ADX<20 and flat -> ranging
        self.assertEqual(
            self._regime_with(15.0, 0.1), {0}
        )  # ADX<20 but sloped -> neutral
        self.assertEqual(
            self._regime_with(22.0, 0.01), {0}
        )  # ADX between 20-25 -> neutral
