#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


REPORT_SQL = """
WITH audit_rows AS (
    SELECT
        'AUDIT' AS source,
        t.id AS trade_id,
        t.timestamp AS close_ts,
        a.first_floor_ts AS conf_drop_ts,
        a.entry_client_order_id,
        t.symbol,
        t.side,
        t.is_shadow,
        t.reason,
        a.trigger_reason,
        a.guard_reason,
        a.defer_count,
        ROUND((julianday(t.timestamp) - julianday(a.first_floor_ts)) * 24.0 * 60.0, 2) AS survival_time_min,
        ROUND(COALESCE(a.entry_confidence, t.entry_confidence), 4) AS entry_confidence,
        ROUND(COALESCE(a.floor_confidence, t.exit_confidence), 4) AS exit_confidence_at_drop,
        ROUND(COALESCE(a.entry_confidence, t.entry_confidence) - COALESCE(a.floor_confidence, t.exit_confidence), 4) AS confidence_drop,
        a.dominant_killer AS vote_verdict,
        ROUND(a.floor_price, 8) AS floor_price,
        ROUND(a.gross_pnl_at_conf_drop_usd, 8) AS gross_pnl_at_conf_drop,
        ROUND(t.pnl, 8) AS final_pnl,
        ROUND(t.pnl - a.gross_pnl_at_conf_drop_usd, 8) AS delta_pnl_by_defer,
        CASE WHEN (t.pnl - a.gross_pnl_at_conf_drop_usd) >= 0 THEN 1 ELSE 0 END AS was_it_worth_it,
        ROUND(a.fee_floor_usd, 8) AS fee_floor_usd,
        ROUND(a.fee_floor_pct, 4) AS fee_floor_pct,
        CASE WHEN a.fee_noise_zone = 1 THEN 'YES' ELSE 'NO' END AS gross_vs_fee_zone,
        ROUND(COALESCE(a.gross_pnl_at_conf_drop_pct, 0.0), 4) AS gross_pnl_at_conf_drop_pct,
        ROUND(t.pnl_percent, 4) AS final_pnl_pct
    FROM confidence_exit_audit a
    JOIN trades t
      ON t.entry_client_order_id = a.entry_client_order_id
    WHERE t.reason LIKE 'DEGRADED_%' OR t.reason LIKE 'CONF_DEGRADED_%'
),
legacy_rows AS (
    SELECT
        'LEGACY' AS source,
        t.id AS trade_id,
        t.timestamp AS close_ts,
        t.timestamp AS conf_drop_ts,
        t.entry_client_order_id,
        t.symbol,
        t.side,
        t.is_shadow,
        t.reason,
        t.reason AS trigger_reason,
        'LEGACY_NO_DEFER_DATA' AS guard_reason,
        0 AS defer_count,
        0.0 AS survival_time_min,
        ROUND(t.entry_confidence, 4) AS entry_confidence,
        ROUND(t.exit_confidence, 4) AS exit_confidence_at_drop,
        ROUND(t.entry_confidence - t.exit_confidence, 4) AS confidence_drop,
        NULL AS vote_verdict,
        ROUND(t.exit_price, 8) AS floor_price,
        ROUND(
            CASE
                WHEN t.side = 'SELL' THEN (t.entry_price - t.exit_price) * (t.fees / (0.001 * (t.entry_price + t.exit_price)))
                ELSE (t.exit_price - t.entry_price) * (t.fees / (0.001 * (t.entry_price + t.exit_price)))
            END,
            8
        ) AS gross_pnl_at_conf_drop,
        ROUND(t.pnl, 8) AS final_pnl,
        ROUND(
            t.pnl - CASE
                WHEN t.side = 'SELL' THEN (t.entry_price - t.exit_price) * (t.fees / (0.001 * (t.entry_price + t.exit_price)))
                ELSE (t.exit_price - t.entry_price) * (t.fees / (0.001 * (t.entry_price + t.exit_price)))
            END,
            8
        ) AS delta_pnl_by_defer,
        0 AS was_it_worth_it,
        ROUND(t.fees, 8) AS fee_floor_usd,
        ROUND((t.fees / NULLIF(t.entry_price * (t.fees / (0.001 * (t.entry_price + t.exit_price))), 0.0)) * 100.0, 4) AS fee_floor_pct,
        CASE
            WHEN ABS(
                CASE
                    WHEN t.side = 'SELL' THEN (t.entry_price - t.exit_price) * (t.fees / (0.001 * (t.entry_price + t.exit_price)))
                    ELSE (t.exit_price - t.entry_price) * (t.fees / (0.001 * (t.entry_price + t.exit_price)))
                END
            ) < ABS(t.fees) THEN 'YES'
            ELSE 'NO'
        END AS gross_vs_fee_zone,
        ROUND(
            (
                CASE
                    WHEN t.side = 'SELL' THEN (t.entry_price - t.exit_price)
                    ELSE (t.exit_price - t.entry_price)
                END / NULLIF(t.entry_price, 0.0)
            ) * 100.0,
            4
        ) AS gross_pnl_at_conf_drop_pct,
        ROUND(t.pnl_percent, 4) AS final_pnl_pct
    FROM trades t
    WHERE (t.reason LIKE 'DEGRADED_%' OR t.reason LIKE 'CONF_DEGRADED_%')
      AND NOT EXISTS (
          SELECT 1
          FROM confidence_exit_audit a
          WHERE a.entry_client_order_id = t.entry_client_order_id
      )
),
combined AS (
    SELECT * FROM audit_rows
    UNION ALL
    SELECT * FROM legacy_rows
)
SELECT
    source,
    trade_id,
    symbol,
    side,
    is_shadow,
    close_ts,
    conf_drop_ts,
    entry_confidence,
    exit_confidence_at_drop,
    confidence_drop,
    vote_verdict,
    trigger_reason,
    guard_reason,
    defer_count,
    survival_time_min,
    floor_price,
    gross_pnl_at_conf_drop,
    final_pnl,
    delta_pnl_by_defer,
    was_it_worth_it,
    fee_floor_usd,
    fee_floor_pct,
    gross_vs_fee_zone,
    gross_pnl_at_conf_drop_pct,
    final_pnl_pct
FROM combined
ORDER BY trade_id DESC
LIMIT ?;
"""

