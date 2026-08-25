import os
import unittest
from pathlib import Path
from unittest.mock import patch

import tools.learning as learning
from core import learning_paths
from core import shadow_logger as shadow_logger_module


class ShadowLoggerModuleTest(unittest.TestCase):
    def test_learning_reexports_shadow_logger_api(self):
        self.assertIs(learning.AsyncShadowLogger, shadow_logger_module.AsyncShadowLogger)
        self.assertIs(learning.LazyShadowLogger, shadow_logger_module.LazyShadowLogger)
        self.assertIs(learning.shadow_logger, shadow_logger_module.shadow_logger)

    def test_default_db_path_matches_legacy_learning_path(self):
        expected = str(Path(learning.__file__).resolve().parent / "sniper_brain.db")
        self.assertEqual(shadow_logger_module.DEFAULT_DB_PATH, expected)
        self.assertEqual(learning._DB_PATH, expected)

    def test_env_db_path_override_is_resolved(self):
        with patch.dict(os.environ, {"SNIPER_DB_PATH": "/tmp/sniper-test.db"}):
            self.assertEqual(learning_paths.resolve_default_db_path(), "/tmp/sniper-test.db")


if __name__ == "__main__":
    unittest.main()
