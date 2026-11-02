"""Non-finite env values must never reach risk limits (odd/tasks/runtime-containment.md, S3)."""

import os
import unittest
from unittest.mock import patch

from core.config import env_helpers
from core.config.env_helpers import env_float, env_int, get_env_warnings


class EnvFiniteTests(unittest.TestCase):
    def setUp(self):
        self._warnings = list(env_helpers._CONFIG_ENV_WARNINGS)
        env_helpers._CONFIG_ENV_WARNINGS.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        env_helpers._CONFIG_ENV_WARNINGS.clear()
        env_helpers._CONFIG_ENV_WARNINGS.extend(self._warnings)

    def test_env_float_rejects_non_finite_values(self):
        for raw in ("nan", "NaN", "inf", "-inf", "Infinity", " inf "):
            with self.subTest(raw=raw), patch.dict(os.environ, {"MAX_RISK_USD": raw}):
                self.assertEqual(env_float("MAX_RISK_USD", 2.0), 2.0)
                self.assertIn(
                    "MAX_RISK_USD inválido; usando default 2.0", get_env_warnings()
                )

    def test_env_int_rejects_non_finite_values_without_raising(self):
        # int(float("inf")) raised OverflowError and crashed config loading.
        for raw in ("nan", "inf", "-inf"):
            with (
                self.subTest(raw=raw),
                patch.dict(os.environ, {"MAX_OPEN_TRADES": raw}),
            ):
                self.assertEqual(env_int("MAX_OPEN_TRADES", 3), 3)
                self.assertIn(
                    "MAX_OPEN_TRADES inválido; usando default 3", get_env_warnings()
                )

    def test_finite_values_unchanged(self):
        with patch.dict(os.environ, {"X_FLOAT": "1.5", "X_INT": "4", "X_INT_F": "4.9"}):
            self.assertEqual(env_float("X_FLOAT", 0.0), 1.5)
            self.assertEqual(env_int("X_INT", 0), 4)
            self.assertEqual(env_int("X_INT_F", 0), 4)
        self.assertEqual(get_env_warnings(), [])

    def test_empty_and_garbage_keep_previous_behaviour(self):
        with patch.dict(os.environ, {"X_FLOAT": "", "X_BAD": "abc"}):
            self.assertEqual(env_float("X_FLOAT", 7.0), 7.0)
            self.assertEqual(get_env_warnings(), [])
            self.assertEqual(env_float("X_BAD", 7.0), 7.0)
            self.assertEqual(get_env_warnings(), ["X_BAD inválido; usando default 7.0"])


if __name__ == "__main__":
    unittest.main()
