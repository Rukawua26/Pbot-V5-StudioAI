#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config.thresholds import threshold_value
from tools.gate_history import append_gate_result
from tools.real_readiness_check import evaluate_config_readiness, evaluate_walk_forward_report
from tools.risk_decision_report import (
    _load_json as _load_json_doc,
    _load_jsonl,
    _load_marker_ts,
    filter_rows_since,
    filter_rows_since_ts,
    summarize_risk_decisions,
)
from tools.shadow_readiness_gate import (
    _load_json,
    evaluate_shadow_readiness,
    summarize_execution_events,
    summarize_runtime,
)


def evaluate_risk_decision_summary(
    summary: dict[str, Any],
    *,
    max_halt_actions: int,
    max_quarantine_actions: int,
    max_risk_decision_per_intent: float,
) -> list[str]:
    failures: list[str] = []
    actions = summary.get("actions") or {}
    halt_actions = int(actions.get("HALT", 0) or 0)
    quarantine_actions = int(actions.get("QUARANTINE", 0) or 0)
    risk_per_intent = float(summary.get("risk_decision_per_intent", 0.0) or 0.0)

    if halt_actions > max_halt_actions:
        failures.append(f"risk HALT actions {halt_actions} > allowed {max_halt_actions}")
    if quarantine_actions > max_quarantine_actions:
        failures.append(
            f"risk QUARANTINE actions {quarantine_actions} > allowed {max_quarantine_actions}"
        )
    if risk_per_intent > max_risk_decision_per_intent:
        failures.append(
            f"risk_decision_per_intent {risk_per_intent:.4f} > allowed {max_risk_decision_per_intent:.4f}"
        )
    return failures


def evaluate_fidelity(
    report: dict[str, Any],
    *,
    min_fidelity_score: float,
    min_fidelity_samples: int,
) -> list[str]:
    failures: list[str] = []
    fidelity = (report or {}).get("fidelity") or {}
    fidelity_summary = fidelity.get("summary") or {}
    fidelity_score = float(fidelity_summary.get("weighted_fidelity_score", 0.0) or 0.0)
    fidelity_samples = int(fidelity_summary.get("total_samples", 0) or 0)
    if fidelity_samples < min_fidelity_samples:
        failures.append(
            f"fidelity.total_samples {fidelity_samples} < {min_fidelity_samples}"
        )
    if fidelity_score < min_fidelity_score:
        failures.append(
            f"fidelity.weighted_fidelity_score {fidelity_score:.4f} < {min_fidelity_score:.4f}"
        )
    return failures


def evaluate_strategy_report_doc(
    report: dict[str, Any],
    *,
    require_strategy_report: bool,
    require_fidelity_report: bool = False,
    min_fidelity_score: float = 0.0,
    min_fidelity_samples: int = 0,
) -> list[str]:
    failures: list[str] = []
    if not report:
        if require_strategy_report:
            failures.append("strategy validation report missing or invalid")
        return failures

    verdict = report.get("verdict") or {}
    if not bool(verdict.get("passed", False)):
        failures.append("strategy validation verdict failed")
        for item in verdict.get("failures") or []:
            failures.append(f"strategy: {item}")

    if require_fidelity_report:
        fidelity = (report or {}).get("fidelity") or {}
        if not fidelity.get("summary"):
            failures.append("fidelity report missing or invalid in strategy report")
        else:
            failures.extend(
                evaluate_fidelity(
                    report,
                    min_fidelity_score=min_fidelity_score,
                    min_fidelity_samples=min_fidelity_samples,
                )
            )
    return failures


