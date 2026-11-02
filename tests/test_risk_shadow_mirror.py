"""SHADOW as a mirror of REAL for small accounts (odd/tasks/mean-reversion-v3.md, S2).

Pins three rules in ``RiskEngine.calculate_position_size_by_stop``:
1. The exchange per-symbol minimum notional wins over the global MIN_NOTIONAL_VALUE.
2. When an order is bumped to the minimum, quantity rounds UP to the step so the
   rounded order still meets the minimum (truncation made REAL reject it).
3. With SHADOW_MIRROR_REAL_LIMITS=true, SHADOW applies the same limits, minimums and
   precision as REAL; with it false, SHADOW keeps its previous permissive behaviour.
"""

import math
import unittest
from decimal import ROUND_DOWN, Decimal
from unittest.mock import MagicMock, patch


class FakeExchange:
    """Minimal ccxt-like surface: markets limits + truncating amount_to_precision."""

    def __init__(self, markets):
        self.markets = markets

    def load_markets(self):
        return self.markets

    def amount_to_precision(self, symbol, amount):
        step = Decimal(str(self.markets[symbol]["precision"]["amount"]))
        value = (Decimal(str(amount)) / step).to_integral_value(
            rounding=ROUND_DOWN
        ) * step
        if value <= 0:
            raise ValueError("amount below precision")
        return format(value.normalize(), "f")


def market(min_cost, step):
    return {"limits": {"cost": {"min": min_cost}}, "precision": {"amount": step}}


MARKETS = {
    "SOL/USDT:USDT": market(5.0, 0.01),
    "ETH/USDT:USDT": market(20.0, 0.001),
    "BTC/USDT:USDT": market(50.0, 0.001),
}