ENSURE_AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS confidence_exit_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_client_order_id TEXT UNIQUE,
    symbol TEXT,
    side TEXT,
    is_shadow BOOLEAN DEFAULT 0,
    entry_price REAL,
    amount REAL,
    entry_time TEXT,
    entry_confidence REAL,
    floor_confidence REAL,
    confidence_drop_pct REAL,
    floor_price REAL,
    gross_pnl_at_conf_drop_usd REAL,
    gross_pnl_at_conf_drop_pct REAL,
    fee_floor_usd REAL,
    fee_floor_pct REAL,
    fee_noise_zone INTEGER DEFAULT 0,
    guard_reason TEXT,
    trigger_reason TEXT,
    votes_json TEXT,
    dominant_killer TEXT,
    first_floor_ts TEXT,
    defer_count INTEGER DEFAULT 0,
    last_defer_ts TEXT,
    final_trade_id INTEGER,
    final_ts TEXT,
    final_reason TEXT,
    final_pnl_usd REAL,
    final_pnl_percent REAL
)
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Reporte de verdad del Fee Guard")
    parser.add_argument("--db", default="sniper_brain.db")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB no encontrada: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(ENSURE_AUDIT_TABLE_SQL)
    rows = conn.execute(REPORT_SQL, (args.limit,)).fetchall()
    conn.close()

    print("=== FEE GUARD TRUTH REPORT ===")
    print(f"DB: {db_path}")
    print(f"Rows: {len(rows)}")
    print()
    for row in rows:
        print(
            " | ".join(
                [
                    f"src={row['source']}",
                    f"id={row['trade_id']}",
                    f"sym={row['symbol']}",
                    f"drop={row['confidence_drop']}",
                    f"killer={row['vote_verdict']}",
                    f"gross={row['gross_pnl_at_conf_drop']}",
                    f"final={row['final_pnl']}",
                    f"delta={row['delta_pnl_by_defer']}",
                    f"worth={row['was_it_worth_it']}",
                    f"survival_min={row['survival_time_min']}",
                    f"zone={row['gross_vs_fee_zone']}",
                    f"reason={row['trigger_reason']}",
                ]
            )
        )


if __name__ == "__main__":
    main()
