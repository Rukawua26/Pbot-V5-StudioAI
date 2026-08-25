#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config.thresholds import threshold_value
from tools.gate_history import append_gate_result


CRITICAL_EVENTS = {
    "ENTRY_ABORTED_NO_HARD_SL",
    "FAIL_SAFE_CLOSE_FAILED_HALT",
    "ACTIVE_STATE_PERSIST_FAILED",
}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _load_marker_ts(path: Path) -> datetime | None:
    marker = _load_json(path)
    ts = marker.get("ts") if marker else None
    return _parse_ts(ts)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def filter_rows_since(rows: list[dict[str, Any]], since_hours: float | None) -> list[dict[str, Any]]:
    if since_hours is None or since_hours <= 0:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(hours=float(since_hours))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ts = _parse_ts(row.get("ts"))
        if ts is None or ts >= cutoff:
            filtered.append(row)
    return filtered


def filter_rows_since_ts(rows: list[dict[str, Any]], since_ts: datetime | None) -> list[dict[str, Any]]:
    if since_ts is None:
        return rows
    return [row for row in rows if (_parse_ts(row.get("ts")) or since_ts) >= since_ts]


def summarize_execution_events(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        event = str(row.get("event") or "")
        if not event:
            continue
        counts[event] = counts.get(event, 0) + 1

    intents = counts.get("ORDER_INTENT_CREATED", 0)
    filled = counts.get("ORDER_FILLED", 0)
    ack_unknown = counts.get("ENTRY_ACK_UNKNOWN_PERSISTED", 0)

    return {
        "counts": counts,
        "order_intents": intents,
        "order_filled": filled,
        "entry_ack_unknown": ack_unknown,
        "entry_ack_unknown_rate": (ack_unknown / intents) if intents > 0 else 0.0,
    }


def summarize_risk_decisions(rows: list[dict[str, Any]]) -> dict[str, int]:
    reasons: dict[str, int] = {}
    actions: dict[str, int] = {}
    for row in rows:
        if str(row.get("event") or "") != "RISK_DECISION":
            continue
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        reason = str(payload.get("reason") or "UNKNOWN")
        action = str(payload.get("action") or "UNKNOWN")
        reasons[reason] = reasons.get(reason, 0) + 1
        actions[action] = actions.get(action, 0) + 1
    return {"reasons": reasons, "actions": actions}


def summarize_runtime(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "samples": 0,
            "rss_max": None,
            "cpu_max": None,
            "guardian_busy_max": None,
        }

    rss_values = [float(row.get("rss_mb", 0.0) or 0.0) for row in rows]
    cpu_values = [float(row.get("cpu_pct", 0.0) or 0.0) for row in rows]
    busy_values = [float(row.get("guardian_busy_pct", 0.0) or 0.0) for row in rows]
    return {
        "samples": len(rows),
        "rss_max": max(rss_values) if rss_values else None,
        "cpu_max": max(cpu_values) if cpu_values else None,
        "guardian_busy_max": max(busy_values) if busy_values else None,
    }


def evaluate_shadow_readiness(
    execution_summary: dict[str, Any],
    runtime_summary: dict[str, Any],
    metrics_summary: dict[str, Any],
    *,
    min_runtime_samples: int,
    min_filled_orders: int,
    max_ack_unknown_rate: float,
    max_rss_mb: float,
    max_cpu_pct: float,
    max_guardian_busy_pct: float,
) -> list[str]:
    failures: list[str] = []

    counts = execution_summary.get("counts") or {}
    for event_name in sorted(CRITICAL_EVENTS):
        if int(counts.get(event_name, 0) or 0) > 0:
            failures.append(f"critical execution event present: {event_name}")

    filled = int(execution_summary.get("order_filled", 0) or 0)
    intents = int(execution_summary.get("order_intents", 0) or 0)
    ack_unknown_rate = float(execution_summary.get("entry_ack_unknown_rate", 0.0) or 0.0)

    if intents <= 0:
        failures.append("execution_events.jsonl has zero ORDER_INTENT_CREATED events")
    if filled < min_filled_orders:
        failures.append(f"ORDER_FILLED {filled} < required minimum {min_filled_orders}")
    if ack_unknown_rate > max_ack_unknown_rate:
        failures.append(
            f"ENTRY_ACK_UNKNOWN rate {ack_unknown_rate:.4f} > allowed {max_ack_unknown_rate:.4f}"
        )

    samples = int(runtime_summary.get("samples", 0) or 0)
    if samples < min_runtime_samples:
        failures.append(
            f"runtime_metrics samples {samples} < required minimum {min_runtime_samples}"
        )

    rss_max = runtime_summary.get("rss_max")
    cpu_max = runtime_summary.get("cpu_max")
    busy_max = runtime_summary.get("guardian_busy_max")
    if rss_max is not None and float(rss_max) > max_rss_mb:
        failures.append(f"rss_max {float(rss_max):.2f}MB > allowed {max_rss_mb:.2f}MB")
    if cpu_max is not None and float(cpu_max) > max_cpu_pct:
        failures.append(f"cpu_max {float(cpu_max):.2f}% > allowed {max_cpu_pct:.2f}%")
    if busy_max is not None and float(busy_max) > max_guardian_busy_pct:
        failures.append(
            f"guardian_busy_max {float(busy_max):.2f}% > allowed {max_guardian_busy_pct:.2f}%"
        )

    if not metrics_summary:
        failures.append("metrics_summary.json is missing or invalid")
    else:
        if bool(metrics_summary.get("halt_system_active", False)):
            failures.append("halt_system_active=true in metrics_summary.json")
        if bool(metrics_summary.get("integrity_lock_active", False)):
            failures.append("integrity_lock_active=true in metrics_summary.json")
        if bool(metrics_summary.get("circuit_breaker_active", False)):
            failures.append("circuit_breaker_active=true in metrics_summary.json")
        if bool(metrics_summary.get("is_paused", False)):
            failures.append("is_paused=true in metrics_summary.json")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Shadow readiness gate")
    parser.add_argument("--root", default=".", help="Ruta raíz del bot")
    parser.add_argument(
        "--min-runtime-samples",
        type=int,
        default=int(threshold_value("SHADOW_GATE_MIN_RUNTIME_SAMPLES")),
    )
    parser.add_argument(
        "--min-filled-orders",
        type=int,
        default=int(threshold_value("SHADOW_GATE_MIN_FILLED_ORDERS")),
    )
    parser.add_argument(
        "--max-ack-unknown-rate",
        type=float,
        default=float(threshold_value("SHADOW_GATE_MAX_ACK_UNKNOWN_RATE")),
    )
    parser.add_argument(
        "--max-rss-mb",
        type=float,
        default=float(threshold_value("SHADOW_GATE_MAX_RSS_MB")),
    )
    parser.add_argument(
        "--max-cpu-pct",
        type=float,
        default=float(threshold_value("SHADOW_GATE_MAX_CPU_PCT")),
    )
    parser.add_argument(
        "--max-guardian-busy-pct",
        type=float,
        default=float(threshold_value("SHADOW_GATE_MAX_GUARDIAN_BUSY_PCT")),
    )
    parser.add_argument(
        "--since-hours",
        type=float,
        default=24.0,
        help="Ventana de evaluación en horas; <=0 desactiva el filtro temporal",
    )
    parser.add_argument(
        "--since-marker",
        default="",
        help="Archivo JSON con {\"ts\": iso8601} para evaluar solo desde el inicio de una sesión",
    )
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
    metrics_summary = _load_json(logs / "metrics_summary.json")

    execution_summary = summarize_execution_events(execution_rows)
    risk_summary = summarize_risk_decisions(execution_rows)
    runtime_summary = summarize_runtime(runtime_rows)
    failures = evaluate_shadow_readiness(
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

    print("SHADOW readiness summary")
    print(f"- order_intents: {execution_summary['order_intents']}")
    print(f"- order_filled: {execution_summary['order_filled']}")
    print(f"- entry_ack_unknown: {execution_summary['entry_ack_unknown']}")
    print(f"- entry_ack_unknown_rate: {execution_summary['entry_ack_unknown_rate']:.4f}")
    print(f"- runtime_samples: {runtime_summary['samples']}")
    print(f"- rss_max_mb: {runtime_summary['rss_max']}")
    print(f"- cpu_max_pct: {runtime_summary['cpu_max']}")
    print(f"- guardian_busy_max_pct: {runtime_summary['guardian_busy_max']}")
    if risk_summary["actions"]:
        print(f"- risk_actions: {risk_summary['actions']}")
    if risk_summary["reasons"]:
        print(f"- risk_reasons: {risk_summary['reasons']}")

    if failures:
        print("SHADOW readiness: FAILED")
        for failure in failures:
            print(f"- {failure}")
        append_gate_result(
            logs / "gate_history.jsonl",
            gate="shadow_readiness",
            passed=False,
            failures=failures,
            metadata={
                "since_marker": args.since_marker,
                "since_hours": args.since_hours,
                "order_intents": execution_summary["order_intents"],
                "order_filled": execution_summary["order_filled"],
            },
        )
        return 1

    print("SHADOW readiness: PASSED")
    append_gate_result(
        logs / "gate_history.jsonl",
        gate="shadow_readiness",
        passed=True,
        failures=[],
        metadata={
            "since_marker": args.since_marker,
            "since_hours": args.since_hours,
            "order_intents": execution_summary["order_intents"],
            "order_filled": execution_summary["order_filled"],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
