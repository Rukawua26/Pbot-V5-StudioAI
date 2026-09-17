import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import shadow_validation
from tools.shadow_validation_report import build_summary, render_markdown


class ShadowValidationMetricTests(unittest.TestCase):
    def test_scan_cycle_records_observational_cost(self):
        with (
            patch.object(shadow_validation.Config, "SHADOW_VALIDATION_ENABLED", True),
            patch("core.shadow_validation.append_runtime_metric") as append_metric,
        ):
            shadow_validation.emit_scan_cycle(125.5, candidates=30, heavy_analysis_calls=8)

        payload = append_metric.call_args.args[1]
        self.assertEqual(payload["event"], "scan_cycle")
        self.assertEqual(payload["duration_ms"], 125.5)
        self.assertEqual(payload["heavy_analysis_calls"], 8)

    def test_config_snapshot_identifies_config_mode_version_and_model(self):
        bot = SimpleNamespace(ghost_model_type="PRO_ENSEMBLE", bootstrap_heuristic_mode=False)
        with (
            patch.object(shadow_validation.Config, "SHADOW_VALIDATION_ENABLED", True),
            patch.object(shadow_validation.Config, "SHADOW_VALIDATION_CAMPAIGN", "campaign-v2"),
            patch.object(shadow_validation.Config, "PAPER_MODE", True),
            patch.dict("os.environ", {"SNIPER_CODE_VERSION": "abc123"}),
            patch("core.shadow_validation.append_runtime_metric") as append_metric,
        ):
            shadow_validation.emit_config_snapshot(bot)

        payload = append_metric.call_args.args[1]
        self.assertEqual(payload["campaign"], "campaign-v2")
        self.assertEqual(payload["code_version"], "abc123")
        self.assertEqual(payload["runtime_mode"], "PAPER")
        self.assertEqual(len(payload["run_id"]), 12)
        self.assertEqual(payload["model_type"], "PRO_ENSEMBLE")
        self.assertFalse(payload["bootstrap_heuristic_mode"])
        self.assertEqual(len(payload["config_fingerprint"]), 12)
        self.assertIn("min_risk_reward_ratio", payload["config_values"])

    def test_filter_decision_payload_is_observational(self):
        with (
            patch.object(shadow_validation.Config, "SHADOW_VALIDATION_ENABLED", True),
            patch.object(shadow_validation.Config, "SHADOW_VALIDATION_CAMPAIGN", "test-campaign"),
            patch("core.shadow_validation.append_runtime_metric") as append_metric,
        ):
            shadow_validation.emit_filter_decision(
                "BTC/USDT",
                "BUY",
                False,
                "FEAR_10_VETO",
                72.5,
                {
                    "fear_greed_index": 10,
                    "btc_dominance": 66.5,
                    "agent_signal_override": True,
                    "agent_direction_score": 24.0,
                },
            )

        append_metric.assert_called_once()
        metric, payload = append_metric.call_args.args
        self.assertEqual(metric, "shadow_validation")
        self.assertEqual(payload["campaign"], "test-campaign")
        self.assertEqual(payload["event"], "filter_decision")
        self.assertEqual(payload["symbol"], "BTC/USDT")
        self.assertFalse(payload["filter_passed"])
        self.assertTrue(payload["agent_signal_override"])

    def test_shadow_trade_closed_only_records_shadow(self):
        with (
            patch.object(shadow_validation.Config, "SHADOW_VALIDATION_ENABLED", True),
            patch("core.shadow_validation.append_runtime_metric") as append_metric,
        ):
            shadow_validation.emit_shadow_trade_closed(
                {"symbol": "BTC/USDT", "is_shadow": False},
                "MANUAL",
                100.0,
                1.0,
                1.0,
                -0.5,
                2.0,
                "MANUAL",
            )
            shadow_validation.emit_shadow_trade_closed(
                {"symbol": "ETH/USDT", "side": "SELL", "is_shadow": True, "entry": 110.0},
                "ATR_TRAILING_HIT",
                100.0,
                2.0,
                1.8,
                -0.2,
                3.5,
                "ATR_TRAILING_HIT",
                0.25,
            )

        append_metric.assert_called_once()
        payload = append_metric.call_args.args[1]
        self.assertEqual(payload["event"], "shadow_trade_closed")
        self.assertEqual(payload["symbol"], "ETH/USDT")
        self.assertEqual(payload["pnl_percent"], 1.8)
        self.assertEqual(payload["fees_usd"], 0.25)


