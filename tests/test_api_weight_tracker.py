import unittest
from unittest.mock import patch

from core.api_weight_tracker import BinanceWeightTracker


class BinanceWeightTrackerTest(unittest.TestCase):
    def test_track_uses_endpoint_default_weight(self):
        tracker = BinanceWeightTracker()

        with patch("core.api_weight_tracker.time.time", return_value=1000.0):
            tracker.track("fetch_balance", category="account")
            self.assertEqual(tracker.get_current_weight(), 5)
            self.assertEqual(tracker.get_status()["categories"], {"account": 5})

    def test_old_entries_expire_from_sliding_window(self):
        tracker = BinanceWeightTracker()

        with patch("core.api_weight_tracker.time.time", return_value=1000.0):
            tracker.track("fetch_balance", category="account")
        with patch("core.api_weight_tracker.time.time", return_value=1061.0):
            self.assertEqual(tracker.get_current_weight(), 0)

    def test_warning_threshold_emits_alert(self):
        tracker = BinanceWeightTracker()
        alerts = []
        tracker.set_alert_callback(lambda level, message: alerts.append((level, message)))

        with patch("core.api_weight_tracker.time.time", return_value=1000.0):
            tracker.track("custom_heavy", weight=1440, category="market")

        self.assertEqual(alerts[0][0], "WARNING")
        self.assertIn("API Weight WARNING", alerts[0][1])

    def test_emergency_mode_blocks_non_essential_not_trading(self):
        tracker = BinanceWeightTracker()

        with patch("core.api_weight_tracker.time.time", return_value=1000.0):
            tracker.track("custom_heavy", weight=2280, category="market")
            self.assertTrue(tracker.should_block("market"))
            self.assertFalse(tracker.should_block("trading"))
            self.assertFalse(tracker.should_block("essential"))

    def test_reset_stats_keeps_current_window(self):
        tracker = BinanceWeightTracker()

        with patch("core.api_weight_tracker.time.time", return_value=1000.0):
            tracker.track("fetch_balance", category="account")
            tracker.reset_stats()
            status = tracker.get_status()
            self.assertEqual(status["total_requests"], 0)
            self.assertEqual(status["total_weight"], 0)
            self.assertEqual(status["current_weight"], 5)


if __name__ == "__main__":
    unittest.main()
