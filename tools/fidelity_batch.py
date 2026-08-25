#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.export_validation_candles import (
    _days_covering_event_range,
    export_validation_candles,
)
from tools.fidelity_audit import FidelityParams, _load_jsonl, run_fidelity_audit
from tools.walk_forward_backtest import BacktestParams


def _safe_symbol_name(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", symbol).strip("_") or "symbol"


def top_symbols_from_events(events: list[dict[str, Any]], *, limit: int) -> list[str]:
    counter: Counter[str] = Counter()
    for event in events:
        if str(event.get("event") or "") not in {"FILTER_APPLIED", "SIGNAL_ANALYZED"}:
            continue
        symbol = str((event.get("payload") or {}).get("symbol") or "").strip()
        if symbol:
            counter[symbol] += 1
    return [symbol for symbol, _count in counter.most_common(max(0, int(limit)))]


def summarize_batch(reports: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    total_samples = 0
    weighted_score = 0.0
    false_positive_count = 0
    false_negative_count = 0
    modeled_veto_components: Counter[str] = Counter()
    runtime_veto_reasons: Counter[str] = Counter()
    exogenous_unmodeled: Counter[str] = Counter()
    false_positive_diagnostics: Counter[str] = Counter()

    for report in reports:
        summary = report.get("summary") or {}
        params = (report.get("params") or {}).get("fidelity") or {}
        symbol = str(params.get("symbol") or "")
        samples = int(summary.get("samples", 0) or 0)
        score = float(summary.get("fidelity_score", 0.0) or 0.0)
        total_samples += samples
        weighted_score += score * samples
        false_positive_count += int(summary.get("false_positive_count", 0) or 0)
        false_negative_count += int(summary.get("false_negative_count", 0) or 0)
        modeled_veto_components.update(summary.get("proxy_modeled_veto_reason_components") or {})
        runtime_veto_reasons.update(summary.get("runtime_veto_reasons") or {})
        exogenous_unmodeled.update(summary.get("exogenous_veto_reasons_not_modeled") or {})
        false_positive_diagnostics.update(summary.get("proxy_false_positive_diagnostics") or {})
        rows.append(
            {
                "symbol": symbol,
                "samples": samples,
                "fidelity_score": score,
                "action_agreement_rate": summary.get("action_agreement_rate"),
                "runtime_execute_rate": summary.get("runtime_execute_rate"),
                "proxy_execute_rate": summary.get("proxy_execute_rate"),
                "false_positive_count": summary.get("false_positive_count"),
                "false_negative_count": summary.get("false_negative_count"),
            }
        )
    return {
        "symbols": len(rows),
        "total_samples": total_samples,
        "weighted_fidelity_score": round(weighted_score / total_samples, 6)
        if total_samples
        else 0.0,
        "false_positive_count": false_positive_count,
        "false_negative_count": false_negative_count,
        "runtime_veto_reasons": dict(runtime_veto_reasons.most_common()),
        "proxy_modeled_veto_reason_components": dict(modeled_veto_components.most_common()),
        "proxy_false_positive_diagnostics": dict(false_positive_diagnostics.most_common()),
        "exogenous_veto_reasons_not_modeled": dict(exogenous_unmodeled.most_common()),
        "rows": rows,
    }


def run_fidelity_batch(
    *,
    events_path: Path,
    symbols: list[str],
    symbol_limit: int,
    candle_dir: Path,
    output_path: Path,
    timeframe: str,
    days_padding: int,
    params: BacktestParams,
    score_pass_threshold: float,
) -> dict[str, Any]:
    events = _load_jsonl(events_path)
    if not symbols:
        symbols = top_symbols_from_events(events, limit=symbol_limit)
    reports = []
    failures = []
    candle_dir.mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        try:
            candle_path = candle_dir / f"{_safe_symbol_name(symbol)}_{timeframe}_runtime.csv"
            days = _days_covering_event_range(
                events_path,
                symbol,
                padding_days=days_padding,
            )
            export_validation_candles(
                symbol=symbol,
                timeframe=timeframe,
                days=days,
                output=candle_path,
            )
            fidelity_params = FidelityParams(
                symbol=symbol,
                limit=500,
                timeframe=timeframe,
                max_time_delta_seconds=3900,
                strategy_mode="mt_sr_regime",
                score_pass_threshold=score_pass_threshold,
                apply_shock_veto=True,
                shock_min_dist_pct=0.4,
                apply_market_breadth_veto=True,
                apply_mtf_veto=True,
                apply_kava_veto=True,
                apply_runtime_confidence_gate=True,
                shadow_min_threshold=55.0,
            )
            reports.append(
                run_fidelity_audit(
                    events_path=events_path,
                    candles_path=candle_path,
                    output_path=output_path.parent
                    / f"fidelity_audit_{_safe_symbol_name(symbol)}.json",
                    params=params,
                    fidelity_params=fidelity_params,
                )
            )
        except Exception as error:
            failures.append({"symbol": symbol, "error": str(error)[:300]})
    batch = {
        "params": {
            "events_path": str(events_path),
            "symbols": symbols,
            "timeframe": timeframe,
            "backtest": asdict(params),
        },
        "summary": summarize_batch(reports),
        "failures": failures,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(batch, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return batch


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fidelity audit across multiple symbols")
    parser.add_argument("--events", default="logs/execution_events.jsonl")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols. Defaults to top symbols from events.")
    parser.add_argument("--symbol-limit", type=int, default=5)
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--candle-dir", default="data/fidelity")
    parser.add_argument("--output", default="reports/fidelity_batch.json")
    parser.add_argument("--days-padding", type=int, default=2)
    parser.add_argument("--score-pass-threshold", type=float, default=0.80)
    args = parser.parse_args()

    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    params = BacktestParams(
        alma_offset=0.85,
        alma_sigma=6.0,
        z_score_threshold=1.6,
        entropy_bins=8,
        adx_threshold=25.0,
        stop_loss_pct=1.2,
        take_profit_pct=2.0,
    )
    report = run_fidelity_batch(
        events_path=Path(args.events),
        symbols=symbols,
        symbol_limit=args.symbol_limit,
        candle_dir=Path(args.candle_dir),
        output_path=Path(args.output),
        timeframe=args.timeframe,
        days_padding=args.days_padding,
        params=params,
        score_pass_threshold=args.score_pass_threshold,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0 if float(report["summary"]["weighted_fidelity_score"]) >= args.score_pass_threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
