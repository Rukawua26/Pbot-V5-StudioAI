import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch
from types import SimpleNamespace

import pandas as pd

from tools.ttf_backtest import (
    TTFBacktestParams,
    TTFTrade,
    backtest_symbol,
    build_report,
    main,
)


def trade(
    symbol="SOLUSDT",
    entry="2026-01-01T00:00Z",
    exit="2026-01-01T00:02Z",
    price=100.0,
    stop=99.0,
    end=101.0,
):
    return TTFTrade(
        symbol,
        "BUY",
        entry,
        entry,
        exit,
        price,
        price,
        stop,
        110.0,
        end,
        "TP",
        1.0,
        1.0,
        0.1,
        0.9,
        2,
        1.0,
        0.0,
    )


def data():
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=3060, freq="min", tz="UTC"),
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "volume": 100000.0,
        }
    )


class ProfileTests(unittest.TestCase):
    def test_minimum_step_unknown_and_nonshadow_margin(self):
        from tools.ttf_backtest import size_account_trade

        p = TTFBacktestParams()
        self.assertEqual(
            size_account_trade(trade("BTCUSDT"), 20.0, p), (0.0, "MIN_MARGIN_-6")
        )
        self.assertEqual(
            size_account_trade(trade("ETHUSDT"), 20.0, p), (0.0, "MIN_MARGIN_-6")
        )
        self.assertEqual(
            size_account_trade(trade("LINKUSDT"), 20.0, p), (0.0, "MIN_MARGIN_-6")
        )
        self.assertEqual(
            size_account_trade(trade("UNKNOWN"), 20.0, p), (0.0, "UNKNOWN_SYMBOL")
        )
        self.assertEqual(size_account_trade(trade(), 20.0, p), (0.1, "TAKEN"))
        # Minimum bump is permitted, but never rounds UP to reach exchange minimum.
        self.assertEqual(
            size_account_trade(trade(price=100.0, stop=1.0), 20.0, p),
            (0.0, "MIN_RISK_-4"),
        )
        self.assertEqual(
            size_account_trade(
                trade(price=101.0, stop=91.0), 20.0, replace(p, risk_per_trade_pct=0.01)
            ),
            (0.0, "POST_ROUND_MIN_NOTIONAL"),
        )

    def test_compounding_fees_concurrency_and_ruin(self):
        from tools.ttf_backtest import simulate_account

        p = TTFBacktestParams(max_open_trades=1)
        rows = [
            trade(),
            trade("XRPUSDT"),
            trade(entry="2026-01-01T00:03Z", exit="2026-01-01T00:05Z", end=90.0),
        ]
        result = simulate_account(rows, p)
        # first size .1; second size floor(20.08995*.5/100/.01)*.01=.1
        expected = 20 + 0.1 * (1 - 0.0005 * 201) + 0.1 * (-10 - 0.0005 * 190)
        self.assertAlmostEqual(result["final_equity"], expected)
        self.assertEqual(result["trades_taken"], 2)
        self.assertEqual(result["skipped_by_concurrency"], 1)
        self.assertGreater(result["max_drawdown_pct"], 0.0)
        self.assertFalse(result["ruined"])
        self.assertTrue(simulate_account([], replace(p, account_balance=9.0))["ruined"])
        self.assertEqual(
            simulate_account([trade("BTCUSDT")], p)["untradeable_by_reason"],
            {"MIN_MARGIN_-6": 1},
        )

    def test_preregistered_gate_boundaries(self):
        from tools.ttf_backtest import preregistered_gate

        s = {"trades": 200, "expectancy_r": 0.01, "profit_factor": 1.1}
        self.assertEqual(preregistered_gate(s, {"return_pct": 0.1}), "PASS")
        for key, value in [
            ("trades", 199),
            ("expectancy_r", 0.0),
            ("profit_factor", 1.099),
        ]:
            changed = dict(s, **{key: value})
            self.assertEqual(
                preregistered_gate(changed, {"return_pct": 0.1}),
                "MUESTRA_INSUFICIENTE" if key == "trades" else "SIN_EDGE",
            )
        self.assertEqual(preregistered_gate(s, {"return_pct": 0.0}), "SIN_EDGE")
        report = build_report([], TTFBacktestParams())
        self.assertIn("account_profile", report)
        self.assertEqual(report["preregistered_gate"], "MUESTRA_INSUFICIENTE")
        self.assertIn("verdict", report["overall"])

    def test_default_cli_writes_reports_and_documents_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SOLUSDT.csv"
            data().iloc[:60].to_csv(path, index=False)
            out = Path(tmp) / "report"
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main(["--csv", str(path), "--out", str(out)]), 0)
            report = json.loads((out / "summary.json").read_text())
            self.assertTrue((out / "trades.csv").exists())
            self.assertEqual(report["account_profile"]["start_equity"], 20.0)
            self.assertEqual(report["params"]["tf_struct"], "5min")
            output = io.StringIO()
            with contextlib.redirect_stdout(output), self.assertRaises(SystemExit):
                main(["--help"])
            self.assertIn("200", output.getvalue())

    def test_shared_backtest_consumption_and_trailing(self):
        from core.strategy.triple_tf.pipeline import TTFDecision

        decision = TTFDecision(
            side="BUY",
            confidence=85.0,
            suggested_sl=99.0,
            entry_price=100.0,
            setup_key=("SOLUSDT", 1, 2),
        )

        def evaluate(*args, **kwargs):
            return (
                TTFDecision()
                if decision.setup_key in kwargs["consumed_setups"]
                else decision
            )

        with (
            patch("tools.ttf_backtest.evaluate_ttf_signal", side_effect=evaluate) as ev,
            patch(
                "tools.ttf_backtest.evaluate_trailing_1m",
                return_value=SimpleNamespace(should_exit=True, is_activated=True),
            ),
        ):
            rows = backtest_symbol(
                "SOLUSDT",
                data(),
                TTFBacktestParams(slippage_pct=0.001, session_filter=False),
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].exit_reason, "TRAILING")
            self.assertAlmostEqual(rows[0].exit_price, 99.9)
            self.assertEqual(ev.call_args.kwargs["params"].max_setup_minutes, 15)

    def test_session_filter_matches_runtime_hours(self):
        from core.strategy.triple_tf.pipeline import TTFDecision

        decision = TTFDecision(
            side="BUY",
            confidence=85.0,
            suggested_sl=99.0,
            entry_price=100.0,
            setup_key=("SOLUSDT", 1, 2),
        )

        def evaluate(*args, **kwargs):
            return decision

        def exit_now(side, entry_idx, *args, **kwargs):
            return entry_idx, 101.0, "TP", 1.0, 0.0

        with (
            patch("tools.ttf_backtest.evaluate_ttf_signal", side_effect=evaluate),
            patch("tools.ttf_backtest._simulate_exit", side_effect=exit_now),
            patch("tools.ttf_backtest.reserve_setup", return_value=True),
        ):
            df = pd.concat(
                [
                    data(),
                    data().assign(
                        time=lambda f: f["time"] + pd.Timedelta(minutes=3060)
                    ),
                ],
                ignore_index=True,
            )
            rows = backtest_symbol("SOLUSDT", df, TTFBacktestParams())
            signal_hours = {pd.Timestamp(r.signal_time).hour for r in rows}
            off = backtest_symbol(
                "SOLUSDT", df, TTFBacktestParams(session_filter=False)
            )
        # Signal at 06:59 open closes at 07:00 (allowed); 21:59 closes at 22:00 (blocked).
        self.assertTrue(rows)
        self.assertEqual(min(signal_hours), 6)
        self.assertNotIn(22, signal_hours)
        self.assertTrue(
            all(
                pd.Timestamp(r.signal_time) + pd.Timedelta(minutes=1)
                < pd.Timestamp(r.signal_time).normalize() + pd.Timedelta(hours=22)
                for r in rows
            )
        )
        self.assertGreater(len(off), len(rows))

    def test_scaled_timeframes_closed_only_and_expiry(self):
        from core.strategy.triple_tf.pipeline import TTFDecision

        df = data()
        with patch(
            "tools.ttf_backtest.evaluate_ttf_signal", return_value=TTFDecision()
        ) as ev:
            backtest_symbol(
                "SOLUSDT",
                df,
                TTFBacktestParams(tf_bias="1h", tf_struct="15min", tf_trigger="5min"),
            )
            self.assertTrue(ev.called)
            args = ev.call_args.args
            now = args[2]["time"].iloc[-1] + pd.Timedelta(minutes=5)
            self.assertLessEqual(args[0]["time"].iloc[-1] + pd.Timedelta(hours=1), now)
            self.assertLessEqual(
                args[1]["time"].iloc[-1] + pd.Timedelta(minutes=15), now
            )
            # Parent explicitly specifies 60 minutes at 15min (not linear x3).
            self.assertEqual(ev.call_args.kwargs["params"].max_setup_minutes, 60)
