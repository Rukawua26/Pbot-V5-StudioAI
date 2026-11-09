import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.strategy.mtf_pullback import MTFParams, MTFSignal
from tools import mtf_backtest
from tools.ttf_backtest import TTFBacktestParams, TTFTrade, simulate_account
from tests.test_mtf_pullback import candles


def always(side="BUY", stop=99.0, setup=("S", "BUY", 1)):
    def signal(feat, i, params=None, symbol="Asset"):
        ref = float(feat.close_1m[i])
        s = stop if stop is not None else ref * (0.99 if side == "BUY" else 1.01)
        return MTFSignal(side, "MTF_PULLBACK_CONFIRMED", ref, s, setup)

    return signal


def flat(n=60 * 24 * 12, price=100.0):
    t = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    return pd.DataFrame(
        {
            "time": t,
            "open": price,
            "high": price + 0.05,
            "low": price - 0.05,
            "close": price,
            "volume": 1.0,
        }
    )


class MTFBacktestTests(unittest.TestCase):
    def _run(self, df, signal, **kw):
        with (
            patch("tools.mtf_backtest.signal_at", side_effect=signal),
            patch(
                "tools.mtf_backtest.build_features", wraps=mtf_backtest.build_features
            ),
        ):
            feat_patch = patch.object(
                mtf_backtest,
                "build_features",
                side_effect=lambda *a, **k: _force_candidates(
                    mtf_backtest.__dict__["_orig_build"](*a, **k)
                ),
            )
            with feat_patch:
                return mtf_backtest.backtest_symbol("SOLUSDT", df, **kw)

    def test_take_profit_is_1_5r_and_setup_used_once(self):
        df = flat()
        df.loc[df.index[-200:], ["high"]] = 102.0  # TP touched late
        trades = self._run(df, always(stop=99.0))
        self.assertEqual(len(trades), 1)  # same setup id never reused
        t = trades[0]
        risk = t.entry_price - t.stop_loss
        self.assertAlmostEqual(t.take_profit, t.entry_price + 1.5 * risk)

    def test_time_exit_after_8_hours(self):
        trades = self._run(flat(), always(stop=99.0, setup=None))
        self.assertTrue(trades)
        self.assertEqual(trades[0].exit_reason, "TIME")
        self.assertEqual(trades[0].bars_held, 480)

    def test_window_limits_signals_and_entry_is_next_open(self):
        df = flat()
        start = pd.Timestamp("2026-01-10", tz="UTC")
        trades = self._run(df, always(stop=99.0, setup=None), trade_start=start)
        self.assertTrue(trades)
        self.assertTrue(
            all(
                pd.Timestamp(t.signal_time) >= start - pd.Timedelta(minutes=1)
                for t in trades
            )
        )
        t = trades[0]
        self.assertEqual(
            pd.Timestamp(t.entry_time) - pd.Timestamp(t.signal_time),
            pd.Timedelta(minutes=1),
        )
        self.assertAlmostEqual(t.entry_price, 100.0 * 1.0005)

    def test_invalid_entry_when_open_beyond_stop(self):
        trades = self._run(flat(), always(stop=100.2, setup=None))
        self.assertEqual(trades, [])

    def test_profiles_gate_uses_tradeable_trades(self):
        rows = [
            TTFTrade(
                "BTCUSDT",
                "BUY",
                "2026-01-01T00:00Z",
                "2026-01-01T00:00Z",
                "2026-01-01T01:00Z",
                100.0,
                100.0,
                99.0,
                101.5,
                101.5,
                "TP",
                1.0,
                1.5,
                0.1,
                1.4,
                60,
                1.5,
                0.0,
            )
        ] * 3
        report = mtf_backtest.build_report(rows, TTFBacktestParams(), MTFParams())
        self.assertEqual(set(report["profiles"]), {"usd20", "usd100"})
        # BTC min notional $50 > max notional $10 at $20: nothing tradeable.
        p20 = report["profiles"]["usd20"]
        self.assertEqual(p20["tradeable_summary"]["trades"], 0)
        self.assertEqual(p20["preregistered_gate"], "MUESTRA_INSUFICIENTE")
        self.assertNotIn("taken_trades", p20["account"])
        json.dumps(report, default=str)

    def test_simulate_account_lists_taken_trades(self):
        t = TTFTrade(
            "SOLUSDT",
            "BUY",
            "2026-01-01T00:00Z",
            "2026-01-01T00:00Z",
            "2026-01-01T01:00Z",
            100.0,
            100.0,
            99.0,
            101.5,
            101.5,
            "TP",
            1.0,
            1.5,
            0.1,
            1.4,
            60,
            1.5,
            0.0,
        )
        res = simulate_account([t], TTFBacktestParams())
        self.assertEqual(res["taken_trades"], [t])

    def test_partial_month_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            df = flat(60)
            df["time"] = df["time"].astype("int64") // 1_000_000
            df.to_csv(cache / "SOLUSDT-1m-2026-10-partial.csv", index=False)
            with (
                patch("tools.mtf_backtest.download_month", return_value=None),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                out = mtf_backtest.load_candles("SOLUSDT", "2026-10", "2026-10", cache)
            self.assertEqual(len(out), 60)

    def test_cli_writes_report(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "tools.mtf_backtest.load_candles",
                return_value=candles(minutes=60 * 24 * 3),
            ),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            out = Path(tmp) / "r"
            code = mtf_backtest.main(
                [
                    "--symbols",
                    "SOLUSDT",
                    "--start",
                    "2026-01",
                    "--end",
                    "2026-01",
                    "--warmup-start",
                    "2026-01",
                    "--out",
                    str(out),
                ]
            )
            self.assertEqual(code, 0)
            report = json.loads((out / "summary.json").read_text())
            self.assertEqual(report["strategy"], "MTF_PULLBACK_V2")
            self.assertIn("strategy_params", report)
            self.assertTrue((out / "trades.csv").exists())


def _force_candidates(feat):
    n = len(feat.warm)
    feat.warm = np.ones(n, bool)
    feat.ctx = np.ones(n, int)
    feat.setup = np.ones(n, int)
    feat.trigger = np.ones(n, int)
    return feat


mtf_backtest._orig_build = mtf_backtest.build_features

if __name__ == "__main__":
    unittest.main()


class MeanReversionBacktestTests(unittest.TestCase):
    def _run(self, df, sig):
        spec = mtf_backtest.mr_spec()
        spec = mtf_backtest.StrategySpec(
            name=spec.name,
            params=spec.params,
            build=spec.build,
            candidates=lambda f: np.ones(len(f.warm), bool),
            signal=lambda f, i, sym: sig(f, i),
            target=spec.target,
            max_hold_minutes=spec.max_hold_minutes,
        )
        return mtf_backtest.backtest_symbol("SOLUSDT", df, spec)

    @staticmethod
    def mr(side="BUY", stop=99.0, target=101.0, setup=None):
        from core.strategy.mean_reversion import MRSignal

        return lambda f, i: MRSignal(
            side, "MR_REVERSION_CONFIRMED", float(f.close_1m[i]), stop, target, setup
        )

    def test_take_profit_is_the_middle_band_target(self):
        df = flat()
        df.loc[df.index[-300:], "high"] = 101.5
        trades = self._run(df, self.mr(setup=("S", "BUY", 1)))
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].take_profit, 101.0)

    def test_time_exit_after_4_hours(self):
        trades = self._run(flat(), self.mr())
        self.assertEqual(trades[0].exit_reason, "TIME")
        self.assertEqual(trades[0].bars_held, 240)

    def test_target_already_passed_at_entry_is_skipped(self):
        self.assertEqual(self._run(flat(), self.mr(target=100.01)), [])

    def test_cli_selects_strategy(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "tools.mtf_backtest.load_candles",
                return_value=candles(minutes=60 * 24 * 3),
            ),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            out = Path(tmp) / "r"
            mtf_backtest.main(
                [
                    "--symbols",
                    "SOLUSDT",
                    "--start",
                    "2026-01",
                    "--end",
                    "2026-01",
                    "--warmup-start",
                    "2026-01",
                    "--out",
                    str(out),
                    "--strategy",
                    "mr",
                ]
            )
            report = json.loads((out / "summary.json").read_text())
            self.assertEqual(report["strategy"], "MEAN_REVERSION_V3")
            self.assertEqual(report["strategy_params"]["max_hold_minutes"], 240)


class RegimeAdaptiveBacktestTests(unittest.TestCase):
    def test_cli_runs_regime_adaptive_strategy(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "tools.mtf_backtest.load_candles",
                return_value=candles(minutes=60 * 24 * 12),
            ),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            out = Path(tmp) / "r"
            code = mtf_backtest.main(
                [
                    "--symbols",
                    "SOLUSDT",
                    "--start",
                    "2026-01",
                    "--end",
                    "2026-01",
                    "--warmup-start",
                    "2026-01",
                    "--out",
                    str(out),
                    "--strategy",
                    "ra",
                ]
            )
            self.assertEqual(code, 0)
            report = json.loads((out / "summary.json").read_text())
            self.assertEqual(report["strategy"], "REGIME_ADAPTIVE_V4")
            self.assertIn("profiles", report)
