#!/usr/bin/env python3
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "sniper_brain.db"
REPORTS_DIR = ROOT / "docs" / "reports"
CONTROLS_PATH = ROOT / "data_storage" / "symbol_controls.json"
MIN_DECISION_TRADES = 5


def _rows(conn: sqlite3.Connection):
    conn.row_factory = sqlite3.Row
    q = """
    WITH base AS (
      SELECT
        symbol,
        COUNT(*) AS trades,
        SUM(CASE WHEN pnl_percent > 0 THEN 1 ELSE 0 END) AS wins,
        SUM(CASE WHEN pnl_percent <= 0 THEN 1 ELSE 0 END) AS losses,
        ROUND(100.0 * SUM(CASE WHEN pnl_percent > 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS win_rate_pct,
        ROUND(SUM(pnl), 6) AS total_pnl_usd,
        ROUND(AVG(pnl_percent), 6) AS avg_pnl_pct,
        ROUND(SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END), 6) AS gross_profit_usd,
        ROUND(ABS(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END)), 6) AS gross_loss_usd,
        ROUND(
          (SUM(CASE WHEN pnl_percent > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*)) *
            COALESCE(AVG(CASE WHEN pnl_percent > 0 THEN pnl_percent END), 0) +
          ((COUNT(*) - SUM(CASE WHEN pnl_percent > 0 THEN 1 ELSE 0 END)) * 1.0 / COUNT(*)) *
            COALESCE(AVG(CASE WHEN pnl_percent <= 0 THEN pnl_percent END), 0),
          6
        ) AS expectancy_pct
      FROM trades
      WHERE symbol IS NOT NULL
        AND COALESCE(side, '') != 'VETO_ERROR'
        AND COALESCE(pnl_percent, 0) > -99.0
      GROUP BY symbol
    )
    SELECT
      symbol,
      trades,
      wins,
      losses,
      win_rate_pct,
      total_pnl_usd,
      avg_pnl_pct,
      CASE WHEN gross_loss_usd > 0 THEN ROUND(gross_profit_usd / gross_loss_usd, 6) ELSE 0 END AS profit_factor,
      expectancy_pct,
      CASE
        WHEN trades < {MIN_DECISION_TRADES} THEN 'OBSERVAR'
        WHEN trades >= {MIN_DECISION_TRADES} AND (CASE WHEN gross_loss_usd > 0 THEN gross_profit_usd / gross_loss_usd ELSE 0 END) >= 1.20 AND expectancy_pct > 0 AND win_rate_pct >= 50 THEN 'MANTENER'
        WHEN trades >= {MIN_DECISION_TRADES} AND (CASE WHEN gross_loss_usd > 0 THEN gross_profit_usd / gross_loss_usd ELSE 0 END) >= 0.90 AND expectancy_pct >= 0 AND win_rate_pct >= 45 THEN 'REDUCIR'
        ELSE 'BLOQUEAR'
      END AS decision,
      CASE
        WHEN trades < {MIN_DECISION_TRADES} THEN 'Muestra insuficiente (<{MIN_DECISION_TRADES})'
        WHEN trades >= {MIN_DECISION_TRADES} AND (CASE WHEN gross_loss_usd > 0 THEN gross_profit_usd / gross_loss_usd ELSE 0 END) >= 1.20 AND expectancy_pct > 0 AND win_rate_pct >= 50 THEN 'PF>=1.2, expectancy>0, WR>=50'
        WHEN trades >= {MIN_DECISION_TRADES} AND (CASE WHEN gross_loss_usd > 0 THEN gross_profit_usd / gross_loss_usd ELSE 0 END) >= 0.90 AND expectancy_pct >= 0 AND win_rate_pct >= 45 THEN 'PF>=0.9, expectancy>=0, WR>=45'
        ELSE 'PF/WR/expectancy debiles'
      END AS rule_reason
    FROM base
    ORDER BY
      CASE decision
        WHEN 'MANTENER' THEN 1
        WHEN 'REDUCIR' THEN 2
        WHEN 'OBSERVAR' THEN 3
        ELSE 4
      END,
      total_pnl_usd DESC;
    """.format(MIN_DECISION_TRADES=MIN_DECISION_TRADES)
    return conn.execute(q).fetchall()


def _write_csv(rows):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "symbol_decision_matrix.csv"
    if not rows:
        out.write_text("", encoding="utf-8")
        return out
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(dict(r))
    return out


def _write_controls(rows):
    blocked = []
    preferred = []
    reduced = []
    for r in rows:
        base = str(r["symbol"]).split("/")[0]
        if r["decision"] == "BLOQUEAR":
            blocked.append(base)
        elif r["decision"] == "MANTENER":
            preferred.append(base)
        elif r["decision"] == "REDUCIR":
            reduced.append(base)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "sniper_brain.db/trades",
        "blocked_symbols": sorted(set(blocked)),
        "preferred_symbols": sorted(set(preferred)),
        "reduced_symbols": sorted(set(reduced)),
    }

    CONTROLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTROLS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _sync_blacklist(conn, blocked_symbols):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn.execute("DELETE FROM symbol_blacklist")
    for s in blocked_symbols:
        conn.execute(
            "INSERT INTO symbol_blacklist (symbol, reason, added_date) VALUES (?, ?, ?)",
            (s, "DecisionMatrix:BLOQUEAR", now),
        )
    conn.commit()


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = _rows(conn)
        csv_path = _write_csv(rows)
        controls = _write_controls(rows)
        _sync_blacklist(conn, controls["blocked_symbols"])
    finally:
        conn.close()

    print("Decision matrix generated:", csv_path)
    print("Controls generated:", CONTROLS_PATH)
    print("Blocked:", len(controls["blocked_symbols"]))
    print("Preferred:", len(controls["preferred_symbols"]))
    print("Reduced:", len(controls["reduced_symbols"]))


if __name__ == "__main__":
    main()
