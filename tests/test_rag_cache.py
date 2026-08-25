import unittest
from types import SimpleNamespace

import numpy as np

from core import rag_cache


class RagCacheTest(unittest.TestCase):
    def test_build_rag_vector_preserves_legacy_weights(self):
        vector = rag_cache.build_rag_vector(
            {
                "rsi": 60,
                "adx": 30,
                "vol_rel": 1.5,
                "btc_delta_tf": 2.0,
                "dist_ema": 0.03,
                "z_score": -1.2,
                "bb_pos": 0.8,
                "ob_status": "BULLISH",
            },
            btc_delta_key="btc_delta_tf",
        )

        self.assertEqual(vector, [60, 30, 15.0, 10.0, 3.0, -1.2, 0.8, 1])

    def test_update_rag_cache_applies_overflow_limit(self):
        brain = SimpleNamespace(
            rag_cache_matrix=np.array([[1, 2, 3, 4, 5, 6, 7, 8]], dtype=float),
            rag_cache_meta=[{"symbol": "OLD/USDT", "pnl": -1.0}],
        )

        rag_cache.update_rag_cache(
            brain,
            {
                "symbol": "BTC/USDT",
                "pnl_percent": 2.5,
                "timestamp": "now",
                "market_snapshot": {"rsi": 55, "adx": 25, "ob_status": "BEARISH"},
            },
            max_trades=1,
        )

        self.assertEqual(len(brain.rag_cache_meta), 1)
        self.assertEqual(brain.rag_cache_meta[0]["symbol"], "BTC/USDT")
        self.assertEqual(brain.rag_cache_matrix.shape, (1, 8))

    def test_get_rag_inference_returns_weighted_scores(self):
        features = {"rsi": 50, "adx": 20, "vol_rel": 1.0, "btc_delta": 0.0}
        brain = SimpleNamespace(
            rag_cache_matrix=np.array([rag_cache.build_rag_vector(features)], dtype=float),
            rag_cache_meta=[{"symbol": "BTC/USDT", "pnl": 3.0}],
        )
        config = SimpleNamespace(RAG_ENABLED=True, RAG_SIMILARITY_THRESHOLD=0.1, RAG_MIN_MATCHES=1)

        scores, evidence = rag_cache.get_rag_inference(brain, "BTC/USDT", features, config)

        self.assertEqual(scores, {"T": 100.0, "V": 100.0, "C": 100.0, "L": 100.0, "S": 100.0})
        self.assertEqual(evidence, ["BTC/USDT (+3.0%)"])

    def test_get_rag_inference_respects_disabled_config(self):
        brain = SimpleNamespace(rag_cache_matrix=np.array([[1.0] * 8]), rag_cache_meta=[])
        config = SimpleNamespace(RAG_ENABLED=False)

        scores, evidence = rag_cache.get_rag_inference(brain, "BTC/USDT", {}, config)

        self.assertEqual(scores, rag_cache.DEFAULT_RAG_SCORES)
        self.assertEqual(evidence, ["RAG_DISABLED"])


if __name__ == "__main__":
    unittest.main()