def evaluate_promotion_gate(
    *,
    shadow_failures: list[str],
    risk_failures: list[str],
    strategy_failures: list[str],
    real_failures: list[str],
) -> dict[str, Any]:
    failures = [
        *[f"shadow: {item}" for item in shadow_failures],
        *[f"risk: {item}" for item in risk_failures],
        *strategy_failures,
        *[f"real: {item}" for item in real_failures],
    ]
    return {"passed": not failures, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(description="Final SHADOW->REAL candidate promotion gate")
    parser.add_argument("--root", default=".")
    parser.add_argument("--since-marker", default="")
    parser.add_argument("--since-hours", type=float, default=24.0)
    parser.add_argument("--strategy-report", default="reports/strategy_validation_report.json")
    parser.add_argument("--require-strategy-report", action="store_true")
    parser.add_argument("--require-fidelity-report", action="store_true")
    parser.add_argument(
        "--min-fidelity-score",
        type=float,
        default=float(threshold_value("STRATEGY_GATE_MIN_FIDELITY_SCORE")),
    )
    parser.add_argument(
        "--min-fidelity-samples",
        type=int,
        default=int(threshold_value("STRATEGY_GATE_MIN_FIDELITY_SAMPLES")),
    )
    parser.add_argument("--walk-forward-report", default="reports/walk_forward_backtest.json")
    parser.add_argument("--require-walk-forward", action="store_true")
    parser.add_argument("--min-profit-factor", type=float, default=float(threshold_value("STRATEGY_GATE_MIN_PROFIT_FACTOR")))
    parser.add_argument("--max-drawdown", type=float, default=float(threshold_value("STRATEGY_GATE_MAX_DRAWDOWN")))
    parser.add_argument("--min-runtime-samples", type=int, default=int(threshold_value("SHADOW_GATE_MIN_RUNTIME_SAMPLES")))
    parser.add_argument("--min-filled-orders", type=int, default=int(threshold_value("SHADOW_GATE_MIN_FILLED_ORDERS")))
    parser.add_argument("--max-ack-unknown-rate", type=float, default=float(threshold_value("SHADOW_GATE_MAX_ACK_UNKNOWN_RATE")))
    parser.add_argument("--max-rss-mb", type=float, default=float(threshold_value("SHADOW_GATE_MAX_RSS_MB")))
    parser.add_argument("--max-cpu-pct", type=float, default=float(threshold_value("SHADOW_GATE_MAX_CPU_PCT")))
    parser.add_argument("--max-guardian-busy-pct", type=float, default=float(threshold_value("SHADOW_GATE_MAX_GUARDIAN_BUSY_PCT")))
    parser.add_argument("--max-halt-actions", type=int, default=int(threshold_value("PROMOTION_GATE_MAX_HALT_ACTIONS")))
    parser.add_argument("--max-quarantine-actions", type=int, default=int(threshold_value("PROMOTION_GATE_MAX_QUARANTINE_ACTIONS")))
    parser.add_argument("--max-risk-decision-per-intent", type=float, default=float(threshold_value("PROMOTION_GATE_MAX_RISK_DECISION_PER_INTENT")))
    args = parser.parse_args()

    root = Path(args.root).resolve()
    logs = root / "logs"
    since_marker_ts = _load_marker_ts(Path(args.since_marker)) if args.since_marker else None
    execution_rows = _load_jsonl(logs / "execution_events.jsonl")
    runtime_rows = _load_jsonl(logs / "runtime_metrics.jsonl")
    if since_marker_ts is not None:
        execution_rows = filter_rows_since_ts(execution_rows, since_marker_ts)
        runtime_rows = filter_rows_since_ts(runtime_rows, since_marker_ts)
    else:
        execution_rows = filter_rows_since(execution_rows, args.since_hours)
        runtime_rows = filter_rows_since(runtime_rows, args.since_hours)

    execution_summary = summarize_execution_events(execution_rows)
    runtime_summary = summarize_runtime(runtime_rows)
    metrics_summary = _load_json(logs / "metrics_summary.json")
    shadow_failures = evaluate_shadow_readiness(
        execution_summary,
        runtime_summary,
        metrics_summary,
        min_runtime_samples=args.min_runtime_samples,
        min_filled_orders=args.min_filled_orders,
        max_ack_unknown_rate=args.max_ack_unknown_rate,
        max_rss_mb=args.max_rss_mb,
        max_cpu_pct=args.max_cpu_pct,
        max_guardian_busy_pct=args.max_guardian_busy_pct,
    )

    risk_summary = summarize_risk_decisions(execution_rows)
    risk_failures = evaluate_risk_decision_summary(
        risk_summary,
        max_halt_actions=args.max_halt_actions,
        max_quarantine_actions=args.max_quarantine_actions,
        max_risk_decision_per_intent=args.max_risk_decision_per_intent,
    )

    strategy_report = _load_json_doc(root / args.strategy_report)
    strategy_failures = evaluate_strategy_report_doc(
        strategy_report,
        require_strategy_report=args.require_strategy_report,
        require_fidelity_report=args.require_fidelity_report,
        min_fidelity_score=args.min_fidelity_score,
        min_fidelity_samples=args.min_fidelity_samples,
    )

    from config import Config

    config = {
        "PAPER_MODE": Config.PAPER_MODE,
        "ALLOW_REAL_TRADING": Config.ALLOW_REAL_TRADING,
        "USE_TESTNET": Config.USE_TESTNET,
        "BINANCE_API_KEY": Config.BINANCE_API_KEY,
        "BINANCE_API_SECRET": Config.BINANCE_API_SECRET,
        "TELEGRAM_TOKEN": Config.TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": Config.TELEGRAM_CHAT_ID,
        "MAX_OPEN_TRADES": Config.MAX_OPEN_TRADES,
        "MAX_RISK_USD": Config.MAX_RISK_USD,
        "RISK_PER_TRADE_PERCENT": Config.RISK_PER_TRADE_PERCENT,
    }
    real_failures = evaluate_config_readiness(config)

    wf_path = root / args.walk_forward_report
    if wf_path.exists():
        wf_report = json.loads(wf_path.read_text(encoding="utf-8"))
        real_failures.extend(
            evaluate_walk_forward_report(
                wf_report,
                min_profit_factor=args.min_profit_factor,
                max_drawdown=args.max_drawdown,
            )
        )
    elif args.require_walk_forward:
        real_failures.append(f"walk-forward report not found: {wf_path}")

    verdict = evaluate_promotion_gate(
        shadow_failures=shadow_failures,
        risk_failures=risk_failures,
        strategy_failures=strategy_failures,
        real_failures=real_failures,
    )

    print("PROMOTION gate summary")
    print(f"- shadow_failures: {len(shadow_failures)}")
    print(f"- risk_failures: {len(risk_failures)}")
    print(f"- strategy_failures: {len(strategy_failures)}")
    print(f"- real_failures: {len(real_failures)}")
    fidelity_report_token = bool((strategy_report or {}).get("fidelity"))
    print(f"- fidelity_present: {fidelity_report_token} (required: {args.require_fidelity_report})")
    print(f"- total_failures: {len(verdict['failures'])}")

    if verdict["passed"]:
        print("PROMOTION gate: PASSED")
        append_gate_result(
            logs / "gate_history.jsonl",
            gate="promotion_gate",
            passed=True,
            failures=[],
            metadata={
                "since_marker": args.since_marker,
                "strategy_report": args.strategy_report,
                "walk_forward_report": args.walk_forward_report,
                "require_fidelity_report": args.require_fidelity_report,
                "min_fidelity_score": args.min_fidelity_score,
                "min_fidelity_samples": args.min_fidelity_samples,
            },
        )
        return 0

    print("PROMOTION gate: FAILED")
    for item in verdict["failures"]:
        print(f"- {item}")
    append_gate_result(
        logs / "gate_history.jsonl",
        gate="promotion_gate",
        passed=False,
        failures=list(verdict["failures"]),
        metadata={
            "since_marker": args.since_marker,
            "strategy_report": args.strategy_report,
            "walk_forward_report": args.walk_forward_report,
            "require_fidelity_report": args.require_fidelity_report,
            "min_fidelity_score": args.min_fidelity_score,
            "min_fidelity_samples": args.min_fidelity_samples,
        },
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