class ShadowMirrorSizingTests(unittest.TestCase):
    def setUp(self):
        with (
            patch("core.risk_engine.CrashPredictor"),
            patch("core.risk_engine.HyperoptConfigLoader") as hyper,
        ):
            hyper.is_enabled.return_value = False
            from core.risk_engine import RiskEngine

            self.engine = RiskEngine(brain=MagicMock())
        self.exchange = FakeExchange(MARKETS)
        self.config = patch("core.risk_engine.Config")
        cfg = self.config.start()
        cfg.RISK_PER_TRADE_PCT = 0.012
        cfg.MAX_RISK_USD = 2.0
        cfg.MAX_MARGIN_PERCENT = 5.0
        cfg.MIN_NOTIONAL_VALUE = 5.0
        cfg.SHADOW_MIRROR_REAL_LIMITS = False
        self.cfg = cfg
        self.addCleanup(self.config.stop)

    def size(self, symbol, balance, entry, stop, shadow=False):
        return self.engine.calculate_position_size_by_stop(
            balance, symbol, entry, stop, 10, is_shadow=shadow, exchange=self.exchange
        )

    # Rule 2 -----------------------------------------------------------------
    def test_bump_to_minimum_rounds_up_and_meets_minimum(self):
        # $20 account, SOL @ 101.37, 1% stop: risk budget $0.24 -> raw notional $24
        # capped to $10 max notional; fine. Use a wide stop so raw notional < $5:
        # risk $0.24 / dist 6.0 = 0.04 SOL = $4.05 -> bump to $5 -> 0.0493 -> must be 0.05.
        amount, notional = self.size("SOL/USDT:USDT", 20.0, 101.37, 95.37)
        self.assertAlmostEqual(amount, 0.05)
        self.assertGreaterEqual(notional, 5.0)
        self.assertAlmostEqual(notional, 0.05 * 101.37)

    def test_round_up_never_exceeds_max_risk_or_margin(self):
        # Rounding up would push risk above MAX_RISK_USD -> reject (-4), never silently.
        # bump: 5/101.37 = 0.04932 SOL, risk 0.2466 <= cap; rounded UP to 0.05 -> risk 0.25 > cap.
        self.cfg.MAX_RISK_USD = 0.248
        amount, code = self.size("SOL/USDT:USDT", 20.0, 101.37, 96.37)
        self.assertEqual((amount, code), (0.0, -4))

    # Rule 1 -----------------------------------------------------------------
    def test_exchange_minimum_wins_over_global_minimum(self):
        # $20 account: max notional $10 < ETH minimum $20 -> reject as margin (-6).
        amount, code = self.size("ETH/USDT:USDT", 20.0, 3000.0, 2970.0)
        self.assertEqual((amount, code), (0.0, -6))

    def test_exchange_minimum_allows_when_capital_suffices(self):
        # $100 account: max notional $50 >= ETH $20; small raw size bumped to >= $20.
        # risk budget $1.2 / dist 60 = 0.02 ETH = $60 -> capped to $50 max notional; use 5% stop:
        # 1.2 / 150 = 0.008 = $24 >= $20, so no bump. Use 9% stop: 1.2/270=0.00444=$13.3 -> bump.
        amount, notional = self.size("ETH/USDT:USDT", 100.0, 3000.0, 2730.0)
        self.assertGreaterEqual(notional, 20.0)
        self.assertEqual(Decimal(str(amount)) % Decimal("0.001"), 0)

    def test_order_below_exchange_minimum_is_rejected_before_sending(self):
        # $50 account, ETH @ 3000, 2.9% stop: 0.6 / 87 = 0.0069 ETH = $20.69 (>= $20, no bump)
        # truncated to 0.006 = $18 < exchange min $20. Old code approved it (global floor $5)
        # and Binance would reject the order; now it is rejected before sending.
        amount, code = self.size("ETH/USDT:USDT", 50.0, 3000.0, 3000.0 * (1 - 0.029))
        self.assertEqual((amount, code), (0.0, -1))

    def test_global_minimum_used_when_market_has_no_limit(self):
        self.exchange.markets["XYZ/USDT:USDT"] = {
            "limits": {"cost": {"min": None}},
            "precision": {"amount": 0.1},
        }
        amount, notional = self.size("XYZ/USDT:USDT", 20.0, 1.0, 0.8)
        self.assertGreaterEqual(notional, 5.0)

    def test_substep_minimum_bump_rounds_up_with_real_ccxt(self):
        # Independent verifier repro: min $50 / 70000 = 0.000714 BTC < one step (0.001).
        # ccxt amount_to_precision raises below one step; the bump must still yield 0.001.
        import ccxt

        ex = ccxt.binance()
        symbol = "BTC/USDT:USDT"
        ex.markets = {
            symbol: {
                "symbol": symbol,
                "precision": {"amount": 0.001},
                "limits": {"cost": {"min": 50}},
            }
        }
        self.cfg.RISK_PER_TRADE_PCT = 0.001
        self.cfg.SHADOW_MIRROR_REAL_LIMITS = True
        for shadow in (False, True):
            with self.subTest(shadow=shadow):
                result = self.engine.calculate_position_size_by_stop(
                    200, symbol, 70000, 69000, 10, is_shadow=shadow, exchange=ex
                )
                self.assertEqual(result, (0.001, 70.0))

    def test_substep_amount_without_bump_is_rejected_not_errored(self):
        # Not bumped (raw >= minimum) but below one step can't happen; a raw amount
        # below one step with no minimum bump must fail closed with -2, never raise.
        self.exchange.markets["TINY/USDT:USDT"] = market(None, 1.0)
        self.cfg.MIN_NOTIONAL_VALUE = 0.0
        self.assertEqual(self.size("TINY/USDT:USDT", 20.0, 100.0, 99.0), (0.0, -2))

    # Rule 3 -----------------------------------------------------------------
    def test_shadow_mirror_applies_real_limits(self):
        self.cfg.SHADOW_MIRROR_REAL_LIMITS = True
        real = self.size("ETH/USDT:USDT", 20.0, 3000.0, 2970.0)
        shadow = self.size("ETH/USDT:USDT", 20.0, 3000.0, 2970.0, shadow=True)
        self.assertEqual(shadow, real)
        self.assertEqual(shadow, (0.0, -6))
        real_sol = self.size("SOL/USDT:USDT", 20.0, 101.37, 95.37)
        shadow_sol = self.size("SOL/USDT:USDT", 20.0, 101.37, 95.37, shadow=True)
        self.assertEqual(shadow_sol, real_sol)

    def test_shadow_mirror_rejects_like_real_on_max_risk(self):
        self.cfg.SHADOW_MIRROR_REAL_LIMITS = True
        self.cfg.MAX_RISK_USD = 0.248
        self.assertEqual(
            self.size("SOL/USDT:USDT", 20.0, 101.37, 96.37, shadow=True), (0.0, -4)
        )

    def test_shadow_without_mirror_keeps_previous_behaviour(self):
        # Previous SHADOW: no margin veto, no precision, no exchange minimum.
        amount, notional = self.size("ETH/USDT:USDT", 20.0, 3000.0, 2970.0, shadow=True)
        self.assertGreater(amount, 0.0)
        self.assertTrue(math.isfinite(notional))
        self.assertNotEqual(Decimal(str(amount)) % Decimal("0.001"), 0)


class ShadowMirrorConfigTests(unittest.TestCase):
    def test_mirror_flag_defaults_off(self):
        from core.config.manager import Config

        self.assertFalse(Config.SHADOW_MIRROR_REAL_LIMITS)


if __name__ == "__main__":
    unittest.main()
