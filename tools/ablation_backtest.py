#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from core.backtester import VectorBacktester
from tools.walk_forward_backtest import BacktestParams, load_candles_csv


DEFAULT_MODES = ("mt_sr_regime", "mt_only", "sr_only", "equal_weight")
DEFAULT_BASELINE_MODE = "mt_sr_regime"


def _row_with_deltas(row: dict, baseline: dict) -> dict:
    return {
        **row,
        "delta_vs_baseline": {
            "objective": float(row["objective"] - baseline["objective"]),
            "profit_factor": float(row["profit_factor"] - baseline["profit_factor"]),
            "max_drawdown": float(row["max_drawdown"] - baseline["max_drawdown"]),
            "net_return_pct": float(row["net_return_pct"] - baseline["net_return_pct"]),
            "trades": int(row["trades"] - baseline["trades"]),
        },
    }


def run_ablation_backtest(
    candles,
    params: BacktestParams,
    modes=DEFAULT_MODES,
    *,
    baseline_mode: str = DEFAULT_BASELINE_MODE,
    candidate_mode: str = "mt_sr_regime",
) -> dict:
    rows = []
    for mode in modes:
        result = VectorBacktester(candles).evaluate(**asdict(params), strategy_mode=mode)
        rows.append({"mode": mode, **asdict(result)})
    rows.sort(key=lambda item: item["objective"], reverse=True)
    baseline = next(row for row in rows if row["mode"] == baseline_mode)
    candidate = next(row for row in rows if row["mode"] == candidate_mode)
    rows_with_deltas = [_row_with_deltas(row, baseline) for row in rows]
    return {
        "baseline_mode": baseline_mode,
        "candidate_mode": candidate_mode,
        "baseline": baseline,
        "candidate": _row_with_deltas(candidate, baseline),
        "best": rows_with_deltas[0],
        "rows": rows_with_deltas,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Vector backtest ablation runner")
    parser.add_argument("--candles", required=True, help="CSV with time,open,high,low,close,volume")
    parser.add_argument("--output", default="reports/ablation_backtest.json")
    parser.add_argument("--z-score-threshold", type=float, default=1.6)
    parser.add_argument("--adx-threshold", type=float, default=25.0)
    parser.add_argument("--stop-loss-pct", type=float, default=1.2)
    parser.add_argument("--take-profit-pct", type=float, default=2.0)
    parser.add_argument("--baseline-mode", default=DEFAULT_BASELINE_MODE, choices=DEFAULT_MODES)
    parser.add_argument("--candidate-mode", default="mt_sr_regime", choices=DEFAULT_MODES)
    args = parser.parse_args()

    params = BacktestParams(
        alma_offset=0.85,
        alma_sigma=6.0,
        z_score_threshold=args.z_score_threshold,
        entropy_bins=8,
        adx_threshold=args.adx_threshold,
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
    )
    report = run_ablation_backtest(
        load_candles_csv(Path(args.candles)),
        params,
        baseline_mode=args.baseline_mode,
        candidate_mode=args.candidate_mode,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "baseline": report["baseline"],
                "candidate": report["candidate"],
                "best": report["best"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
