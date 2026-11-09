"""Opt-in wallet-sync HARD SL repair tests sending real TESTNET orders only.

Skipped by default. With dedicated Binance Futures TESTNET credentials exported
as BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET, run:

    RUN_BINANCE_TESTNET_E2E=true SNIPER_DISABLE_FILE_TELEMETRY=1 \
        ./.venv/bin/python -m unittest \
        tests.integration.test_binance_testnet_wallet_sync_sl_repair -v

BINANCE_TESTNET_SYMBOL defaults to BTC/USDT; BINANCE_TESTNET_ORDER_AMOUNT defaults
to 0.001. If half that amount rounds to zero or falls below the market minimum,
the entry uses twice the configured amount so its half can be a valid stop.
Use a dedicated, funded, one-way-mode testnet account with no other positions or
orders: wallet sync inspects the whole account, and cleanup cancels all orders
and flattens the selected symbol. Sandbox activation must succeed before any
network call. Runtime imports are deferred until after the opt-in/credential gate.
"""

import math
import os
import time
import unittest
from datetime import datetime
from threading import RLock
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _env_bool(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _position_contracts(exchange, symbol: str) -> float:
    positions = exchange.fetch_positions([symbol]) or []
    total = 0.0
    for position in positions:
        if str(position.get("symbol") or "").split(":")[0] != symbol.split(":")[0]:
            continue
        contracts = position.get("contracts")
        if contracts is None:
            contracts = (position.get("info") or {}).get("positionAmt", 0)
        total += float(contracts or 0.0)
    return total


def _cleanup_symbol(exchange, symbol: str) -> None:
    try:
        exchange.cancel_all_orders(symbol)
    except Exception:
        pass

    contracts = _position_contracts(exchange, symbol)
    if abs(contracts) <= 0.0:
        return

    side = "sell" if contracts > 0 else "buy"
    exchange.create_order(
        symbol,
        "market",
        side,
        abs(contracts),
        None,
        {"reduceOnly": True},
    )


def _reduce_only_stops(orders):
    stops = []
    for order in orders:
        info = order.get("info") or {}
        order_type = str(order.get("type") or info.get("type") or "").upper()
        reduce_only = info.get("reduceOnly", order.get("reduceOnly", False))
        if order_type == "STOP_MARKET" and str(reduce_only).lower() in {
            "true",
            "1",
            "yes",
        }:
            stops.append(order)
    return stops


@unittest.skipUnless(
    _env_bool("RUN_BINANCE_TESTNET_E2E"),
    "Set RUN_BINANCE_TESTNET_E2E=true to run live Binance Futures testnet E2E.",
)
class BinanceTestnetWalletSyncSlRepairTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        api_key = os.getenv("BINANCE_TESTNET_API_KEY")
        api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")
        if not api_key or not api_secret:
            raise unittest.SkipTest(
                "Binance testnet API credentials are required (set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET)"
            )

        cls.symbol = os.getenv("BINANCE_TESTNET_SYMBOL", "BTC/USDT")
        cls.amount = float(os.getenv("BINANCE_TESTNET_ORDER_AMOUNT", "0.001"))
        if not math.isfinite(cls.amount) or cls.amount <= 0:
            raise unittest.SkipTest(
                "BINANCE_TESTNET_ORDER_AMOUNT must be positive and finite"
            )

        from core.execution_service import ExecutionService

        cls.execution = ExecutionService(api_key, api_secret)
        cls.execution.exchange.options["disableFuturesSandboxWarning"] = True
        cls.execution.exchange.set_sandbox_mode(True)
        cls.execution.exchange.load_time_difference()
        cls.execution.exchange.load_markets()
        if cls.symbol not in cls.execution.exchange.markets:
            fallback = f"{cls.symbol}:USDT" if ":" not in cls.symbol else cls.symbol
            if fallback not in cls.execution.exchange.markets:
                raise unittest.SkipTest(f"Symbol unavailable on testnet: {cls.symbol}")
            cls.symbol = fallback

    def tearDown(self):
        _cleanup_symbol(self.execution.exchange, self.symbol)
        self.assertLessEqual(
            abs(_position_contracts(self.execution.exchange, self.symbol)),
            1e-12,
            "Teardown must leave the testnet position flat",
        )

    def _half_amount(self, contracts):
        from ccxt import InvalidOrder

        try:
            return float(
                self.execution.exchange.amount_to_precision(self.symbol, contracts / 2)
            )
        except InvalidOrder:
            # CCXT can reject a positive amount that truncates to zero.
            return 0.0

    def _open_with_insufficient_sl(self):
        from core.symbol_utils import normalize_position_symbol
        from core.trade_keys import make_trade_key

        exchange = self.execution.exchange
        _cleanup_symbol(exchange, self.symbol)
        self.assertLessEqual(
            abs(_position_contracts(exchange, self.symbol)),
            1e-12,
            "Initial cleanup must confirm a flat testnet position",
        )
        ticker = exchange.fetch_ticker(self.symbol) or {}
        last = float(ticker.get("last") or ticker.get("mark") or 0.0)
        self.assertGreater(last, 0.0, "Exchange must provide a positive entry price")

        minimum = float(
            (
                (exchange.market(self.symbol).get("limits") or {}).get("amount") or {}
            ).get("min")
            or 0.0
        )
        entry_amount = self.amount
        half = self._half_amount(entry_amount)
        if half <= 0 or half < minimum:
            # Double before entry, not by adding exposure after a partial fill.
            entry_amount = self.amount * 2
        half = self._half_amount(entry_amount)
        self.assertGreater(half, 0.0, "Configured entry must allow a nonzero half stop")
        self.assertGreaterEqual(half, minimum, "Half stop must meet the market minimum")

        ts = int(time.time())
        entry_client_id = f"sai-e2e-ws-entry-{ts}"
        entry = self.execution.create_precision_order(
            self.symbol,
            "BUY",
            entry_amount,
            last,
            slippage_pct=1.0,
            client_order_id=entry_client_id,
        )
        self.assertIsInstance(entry, dict, "Entry must return an exchange order ACK")
        self.assertGreater(
            float(entry.get("filled") or 0.0), 0.0, "Testnet BUY entry must fill"
        )
        contracts = _position_contracts(exchange, self.symbol)
        self.assertGreater(contracts, 0.0, "Exchange must report an open BUY position")
        half = self._half_amount(contracts)
        self.assertGreater(half, 0.0, "Filled contracts must allow a nonzero half stop")
        self.assertGreaterEqual(half, minimum, "Filled half must meet market minimum")
        self.assertLess(half, contracts, "Old stop must cover less than full exposure")

        sl_price = last * 0.95
        old_client_id = f"sai-e2e-ws-oldsl-{ts}"
        old_sl = self.execution.place_hard_sl(
            self.symbol, "BUY", half, sl_price, client_order_id=old_client_id
        )
        self.assertIsInstance(old_sl, dict, "Insufficient SL must return an ACK")
        self.assertTrue(old_sl.get("id"), "Insufficient SL must have an exchange ID")
        stops = _reduce_only_stops(exchange.fetch_open_orders(self.symbol) or [])
        self.assertEqual(len(stops), 1, "Exchange must expose exactly the old stop")
        self.assertEqual(
            str(stops[0].get("id")), str(old_sl["id"]), "Old SL must be open"
        )
        self.assertLess(
            float(stops[0].get("amount") or 0),
            contracts,
            "Exchange must confirm the old SL is insufficient",
        )

        symbol = normalize_position_symbol(self.symbol)
        trade_key = make_trade_key(symbol, "BUY")
        trade = {
            "trade_key": trade_key,
            "symbol": symbol,
            "side": "BUY",
            "entry": float(entry.get("average") or last),
            "amount": contracts,
            "sl": sl_price,
            "is_shadow": False,
            "open_time": datetime.now(),
            "entry_client_order_id": entry_client_id,
            "sl_exchange_order_id": old_sl["id"],
            "sl_client_order_id": old_client_id,
            "sl_repair_count": 0,
        }
        bot = SimpleNamespace(
            lock=RLock(),
            balance_lock=RLock(),
            db_lock=RLock(),
            log=MagicMock(),
            balance=100.0,
            get_current_balance=lambda: 100.0,
            brain=SimpleNamespace(
                save_active_trade_state=MagicMock(return_value=True),
                save_error_snapshot=MagicMock(),
                delete_active_trade_state=MagicMock(),
            ),
            execution=self.execution,
            is_hedge_mode=False,
            active_trades={trade_key: trade},
        )
        return bot, trade, old_sl, contracts

    def _sync_and_assert_repaired(self, bot, trade, old_sl, contracts):
        from core.bot_wallet_sync import sync_wallet

        with (
            patch("core.bot_wallet_sync.Config.PAPER_MODE", False),
            patch("core.bot_wallet_sync.send_telegram_msg"),
        ):
            sync_wallet(bot)

        orders = self.execution.exchange.fetch_open_orders(self.symbol) or []
        self.assertNotIn(
            str(old_sl["id"]),
            {str(order.get("id")) for order in orders},
            "Insufficient SL must no longer be open after repair",
        )
        stops = _reduce_only_stops(orders)
        self.assertEqual(
            len(stops), 1, "Repair must leave exactly one reduce-only stop"
        )
        replacement = stops[0]
        self.assertEqual(
            str(replacement.get("side")).upper(),
            "SELL",
            "BUY exposure needs a SELL stop",
        )
        self.assertGreaterEqual(
            float(replacement.get("amount") or 0),
            contracts,
            "Replacement STOP_MARKET must cover all exchange contracts",
        )
        self.assertEqual(
            str(trade.get("sl_exchange_order_id")),
            str(replacement.get("id")),
            "Local trade must reference the exchange replacement",
        )
        self.assertEqual(trade.get("status"), "OPEN", "Repaired trade must remain OPEN")
        self.assertFalse(
            getattr(bot, "halt_system_active", False), "Successful repair must not HALT"
        )
        self.assertAlmostEqual(
            _position_contracts(self.execution.exchange, self.symbol),
            contracts,
            delta=1e-12,
            msg="Repair must preserve the open exchange exposure",
        )
        return replacement

    def _close_and_assert_flat(self, contracts):
        closed = self.execution.close_position(self.symbol, "BUY", contracts)
        self.assertIsInstance(
            closed, dict, "Position close must return an exchange ACK"
        )
        self.assertLessEqual(
            abs(_position_contracts(self.execution.exchange, self.symbol)),
            1e-12,
            "Exchange must confirm flat exposure after closing",
        )
        _cleanup_symbol(self.execution.exchange, self.symbol)

    def test_wallet_sync_replaces_insufficient_hard_sl(self):
        bot, trade, old_sl, contracts = self._open_with_insufficient_sl()

        self._sync_and_assert_repaired(bot, trade, old_sl, contracts)

        self._close_and_assert_flat(contracts)

    def test_wallet_sync_adopts_pending_replacement_without_duplicate(self):
        from core.bot_wallet_sync import _repair_sl_client_order_id

        bot, trade, old_sl, contracts = self._open_with_insufficient_sl()
        pending_id = _repair_sl_client_order_id(
            trade["entry_client_order_id"], trade["sl_repair_count"] + 1
        )
        accepted = self.execution.place_hard_sl(
            self.symbol, "BUY", contracts, trade["sl"], client_order_id=pending_id
        )
        self.assertIsInstance(accepted, dict, "Pending replacement must return an ACK")
        self.assertTrue(accepted.get("id"), "Pending replacement needs an exchange ID")
        before = _reduce_only_stops(
            self.execution.exchange.fetch_open_orders(self.symbol) or []
        )
        self.assertEqual(len(before), 2, "Old and accepted replacement must coexist")
        self.assertEqual(
            {str(order.get("id")) for order in before},
            {str(old_sl["id"]), str(accepted["id"])},
            "Exchange must expose both known stop identities before adoption",
        )
        trade["sl_repair_pending_client_order_id"] = pending_id

        replacement = self._sync_and_assert_repaired(bot, trade, old_sl, contracts)

        self.assertEqual(
            str(replacement.get("id")),
            str(accepted["id"]),
            "Wallet sync must adopt the accepted stop, not create another one",
        )
        self.assertEqual(
            trade.get("sl_client_order_id"),
            pending_id,
            "Stable client ID must be adopted",
        )
        self.assertNotIn(
            "sl_repair_pending_client_order_id",
            trade,
            "Pending identity must be cleared",
        )
        self.assertEqual(
            trade.get("sl_repair_count"), 1, "Only one repair must complete"
        )
        self._close_and_assert_flat(contracts)


if __name__ == "__main__":
    unittest.main()
