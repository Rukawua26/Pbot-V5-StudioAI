#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def evaluate_config_readiness(config: dict[str, Any]) -> list[str]:
    failures = []
    if _bool(config.get("PAPER_MODE", True)):
        failures.append("PAPER_MODE must be false for REAL readiness check")
    if not _bool(config.get("ALLOW_REAL_TRADING", False)):
        failures.append("ALLOW_REAL_TRADING=true is required")
    if _bool(config.get("USE_TESTNET", False)):
        failures.append("USE_TESTNET must be false for REAL")
    if not config.get("BINANCE_API_KEY") or not config.get("BINANCE_API_SECRET"):
        failures.append("Binance API credentials are required")
    if not config.get("TELEGRAM_TOKEN") or not config.get("TELEGRAM_CHAT_ID"):
        failures.append("Telegram token/chat_id are required")

    max_open = int(float(config.get("MAX_OPEN_TRADES", 0) or 0))
    max_risk = float(config.get("MAX_RISK_USD", 0.0) or 0.0)
    risk_pct = float(config.get("RISK_PER_TRADE_PERCENT", 0.0) or 0.0)
    if max_open < 1 or max_open > 3:
        failures.append("MAX_OPEN_TRADES must be between 1 and 3 for initial REAL")
    if max_risk <= 0 or max_risk > 50:
        failures.append("MAX_RISK_USD must be in (0, 50] for initial REAL")
    if risk_pct <= 0 or risk_pct > 0.5:
        failures.append("RISK_PER_TRADE_PERCENT must be in (0, 0.5] for initial REAL")
    return failures


def evaluate_walk_forward_report(
    report: dict[str, Any], *, min_profit_factor: float, max_drawdown: float
) -> list[str]:
    summary = report.get("summary") or {}
    failures = []
    windows = int(summary.get("windows", 0) or 0)
    positive_windows = int(summary.get("positive_validation_windows", 0) or 0)
    profit_factor = float(summary.get("avg_validation_profit_factor", 0.0) or 0.0)
    drawdown = float(summary.get("max_validation_drawdown", 1.0) or 1.0)
    trades = int(summary.get("total_validation_trades", 0) or 0)

    if windows <= 0:
        failures.append("walk-forward report has no validation windows")
    if windows > 0 and positive_windows < max(1, (windows + 1) // 2):
        failures.append("positive validation windows are insufficient")
    if profit_factor < min_profit_factor:
        failures.append(f"avg validation profit factor {profit_factor:.4f} < {min_profit_factor:.4f}")
    if drawdown > max_drawdown:
        failures.append(f"max validation drawdown {drawdown:.4f} > {max_drawdown:.4f}")
    if trades <= 0:
        failures.append("walk-forward validation produced zero trades")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="REAL trading readiness gate")
    parser.add_argument("--walk-forward-report", default="reports/walk_forward_backtest.json")
    parser.add_argument("--require-walk-forward", action="store_true")
    parser.add_argument("--min-profit-factor", type=float, default=1.2)
    parser.add_argument("--max-drawdown", type=float, default=0.20)
    args = parser.parse_args()

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
    failures = evaluate_config_readiness(config)

    report_path = Path(args.walk_forward_report)
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        failures.extend(
            evaluate_walk_forward_report(
                report,
                min_profit_factor=args.min_profit_factor,
                max_drawdown=args.max_drawdown,
            )
        )
    elif args.require_walk_forward:
        failures.append(f"walk-forward report not found: {report_path}")

    if failures:
        print("REAL readiness: FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("REAL readiness: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
