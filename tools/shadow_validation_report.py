#!/usr/bin/env python3
"""Build a campaign-safe report from SHADOW runtime telemetry."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METRICS_PATH = PROJECT_ROOT / "logs" / "runtime_metrics.jsonl"


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
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


def _load_records(path: Path) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    malformed = 0
    if not path.exists():
        return records, malformed
    with path.open("r", encoding="utf-8") as file_obj:
        for raw_line in file_obj:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(record, dict):
                records.append(record)
            else:
                malformed += 1
    return records, malformed


def _identity(payload: dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    bootstrap = payload.get("bootstrap_heuristic_mode")
    return (
        str(payload.get("campaign") or "legacy-unidentified"),
        str(payload.get("config_fingerprint") or "unknown"),
        str(payload.get("code_version") or "unknown"),
        str(payload.get("model_type") or "UNKNOWN"),
        "unknown" if bootstrap is None else str(bool(bootstrap)).lower(),
        str(payload.get("runtime_mode") or "UNKNOWN"),
        str(payload.get("run_id") or "unknown"),
    )


def _pct(value: float, total: float) -> float:
    return round((value / total) * 100.0, 2) if total else 0.0


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _equity_metrics(valid: list[tuple[dict[str, Any], float]]) -> dict[str, Any]:
    if not valid:
        return {
            "account_return_pct": None,
            "max_drawdown_pct": None,
            "equity_curve_source": None,
            "equity_curve_status": "NO_TRADES",
        }
    equity_points: list[float] = []
    previous_after = None
    source = None
    for trade, _ in valid:
        before = _finite(trade.get("equity_before_usd"))
        after = _finite(trade.get("equity_after_usd"))
        if before is None or after is None or before <= 0.0 or after <= 0.0:
            return {
                "account_return_pct": None,
                "max_drawdown_pct": None,
                "equity_curve_source": None,
                "equity_curve_status": "INCOMPLETE",
            }
        if previous_after is not None and not math.isclose(
            before, previous_after, rel_tol=1e-8, abs_tol=1e-8
        ):
            return {
                "account_return_pct": None,
                "max_drawdown_pct": None,
                "equity_curve_source": None,
                "equity_curve_status": "DISCONTINUOUS",
            }
        if not equity_points:
            equity_points.append(before)
        equity_points.append(after)
        previous_after = after
        source = str(trade.get("equity_curve_source") or "unknown")

    initial = equity_points[0]
    maximum = 0.0
    peak = initial
    for equity in equity_points:
        peak = max(peak, equity)
        if peak > 0.0:
            maximum = max(maximum, 1.0 - equity / peak)
    return {
        "account_return_pct": round((equity_points[-1] / initial - 1.0) * 100.0, 4),
        "max_drawdown_pct": round(maximum * 100.0, 4),
        "equity_curve_source": source,
        "equity_curve_status": "COMPLETE",
    }


def _trade_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    trades = sorted(
        trades,
        key=lambda trade: _parse_ts(trade.get("_event_ts")) or datetime.min.replace(tzinfo=timezone.utc),
    )
    valid = [(trade, _finite(trade.get("pnl_percent"))) for trade in trades]
    valid = [(trade, result) for trade, result in valid if result is not None]
    returns = [result for _, result in valid]
    wins = [result for result in returns if result > 0.0]
    losses = [result for result in returns if result < 0.0]

    def average_field(name: str) -> float | None:
        values = [_finite(trade.get(name)) for trade, _ in valid]
        values = [value for value in values if value is not None]
        return round(sum(values) / len(values), 4) if values else None

    fees = [_finite(trade.get("fees_usd")) for trade, _ in valid]
    observed_fees = [value for value in fees if value is not None]
    fee_sources = Counter(str(trade.get("fees_source") or "UNKNOWN") for trade, _ in valid)
    notionals = [_finite(trade.get("notional_usd")) for trade, _ in valid]
    observed_notionals = [value for value in notionals if value is not None]
    by_side = Counter(str(trade.get("side") or "UNKNOWN") for trade, _ in valid)
    by_regime = Counter(str(trade.get("market_regime") or "UNKNOWN") for trade, _ in valid)
    pnl_usd = [_finite(trade.get("pnl_usd")) for trade, _ in valid]
    observed_pnl_usd = [value for value in pnl_usd if value is not None]
    pnl_wins = [value for value in observed_pnl_usd if value > 0.0]
    pnl_losses = [value for value in observed_pnl_usd if value < 0.0]
    profit_factor = (
        round(sum(pnl_wins) / abs(sum(pnl_losses)), 4)
        if len(observed_pnl_usd) == len(valid) and pnl_losses
        else None
    )
    equity_metrics = _equity_metrics(valid)
    return {
        "closed": len(valid),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(returns) - len(wins) - len(losses),
        "winrate_pct": _pct(len(wins), len(valid)),
        "expectancy_pct": round(sum(returns) / len(returns), 4) if returns else None,
        "expectancy_usd": (
            round(sum(observed_pnl_usd) / len(observed_pnl_usd), 4)
            if observed_pnl_usd and len(observed_pnl_usd) == len(valid)
            else None
        ),
        "profit_factor": profit_factor,
        "profit_factor_source": "net_pnl_usd" if profit_factor is not None else None,
        "compounded_return_pct": None,
        **equity_metrics,
        "total_pnl_usd": round(sum(observed_pnl_usd), 4),
        "pnl_records_missing": len(pnl_usd) - len(observed_pnl_usd),
        "fees_usd": round(sum(observed_fees), 4) if observed_fees else None,
        "fee_sources": dict(sorted(fee_sources.items())),
        "cost_records_missing": len(fees) - len(observed_fees),
        "avg_mae_pct": average_field("mae_percent"),
        "avg_mfe_pct": average_field("mfe_percent"),
        "max_notional_usd": max(observed_notionals) if observed_notionals else None,
        "by_side": dict(sorted(by_side.items())),
        "by_regime": dict(sorted(by_regime.items())),
    }


def _reason_bucket(value: Any) -> str:
    reason = str(value or "UNKNOWN").strip()
    for prefix in (
        "MARKET_BREADTH_FEAR",
        "BULL_TREND_ENTRY_VETO",
        "MIN_ATR_PCT",
        "VETO_KAVA",
        "SHOCK DEMASIADO CERCA",
        "Símbolo en blacklist",
    ):
        if reason.startswith(prefix):
            return prefix
    return reason.split(" (", 1)[0] or "UNKNOWN"


def _filter_metrics(filters: list[dict[str, Any]]) -> dict[str, Any]:
    vetoes = [event for event in filters if not bool(event.get("filter_passed", False))]
    reasons = Counter(_reason_bucket(event.get("filter_reason")) for event in vetoes)
    macro_vetoes = sum(
        1
        for event in vetoes
        if "FEAR_" in str(event.get("filter_reason", ""))
        or "MARKET_BREADTH" in str(event.get("filter_reason", ""))
    )
    macro_boosts = sum(1 for event in filters if str(event.get("macro_boost_reason") or ""))
    overrides = sum(1 for event in filters if bool(event.get("agent_signal_override", False)))
    return {
        "total": len(filters),
        "vetoes": len(vetoes),
        "veto_rate_pct": _pct(len(vetoes), len(filters)),
        "macro_vetoes": macro_vetoes,
        "macro_boosts": macro_boosts,
        "agent_overrides": overrides,
        "agent_override_rate_pct": _pct(overrides, len(filters)),
        "veto_reasons": dict(reasons.most_common()),
    }


def _deduplicate_trades(trades: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    without_key = []
    by_key = {}
    duplicates = 0
    for trade in trades:
        trade_key = str(trade.get("trade_key") or "").strip()
        if not trade_key:
            without_key.append(trade)
            continue
        if trade_key in by_key:
            duplicates += 1
        by_key[trade_key] = trade
    return [*without_key, *by_key.values()], duplicates


def _operations(records: list[dict[str, Any]], start: datetime | None, end: datetime | None) -> dict:
    if start is None or end is None:
        return {"available": False, "reason": "selected campaign has no valid timestamps"}
    in_window = []
    for record in records:
        ts = _parse_ts(record.get("ts"))
        if ts is not None and start <= ts <= end:
            in_window.append(record)
    exchange = [record.get("payload") or {} for record in in_window if record.get("metric") == "exchange_call"]
    latencies = [_finite(payload.get("latency_ms")) for payload in exchange]
    latencies = [value for value in latencies if value is not None]
    failures = [payload for payload in exchange if not bool(payload.get("ok", False))]
    monitor = [
        record
        for record in in_window
        if "rss_mb" in record and "guardian_loops" in record and "metric" not in record
    ]
    return {
        "available": bool(exchange or monitor),
        "exchange_calls": len(exchange),
        "exchange_failures": len(failures),
        "exchange_failure_rate_pct": _pct(len(failures), len(exchange)),
        "exchange_avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "runtime_samples": len(monitor),
        "max_rss_mb": max((_finite(row.get("rss_mb")) or 0.0 for row in monitor), default=None),
        "max_cpu_pct": max((_finite(row.get("cpu_pct")) or 0.0 for row in monitor), default=None),
    }


def build_summary(
    path: Path = DEFAULT_METRICS_PATH,
    *,
    campaign: str | None = None,
    fingerprint: str | None = None,
) -> dict[str, Any]:
    records, malformed = _load_records(path)
    shadow_rows = []
    for index, record in enumerate(records):
        if record.get("metric") != "shadow_validation":
            continue
        payload = record.get("payload")
        if isinstance(payload, dict):
            shadow_rows.append((index, record.get("ts"), payload))

    candidates = [row for row in shadow_rows if campaign is None or _identity(row[2])[0] == campaign]
    candidates = [row for row in candidates if fingerprint is None or _identity(row[2])[1] == fingerprint]
    identities = []
    for row in candidates:
        identity = _identity(row[2])
        if identity not in identities:
            identities.append(identity)
    selected_identity = _identity(candidates[-1][2]) if candidates else None
    selected = [row for row in candidates if _identity(row[2]) == selected_identity]
    payloads = [{**row[2], "_event_ts": row[1]} for row in selected]
    timestamps = [_parse_ts(row[1]) for row in selected]
    valid_timestamps = [ts for ts in timestamps if ts is not None]
    start = min(valid_timestamps) if valid_timestamps else None
    end = max(valid_timestamps) if valid_timestamps else None

    filters = [event for event in payloads if event.get("event") == "filter_decision"]
    trade_events = [event for event in payloads if event.get("event") == "shadow_trade_closed"]
    trades, duplicate_trades = _deduplicate_trades(trade_events)
    fvg_cycles = [event for event in payloads if event.get("event") == "fvg_cycle"]
    scan_cycles = [event for event in payloads if event.get("event") == "scan_cycle"]
    config_snapshots = [event for event in payloads if event.get("event") == "config_snapshot"]
    warnings = []
    if len(identities) > 1:
        warnings.append("multiple campaign identities found; report selected only the latest identity")
    if selected_identity and (selected_identity[1] == "unknown" or selected_identity[2] == "unknown"):
        warnings.append("campaign identity is incomplete; set SNIPER_CODE_VERSION and emit config snapshot")
    if any(ts is None for ts in timestamps):
        warnings.append("selected campaign contains events without valid timestamps")
    trade_metrics = _trade_metrics(trades)
    if trade_metrics["cost_records_missing"]:
        warnings.append("some trades lack cost fields; net-cost attribution is incomplete")
    if trade_metrics["pnl_records_missing"]:
        warnings.append("some trades lack pnl_usd; monetary profit factor is unavailable")
    if trades and trade_metrics["equity_curve_status"] != "COMPLETE":
        warnings.append(
            "account return/drawdown unavailable: equity snapshots are incomplete or discontinuous"
        )
    if duplicate_trades:
        warnings.append(f"deduplicated {duplicate_trades} repeated trade close events")
    if not trades:
        warnings.append("no closed SHADOW trades; economic conclusions are unavailable")

    filter_metrics = _filter_metrics(filters)
    if trade_metrics["closed"] < 20:
        dominant_problem = "INSUFFICIENT_SAMPLE"
    elif trade_metrics["pnl_records_missing"]:
        dominant_problem = "INCOMPLETE_ECONOMIC_DATA"
    elif (
        trade_metrics["expectancy_usd"] is not None
        and trade_metrics["expectancy_usd"] <= 0.0
    ) or (
        trade_metrics["profit_factor"] is not None
        and trade_metrics["profit_factor"] < 1.0
    ):
        dominant_problem = "NEGATIVE_TRADE_EXPECTANCY"
    elif filter_metrics["veto_rate_pct"] >= 80.0:
        dominant_problem = "ENTRY_FUNNEL_OVER_FILTERED"
    else:
        dominant_problem = "NO_DOMINANT_PROBLEM_DETECTED"

    last_fvg = fvg_cycles[-1] if fvg_cycles else {}
    scan_latencies = [_finite(event.get("duration_ms")) for event in scan_cycles]
    scan_latencies = [value for value in scan_latencies if value is not None]
    heavy_calls = [int(event.get("heavy_analysis_calls") or 0) for event in scan_cycles]
    return {
        "selection": {
            "campaign": selected_identity[0] if selected_identity else campaign,
            "config_fingerprint": selected_identity[1] if selected_identity else fingerprint,
            "code_version": selected_identity[2] if selected_identity else None,
            "model_type": selected_identity[3] if selected_identity else None,
            "bootstrap_heuristic_mode": selected_identity[4] if selected_identity else None,
            "runtime_mode": selected_identity[5] if selected_identity else None,
            "run_id": selected_identity[6] if selected_identity else None,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
        "segments": [
            {
                "campaign": identity[0],
                "config_fingerprint": identity[1],
                "code_version": identity[2],
                "model_type": identity[3],
                "bootstrap_heuristic_mode": identity[4],
                "runtime_mode": identity[5],
                "run_id": identity[6],
                "events": sum(1 for row in candidates if _identity(row[2]) == identity),
            }
            for identity in identities
        ],
        "events": len(payloads),
        "latest_config": config_snapshots[-1] if config_snapshots else {},
        "filters": filter_metrics,
        "shadow_trades": trade_metrics,
        "fvg": {
            "cycles": len(fvg_cycles),
            "new_gaps": sum(int(event.get("new_gaps") or 0) for event in fvg_cycles),
            "last_active_total": int(last_fvg.get("active_total") or 0),
            "last_status_counts": last_fvg.get("status_counts") or {},
        },
        "operations": {
            **_operations(records, start, end),
            "scan_cycles": len(scan_cycles),
            "scan_cycle_avg_latency_ms": (
                round(sum(scan_latencies) / len(scan_latencies), 3) if scan_latencies else None
            ),
            "heavy_analysis_calls_per_cycle": (
                round(sum(heavy_calls) / len(heavy_calls), 3) if heavy_calls else None
            ),
        },
        "integrity": {
            "malformed_lines": malformed,
            "shadow_events_total": len(shadow_rows),
            "selected_events": len(payloads),
            "mixed_identities": len(identities) > 1,
            "duplicate_trade_events": duplicate_trades,
            "warnings": warnings,
        },
        "conclusion": dominant_problem,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    selection = summary["selection"]
    filters = summary["filters"]
    trades = summary["shadow_trades"]
    integrity = summary["integrity"]
    account_return = trades["account_return_pct"]
    drawdown = trades["max_drawdown_pct"]
    account_return_text = f"{account_return}%" if account_return is not None else "N/A"
    drawdown_text = f"{drawdown}%" if drawdown is not None else "N/A"
    lines = ["# SHADOW Validation Report", ""]
    lines.append(
        f"- Campaign: {selection['campaign']} / {selection['config_fingerprint']} / {selection['code_version']}"
    )
    lines.append(f"- Runtime: {selection['runtime_mode']} / run={selection['run_id']}")
    lines.append(f"- Model: {selection['model_type']} (bootstrap={selection['bootstrap_heuristic_mode']})")
    lines.append(f"- Period: {selection['start']} -> {selection['end']}")
    lines.append(f"- Closed trades: {trades['closed']} | conclusion: {summary['conclusion']}")
    lines.append(
        f"- Winrate / expectancy / PF: {trades['winrate_pct']}% / {trades['expectancy_pct']} / {trades['profit_factor']}"
    )
    lines.append(
        f"- Account return / max drawdown: {account_return_text} / {drawdown_text}"
    )
    lines.append(f"- Net PnL / fees USD: {trades['total_pnl_usd']} / {trades['fees_usd']}")
    lines.append(f"- Avg MAE / MFE: {trades['avg_mae_pct']} / {trades['avg_mfe_pct']}")
    lines.append(f"- Filters / veto rate: {filters['total']} / {filters['veto_rate_pct']}%")
    lines.append(f"- Veto reasons: {filters['veto_reasons']}")
    if integrity["warnings"]:
        lines.append("- Integrity warnings: " + " | ".join(integrity["warnings"]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--campaign")
    parser.add_argument("--fingerprint")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    summary = build_summary(args.path, campaign=args.campaign, fingerprint=args.fingerprint)
    if args.as_json:
        print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(render_markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
