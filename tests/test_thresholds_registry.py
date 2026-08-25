import json
import tempfile
import unittest
from pathlib import Path

from core.config.thresholds import export_thresholds, get_threshold, validate_thresholds
from tools.gate_history import append_gate_result


class ThresholdRegistryTests(unittest.TestCase):
    def test_validate_thresholds_returns_no_failures_for_registry(self):
        self.assertEqual(validate_thresholds(), [])

    def test_get_threshold_returns_spec_with_metadata(self):
        spec = get_threshold("STRATEGY_GATE_MIN_PROFIT_FACTOR")
        self.assertEqual(spec.name, "STRATEGY_GATE_MIN_PROFIT_FACTOR")
        self.assertGreater(spec.value, 0)
        self.assertTrue(spec.rationale)
        self.assertTrue(spec.owner)

    def test_export_thresholds_contains_named_entries(self):
        exported = export_thresholds()
        names = {row["name"] for row in exported}
        self.assertIn("SHADOW_GATE_MIN_RUNTIME_SAMPLES", names)
        self.assertIn("PROMOTION_GATE_MAX_HALT_ACTIONS", names)


class GateHistoryTests(unittest.TestCase):
    def test_append_gate_result_writes_jsonl_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "gate_history.jsonl"
            append_gate_result(
                path,
                gate="shadow_readiness",
                passed=False,
                failures=["too few fills"],
                metadata={"since_marker": "marker.json"},
            )

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["gate"], "shadow_readiness")
        self.assertFalse(rows[0]["passed"])
        self.assertEqual(rows[0]["failures"], ["too few fills"])


if __name__ == "__main__":
    unittest.main()
