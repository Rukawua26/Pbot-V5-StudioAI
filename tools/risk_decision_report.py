#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


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


def _load_marker_ts(path: Path) -> datetime | None:
    marker = _load_json(path)
    return _parse_ts(marker.get("ts") if marker else None)


def filter_rows_since(rows: list[dict[str, Any]], since_hours: float | None) -> list[dict[str, Any]]:
    if since_hours is None or since_hours <= 0:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(hours=float(since_hours))
    return [row for row in rows if (_parse_ts(row.get("ts")) or cutoff) >= cutoff]


def filter_rows_since_ts(rows: list[dict[str, Any]], since_ts: datetime | None) -> list[dict[str, Any]]:
    if since_ts is None:
        return rows
    return [row for row in rows if (_parse_ts(row.get("ts")) or since_ts) >= since_ts]


def summarize_risk_decisions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    decision_rows = [
        row for row in rows if str(row.get("event") or "") == "RISK_DECISION"
    ]
    actions = Counter()
    reasons = Counter()
    sources = Counter()
    symbols = Counter()
    reason_by_symbol: dict[str, Counter] = defaultdict(Counter)

    for row in decision_rows:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        action = str(payload.get("action") or "UNKNOWN")
        reason = str(payload.get("reason") or "UNKNOWN")
        source = str(payload.get("source") or "UNKNOWN")
        symbol = str(payload.get("symbol") or "UNKNOWN")
        actions[action] += 1
        reasons[reason] += 1
        sources[source] += 1
        symbols[symbol] += 1
        reason_by_symbol[symbol][reason] += 1

    total_risk_decisions = len(decision_rows)
    order_intents = sum(
        1 for row in rows if str(row.get("event") or "") == "ORDER_INTENT_CREATED"
    )
    order_filled = sum(
        1 for row in rows if str(row.get("event") or "") == "ORDER_FILLED"
    )

    return {
        "total_risk_decisions": total_risk_decisions,
        "actions": dict(actions),
        "reasons": dict(reasons),
        "sources": dict(sources),
        "symbols": dict(symbols),
        "reason_by_symbol": {
            symbol: dict(counter) for symbol, counter in reason_by_symbol.items()
        },
        "order_intents": order_intents,
        "order_filled": order_filled,
        "risk_decision_per_intent": (
            total_risk_decisions / order_intents if order_intents > 0 else 0.0
        ),
    }


def print_summary(summary: dict[str, Any]) -> None:
    print("RISK decision report")
    print(f"- total_risk_decisions: {summary['total_risk_decisions']}")
    print(f"- order_intents: {summary['order_intents']}")
    print(f"- order_filled: {summary['order_filled']}")
    print(f"- risk_decision_per_intent: {summary['risk_decision_per_intent']:.4f}")

    print("- actions:")
    for key, value in sorted(summary["actions"].items(), key=lambda item: (-item[1], item[0])):
        print(f"  - {key}: {value}")

    print("- top reasons:")
    for key, value in sorted(summary["reasons"].items(), key=lambda item: (-item[1], item[0]))[:10]:
        print(f"  - {key}: {value}")

    print("- top sources:")
    for key, value in sorted(summary["sources"].items(), key=lambda item: (-item[1], item[0])):
        print(f"  - {key}: {value}")

    print("- top symbols:")
    for key, value in sorted(summary["symbols"].items(), key=lambda item: (-item[1], item[0]))[:10]:
        print(f"  - {key}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Risk decision session report")
    parser.add_argument("--root", default=".", help="Ruta raíz del bot")
    parser.add_argument(
        "--since-hours",
        type=float,
        default=24.0,
        help="Ventana de evaluación en horas; <=0 desactiva el filtro temporal",
    )
    parser.add_argument(
        "--since-marker",
        default="",
        help="Archivo JSON con {\"ts\": iso8601} para evaluar una sesión",
    )
    parser.add_argument("--json-out", default="", help="Guardar resumen JSON opcional")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    logs = root / "logs"
    rows = _load_jsonl(logs / "execution_events.jsonl")
    since_marker_ts = _load_marker_ts(Path(args.since_marker)) if args.since_marker else None
    if since_marker_ts is not None:
        rows = filter_rows_since_ts(rows, since_marker_ts)
    else:
        rows = filter_rows_since(rows, args.since_hours)

    summary = summarize_risk_decisions(rows)
    print_summary(summary)

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(f"- json_out: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
