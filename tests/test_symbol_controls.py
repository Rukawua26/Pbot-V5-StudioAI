import sqlite3
import unittest

from tools import generate_symbol_controls


class SymbolControlsDecisionMatrixTest(unittest.TestCase):
    def _conn_with_trades(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE trades (
                symbol TEXT,
                side TEXT,
                pnl REAL,
                pnl_percent REAL
            )
            """
        )
        return conn

    def test_rows_exclude_veto_error_sentinels_from_decision_matrix(self):
        conn = self._conn_with_trades()
        try:
            for _idx in range(8):
                conn.execute(
                    "INSERT INTO trades VALUES (?, ?, ?, ?)",
                    ("ZEC/USDT", "VETO_ERROR", None, -99.0),
                )

            rows = generate_symbol_controls._rows(conn)

            self.assertEqual(rows, [])
        finally:
            conn.close()

    def test_rows_observe_until_minimum_valid_trade_sample(self):
        conn = self._conn_with_trades()
        try:
            for _idx in range(generate_symbol_controls.MIN_DECISION_TRADES - 1):
                conn.execute(
                    "INSERT INTO trades VALUES (?, ?, ?, ?)",
                    ("DASH/USDT", "BUY", -0.01, -0.2),
                )

            rows = generate_symbol_controls._rows(conn)

            self.assertEqual(rows[0]["decision"], "OBSERVAR")
            self.assertIn("Muestra insuficiente", rows[0]["rule_reason"])
        finally:
            conn.close()

    def test_rows_block_after_minimum_valid_weak_sample(self):
        conn = self._conn_with_trades()
        try:
            for _idx in range(generate_symbol_controls.MIN_DECISION_TRADES):
                conn.execute(
                    "INSERT INTO trades VALUES (?, ?, ?, ?)",
                    ("PIEVERSE/USDT", "BUY", -0.01, -0.2),
                )

            rows = generate_symbol_controls._rows(conn)

            self.assertEqual(rows[0]["decision"], "BLOQUEAR")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
