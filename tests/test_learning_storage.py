import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.learning import Brain


class LearningStorageTest(unittest.TestCase):
    def test_brain_sqlite_uses_normal_synchronous(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "brain.db"
            brain = Brain(str(db_path))
            conn = brain._get_conn()
            try:
                synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(int(synchronous), 1)

    def test_signal_alert_status_updates_after_trade_id_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            brain = Brain(str(Path(tmp) / "brain.db"))
            brain.log_signal_alert(
                symbol="BTC/USDT",
                alert_type="BUY",
                execution_mode="PAPER",
                entry_client_order_id="entry-1",
            )

            updated = brain.update_signal_alert_status("entry-1", "EXECUTED")
            conn = brain._get_conn()
            try:
                status = conn.execute(
                    "SELECT status FROM signal_alerts WHERE entry_client_order_id = ?",
                    ("entry-1",),
                ).fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(updated, 1)
        self.assertEqual(status, "EXECUTED")

    def test_fresh_db_trade_id_migration_is_quiet(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertNoLogs("tools.learning", level="WARNING"):
                Brain(str(Path(tmp) / "brain.db"))

    def test_unexpected_trade_id_migration_failure_is_logged(self):
        # An index on trade_id makes DROP COLUMN fail: it must not be swallowed.
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "brain.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE signal_alerts (id INTEGER PRIMARY KEY, ts TEXT, "
                "status TEXT, entry_client_order_id TEXT, trade_id INTEGER)"
            )
            conn.execute("CREATE INDEX idx_alert_trade ON signal_alerts(trade_id)")
            conn.commit()
            conn.close()

            with self.assertLogs("tools.learning", level="WARNING") as logs:
                Brain(str(db_path))

        self.assertTrue(any("trade_id" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
