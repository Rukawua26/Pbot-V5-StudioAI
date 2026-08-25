#!/usr/bin/env python3
"""
Purga trades basura de tipo VETO_ERROR (-99%) de sniper_brain.db.

Uso:
  python tools/purge_veto_error_trades.py --db sniper_brain.db --apply

Por defecto corre en modo dry-run (no borra nada).
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path


PURGE_WHERE = """
(
    (COALESCE(side, '') = 'VETO_ERROR' OR COALESCE(reason, '') = 'VETO_ERROR')
    AND COALESCE(pnl_percent, 0) <= -98.0
)
"""


def query_count(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM trades WHERE {PURGE_WHERE}")
    row = cur.fetchone()
    return int(row[0] if row else 0)


def backup_db(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"sniper_brain_pre_purge_{ts}.db"

    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(backup_path))
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return backup_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Purga trades VETO_ERROR (-99%)")
    parser.add_argument("--db", default="sniper_brain.db")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica borrado real (sin este flag solo simula)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB no encontrada: {db_path}")

    conn = sqlite3.connect(str(db_path))
    before = query_count(conn)

    print("=== Purga VETO_ERROR ===")
    print(f"DB: {db_path}")
    print(f"Registros candidatos: {before}")

    if not args.apply:
        print("Modo dry-run. Usa --apply para borrar.")
        conn.close()
        return

    backup_path = backup_db(db_path)
    print(f"Backup creado: {backup_path}")

    cur = conn.cursor()
    cur.execute("BEGIN")
    cur.execute(f"DELETE FROM trades WHERE {PURGE_WHERE}")
    deleted = cur.rowcount if cur.rowcount is not None else 0
    cur.execute("COMMIT")

    cur.execute("VACUUM")
    after = query_count(conn)
    conn.close()

    print(f"Registros borrados: {deleted}")
    print(f"Registros restantes (candidatos): {after}")


if __name__ == "__main__":
    main()