class ShadowValidationReportTests(unittest.TestCase):
    def test_report_aggregates_equivalent_runs_in_same_campaign_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime_metrics.jsonl"
            records = [
                {
                    "ts": f"2026-09-08T00:0{index}:00+00:00",
                    "metric": "shadow_validation",
                    "payload": {
                        "campaign": "continuous",
                        "config_fingerprint": "same-config",
                        "code_version": "same-code",
                        "model_type": "OFF",
                        "bootstrap_heuristic_mode": True,
                        "runtime_mode": "PAPER",
                        "run_id": run_id,
                        "event": "shadow_trade_closed",
                        "trade_key": f"trade-{index}",
                        "pnl_percent": 1.0,
                        "pnl_usd": 0.1,
                        "fees_usd": 0.01,
                    },
                }
                for index, run_id in enumerate(("run-a", "run-b"))
            ]
            path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

            summary = build_summary(path)

        self.assertFalse(summary["integrity"]["mixed_identities"])
        self.assertEqual(summary["integrity"]["runs"], 2)
        self.assertEqual(summary["selection"]["run_count"], 2)
        self.assertEqual(summary["shadow_trades"]["closed"], 2)
        self.assertEqual(len(summary["segments"]), 1)

    def test_report_deduplicates_repeated_trade_close_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime_metrics.jsonl"
            records = [
                {
                    "ts": f"2026-09-07T00:0{index}:00+00:00",
                    "metric": "shadow_validation",
                    "payload": {
                        "campaign": "dedupe",
                        "config_fingerprint": "fixed",
                        "code_version": "code-4",
                        "event": "shadow_trade_closed",
                        "trade_key": "BTC/USDT|BUY|1",
                        "pnl_percent": 1.0,
                        "pnl_usd": 0.1,
                        "fees_usd": 0.01,
                    },
                }
                for index in range(2)
            ]
            path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

            summary = build_summary(path)

        self.assertEqual(summary["shadow_trades"]["closed"], 1)
        self.assertEqual(summary["integrity"]["duplicate_trade_events"], 1)

    def test_invalid_trade_results_do_not_satisfy_minimum_sample(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime_metrics.jsonl"
            records = [
                {
                    "ts": f"2026-09-05T00:{index:02d}:00+00:00",
                    "metric": "shadow_validation",
                    "payload": {
                        "campaign": "invalid-results",
                        "config_fingerprint": "fixed",
                        "code_version": "code-3",
                        "event": "shadow_trade_closed",
                        "pnl_percent": "not-a-number",
                    },
                }
                for index in range(20)
            ]
            path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

            summary = build_summary(path)

        self.assertEqual(summary["shadow_trades"]["closed"], 0)
        self.assertEqual(summary["conclusion"], "INSUFFICIENT_SAMPLE")

    def test_report_identifies_negative_expectancy_with_sufficient_sample(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime_metrics.jsonl"
            records = [
                {
                    "ts": f"2026-09-04T00:{index:02d}:00+00:00",
                    "metric": "shadow_validation",
                    "payload": {
                        "campaign": "negative-edge",
                        "config_fingerprint": "fixed",
                        "code_version": "code-2",
                        "model_type": "OFF",
                        "bootstrap_heuristic_mode": True,
                        "event": "shadow_trade_closed",
                        "pnl_percent": -1.0,
                        "pnl_usd": -0.1,
                        "fees_usd": 0.01,
                    },
                }
                for index in range(20)
            ]
            path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

            summary = build_summary(path)

        self.assertEqual(summary["conclusion"], "NEGATIVE_TRADE_EXPECTANCY")

    def test_report_selects_latest_identity_instead_of_mixing_campaigns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime_metrics.jsonl"
            records = [
                {
                    "ts": "2026-09-01T00:00:00+00:00",
                    "metric": "shadow_validation",
                    "payload": {
                        "campaign": "baseline",
                        "config_fingerprint": "old-config",
                        "code_version": "old-code",
                        "model_type": "OFF",
                        "bootstrap_heuristic_mode": True,
                        "event": "shadow_trade_closed",
                        "pnl_percent": 50.0,
                        "pnl_usd": 50.0,
                        "fees_usd": 1.0,
                    },
                },
                {
                    "ts": "2026-09-02T00:00:00+00:00",
                    "metric": "shadow_validation",
                    "payload": {
                        "campaign": "baseline",
                        "config_fingerprint": "new-config",
                        "code_version": "new-code",
                        "model_type": "RF",
                        "bootstrap_heuristic_mode": False,
                        "event": "shadow_trade_closed",
                        "pnl_percent": -10.0,
                        "pnl_usd": -2.0,
                        "fees_usd": 0.2,
                    },
                },
            ]
            path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

            summary = build_summary(path)

        self.assertTrue(summary["integrity"]["mixed_identities"])
        self.assertEqual(len(summary["segments"]), 2)
        self.assertEqual(summary["selection"]["config_fingerprint"], "new-config")
        self.assertEqual(summary["shadow_trades"]["closed"], 1)
        self.assertEqual(summary["shadow_trades"]["total_pnl_usd"], -2.0)
        self.assertIsNone(summary["shadow_trades"]["account_return_pct"])

    def test_report_computes_compounded_return_drawdown_and_profit_factor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime_metrics.jsonl"
            records = []
            for index, result in enumerate((10.0, -10.0)):
                records.append(
                    {
                        "ts": f"2026-09-03T00:0{index}:00+00:00",
                        "metric": "shadow_validation",
                        "payload": {
                            "campaign": "economics",
                            "config_fingerprint": "same-config",
                            "code_version": "code-1",
                            "model_type": "OFF",
                            "bootstrap_heuristic_mode": True,
                            "event": "shadow_trade_closed",
                            "pnl_percent": result,
                            "pnl_usd": result,
                            "fees_usd": 0.1,
                            "mae_percent": -2.0,
                            "mfe_percent": 3.0,
                            "side": "BUY",
                            "market_regime": "RANGE",
                        },
                    }
                )
            records.append(
                {
                    "ts": "2026-09-03T00:03:00+00:00",
                    "metric": "shadow_validation",
                    "payload": {
                        "campaign": "economics",
                        "config_fingerprint": "same-config",
                        "code_version": "code-1",
                        "model_type": "OFF",
                        "bootstrap_heuristic_mode": True,
                        "event": "scan_cycle",
                        "duration_ms": 250.0,
                        "heavy_analysis_calls": 6,
                    },
                }
            )
            records.extend(
                [
                    {
                        "ts": "2026-09-03T00:04:00+00:00",
                        "metric": "shadow_validation",
                        "payload": {
                            "campaign": "economics",
                            "config_fingerprint": "same-config",
                            "code_version": "code-1",
                            "model_type": "OFF",
                            "bootstrap_heuristic_mode": True,
                            "event": "filter_decision",
                            "filter_passed": False,
                            "filter_reason": reason,
                        },
                    }
                    for reason in (
                        "SHOCK DEMASIADO CERCA (0.01% < 0.20%)",
                        "SHOCK DEMASIADO CERCA (0.09% < 0.20%)",
                    )
                ]
            )
            path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

            summary = build_summary(path)
            trades = summary["shadow_trades"]

        self.assertEqual(trades["profit_factor"], 1.0)
        self.assertIsNone(trades["account_return_pct"])
        self.assertIsNone(trades["max_drawdown_pct"])
        self.assertEqual(trades["fees_usd"], 0.2)
        self.assertEqual(trades["by_regime"], {"RANGE": 2})
        self.assertEqual(summary["operations"]["scan_cycle_avg_latency_ms"], 250.0)
        self.assertEqual(summary["operations"]["heavy_analysis_calls_per_cycle"], 6.0)
        self.assertEqual(summary["filters"]["veto_reasons"], {"SHOCK DEMASIADO CERCA": 2})

    def test_report_orders_equity_snapshots_and_computes_account_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime_metrics.jsonl"
            common = {
                "campaign": "equity",
                "config_fingerprint": "same-config",
                "code_version": "code-equity",
                "model_type": "OFF",
                "bootstrap_heuristic_mode": True,
                "event": "shadow_trade_closed",
                "fees_usd": 0.1,
            }
            records = [
                {
                    "ts": "2026-09-06T00:02:00+00:00",
                    "metric": "shadow_validation",
                    "payload": {
                        **common,
                        "trade_key": "second",
                        "pnl_percent": -10.0,
                        "pnl_usd": -11.0,
                        "equity_before_usd": 110.0,
                        "equity_after_usd": 99.0,
                        "equity_curve_source": "simulated_wallet_settlement",
                    },
                },
                {
                    "ts": "2026-09-06T00:01:00+00:00",
                    "metric": "shadow_validation",
                    "payload": {
                        **common,
                        "trade_key": "first",
                        "pnl_percent": 10.0,
                        "pnl_usd": 10.0,
                        "equity_before_usd": 100.0,
                        "equity_after_usd": 110.0,
                        "equity_curve_source": "simulated_wallet_settlement",
                    },
                },
            ]
            path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

            trades = build_summary(path)["shadow_trades"]

        self.assertEqual(trades["account_return_pct"], -1.0)
        self.assertEqual(trades["max_drawdown_pct"], 10.0)
        self.assertEqual(trades["equity_curve_source"], "simulated_wallet_settlement")

    def test_report_summarizes_runtime_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime_metrics.jsonl"
            records = [
                {
                    "metric": "shadow_validation",
                    "payload": {
                        "event": "filter_decision",
                        "filter_passed": False,
                        "filter_reason": "FEAR_10_VETO",
                        "agent_signal_override": True,
                    },
                },
                {
                    "metric": "shadow_validation",
                    "payload": {
                        "event": "filter_decision",
                        "filter_passed": True,
                        "macro_boost_reason": "BTC_DOM=66.5%",
                    },
                },
                {
                    "metric": "shadow_validation",
                    "payload": {
                        "event": "shadow_trade_closed",
                        "pnl_percent": 2.0,
                        "pnl_usd": 1.2,
                        "mae_percent": -0.5,
                        "mfe_percent": 3.0,
                    },
                },
                {
                    "metric": "shadow_validation",
                    "payload": {
                        "event": "shadow_trade_closed",
                        "pnl_percent": -1.0,
                        "pnl_usd": -0.8,
                        "mae_percent": -1.5,
                        "mfe_percent": 0.7,
                    },
                },
                {
                    "metric": "shadow_validation",
                    "payload": {
                        "event": "fvg_cycle",
                        "new_gaps": 3,
                        "active_total": 5,
                        "status_counts": {"ACTIVE": 4, "FILLED": 1},
                    },
                },
            ]
            path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

            summary = build_summary(path)

        self.assertEqual(summary["filters"]["total"], 2)
        self.assertEqual(summary["filters"]["veto_rate_pct"], 50.0)
        self.assertEqual(summary["filters"]["macro_vetoes"], 1)
        self.assertEqual(summary["filters"]["macro_boosts"], 1)
        self.assertEqual(summary["filters"]["agent_override_rate_pct"], 50.0)
        self.assertEqual(summary["shadow_trades"]["closed"], 2)
        self.assertEqual(summary["shadow_trades"]["winrate_pct"], 50.0)
        self.assertEqual(summary["shadow_trades"]["total_pnl_usd"], 0.4)
        self.assertEqual(summary["fvg"]["new_gaps"], 3)
        self.assertIn("SHADOW Validation Report", render_markdown(summary))


if __name__ == "__main__":
    unittest.main()
