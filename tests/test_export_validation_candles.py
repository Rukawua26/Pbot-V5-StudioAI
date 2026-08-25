import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from tools.export_validation_candles import (
    _days_covering_event_range,
    _load_event_time_range,
)


class ExportValidationCandlesEventsTest(unittest.TestCase):
    def test_load_event_time_range_filters_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            rows = [
                {
                    "ts": "2026-05-10T00:00:00+00:00",
                    "event": "FILTER_APPLIED",
                    "payload": {"symbol": "ETH/USDT"},
                },
                {
                    "ts": "2026-05-11T01:00:00+00:00",
                    "event": "FILTER_APPLIED",
                    "payload": {"symbol": "BTC/USDT"},
                },
                {
                    "ts": "2026-05-11T03:00:00+00:00",
                    "event": "SIGNAL_ANALYZED",
                    "payload": {"symbol": "BTC/USDT"},
                },
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

            start, end = _load_event_time_range(path, "BTC/USDT")

        self.assertEqual(start.isoformat(), "2026-05-11T01:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-05-11T03:00:00+00:00")

    def test_days_covering_event_range_adds_padding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            row = {
                "ts": "2026-05-09T00:00:00+00:00",
                "event": "FILTER_APPLIED",
                "payload": {"symbol": "BTC/USDT"},
            }
            path.write_text(json.dumps(row), encoding="utf-8")

            days = _days_covering_event_range(
                path,
                "BTC/USDT",
                padding_days=2,
                now=datetime(2026, 5, 11, 1, 0, tzinfo=UTC),
            )

        self.assertEqual(days, 5)


if __name__ == "__main__":
    unittest.main()
