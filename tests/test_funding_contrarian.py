import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.strategy.funding_contrarian import FCFeatures, FCParams, FCSignal, build_features, signal_at


def make_funding(rates, start="2026-01-01"):
    times = pd.date_range(start, periods=len(rates), freq="8h", tz="UTC")
    return pd.DataFrame({"fundingTime": times.astype("int64") // 1_000_000, "fundingRate": rates})


def make_candles(n=200, price=100.0):
    t = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"time": t, "open": price, "high": price + 1, "low": price - 1,
                         "close": price, "volume": 1.0})


class FundingContrarianTests(unittest.TestCase):
    def test_extreme_positive_funding_shorts(self):
        # funding > 0.05% -> short bias (contrarian)
        df = make_candles(200)
        fr = make_funding([0.001] * 30)  # 0.1% positive
        feat = build_features(df, fr)
        # find a bar with extreme funding
        extremes = np.where(feat.funding_extreme == 1)[0]
        extremes = [i for i in extremes if feat.warm[i]]
        self.assertTrue(len(extremes) > 0)
        sig = signal_at(feat, extremes[0])
        self.assertEqual(sig.side, "SELL")
        self.assertEqual(sig.reason, "FC_FUNDING_EXTREME")

    def test_extreme_negative_funding_longs(self):
        df = make_candles(200)
        fr = make_funding([-0.001] * 30)
        feat = build_features(df, fr)
        extremes = np.where(feat.funding_extreme == -1)[0]
        extremes = [i for i in extremes if feat.warm[i]]
        self.assertTrue(len(extremes) > 0)
        sig = signal_at(feat, extremes[0])
        self.assertEqual(sig.side, "BUY")

    def test_neutral_funding_no_trade(self):
        df = make_candles(200)
        fr = make_funding([0.0001] * 30)  # below threshold
        feat = build_features(df, fr)
        for i in range(len(feat.warm)):
            if feat.warm[i]:
                self.assertEqual(signal_at(feat, i).side, "WAIT")

    def test_stop_out_of_range(self):
        df = make_candles(200)
        fr = make_funding([0.001] * 30)
        feat = build_features(df, fr)
        extremes = [i for i in np.where(feat.funding_extreme == 1)[0] if feat.warm[i]]
        # Force extreme ATR to make stop out of range
        feat2 = FCFeatures(
            close_time_ns=feat.close_time_ns,
            close_1h=feat.close_1h,
            atr_1h=np.full(len(feat.close_1h), 0.001),  # tiny ATR -> huge stop pct
            funding=feat.funding,
            funding_extreme=feat.funding_extreme,
            warm=np.ones(len(feat.close_1h), dtype=bool),
        )
        sig = signal_at(feat2, 14)
        self.assertEqual(sig.reason, "STOP_OUT_OF_RANGE")

    def test_session_filter(self):
        df = make_candles(200)
        fr = make_funding([0.001] * 30)
        feat = build_features(df, fr)
        extremes = np.where(feat.funding_extreme == 1)[0]
        # Force a bar at 23:00 UTC
        feat2 = FCFeatures(
            close_time_ns=np.array([pd.Timestamp("2026-01-01T23:00Z").value]),
            close_1h=np.array([100.0]),
            atr_1h=np.array([1.0]),
            funding=np.array([0.001]),
            funding_extreme=np.array([1]),
            warm=np.array([True]),
        )
        sig = signal_at(feat2, 0)
        self.assertEqual(sig.reason, "SESSION_OUTSIDE_HOURS")

    def test_params_respected(self):
        p = replace(FCParams(), funding_threshold=0.01)  # very high threshold
        df = make_candles(200)
        fr = make_funding([0.001] * 30)
        feat = build_features(df, fr, p)
        # With high threshold, no extremes
        self.assertFalse(feat.funding_extreme.any())

    def test_warmup(self):
        df = make_candles(10)
        fr = make_funding([0.001] * 5)
        feat = build_features(df, fr)
        sig = signal_at(feat, 0)
        self.assertEqual(sig.side, "WAIT")
        self.assertEqual(sig.reason, "WARMUP")

    def test_causality(self):
        df = make_candles(200)
        fr = make_funding([0.001] * 30)
        full = build_features(df, fr)
        cut = len(df) - 50
        past = build_features(df.iloc[:cut].reset_index(drop=True), fr)
        safe = cut - 5
        np.testing.assert_array_equal(full.funding_extreme[:safe], past.funding_extreme[:safe])

    def test_cli_runs(self):
        import contextlib, io, json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        df = make_candles(60 * 24 * 3)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "tools.fc_backtest.load_candles", return_value=df
        ), patch("tools.fc_backtest.fetch_funding", return_value=make_funding([0.001] * 100)), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            out = Path(tmp) / "r"
            import tools.fc_backtest as fc
            code = fc.main(["--symbols", "SOLUSDT", "--start", "2026-01", "--end", "2026-01",
                            "--warmup-start", "2026-01", "--out", str(out)])
            self.assertEqual(code, 0)
            report = json.loads((out / "summary.json").read_text())
            self.assertEqual(report["strategy"], "FUNDING_CONTRARIAN_V5")


if __name__ == "__main__":
    unittest.main()
