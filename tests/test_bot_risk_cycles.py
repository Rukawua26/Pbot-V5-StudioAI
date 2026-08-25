import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.bot_risk_cycles import run_btc_panic_cycle, run_crash_predictor_cycle


class _CloseSeries:
    def __init__(self, values):
        self._values = values
        self.iloc = self

    def __getitem__(self, index):
        return self._values[index]


class _BtcData:
    def __init__(self, closes):
        self._closes = closes

    def __len__(self):
        return len(self._closes)

    def __getitem__(self, key):
        if key != "close":
            raise KeyError(key)
        return _CloseSeries(self._closes)


class BotRiskCyclesTest(unittest.TestCase):
    @patch("core.bot_risk_cycles.Config.BTC_RISK_MAX_PRICE_AGE_SECONDS", 90.0)
    @patch("core.bot_risk_cycles.time.monotonic", return_value=1_000.0)
    def test_btc_panic_skips_stale_btc_price(self, _mono):
        bot = SimpleNamespace(
            force_btc_panic=False,
            btc_panic=False,
            market_btc_price_ts=100.0,
            log=MagicMock(),
            _get_cached_btc_data=MagicMock(return_value=_BtcData([100.0, 95.0])),
        )

        run_btc_panic_cycle(bot)

        self.assertFalse(bot.btc_panic)
        bot._get_cached_btc_data.assert_not_called()

    @patch("core.bot_risk_cycles.send_telegram_msg")
    @patch("core.bot_risk_cycles.time.monotonic", return_value=1_000.0)
    @patch("core.bot_risk_cycles.time.time", return_value=1_000.0)
    @patch("core.bot_risk_cycles.Config.BTC_PANIC_DROP_PERCENT", 1.5)
    def test_btc_panic_activates_on_drop_and_rate_limits_alert(self, _time, _mono, telegram):
        bot = SimpleNamespace(
            force_btc_panic=False,
            btc_panic=False,
            last_panic_alert=0.0,
            market_btc_price_ts=999.0,
            log=MagicMock(),
            _get_cached_btc_data=MagicMock(return_value=_BtcData([100.0, 98.0])),
        )

        run_btc_panic_cycle(bot)

        self.assertTrue(bot.btc_panic)
        self.assertAlmostEqual(bot.market_btc_change_tf, -2.0)
        telegram.assert_called_once()

    @patch("core.bot_risk_cycles.send_telegram_msg")
    @patch("core.bot_risk_cycles.time.monotonic", return_value=1_100.0)
    @patch("core.bot_risk_cycles.time.time", return_value=1_100.0)
    @patch("core.bot_risk_cycles.Config.BTC_PANIC_DROP_PERCENT", 1.5)
    def test_btc_panic_keeps_forced_state_without_duplicate_alert(self, _time, _mono, telegram):
        bot = SimpleNamespace(
            force_btc_panic=True,
            btc_panic=False,
            last_panic_alert=1_000.0,
            market_btc_price_ts=1_099.0,
            log=MagicMock(),
            _get_cached_btc_data=MagicMock(return_value=_BtcData([100.0, 99.8])),
        )

        run_btc_panic_cycle(bot)

        self.assertTrue(bot.btc_panic)
        telegram.assert_not_called()

    @patch("core.bot_risk_cycles.time.sleep", return_value=None)
    @patch("core.bot_risk_cycles.time.monotonic", return_value=1_000.0)
    @patch("core.bot_risk_cycles.send_telegram_msg")
    @patch("core.bot_risk_cycles.Config.CRASH_DETECTION_ENABLED", True)
    def test_crash_predictor_close_all_sets_circuit_breaker(self, telegram, _mono, _sleep):
        predictor = MagicMock()
        predictor.analyze_crash_risk.return_value = {
            "recommended_action": "CLOSE_ALL",
            "crash_probability": 88,
        }
        bot = SimpleNamespace(
            market_btc_price=65_000.0,
            market_btc_price_ts=999.0,
            market_btc_change_tf=-2.5,
            crash_predictor=predictor,
            circuit_breaker_active=False,
            _close_all_positions_emergency=MagicMock(return_value=2),
            log=MagicMock(),
        )

        triggered = run_crash_predictor_cycle(bot)

        self.assertTrue(triggered)
        self.assertTrue(bot.circuit_breaker_active)
        bot._close_all_positions_emergency.assert_called_once()
        telegram.assert_called_once()

    @patch("core.bot_risk_cycles.Config.CRASH_DETECTION_ENABLED", True)
    @patch("core.bot_risk_cycles.time.monotonic", return_value=1_000.0)
    def test_crash_predictor_reduce_exposure_does_not_close_positions(self, _mono):
        predictor = MagicMock()
        predictor.analyze_crash_risk.return_value = {
            "recommended_action": "REDUCE_EXPOSURE",
            "crash_probability": 60,
        }
        bot = SimpleNamespace(
            market_btc_price=65_000.0,
            market_btc_price_ts=999.0,
            market_btc_change_tf=-1.0,
            crash_predictor=predictor,
            _close_all_positions_emergency=MagicMock(),
            log=MagicMock(),
        )

        triggered = run_crash_predictor_cycle(bot)

        self.assertFalse(triggered)
        bot._close_all_positions_emergency.assert_not_called()

    @patch("core.bot_risk_cycles.Config.CRASH_DETECTION_ENABLED", True)
    @patch("core.bot_risk_cycles.Config.BTC_RISK_MAX_PRICE_AGE_SECONDS", 90.0)
    @patch("core.bot_risk_cycles.time.monotonic", return_value=1_000.0)
    def test_crash_predictor_skips_stale_btc_price(self, _mono):
        predictor = MagicMock()
        bot = SimpleNamespace(
            market_btc_price=65_000.0,
            market_btc_price_ts=100.0,
            crash_predictor=predictor,
            log=MagicMock(),
        )

        self.assertFalse(run_crash_predictor_cycle(bot))
        predictor.analyze_crash_risk.assert_not_called()


if __name__ == "__main__":
    unittest.main()
