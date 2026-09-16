#!/usr/bin/env python3
"""
Script de Respaldo y Reinicio Limpio de Base de Datos para SniperAI.
Respalda tools/sniper_brain.db y sniper_brain.db a backups/legacy_trinity_backup_<timestamp>/
y limpia las tablas operativas para iniciar la prueba de la nueva estrategia.
"""

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def backup_and_clean():
    base_dir = Path(__file__).resolve().parent.parent
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_dir = base_dir / "backups" / f"legacy_trinity_backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_paths = [
        base_dir / "tools" / "sniper_brain.db",
        base_dir / "sniper_brain.db",
    ]

    print(f"📦 Creando respaldo en: {backup_dir}")
    for db_path in db_paths:
        if db_path.exists() and db_path.stat().st_size > 0:
            target_path = backup_dir / db_path.name
            shutil.copy2(db_path, target_path)
            print(f"  ✅ Respaldado: {db_path} -> {target_path} ({db_path.stat().st_size / 1024 / 1024:.2f} MB)")

    # Limpieza de tablas operativas en tools/sniper_brain.db
    primary_db = base_dir / "tools" / "sniper_brain.db"
    if primary_db.exists():
        print(f"🧹 Limpiando tablas operativas en: {primary_db}")
        conn = sqlite3.connect(str(primary_db))
        cursor = conn.cursor()

        tables_to_truncate = [
            "trades",
            "trade_context_annotations",
            "advisory_snapshots",
            "active_trades_state",
            "confidence_exit_audit",
            "equity_history",
            "signal_alerts",
            "trade_context_snapshots",
            "error_snapshots",
            "elite_patterns",
            "experimental_patterns",
            "elite_audit_log",
            "shadow_telemetry",
            "market_context_events",
        ]

        for table in tables_to_truncate:
            try:
                cursor.execute(f"DELETE FROM {table};")
                print(f"  🗑️ Vaciada tabla: {table}")
            except sqlite3.OperationalError as e:
                print(f"  ⚠️ Tabla {table} omitida: {e}")

        # Reset sequences if available
        try:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('trades', 'signal_alerts', 'shadow_telemetry');")
        except Exception:
            pass

        conn.commit()
        cursor.execute("VACUUM;")
        conn.close()
        print("✨ Limpieza completada con éxito. Base de datos lista para nueva estrategia.")


if __name__ == "__main__":
    backup_and_clean()
