import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from core.cooldown_state import (
    is_symbol_in_cooldown,
    load_cooldowns,
    set_symbol_cooldown,
)
from core.time_utils import utc_now


class _FakeBrain:
    def __init__(self):
        self.store = {}

    def get_metadata_json(self, key, default=None):
        return self.store.get(key, default)

    def set_metadata_json(self, key, value):
        self.store[key] = value


class CooldownStateTest(unittest.TestCase):
    def test_persists_and_restores_cooldown(self):
        brain = _FakeBrain()
        bot = SimpleNamespace(
            brain=brain,
            cooldown_pairs={},
            cooldown_deadlines_mono={},
        )

        set_symbol_cooldown(bot, "BTC/USDT", utc_now() + timedelta(minutes=5))

        fresh_bot = SimpleNamespace(
            brain=brain,
            cooldown_pairs={},
            cooldown_deadlines_mono={},
        )
        load_cooldowns(fresh_bot)

        in_cd, remaining = is_symbol_in_cooldown(fresh_bot, "BTC/USDT")
        self.assertTrue(in_cd)
        self.assertGreaterEqual(remaining, 1)

    def test_runtime_countdown_uses_monotonic_under_wall_clock_jump(self):
        brain = _FakeBrain()
        bot = SimpleNamespace(
            brain=brain,
            cooldown_pairs={"BTC/USDT": utc_now() + timedelta(minutes=5)},
            cooldown_deadlines_mono={"BTC/USDT": 160.0},
        )

        with (
            patch("core.cooldown_state.monotonic_now", return_value=120.0),
            patch("core.cooldown_state.utc_now") as mocked_utc,
        ):
            mocked_utc.return_value = utc_now() + timedelta(days=10)
            in_cd, remaining = is_symbol_in_cooldown(bot, "BTC/USDT")

        self.assertTrue(in_cd)
        self.assertGreaterEqual(remaining, 1)


if __name__ == "__main__":
    unittest.main()
