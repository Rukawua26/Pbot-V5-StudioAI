#!/usr/bin/env python3
"""Reporte baseline 48h (solo lectura).

Reglas:
- No modifica codigo de produccion.
- Solo lectura de sniper_brain.db y sniper.log.

Salida:
- Trades Totales (SHADOW)
- Win Rate % y PnL Neto
- Promedio MAE y MFE
- % cierres DEGRADED vs SL/TP duro
- Cantidad de senales bloqueadas por VETO 4H (log)
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional


DEFAULT_DB = Path("sniper_brain.db")
DEFAULT_LOG = Path("sniper.log")

LOG_TS_FMT = "%Y-%m-%d %H:%M:%S"


@dataclass
class TradeRow:
    timestamp: Optional[str]
    open_time: Optional[str]
    pnl_percent: Optional[float]
    mae_percent: Optional[float]
    mfe_percent: Optional[float]
    reason: Optional[str]
    is_shadow: int


def parse_dt(value: object) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value))
        except Exception:
            return None

    text = str(value).strip()
    if not text:
        return None

    fmts = (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    )
    for fmt in fmts:
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue

    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return (part / total) * 100.0


def classify_reason(reason: Optional[str]) -> str:
    txt = (reason or "").upper().strip()
    if not txt:
        return "OTHER"

    degraded_markers = (
        "DEGRADED_",
        "CONF_DEGRADED_",
        "SHORT_THESIS_INVALIDATED",
        "CONFIDENCE_FLOOR_VIOLATED",
        "SUDDEN_CONFIDENCE_CRASH",
    )
    if any(m in txt for m in degraded_markers):
        return "DEGRADED"

    hard_patterns = (
        r"\bSL\b",
        r"STOP[_ ]?LOSS",
        r"HARD[_ ]?SL",
        r"\bTP\d*\b",
        r"TAKE[_ ]?PROFIT",
    )
    if any(re.search(p, txt) for p in hard_patterns):
        return "HARD_SLTP"

    return "OTHER"


def load_shadow_trades(db_path: Path) -> list[TradeRow]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT timestamp, open_time, pnl_percent, mae_percent, mfe_percent, reason, is_shadow
        FROM trades
        WHERE is_shadow = 1
        """
    )
    rows = [
        TradeRow(
            timestamp=row["timestamp"],
            open_time=row["open_time"],
            pnl_percent=row["pnl_percent"],
            mae_percent=row["mae_percent"],
            mfe_percent=row["mfe_percent"],
            reason=row["reason"],
            is_shadow=int(row["is_shadow"] or 0),
        )
        for row in cur.fetchall()
    ]
    conn.close()
    return rows


def filter_last_hours(rows: Iterable[TradeRow], hours: int) -> list[TradeRow]:
    now = datetime.now()
    cutoff = now - timedelta(hours=hours)
    out: list[TradeRow] = []

    for row in rows:
        ts = parse_dt(row.timestamp) or parse_dt(row.open_time)
        if ts is None:
            continue
        if ts >= cutoff:
            out.append(row)

    return out


def count_veto_4h(log_path: Path, hours: int) -> int:
    if not log_path.exists():
        return 0

    now = datetime.now()
    cutoff = now - timedelta(hours=hours)
    count = 0

    with log_path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if "VETO_4H" not in line:
                continue

            # Formato esperado: YYYY-MM-DD HH:MM:SS | ...
            ts = None
            if len(line) >= 19:
                try:
                    ts = datetime.strptime(line[:19], LOG_TS_FMT)
                except Exception:
                    ts = None

            if ts is None or ts < cutoff:
                continue
            count += 1

    return count


def fmt_float(v: Optional[float], digits: int = 2) -> str:
    if v is None:
        return "N/A"
    return f"{v:.{digits}f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Reporte baseline 48h (solo lectura)")
    parser.add_argument("--hours", type=int, default=48, help="Ventana en horas")
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB, help="Ruta a sniper_brain.db"
    )
    parser.add_argument(
        "--log", type=Path, default=DEFAULT_LOG, help="Ruta a sniper.log"
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"DB no encontrada: {args.db}")

    trades_all = load_shadow_trades(args.db)
    trades = filter_last_hours(trades_all, args.hours)

    total = len(trades)
    closed = [t for t in trades if t.pnl_percent is not None]

    wins = sum(1 for t in closed if (t.pnl_percent or 0.0) > 0)
    pnl_neto = sum((t.pnl_percent or 0.0) for t in closed)

    mae_vals = [float(t.mae_percent) for t in closed if t.mae_percent is not None]
    mfe_vals = [float(t.mfe_percent) for t in closed if t.mfe_percent is not None]
    avg_mae = sum(mae_vals) / len(mae_vals) if mae_vals else None
    avg_mfe = sum(mfe_vals) / len(mfe_vals) if mfe_vals else None

    degraded_n = 0
    hard_sltp_n = 0
    other_n = 0
    for t in closed:
        c = classify_reason(t.reason)
        if c == "DEGRADED":
            degraded_n += 1
        elif c == "HARD_SLTP":
            hard_sltp_n += 1
        else:
            other_n += 1

    veto_4h_count = count_veto_4h(args.log, args.hours)

    now = datetime.now()
    start = now - timedelta(hours=args.hours)

    print("=" * 72)
    print("BASELINE 48H - RESUMEN EJECUTIVO (SOLO LECTURA)")
    print("=" * 72)
    print(
        f"Ventana: {start.strftime('%Y-%m-%d %H:%M:%S')} -> {now.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print(f"DB: {args.db}")
    print(f"Log: {args.log}")
    print("-" * 72)

    print(f"Trades Totales SHADOW: {total}")
    print(f"Trades cerrados (con pnl): {len(closed)}")
    print(f"Win Rate: {pct(wins, len(closed)):.2f}% ({wins}/{len(closed)})")
    print(f"PnL Neto: {pnl_neto:+.2f}%")
    print(f"MAE promedio: {fmt_float(avg_mae)}%")
    print(f"MFE promedio: {fmt_float(avg_mfe)}%")

    print("-" * 72)
    print("Cierres por tipo:")
    print(
        f"  DEGRADED (Smart Exit): {degraded_n} ({pct(degraded_n, len(closed)):.2f}%)"
    )
    print(f"  SL/TP duro: {hard_sltp_n} ({pct(hard_sltp_n, len(closed)):.2f}%)")
    print(f"  Otros: {other_n} ({pct(other_n, len(closed)):.2f}%)")

    print("-" * 72)
    print(f"Senales bloqueadas por VETO 4H (log): {veto_4h_count}")
    print("=" * 72)

    if total == 0:
        print("ADVERTENCIA: no hay trades SHADOW en la ventana consultada.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
