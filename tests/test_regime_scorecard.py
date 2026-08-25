import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.regime_scorecard import compute_regime_scorecard


class RegimeScorecardTests(unittest.TestCase):
    def test_compute_regime_scorecard_groups_metrics_by_regime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                """
                CREATE TABLE trades (
                    market_regime TEXT,
                    pnl_percent REAL,
                    timestamp TEXT,
                    is_shadow INTEGER DEFAULT 1
                )
                """
            )
            conn.executemany(
                "INSERT INTO trades (market_regime, pnl_percent, timestamp, is_shadow) VALUES (?, ?, ?, ?)",
                [
                    ("BULL_TREND", 1.0, "2026-01-01T00:00:00+00:00", 1),
                    ("BULL_TREND", -0.5, "2026-01-02T00:00:00+00:00", 1),
                    ("RANGE", 0.2, "2026-01-03T00:00:00+00:00", 1),
                ],
            )
            conn.commit()

            rows = compute_regime_scorecard(conn, "is_shadow = 1")
            conn.close()

        by_regime = {row.regime: row for row in rows}
        self.assertEqual(by_regime["BULL_TREND"].trades, 2)
        self.assertEqual(by_regime["RANGE"].trades, 1)
        self.assertAlmostEqual(by_regime["BULL_TREND"].net_pnl_pct, 0.5)


if __name__ == "__main__":
    unittest.main()
