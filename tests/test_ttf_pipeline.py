"""Public TTF pipeline and runtime acceptance contracts."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from config import Config
from tools.strategy import Strategy


def candles():
    return pd.DataFrame(
        {
            "time": pd.date_range("2025-01-01", periods=60, freq="h", tz="UTC"),
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 100.0,
            "volume": 100000.0,
        }
    )


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.df = candles()
        self.brain = SimpleNamespace()
        self.bias = SimpleNamespace(bias="BUY", reason="bias")
        self.struct = SimpleNamespace(
            valid_setup=True,
            suggested_sl=98.0,
            mss_time=1,
            pullback_time=2,
            reason="struct",
        )
        self.trigger = SimpleNamespace(
            triggered=True,
            side="BUY",
            entry_price=100.0,
            trigger_time=3,
            reason="trigger",
        )
        self.patches = [
            patch.object(Config, "STRATEGY_ENGINE", "triple_tf"),
            patch(
                "core.strategy.triple_tf.bias_1h.evaluate_bias_1h",
                return_value=self.bias,
            ),
            patch(
                "core.strategy.triple_tf.structure_5m.evaluate_structure_5m",
                return_value=self.struct,
            ),
            patch(
                "core.strategy.triple_tf.trigger_1m.evaluate_trigger_1m",
                return_value=self.trigger,
            ),
            patch("core.strategy.triple_tf.fvg_5m.detect_fvg_5m", return_value=None),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def analyze(self):
        return Strategy.analyze(
            self.df, self.df, self.brain, symbol="SOLUSDT", df_5m=self.df, df_1m=self.df
        )

    def test_two_analyzes_are_pure_and_preserve_tuple(self):
        first, second = self.analyze(), self.analyze()
        self.assertEqual((first[0], second[0]), ("BUY", "BUY"))
        self.assertFalse(hasattr(self.brain, "_ttf_consumed_setups"))
        self.assertEqual(len(first), 6)
        self.assertEqual(first[3], 85.0)
        self.assertTrue(
            {"ttf_metrics", "signal_close_time", "stop_loss", "votos", "regime"}
            <= first[4].keys()
        )

    def test_shared_pipeline_fvg_expiry_causality_consumption(self):
        from core.strategy.triple_tf.pipeline import (
            TTFSignalParams,
            evaluate_ttf_signal,
        )

        zone = SimpleNamespace(suggested_sl=99.0)
        params = TTFSignalParams(max_setup_minutes=60, min_fvg_gap_pct=0.5)
        with (
            patch(
                "core.strategy.triple_tf.fvg_5m.detect_fvg_5m", return_value=zone
            ) as fvg,
            patch(
                "core.strategy.triple_tf.structure_5m.evaluate_structure_5m",
                return_value=self.struct,
            ) as structure,
            patch(
                "core.strategy.triple_tf.trigger_1m.evaluate_trigger_1m",
                return_value=self.trigger,
            ) as trigger,
        ):
            used = {}
            d = evaluate_ttf_signal(
                self.df,
                self.df,
                self.df,
                symbol="SOLUSDT",
                params=params,
                consumed_setups=used,
            )
            self.assertEqual(
                (d.side, d.suggested_sl, d.setup_key), ("BUY", 99.0, ("SOLUSDT", 1, 2))
            )
            self.assertEqual(used, {})
            self.assertEqual(structure.call_args.kwargs["max_setup_minutes"], 60)
            self.assertEqual(fvg.call_args.kwargs["min_gap_pct"], 0.5)
            self.assertIs(trigger.call_args.kwargs["fvg_zone"], zone)
            used[d.setup_key] = None
            blocked = evaluate_ttf_signal(
                self.df,
                self.df,
                self.df,
                symbol="SOLUSDT",
                params=params,
                consumed_setups=used,
            )
            self.assertEqual(blocked.side, "WAIT")
            self.assertIn("TTF_SETUP_ALREADY_CONSUMED", blocked.reason)
            self.struct.pullback_time = 4
            blocked = evaluate_ttf_signal(self.df, self.df, self.df, params=params)
            self.assertEqual(blocked.side, "WAIT")
            self.assertIn("TTF_CAUSALITY_VIOLATION", blocked.reason)

    def test_rvol_veto_and_recorded_failure(self):
        from core.strategy.triple_tf.pipeline import evaluate_ttf_signal

        df = self.df.copy()
        df.loc[df.index[-1], "volume"] = 0
        self.assertEqual(
            evaluate_ttf_signal(df, self.df, self.df).telemetry["regime"], "VOL_DORMIDO"
        )
        df = df.drop(columns="volume")
        self.assertIn(
            "RVOL_ERROR",
            evaluate_ttf_signal(df, self.df, self.df).telemetry["rvol_status"],
        )

    def test_reserve_only_after_filters_and_keep_candle_dedup(self):
        from core.signals.filters import _apply_entry_filters_and_adjust_prob

        bot = SimpleNamespace(
            brain=self.brain, _get_market_regime=lambda: "RANGE", log=lambda msg: None
        )
        ctx = self.analyze()[4]
        # Runtime context forwards ttf_metrics, not arbitrary top-level telemetry.
        ctx.pop("setup_key", None)
        with (
            patch.object(Config, "PAPER_MODE", True),
            patch.object(Config, "TTF_REQUIRE_SESSION_FILTER", False),
            patch.object(Config, "TTF_REQUIRE_MACRO_REGIME_FILTER", False),
        ):

            def accept(c):
                return _apply_entry_filters_and_adjust_prob(
                    bot, "SOLUSDT", "SOLUSDT", self.df, "BUY", 85.0, c, 1.0
                )

            self.assertTrue(accept(ctx)[1])
            self.assertEqual(accept(ctx)[2], "TTF_DUPLICATE_SIGNAL")
            self.assertEqual(self.analyze()[0], "WAIT")
            newer = dict(ctx, signal_close_time=ctx["signal_close_time"] + 60000)
            self.assertEqual(accept(newer)[2], "TTF_SETUP_ALREADY_CONSUMED")
            self.assertEqual(len(self.brain._ttf_consumed_setups), 1)
