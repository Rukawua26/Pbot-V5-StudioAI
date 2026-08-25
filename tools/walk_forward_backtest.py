#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Iterable

import pandas as pd

from core.backtester import VectorBacktester, VectorBacktestResult
from tools.train_models import build_walk_forward_windows


@dataclass(frozen=True)
class BacktestParams:
    alma_offset: float
    alma_sigma: float
    z_score_threshold: float
    entropy_bins: int
    adx_threshold: float
    stop_loss_pct: float
    take_profit_pct: float
    fee_rate: float = 0.0004
    min_probability_threshold: float = 0.0


def default_param_grid() -> list[BacktestParams]:
    grid = []
    for z_score_threshold in (1.2, 1.6, 2.0):
        for adx_threshold in (20.0, 25.0, 30.0):
            for stop_loss_pct, take_profit_pct in ((1.0, 1.5), (1.2, 2.0), (1.5, 2.5)):
                grid.append(
                    BacktestParams(
                        alma_offset=0.85,
                        alma_sigma=6.0,
                        z_score_threshold=z_score_threshold,
                        entropy_bins=8,
                        adx_threshold=adx_threshold,
                        stop_loss_pct=stop_loss_pct,
                        take_profit_pct=take_profit_pct,
                    )
                )
    return grid


def load_candles_csv(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        candles = pd.read_parquet(path)
    else:
        candles = pd.read_csv(path)
    required = {"time", "open", "high", "low", "close", "volume"}
    missing = required - set(candles.columns)
    if missing:
        raise ValueError(f"Missing candle columns: {sorted(missing)}")
    candles = candles.copy()
    candles["time"] = pd.to_datetime(candles["time"], utc=True, errors="coerce")
    if candles["time"].isna().any():
        raise ValueError("Invalid candle time values")
    return candles.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)


def evaluate_params(candles: pd.DataFrame, params: BacktestParams) -> VectorBacktestResult:
    return VectorBacktester(candles).evaluate(**asdict(params))


def select_best_params(
    train_candles: pd.DataFrame,
    grid: Iterable[BacktestParams],
    min_train_trades: int,
) -> tuple[BacktestParams, VectorBacktestResult]:
    best: tuple[BacktestParams, VectorBacktestResult] | None = None
    for params in grid:
        result = evaluate_params(train_candles, params)
        if result.trades < min_train_trades:
            continue
        if best is None or result.objective > best[1].objective:
            best = (params, result)
    if best is None:
        raise ValueError(f"No parameter set produced >= {min_train_trades} train trades")
    return best


def _slice(candles: pd.DataFrame, idx) -> pd.DataFrame:
    return candles.iloc[idx].copy().reset_index(drop=True)


def run_walk_forward_backtest(
    candles: pd.DataFrame,
    *,
    train_months: int = 8,
    val_months: int = 4,
    min_windows: int = 1,
    min_train_trades: int = 8,
    grid: Iterable[BacktestParams] | None = None,
) -> dict:
    candles = candles.copy()
    candles["time"] = pd.to_datetime(candles["time"], utc=True, errors="coerce")
    if candles["time"].isna().any():
        raise ValueError("Invalid candle time values")
    candles = candles.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)

    if len(candles) < 200:
        raise ValueError("At least 200 candles are required for walk-forward backtest")

    windows = build_walk_forward_windows(
        candles["time"].to_numpy(), train_months=train_months, val_months=val_months
    )
    if len(windows) < min_windows:
        raise ValueError(
            f"Insufficient walk-forward windows: {len(windows)} < {min_windows}. "
            "Use more historical candles or shorter train/validation windows."
        )

    grid = list(grid or default_param_grid())
    window_rows = []
    for window in windows:
        train_candles = _slice(candles, window["train_idx"])
        val_candles = _slice(candles, window["val_idx"])
        params, train_result = select_best_params(train_candles, grid, min_train_trades)
        val_result = evaluate_params(val_candles, params)
        window_rows.append(
            {
                "name": window["name"],
                "train_months": window["train_months"],
                "val_months": window["val_months"],
                "best_params": asdict(params),
                "train": asdict(train_result),
                "validation": asdict(val_result),
            }
        )

    val_results = [row["validation"] for row in window_rows]
    validation_profit_factors = [float(row["profit_factor"]) for row in val_results]
    validation_drawdowns = [float(row["max_drawdown"]) for row in val_results]
    validation_returns = [float(row["net_return_pct"]) for row in val_results]
    validation_trades = [int(row["trades"]) for row in val_results]
    positive_windows = sum(1 for value in validation_returns if value > 0.0)

    return {
        "summary": {
            "windows": len(window_rows),
            "positive_validation_windows": positive_windows,
            "avg_validation_profit_factor": sum(validation_profit_factors) / len(validation_profit_factors),
            "median_validation_profit_factor": median(validation_profit_factors),
            "max_validation_drawdown": max(validation_drawdowns),
            "total_validation_trades": sum(validation_trades),
            "avg_validation_return_pct": sum(validation_returns) / len(validation_returns),
        },
        "windows": window_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward vector backtest runner")
    parser.add_argument("--candles", required=True, help="CSV with time,open,high,low,close,volume")
    parser.add_argument("--output", default="reports/walk_forward_backtest.json")
    parser.add_argument("--train-months", type=int, default=8)
    parser.add_argument("--val-months", type=int, default=4)
    parser.add_argument("--min-windows", type=int, default=1)
    parser.add_argument("--min-train-trades", type=int, default=8)
    args = parser.parse_args()

    report = run_walk_forward_backtest(
        load_candles_csv(Path(args.candles)),
        train_months=args.train_months,
        val_months=args.val_months,
        min_windows=args.min_windows,
        min_train_trades=args.min_train_trades,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
