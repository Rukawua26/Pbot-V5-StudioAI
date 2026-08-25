import unittest

from tools.fidelity_batch import summarize_batch, top_symbols_from_events


class FidelityBatchTest(unittest.TestCase):
    def test_top_symbols_from_events_counts_runtime_decisions(self):
        events = [
            {"event": "FILTER_APPLIED", "payload": {"symbol": "BTC/USDT"}},
            {"event": "SIGNAL_ANALYZED", "payload": {"symbol": "ETH/USDT"}},
            {"event": "FILTER_APPLIED", "payload": {"symbol": "BTC/USDT"}},
            {"event": "MTF_FILTER", "payload": {"symbol": "SOL/USDT"}},
        ]

        symbols = top_symbols_from_events(events, limit=2)

        self.assertEqual(symbols, ["BTC/USDT", "ETH/USDT"])

    def test_summarize_batch_weights_fidelity_by_samples(self):
        reports = [
            {
                "params": {"fidelity": {"symbol": "BTC/USDT"}},
                "summary": {
                    "samples": 2,
                    "fidelity_score": 0.5,
                    "false_positive_count": 1,
                    "false_negative_count": 0,
                    "runtime_veto_reasons": {"SHOCK DEMASIADO CERCA": 1},
                    "proxy_modeled_veto_reason_components": {"SHOCK DEMASIADO CERCA": 1},
                    "exogenous_veto_reasons_not_modelled": {},
                },
            },
            {
                "params": {"fidelity": {"symbol": "ETH/USDT"}},
                "summary": {
                    "samples": 6,
                    "fidelity_score": 1.0,
                    "false_positive_count": 0,
                    "false_negative_count": 1,
                    "runtime_veto_reasons": {"MTF_VETO": 2},
                    "proxy_modeled_veto_reason_components": {"MTF_VETO": 2},
                    "exogenous_veto_reasons_not_modeled": {},
                },
            },
        ]

        summary = summarize_batch(reports)

        self.assertEqual(summary["symbols"], 2)
        self.assertEqual(summary["total_samples"], 8)
        self.assertAlmostEqual(summary["weighted_fidelity_score"], 0.875)
        self.assertEqual(summary["false_positive_count"], 1)
        self.assertEqual(summary["false_negative_count"], 1)


if __name__ == "__main__":
    unittest.main()
