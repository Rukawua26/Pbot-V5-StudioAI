"""
SNIPER AI - MASTER DATASET EXPORTER (LSTM READY)
================================================
Exporta el historial de trades y snapshots a un formato secuencial
listo para entrenar redes neuronales recurrentes (LSTM/GRU).
"""

import sqlite3
import pandas as pd
import json
import os
import sys

# Ajustar path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def export_dataset():
    db_path = "sniper_brain.db"
    if not os.path.exists(db_path):
        print(f"❌ No se encontró {db_path}")
        return

    print("🚀 Iniciando exportación de Dataset Maestro...")
    conn = sqlite3.connect(db_path)

    # Extraemos datos ordenados por tiempo para mantener la secuencia (vivo + archivo)
    def _table_exists(table_name: str) -> bool:
        check_q = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1"
        row = conn.execute(check_q, (table_name,)).fetchone()
        return row is not None

    has_trades = _table_exists("trades")
    has_archive = _table_exists("trades_archive_v1")

    if not has_trades and not has_archive:
        print("⚠️ No existen tablas de trades para exportar.")
        conn.close()
        return

    if has_trades and has_archive:
        query = """
            SELECT timestamp, symbol, side, pnl_percent, market_snapshot, is_shadow
            FROM trades
            WHERE market_snapshot IS NOT NULL
            UNION ALL
            SELECT timestamp, symbol, side, pnl_percent, market_snapshot, is_shadow
            FROM trades_archive_v1
            WHERE market_snapshot IS NOT NULL
            ORDER BY timestamp ASC
        """
    elif has_trades:
        query = """
            SELECT timestamp, symbol, side, pnl_percent, market_snapshot, is_shadow
            FROM trades
            WHERE market_snapshot IS NOT NULL
            ORDER BY timestamp ASC
        """
    else:
        query = """
            SELECT timestamp, symbol, side, pnl_percent, market_snapshot, is_shadow
            FROM trades_archive_v1
            WHERE market_snapshot IS NOT NULL
            ORDER BY timestamp ASC
        """

    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("⚠️ No hay snapshots disponibles en tablas de trades/archivo.")
        return

    # --- LIMPIEZA DE OUTLIERS (Errores de API o Liquidaciones extremas) ---
    # Filtramos PnL > 500% (posible error de cálculo) o < -100% (imposible en spot/isolated sin deuda)
    initial_len = len(df)
    df = df[(df["pnl_percent"] > -100) & (df["pnl_percent"] < 500)]
    print(
        f"📊 Procesando {len(df)} registros (Filtrados {initial_len - len(df)} outliers)..."
    )

    # Aplanar el JSON de market_snapshot en columnas
    expected_agents = {"T", "V", "J", "G", "C", "L", "F", "S"}

    valid_mask = df["market_snapshot"].notna()
    valid_df = df[valid_mask].copy()

    snapshot_list = []
    for snap_str in valid_df["market_snapshot"]:
        try:
            snap = json.loads(snap_str)

            if "votos" in snap:
                for agent in expected_agents:
                    snap[f"vote_{agent}"] = snap["votos"].get(agent, 50.0)
                del snap["votos"]

            if "rsi" in snap and isinstance(snap["rsi"], dict):
                snap["rsi"] = snap["rsi"].get("val", 50)
            if "adx" in snap and isinstance(snap["adx"], dict):
                snap["adx"] = snap["adx"].get("val", 20)

            snapshot_list.append(snap)
        except (ValueError, TypeError, json.JSONDecodeError):
            continue

    for i, row in enumerate(valid_df[valid_mask.values].itertuples()):
        if i < len(snapshot_list):
            snapshot_list[i]["target_pnl"] = row.pnl_percent
            snapshot_list[i]["target_label"] = 1 if row.pnl_percent > 0 else 0
            snapshot_list[i]["symbol"] = row.symbol
            snapshot_list[i]["timestamp"] = row.timestamp
            snapshot_list[i]["side"] = 1 if row.side == "BUY" else -1
            snapshot_list[i]["is_shadow"] = 1 if row.is_shadow else 0

    df_export = pd.DataFrame(snapshot_list) if snapshot_list else pd.DataFrame()

    for agent in expected_agents:
        col = f"vote_{agent}"
        if col not in df_export.columns:
            df_export[col] = 50.0
        else:
            df_export[col] = df_export[col].fillna(50.0)

    # Limpieza básica
    # 1. Eliminar filas donde el precio (close) sea 0 o inválido, ya que son datos corruptos
    if "close" in df_export.columns:
        df_export["close"] = pd.to_numeric(df_export["close"], errors="coerce")
        initial_count = len(df_export)
        df_export = df_export[df_export["close"] > 0]
        print(
            f"🧹 Limpieza: Se eliminaron {initial_count - len(df_export)} registros con precio vacío/cero."
        )

    # 2. Rellenar btc_price inteligentemente (si falta, usar el anterior)
    if "btc_price" in df_export.columns:
        df_export["btc_price"] = pd.to_numeric(
            df_export["btc_price"], errors="coerce"
        ).replace(0, pd.NA)
        df_export["btc_price"] = df_export["btc_price"].ffill().bfill()

    # 3. Rellenar el resto de columnas numéricas con 0 y otras con cadena vacía
    numeric_cols = df_export.select_dtypes(include=["number"]).columns
    df_export[numeric_cols] = df_export[numeric_cols].fillna(0)
    other_cols = df_export.select_dtypes(exclude=["number"]).columns
    df_export[other_cols] = df_export[other_cols].fillna("")

    output_file = "data_storage/master_dataset_lstm.csv"
    os.makedirs("data_storage", exist_ok=True)
    df_export.to_csv(output_file, index=False)

    print(f"✅ EXPORTACIÓN COMPLETADA: {output_file}")
    print(f"   - Registros: {len(df_export)}")
    print(f"   - Features: {len(df_export.columns)}")
    print("   - Listo para TensorFlow/PyTorch.")


if __name__ == "__main__":
    export_dataset()
