import unittest
from datetime import UTC, datetime, timedelta
from threading import RLock
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.bot_wallet_sync import _manage_partial_fill_trade, sync_wallet


def _valid_hard_sl_ack(
    symbol: str, sl_side: str, amount: float, order_id: str = "sl-1"
) -> dict:
    """ACK estructuralmente válido para hard_sl_ack_looks_valid."""
    return {
        "id": order_id,
        "symbol": symbol,
        "type": "STOP_MARKET",
        "side": sl_side.lower(),
        "amount": amount,
        "status": "open",
        "info": {"reduceOnly": True},
    }


class WalletSyncSlRecoveryTest(unittest.TestCase):
    def _base_bot(self):
        bot = SimpleNamespace()
        bot.lock = RLock()
        bot.balance_lock = RLock()
        bot.db_lock = RLock()
        bot.log = MagicMock()
        bot.balance = 100.0
        bot.get_current_balance = lambda: 100.0
        bot.brain = SimpleNamespace(
            save_active_trade_state=MagicMock(return_value=True),
            save_error_snapshot=MagicMock(),
            delete_active_trade_state=MagicMock(),
        )
        return bot

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_attaches_hard_sl_when_missing_for_live_position(self):
        bot = self._base_bot()
        bot.active_trades = {
            "BTC/USDT": {
                "symbol": "BTC/USDT",
                "side": "BUY",
                "entry": 100.0,
                "amount": 1.0,
                "sl": 99.0,
                "is_shadow": False,
                "open_time": datetime.now(),
                "entry_client_order_id": "sai-v118-x",
                "sl_exchange_order_id": None,
            }
        }
        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "BTC/USDT:USDT",
                    "contracts": 1.0,
                    "side": "long",
                    "entryPrice": 100.0,
                    "unrealizedPnl": 0.0,
                    "info": {},
                }
            ],
            fetch_open_orders=lambda _symbol=None: [],
            place_hard_sl=MagicMock(
                return_value=_valid_hard_sl_ack("BTC/USDT", "sell", 1.0, "sl-123")
            ),
        )

        sync_wallet(bot)

        self.assertEqual(
            bot.active_trades["BTC/USDT"].get("sl_exchange_order_id"), "sl-123"
        )
        bot.execution.place_hard_sl.assert_called_once()

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_sync_wallet_preserves_dual_hedge_legs_for_same_symbol(self):
        bot = self._base_bot()
        bot.active_trades = {
            "BTC/USDT|BUY": {
                "trade_key": "BTC/USDT|BUY",
                "symbol": "BTC/USDT",
                "side": "BUY",
                "entry": 100.0,
                "amount": 1.0,
                "sl": 99.0,
                "is_shadow": False,
                "open_time": datetime.now(),
                "sl_exchange_order_id": "sl-buy",
            },
            "BTC/USDT|SELL": {
                "trade_key": "BTC/USDT|SELL",
                "symbol": "BTC/USDT",
                "side": "SELL",
                "entry": 101.0,
                "amount": 2.0,
                "sl": 102.0,
                "is_shadow": False,
                "open_time": datetime.now(),
                "sl_exchange_order_id": "sl-sell",
            },
        }
        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "BTC/USDT:USDT",
                    "contracts": 1.5,
                    "side": "long",
                    "entryPrice": 100.5,
                    "unrealizedPnl": 1.0,
                    "info": {},
                },
                {
                    "symbol": "BTC/USDT:USDT",
                    "contracts": 2.5,
                    "side": "short",
                    "entryPrice": 101.5,
                    "unrealizedPnl": -1.0,
                    "info": {},
                },
            ],
            fetch_open_orders=lambda _symbol=None: [
                {
                    "id": "sl-buy",
                    "symbol": "BTC/USDT",
                    "status": "open",
                    "type": "stop_market",
                    "side": "SELL",
                    "reduceOnly": True,
                    "amount": 1.5,
                },
                {
                    "id": "sl-sell",
                    "symbol": "BTC/USDT",
                    "status": "open",
                    "type": "stop_market",
                    "side": "BUY",
                    "reduceOnly": True,
                    "amount": 2.5,
                },
            ],
            place_hard_sl=MagicMock(),
        )

        sync_wallet(bot)

        self.assertEqual(set(bot.active_trades), {"BTC/USDT|BUY", "BTC/USDT|SELL"})
        self.assertEqual(bot.active_trades["BTC/USDT|BUY"]["entry"], 100.5)
        self.assertEqual(bot.active_trades["BTC/USDT|BUY"]["amount"], 1.5)
        self.assertEqual(bot.active_trades["BTC/USDT|SELL"]["entry"], 101.5)
        self.assertEqual(bot.active_trades["BTC/USDT|SELL"]["amount"], 2.5)
        bot.execution.place_hard_sl.assert_not_called()

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_reuses_existing_exchange_stop_without_duplicating(self):
        bot = self._base_bot()
        bot.active_trades = {
            "ETH/USDT": {
                "symbol": "ETH/USDT",
                "side": "BUY",
                "entry": 2000.0,
                "amount": 0.5,
                "sl": 1980.0,
                "is_shadow": False,
                "open_time": datetime.now(),
                "sl_exchange_order_id": None,
            }
        }
        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "ETH/USDT:USDT",
                    "contracts": 0.5,
                    "side": "long",
                    "entryPrice": 2000.0,
                    "unrealizedPnl": 0.0,
                    "info": {},
                }
            ],
            fetch_open_orders=lambda _symbol=None: [
                {
                    "id": "existing-sl",
                    "type": "STOP_MARKET",
                    "side": "sell",
                    "amount": 0.5,
                    "info": {"reduceOnly": True, "type": "STOP_MARKET"},
                }
            ],
            place_hard_sl=MagicMock(
                return_value=_valid_hard_sl_ack(
                    "ETH/USDT", "sell", 0.5, "should-not-create"
                )
            ),
        )

        sync_wallet(bot)

        self.assertEqual(
            bot.active_trades["ETH/USDT"].get("sl_exchange_order_id"), "existing-sl"
        )
        bot.execution.place_hard_sl.assert_not_called()

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_stale_local_sl_visibility_gap_halts_without_duplicating(self):
        bot = self._base_bot()
        bot.active_trades = {
            "ETH/USDT": {
                "symbol": "ETH/USDT",
                "side": "BUY",
                "entry": 2000.0,
                "amount": 0.5,
                "sl": 1980.0,
                "is_shadow": False,
                "open_time": datetime.now(),
                "sl_exchange_order_id": "stale-sl",
            }
        }
        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "ETH/USDT:USDT",
                    "contracts": 0.5,
                    "side": "long",
                    "entryPrice": 2000.0,
                    "unrealizedPnl": 0.0,
                    "info": {},
                }
            ],
            fetch_open_orders=lambda _symbol=None: [],
            place_hard_sl=MagicMock(
                return_value=_valid_hard_sl_ack("ETH/USDT", "sell", 0.5, "new-sl")
            ),
        )

        sync_wallet(bot)

        # With the repair path, a stale/insufficient SL is replaced instead of
        # halting forever (audit #5). The new SL is placed for the full amount.
        self.assertEqual(bot.active_trades["ETH/USDT"].get("status"), "OPEN")
        self.assertEqual(
            bot.active_trades["ETH/USDT"].get("sl_exchange_order_id"), "new-sl"
        )
        bot.execution.place_hard_sl.assert_called_once()

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_does_not_purge_local_real_trade_when_second_position_check_not_flat(self):
        bot = self._base_bot()
        bot.is_paused = False
        bot.integrity_lock_active = False
        bot.halt_system_active = False
        old_open = datetime(2020, 1, 1)
        bot.active_trades = {
            "BTC/USDT": {
                "symbol": "BTC/USDT",
                "side": "BUY",
                "entry": 100.0,
                "amount": 1.0,
                "sl": 99.0,
                "is_shadow": False,
                "open_time": old_open,
                "sl_exchange_order_id": "sl-live",
            }
        }
        fetch_positions = MagicMock(
            side_effect=[
                [
                    {
                        "symbol": "ETH/USDT:USDT",
                        "contracts": 0.1,
                        "side": "long",
                        "entryPrice": 2000.0,
                        "unrealizedPnl": 0.0,
                        "info": {},
                    }
                ],
                [
                    {
                        "symbol": "BTC/USDT:USDT",
                        "contracts": 1.0,
                        "side": "long",
                        "entryPrice": 100.0,
                        "unrealizedPnl": 0.0,
                        "info": {},
                    }
                ],
            ]
        )
        bot.execution = SimpleNamespace(
            fetch_positions=fetch_positions,
            fetch_open_orders=MagicMock(return_value=[]),
            place_hard_sl=MagicMock(),
        )

        sync_wallet(bot)

        self.assertIn("BTC/USDT", bot.active_trades)
        self.assertTrue(bot.halt_system_active)
        bot.brain.delete_active_trade_state.assert_not_called()

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_open_orders_lookup_failure_halts_without_duplicating_sl(self):
        bot = self._base_bot()
        bot.is_paused = False
        bot.integrity_lock_active = False
        bot.halt_system_active = False
        bot.active_trades = {
            "ETH/USDT": {
                "symbol": "ETH/USDT",
                "side": "BUY",
                "entry": 2000.0,
                "amount": 0.5,
                "sl": 1980.0,
                "is_shadow": False,
                "open_time": datetime.now(),
                "sl_exchange_order_id": None,
            }
        }
        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "ETH/USDT:USDT",
                    "contracts": 0.5,
                    "side": "long",
                    "entryPrice": 2000.0,
                    "unrealizedPnl": 0.0,
                    "info": {},
                }
            ],
            fetch_open_orders=MagicMock(side_effect=RuntimeError("orders unavailable")),
            place_hard_sl=MagicMock(
                return_value=_valid_hard_sl_ack("ETH/USDT", "sell", 0.5, "duplicate-sl")
            ),
        )

        sync_wallet(bot)

        self.assertTrue(bot.is_paused)
        self.assertTrue(bot.integrity_lock_active)
        self.assertTrue(bot.halt_system_active)
        bot.execution.place_hard_sl.assert_not_called()
        bot.brain.save_error_snapshot.assert_called()

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_ignores_partial_unrelated_stop_as_hard_sl_coverage(self):
        bot = self._base_bot()
        bot.active_trades = {
            "ETH/USDT": {
                "symbol": "ETH/USDT",
                "side": "BUY",
                "entry": 2000.0,
                "amount": 0.5,
                "sl": 1980.0,
                "is_shadow": False,
                "open_time": datetime.now(),
                "sl_exchange_order_id": None,
            }
        }
        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "ETH/USDT:USDT",
                    "contracts": 0.5,
                    "side": "long",
                    "entryPrice": 2000.0,
                    "unrealizedPnl": 0.0,
                    "info": {},
                }
            ],
            fetch_open_orders=lambda _symbol=None: [
                {
                    "id": "partial-stop",
                    "type": "STOP_MARKET",
                    "side": "sell",
                    "amount": 0.1,
                    "info": {"reduceOnly": True, "type": "STOP_MARKET"},
                }
            ],
            place_hard_sl=MagicMock(
                return_value=_valid_hard_sl_ack("ETH/USDT", "sell", 0.5, "full-sl")
            ),
        )

        sync_wallet(bot)

        self.assertEqual(
            bot.active_trades["ETH/USDT"].get("sl_exchange_order_id"), "full-sl"
        )
        bot.execution.place_hard_sl.assert_called_once()

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_emergency_market_close_when_sl_is_rejected_by_gap(self):
        bot = self._base_bot()
        positions = [
            [
                {
                    "symbol": "SOL/USDT:USDT",
                    "contracts": 1.0,
                    "side": "long",
                    "entryPrice": 120.0,
                    "unrealizedPnl": -10.0,
                    "info": {},
                }
            ],
            [],
        ]
        bot.active_trades = {
            "SOL/USDT": {
                "symbol": "SOL/USDT",
                "side": "BUY",
                "entry": 120.0,
                "amount": 1.0,
                "sl": 118.0,
                "is_shadow": False,
                "open_time": datetime.now(),
                "entry_client_order_id": "sai-v118-sol",
                "sl_exchange_order_id": None,
            }
        }
        bot.execution = SimpleNamespace(
            fetch_positions=MagicMock(side_effect=positions),
            fetch_open_orders=lambda _symbol=None: [],
            place_hard_sl=MagicMock(return_value=None),
            close_position=MagicMock(return_value={"id": "close-1"}),
            last_hard_sl_error="Order would trigger immediately. (-2021)",
        )

        sync_wallet(bot)

        bot.execution.close_position.assert_called_once()
        self.assertNotIn("SOL/USDT", bot.active_trades)
        bot.brain.delete_active_trade_state.assert_called_once_with("SOL/USDT")

    @patch("core.bot_wallet_sync.send_telegram_msg")
    @patch("core.bot_wallet_sync.Config.PARTIAL_FILL_TIMEOUT_SECONDS", 1)
    def test_partial_fill_cancel_failure_halts_for_manual_reconciliation(
        self, mocked_tg
    ):
        bot = self._base_bot()
        bot.is_paused = False
        bot.integrity_lock_active = False
        bot.halt_system_active = False
        bot.execution = SimpleNamespace(
            fetch_open_orders=MagicMock(
                return_value=[{"id": "entry-1", "clientOrderId": "cid-1"}]
            ),
            cancel_order=MagicMock(side_effect=RuntimeError("cancel down")),
        )
        trade = {
            "symbol": "BTC/USDT",
            "status": "PARTIAL_FILL_PENDING",
            "partial_fill_pending": True,
            "amount": 0.05,
            "requested_amount": 0.10,
            "entry": 100.0,
            "entry_exchange_order_id": "entry-1",
            "entry_client_order_id": "cid-1",
            "partial_fill_started_at": "2026-05-04T00:00:00",
        }

        _manage_partial_fill_trade(
            bot,
            "BTC/USDT",
            trade,
            {"amount": 0.05, "entry": 100.0},
        )

        self.assertEqual(trade["status"], "PARTIAL_FILL_CANCEL_FAILED")
        self.assertTrue(bot.is_paused)
        self.assertTrue(bot.integrity_lock_active)
        self.assertTrue(bot.halt_system_active)
        bot.brain.save_active_trade_state.assert_called()
        mocked_tg.assert_called_once()

    @patch("core.bot_wallet_sync.send_telegram_msg")
    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_emergency_close_keeps_trade_when_position_not_flat(self, mocked_tg):
        bot = self._base_bot()
        bot.integrity_lock_active = False
        bot.is_paused = False
        bot.active_trades = {
            "SOL/USDT": {
                "symbol": "SOL/USDT",
                "side": "BUY",
                "entry": 120.0,
                "amount": 1.0,
                "sl": 118.0,
                "is_shadow": False,
                "open_time": datetime.now(),
                "entry_client_order_id": "sai-v118-sol",
                "sl_exchange_order_id": None,
            }
        }
        open_position = [
            {
                "symbol": "SOL/USDT:USDT",
                "contracts": 1.0,
                "side": "long",
                "entryPrice": 120.0,
                "unrealizedPnl": -10.0,
                "info": {},
            }
        ]
        bot.execution = SimpleNamespace(
            fetch_positions=MagicMock(return_value=open_position),
            fetch_open_orders=lambda _symbol=None: [],
            place_hard_sl=MagicMock(return_value=None),
            close_position=MagicMock(return_value={"id": "close-1", "status": "open"}),
            last_hard_sl_error="Order would trigger immediately. (-2021)",
        )

        sync_wallet(bot)

        self.assertIn("SOL/USDT", bot.active_trades)
        self.assertEqual(
            bot.active_trades["SOL/USDT"].get("status"), "EMERGENCY_CLOSE_PENDING"
        )
        self.assertTrue(bot.is_paused)
        self.assertTrue(bot.integrity_lock_active)
        self.assertTrue(getattr(bot, "halt_system_active", False))
        bot.brain.delete_active_trade_state.assert_not_called()
        self.assertEqual(bot.execution.close_position.call_count, 3)
        mocked_tg.assert_called_once()

    @patch("core.bot_wallet_sync.send_telegram_msg")
    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_halts_system_when_emergency_close_fails_after_retries(self, mocked_tg):
        bot = self._base_bot()
        bot.integrity_lock_active = False
        bot.is_paused = False
        bot.active_trades = {
            "ADA/USDT": {
                "symbol": "ADA/USDT",
                "side": "BUY",
                "entry": 1.0,
                "amount": 100.0,
                "sl": 0.99,
                "is_shadow": False,
                "open_time": datetime.now(),
                "entry_client_order_id": "sai-v118-ada",
                "sl_exchange_order_id": None,
            }
        }
        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "ADA/USDT:USDT",
                    "contracts": 100.0,
                    "side": "long",
                    "entryPrice": 1.0,
                    "unrealizedPnl": -5.0,
                    "info": {},
                }
            ],
            fetch_open_orders=lambda _symbol=None: [],
            place_hard_sl=MagicMock(return_value=None),
            close_position=MagicMock(side_effect=RuntimeError("rate limit")),
            last_hard_sl_error="Order would trigger immediately. (-2021)",
        )

        sync_wallet(bot)

        self.assertTrue(bot.is_paused)
        self.assertTrue(bot.integrity_lock_active)
        self.assertTrue(getattr(bot, "halt_system_active", False))
        self.assertIn("ADA/USDT", bot.active_trades)
        self.assertEqual(bot.execution.close_position.call_count, 3)
        mocked_tg.assert_called_once()

    @patch("core.bot_wallet_sync.send_telegram_msg")
    @patch("core.bot_wallet_sync.Config.HARD_SL_ATTACH_MAX_RETRIES", 1)
    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_non_immediate_sl_failures_escalate_to_emergency_close(self, mocked_tg):
        bot = self._base_bot()
        bot.integrity_lock_active = False
        bot.is_paused = False
        bot.active_trades = {
            "XRP/USDT": {
                "symbol": "XRP/USDT",
                "side": "BUY",
                "entry": 0.5,
                "amount": 100.0,
                "sl": 0.49,
                "is_shadow": False,
                "open_time": datetime.now(),
                "entry_client_order_id": "sai-v118-xrp",
                "sl_exchange_order_id": None,
            }
        }
        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "XRP/USDT:USDT",
                    "contracts": 100.0,
                    "side": "long",
                    "entryPrice": 0.5,
                    "unrealizedPnl": -2.0,
                    "info": {},
                }
            ],
            fetch_open_orders=lambda _symbol=None: [],
            place_hard_sl=MagicMock(return_value=None),
            close_position=MagicMock(side_effect=RuntimeError("exchange unavailable")),
            last_hard_sl_error="minNotional validation failed",
        )

        sync_wallet(bot)

        self.assertTrue(bot.is_paused)
        self.assertTrue(bot.integrity_lock_active)
        self.assertTrue(getattr(bot, "halt_system_active", False))
        self.assertEqual(bot.execution.close_position.call_count, 3)
        mocked_tg.assert_called_once()

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    @patch("core.bot_wallet_sync.Config.PARTIAL_FILL_TIMEOUT_SECONDS", 60)
    def test_partial_fill_timeout_cancels_remaining_order(self):
        bot = self._base_bot()
        bot.active_trades = {
            "BNB/USDT": {
                "symbol": "BNB/USDT",
                "side": "BUY",
                "entry": 300.0,
                "amount": 4.0,
                "requested_amount": 10.0,
                "remaining_amount": 6.0,
                "status": "PARTIAL_FILL_PENDING",
                "partial_fill_pending": True,
                "partial_fill_started_at": datetime.fromtimestamp(
                    datetime.now().timestamp() - 120
                ).isoformat(),
                "is_shadow": False,
                "open_time": datetime.now(),
                "entry_exchange_order_id": "entry-ord-1",
                "sl_exchange_order_id": "sl-1",
            }
        }

        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "BNB/USDT:USDT",
                    "contracts": 4.0,
                    "side": "long",
                    "entryPrice": 301.0,
                    "unrealizedPnl": 0.0,
                    "info": {},
                }
            ],
            fetch_open_orders=lambda _symbol=None: [
                {
                    "id": "entry-ord-1",
                    "symbol": "BNB/USDT",
                    "status": "open",
                    "clientOrderId": "cid-entry",
                }
            ],
            cancel_order=MagicMock(
                return_value={"id": "entry-ord-1", "status": "canceled"}
            ),
            place_hard_sl=MagicMock(
                return_value=_valid_hard_sl_ack("BNB/USDT", "sell", 4.0, "sl-1")
            ),
        )

        sync_wallet(bot)

        trade = bot.active_trades["BNB/USDT"]
        self.assertEqual(trade.get("status"), "OPEN")
        self.assertFalse(trade.get("partial_fill_pending"))
        self.assertEqual(trade.get("remaining_amount"), 0.0)
        self.assertEqual(trade.get("unfilled_canceled_amount"), 6.0)
        bot.execution.cancel_order.assert_called_once_with("BNB/USDT", "entry-ord-1")

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_partial_fill_keeps_pending_when_entry_lookup_fails(self):
        bot = self._base_bot()
        bot.active_trades = {
            "BNB/USDT": {
                "symbol": "BNB/USDT",
                "side": "BUY",
                "entry": 300.0,
                "amount": 4.0,
                "requested_amount": 10.0,
                "remaining_amount": 6.0,
                "status": "PARTIAL_FILL_PENDING",
                "partial_fill_pending": True,
                "partial_fill_started_at": datetime.now().isoformat(),
                "is_shadow": False,
                "open_time": datetime.now(),
                "entry_exchange_order_id": "entry-ord-1",
                "sl_exchange_order_id": "sl-1",
            }
        }

        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "BNB/USDT:USDT",
                    "contracts": 4.0,
                    "side": "long",
                    "entryPrice": 301.0,
                    "unrealizedPnl": 0.0,
                    "info": {},
                }
            ],
            fetch_open_orders=MagicMock(side_effect=RuntimeError("exchange down")),
            cancel_order=MagicMock(),
            place_hard_sl=MagicMock(
                return_value=_valid_hard_sl_ack("BNB/USDT", "sell", 4.0, "sl-1")
            ),
        )

        sync_wallet(bot)

        trade = bot.active_trades["BNB/USDT"]
        self.assertEqual(trade.get("status"), "PARTIAL_FILL_PENDING")
        self.assertTrue(trade.get("partial_fill_pending"))
        self.assertEqual(trade.get("remaining_amount"), 6.0)
        bot.execution.cancel_order.assert_not_called()
        bot.brain.save_active_trade_state.assert_called()

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_empty_positions_snapshot_with_local_real_trade_halts_without_purge(self):
        bot = self._base_bot()
        bot.integrity_lock_active = False
        bot.is_paused = False
        bot.halt_system_active = False
        bot.active_trades = {
            "BTC/USDT": {
                "symbol": "BTC/USDT",
                "side": "BUY",
                "entry": 100.0,
                "amount": 1.0,
                "sl": 99.0,
                "is_shadow": False,
                "open_time": datetime.fromtimestamp(datetime.now().timestamp() - 300),
                "sl_exchange_order_id": "sl-1",
            }
        }
        bot.execution = SimpleNamespace(fetch_positions=MagicMock(return_value=[]))

        sync_wallet(bot)

        self.assertIn("BTC/USDT", bot.active_trades)
        self.assertTrue(bot.is_paused)
        self.assertTrue(bot.integrity_lock_active)
        self.assertTrue(bot.halt_system_active)
        bot.brain.delete_active_trade_state.assert_not_called()


