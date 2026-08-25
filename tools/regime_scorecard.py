#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class RegimeMetrics:
    regime: str
    trades: int
    wins: int
    losses: int
    win_rate: float
    expectancy_pct: float
    gross_profit_pct: float
    gross_loss_pct: float
    profit_factor: float
    avg_win_pct: float
    avg_loss_pct: float
    net_pnl_pct: float
    max_drawdown_pct: float


def safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _fetch_trade_rows(conn: sqlite3.Connection, where_sql: str) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT market_regime, pnl_percent, timestamp
        FROM trades
        WHERE pnl_percent IS NOT NULL AND {where_sql}
        ORDER BY timestamp ASC
        """
    )
    return list(cur.fetchall())


def _compute_drawdown_from_returns(returns_pct: Iterable[float]) -> float:
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for ret_pct in returns_pct:
        equity *= 1.0 + (float(ret_pct) / 100.0)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, 1.0 - (equity / peak))
    return max_dd * 100.0


def compute_regime_scorecard(conn: sqlite3.Connection, where_sql: str) -> list[RegimeMetrics]:
    rows = _fetch_trade_rows(conn, where_sql)
    grouped: dict[str, list[float]] = {}
    for row in rows:
        regime = str(row["market_regime"] or "UNKNOWN")
        grouped.setdefault(regime, []).append(float(row["pnl_percent"] or 0.0))

    metrics: list[RegimeMetrics] = []
    for regime, returns in sorted(grouped.items()):
        trades = len(returns)
        wins = sum(1 for ret in returns if ret > 0.0)
        losses = sum(1 for ret in returns if ret <= 0.0)
        gross_profit = sum(ret for ret in returns if ret > 0.0)
        gross_loss = sum(ret for ret in returns if ret <= 0.0)
        avg_win = safe_div(gross_profit, wins)
        avg_loss = safe_div(gross_loss, losses)
        p_win = safe_div(wins, trades)
        p_loss = safe_div(losses, trades)
        metrics.append(
            RegimeMetrics(
                regime=regime,
                trades=trades,
                wins=wins,
                losses=losses,
                win_rate=p_win * 100.0,
                expectancy_pct=(p_win * avg_win) + (p_loss * avg_loss),
                gross_profit_pct=gross_profit,
                gross_loss_pct=gross_loss,
                profit_factor=safe_div(gross_profit, abs(gross_loss)),
                avg_win_pct=avg_win,
                avg_loss_pct=avg_loss,
                net_pnl_pct=sum(returns),
                max_drawdown_pct=_compute_drawdown_from_returns(returns),
            )
        )
    return metrics


def print_scorecard(rows: list[RegimeMetrics]) -> None:
    print("REGIME scorecard")
    print(
        "regime         trades  wr%    exp%     pf      net%      max_dd%   avg_win%  avg_loss%"
    )
    print("------------------------------------------------------------------------------------------")
    for row in rows:
        print(
            f"{row.regime:13} {row.trades:6d} {row.win_rate:5.1f} {row.expectancy_pct:8.4f} "
            f"{row.profit_factor:7.4f} {row.net_pnl_pct:9.4f} {row.max_drawdown_pct:10.4f} "
            f"{row.avg_win_pct:9.4f} {row.avg_loss_pct:10.4f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Scorecard por régimen desde trades históricos")
    parser.add_argument("--db", default="sniper_brain.db")
    parser.add_argument("--shadow-only", action="store_true")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB no encontrada: {db_path}")
    if args.shadow_only and args.real_only:
        raise SystemExit("No puedes usar --shadow-only y --real-only al mismo tiempo")

    where_sql = "1=1"
    if args.shadow_only:
        where_sql = "is_shadow = 1"
    elif args.real_only:
        where_sql = "is_shadow = 0"

    conn = sqlite3.connect(str(db_path))
    try:
        rows = compute_regime_scorecard(conn, where_sql)
    finally:
        conn.close()

    print_scorecard(rows)
    if args.json_out:
        out = Path(args.json_out)
        out.write_text(
            __import__("json").dumps([asdict(row) for row in rows], indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"json_out: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
