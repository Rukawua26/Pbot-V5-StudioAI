#!/usr/bin/env python3
"""Hyperparameter optimization for Sniper AI (MT + SR agents).

Phase 2:
- Ensure deep historical ingestion (target 30 days / 1h for BTC/USDT).
- Use vectorized institutional backtest engine.
- Run Optuna at high speed over full dataset.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, Tuple

import ccxt
import optuna
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from core.backtester import VectorBacktester
from core.data_service import DataService

optuna.logging.set_verbosity(optuna.logging.WARNING)

DEFAULT_SYMBOL = "BTC/USDT"
DEFAULT_TIMEFRAME = "1h"
DEFAULT_CANDLES_PATH = Path("data_storage/candles/BTC_USDT_1h.parquet")


def candle_path_for(symbol: str, timeframe: str) -> Path:
    safe_symbol = symbol.replace("/", "_").replace(":", "_")
    safe_tf = timeframe.replace("/", "_").replace(":", "_")
    return Path("data_storage/candles") / f"{safe_symbol}_{safe_tf}.parquet"


def load_candles(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Candle file not found: {path}")

    if path.suffix == ".parquet":
        df_obj = pd.read_parquet(path)
    elif path.suffix == ".pkl":
        df_obj = pd.read_pickle(path)
    else:
        raise ValueError(f"Unsupported candle format: {path}")

    if not isinstance(df_obj, pd.DataFrame):
        raise ValueError("Candle file content is not a DataFrame")
    df = df_obj

    required = {"time", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    return pd.DataFrame(df[["time", "open", "high", "low", "close", "volume"]].copy())


def maybe_refresh_data(symbol: str, timeframe: str, days: int) -> Path:
    exchange = ccxt.binance(
        {
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        }
    )
    service = DataService(exchange)
    service.download_historical_data(symbol=symbol, timeframe=timeframe, days=days)
    return Path(service._candle_file_path(symbol, timeframe))


def run_study(
    engine: VectorBacktester,
    n_trials: int,
    seed: int,
) -> Tuple[optuna.Study, Dict[str, float]]:
    best_snapshot: Dict[str, float] = {}

    def objective(trial: optuna.Trial) -> float:
        alma_offset = trial.suggest_float("alma_offset", 0.70, 0.99)
        alma_sigma = trial.suggest_float("alma_sigma", 4.0, 10.0)
        z_score_threshold = trial.suggest_float("z_score_threshold", 2.0, 3.5)
        entropy_bins = trial.suggest_int("entropy_bins", 8, 20)
        adx_threshold = trial.suggest_float("adx_threshold", 20.0, 30.0)
        stop_loss_pct = trial.suggest_float("stop_loss_pct", 1.0, 3.5)
        take_profit_pct = trial.suggest_float("take_profit_pct", 2.0, 8.0)

        # Restricción mínima de simetría riesgo/beneficio: 1 : 1.2
        if take_profit_pct <= (stop_loss_pct * 1.2):
            trial.set_user_attr("profit_factor", 0.0)
            trial.set_user_attr("max_drawdown", 1.0)
            trial.set_user_attr("trades", 0)
            trial.set_user_attr("net_return_pct", -100.0)
            return 0.0

        result = engine.evaluate(
            alma_offset=alma_offset,
            alma_sigma=alma_sigma,
            z_score_threshold=z_score_threshold,
            entropy_bins=entropy_bins,
            adx_threshold=adx_threshold,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )

        trial.set_user_attr("profit_factor", result.profit_factor)
        trial.set_user_attr("max_drawdown", result.max_drawdown)
        trial.set_user_attr("trades", result.trades)
        trial.set_user_attr("net_return_pct", result.net_return_pct)

        return result.objective

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    t0 = time.perf_counter()
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    elapsed = time.perf_counter() - t0

    best_trial = study.best_trial
    best_snapshot.update(best_trial.params)
    best_snapshot["objective"] = float(
        best_trial.value if best_trial.value is not None else 0.0
    )
    best_snapshot["profit_factor"] = float(
        best_trial.user_attrs.get("profit_factor", 0.0)
    )
    best_snapshot["max_drawdown"] = float(
        best_trial.user_attrs.get("max_drawdown", 0.0)
    )
    best_snapshot["trades"] = int(best_trial.user_attrs.get("trades", 0))
    best_snapshot["net_return_pct"] = float(
        best_trial.user_attrs.get("net_return_pct", 0.0)
    )
    best_snapshot["elapsed_s"] = float(elapsed)

    return study, best_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sniper AI Hyperopt - Vectorized MT/SR"
    )
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--candles", type=Path, default=None)
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--export-json",
        action="store_true",
        help="Export best parameters to config_hyperopt.json",
    )
    parser.add_argument(
        "--refresh-data",
        action="store_true",
        help="Download full historical candles before optimizing",
    )
    args = parser.parse_args()

    if args.trials < 100:
        print("[WARN] Requested trials < 100. For robust search use at least 100.")

    candle_path = (
        args.candles if args.candles else candle_path_for(args.symbol, args.timeframe)
    )
    if args.refresh_data:
        try:
            candle_path = maybe_refresh_data(
                symbol=args.symbol,
                timeframe=args.timeframe,
                days=args.days,
            )
        except Exception as e:
            print(f"[WARN] Historical download failed, using local cache: {e}")

    candles = load_candles(candle_path)
    engine = VectorBacktester(candles)
    meta = engine.metadata()

    study, best = run_study(engine=engine, n_trials=args.trials, seed=args.seed)

    print("=" * 72)
    print("SNIPER AI HYPEROPT REPORT (OPTUNA + VECTOR ENGINE)")
    print("=" * 72)
    print(f"Trials executed : {len(study.trials)}")
    print(f"Data file       : {candle_path}")
    print(f"Data rows       : {meta['rows']}")
    print(f"Data range      : {meta['start']} -> {meta['end']}")
    print(f"Execution time  : {best['elapsed_s']:.2f}s")
    if args.trials >= 100 and best["elapsed_s"] > 15.0:
        print("[WARN] Study exceeded 15s target on current CPU/runtime.")

    print("Best Parameters Found:")
    print(f"  alma_offset      : {best['alma_offset']:.5f}")
    print(f"  alma_sigma       : {best['alma_sigma']:.5f}")
    print(f"  z_score_threshold: {best['z_score_threshold']:.5f}")
    print(f"  entropy_bins     : {int(best['entropy_bins'])}")
    print(f"  adx_threshold    : {best['adx_threshold']:.5f}")
    print(f"  stop_loss_pct    : {best['stop_loss_pct']:.5f}%")
    print(f"  take_profit_pct  : {best['take_profit_pct']:.5f}%")

    print("Performance (estimated):")
    print(f"  Profit Factor    : {best['profit_factor']:.4f}")
    print(f"  Max Drawdown     : {best['max_drawdown'] * 100:.2f}%")
    print(f"  Net Return       : {best['net_return_pct']:.2f}%")
    print(f"  Trades           : {int(best['trades'])}")
    print(f"  Objective Score  : {best['objective']:.4f}")
    print("=" * 72)

    if args.export_json:
        export_payload = {
            "enabled": True,
            "timeframe": args.timeframe,
            "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "source": f"tools/hyperopt_sniper.py --symbol {args.symbol} --timeframe {args.timeframe} --days {args.days} --trials {args.trials}",
            "params": {
                "alma_offset": best["alma_offset"],
                "alma_sigma": best["alma_sigma"],
                "z_score_threshold": best["z_score_threshold"],
                "entropy_bins": int(best["entropy_bins"]),
                "adx_threshold": best["adx_threshold"],
                "stop_loss_pct": best["stop_loss_pct"],
                "take_profit_pct": best["take_profit_pct"],
            },
        }
        out_file = ROOT_DIR / "config_hyperopt.json"
        out_file.write_text(json.dumps(export_payload, indent=2), encoding="utf-8")
        print(f"Exported best config to: {out_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