class WalletSyncHardeningTest(unittest.TestCase):
    """Regressions from odd/tasks/wallet-sync-hardening.md (S1-S3)."""

    _base_bot = WalletSyncSlRecoveryTest._base_bot

    def _partial_fill_bot(self, started_at):
        bot = self._base_bot()
        bot.active_trades = {
            "BNB/USDT": {
                "symbol": "BNB/USDT",
                "side": "BUY",
                "entry": 300.0,
                "amount": 4.0,
                "requested_amount": 10.0,
                "remaining_amount": 6.0,
                "status": "PARTIAL_FILL_PENDING",
                "partial_fill_pending": True,
                "partial_fill_started_at": started_at,
                "is_shadow": False,
                "open_time": datetime.now(),
                "entry_exchange_order_id": "entry-ord-1",
                "sl_exchange_order_id": "sl-1",
            }
        }
        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "BNB/USDT:USDT",
                    "contracts": 4.0,
                    "side": "long",
                    "entryPrice": 300.0,
                    "unrealizedPnl": 0.0,
                    "info": {},
                }
            ],
            fetch_open_orders=lambda _symbol=None: [
                {"id": "entry-ord-1", "symbol": "BNB/USDT", "status": "open"},
                {
                    "id": "sl-1",
                    "symbol": "BNB/USDT",
                    "type": "STOP_MARKET",
                    "side": "sell",
                    "amount": 4.0,
                    "info": {"reduceOnly": True},
                },
            ],
            cancel_order=MagicMock(
                return_value={"id": "entry-ord-1", "status": "canceled"}
            ),
            place_hard_sl=MagicMock(return_value=None),
        )
        return bot

    # --- S1: timezone-aware partial fill timeout -------------------------
    @patch("core.bot_wallet_sync.Config.PARTIAL_FILL_TIMEOUT_SECONDS", 300)
    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_partial_fill_timeout_with_utc_aware_timestamp_cancels(self):
        started = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
        bot = self._partial_fill_bot(started)

        sync_wallet(bot)

        trade = bot.active_trades["BNB/USDT"]
        bot.execution.cancel_order.assert_called_once_with("BNB/USDT", "entry-ord-1")
        self.assertEqual(trade.get("status"), "OPEN")
        self.assertEqual(trade.get("unfilled_canceled_amount"), 6.0)
        self.assertFalse(getattr(bot, "halt_system_active", False))

    @patch("core.bot_wallet_sync.Config.PARTIAL_FILL_TIMEOUT_SECONDS", 300)
    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_partial_fill_with_recent_utc_aware_timestamp_stays_pending(self):
        started = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        bot = self._partial_fill_bot(started)

        sync_wallet(bot)

        trade = bot.active_trades["BNB/USDT"]
        bot.execution.cancel_order.assert_not_called()
        self.assertEqual(trade.get("status"), "PARTIAL_FILL_PENDING")
        self.assertFalse(getattr(bot, "halt_system_active", False))

    @patch("core.bot_wallet_sync.Config.PARTIAL_FILL_TIMEOUT_SECONDS", 300)
    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_partial_fill_with_recent_naive_local_timestamp_stays_pending(self):
        # Legacy rows were written with naive datetime.now() (local time).
        started = (datetime.now() - timedelta(seconds=30)).isoformat()
        bot = self._partial_fill_bot(started)

        sync_wallet(bot)

        bot.execution.cancel_order.assert_not_called()
        self.assertEqual(
            bot.active_trades["BNB/USDT"].get("status"), "PARTIAL_FILL_PENDING"
        )

    # --- S2: SL repair places the replacement before cancelling ----------
    def _insufficient_sl_bot(self, place_result):
        bot = self._base_bot()
        bot.active_trades = {
            "ETH/USDT": {
                "symbol": "ETH/USDT",
                "side": "BUY",
                "entry": 2000.0,
                "amount": 0.5,
                "sl": 1980.0,
                "is_shadow": False,
                "open_time": datetime.now(),
                "entry_client_order_id": "sai-v118-eth",
                "sl_exchange_order_id": "old-sl",
                "sl_client_order_id": "SL_old",
            }
        }
        calls = MagicMock()
        calls.place_hard_sl.return_value = place_result
        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "ETH/USDT:USDT",
                    "contracts": 0.5,
                    "side": "long",
                    "entryPrice": 2000.0,
                    "unrealizedPnl": 0.0,
                    "info": {},
                }
            ],
            # The recorded SL only covers 0.2 of a 0.5 position.
            fetch_open_orders=lambda _symbol=None: [
                {
                    "id": "old-sl",
                    "clientOrderId": "SL_old",
                    "symbol": "ETH/USDT",
                    "type": "STOP_MARKET",
                    "side": "sell",
                    "amount": 0.2,
                    "info": {"reduceOnly": True},
                }
            ],
            place_hard_sl=calls.place_hard_sl,
            cancel_order=calls.cancel_order,
            last_hard_sl_error="network timeout",
        )
        return bot, calls

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_sl_repair_places_new_sl_before_cancelling_stale_one(self):
        bot, calls = self._insufficient_sl_bot(
            _valid_hard_sl_ack("ETH/USDT", "sell", 0.5, "new-sl")
        )

        sync_wallet(bot)

        names = [c[0] for c in calls.mock_calls]
        self.assertEqual(names, ["place_hard_sl", "cancel_order"])
        calls.cancel_order.assert_called_once_with("ETH/USDT", "old-sl")
        new_coid = calls.place_hard_sl.call_args.kwargs["client_order_id"]
        self.assertTrue(new_coid)
        self.assertNotEqual(new_coid, "SL_old")
        trade = bot.active_trades["ETH/USDT"]
        self.assertEqual(trade.get("sl_exchange_order_id"), "new-sl")
        self.assertEqual(trade.get("status"), "OPEN")

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_sl_repair_failure_keeps_stale_sl_in_book(self):
        bot, calls = self._insufficient_sl_bot(None)

        sync_wallet(bot)

        calls.place_hard_sl.assert_called_once()
        calls.cancel_order.assert_not_called()
        trade = bot.active_trades["ETH/USDT"]
        self.assertEqual(trade.get("status"), "HARD_SL_UNPROTECTED")
        self.assertEqual(trade.get("sl_exchange_order_id"), "old-sl")
        self.assertTrue(getattr(bot, "halt_system_active", False))

    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_sl_repair_halts_when_stale_lookup_fails(self):
        # A failed open-orders lookup is not proof that the stale SL is gone.
        bot, calls = self._insufficient_sl_bot(
            _valid_hard_sl_ack("ETH/USDT", "sell", 0.5, "new-sl")
        )
        old_orders = bot.execution.fetch_open_orders("ETH/USDT")
        bot.execution.fetch_open_orders = MagicMock(
            side_effect=[old_orders, RuntimeError("temporary failure"), old_orders]
        )

        sync_wallet(bot)

        trade = bot.active_trades["ETH/USDT"]
        self.assertEqual(trade.get("sl_exchange_order_id"), "old-sl")
        self.assertEqual(trade.get("sl_client_order_id"), "SL_old")
        calls.place_hard_sl.assert_not_called()
        calls.cancel_order.assert_not_called()
        self.assertTrue(getattr(bot, "halt_system_active", False))

    def test_sl_repair_client_ids_stay_unique_across_many_repairs(self):
        from core.bot_wallet_sync import _repair_sl_client_order_id

        ids = {_repair_sl_client_order_id("sai-v118-eth", n) for n in range(1, 2001)}
        self.assertEqual(len(ids), 2000)
        self.assertTrue(all(len(i) <= 32 for i in ids))

    # --- S3: amount follows the exchange even with unchanged entry -------
    @patch("core.bot_wallet_sync.Config.PAPER_MODE", False)
    def test_amount_syncs_when_exchange_size_changes_with_same_entry(self):
        bot = self._base_bot()
        bot.active_trades = {
            "BTC/USDT": {
                "symbol": "BTC/USDT",
                "side": "BUY",
                "entry": 100.0,
                "amount": 1.0,
                "size_usd": 100.0,
                "sl": 99.0,
                "is_shadow": False,
                "open_time": datetime.now(),
                "sl_exchange_order_id": "sl-1",
            }
        }
        bot.execution = SimpleNamespace(
            fetch_positions=lambda: [
                {
                    "symbol": "BTC/USDT:USDT",
                    "contracts": 2.0,
                    "side": "long",
                    "entryPrice": 100.0,
                    "unrealizedPnl": 0.0,
                    "info": {},
                }
            ],
            fetch_open_orders=lambda _symbol=None: [
                {
                    "id": "sl-1",
                    "symbol": "BTC/USDT",
                    "type": "STOP_MARKET",
                    "side": "sell",
                    "amount": 2.0,
                    "info": {"reduceOnly": True},
                }
            ],
            place_hard_sl=MagicMock(return_value=None),
        )

        sync_wallet(bot)

        trade = bot.active_trades["BTC/USDT"]
        self.assertEqual(trade.get("amount"), 2.0)
        self.assertEqual(trade.get("size_usd"), 200.0)
        self.assertEqual(trade.get("entry"), 100.0)
        bot.execution.place_hard_sl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
