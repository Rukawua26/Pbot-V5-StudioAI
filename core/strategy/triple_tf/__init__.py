from core.strategy.triple_tf.bias_1h import Bias1HResult, evaluate_bias_1h
from core.strategy.triple_tf.engine import TripleTFEngine
from core.strategy.triple_tf.structure_5m import (
    Structure5MResult,
    evaluate_structure_5m,
)
from core.strategy.triple_tf.trailing_1m import evaluate_trailing_1m
from core.strategy.triple_tf.trigger_1m import Trigger1MResult, evaluate_trigger_1m


def is_ttf_signal(ctx) -> bool:
    """Única fuente de verdad para detectar si un contexto de señal proviene de Triple Timeframe.

    La detección se basa exclusivamente en la presencia de 'ttf_metrics' en el contexto
    del análisis. NO usar Config.STRATEGY_ENGINE como criterio, ya que su valor por
    defecto ('triple_tf') haría que todos los tests heredados sean tratados como TTF.
    """
    return bool((ctx or {}).get("ttf_metrics"))


def is_ttf_trade(trade: dict | None) -> bool:
    """Única fuente de verdad para detectar si una posición abierta pertenece a TTF."""
    if not trade or not isinstance(trade, dict):
        return False
    return (
        bool(trade.get("ttf_metrics"))
        or str(trade.get("strategy_engine", "")).lower() == "triple_tf"
    )


__all__ = [
    "TripleTFEngine",
    "evaluate_bias_1h",
    "evaluate_structure_5m",
    "evaluate_trigger_1m",
    "evaluate_trailing_1m",
    "is_ttf_signal",
    "is_ttf_trade",
    "Bias1HResult",
    "Structure5MResult",
    "Trigger1MResult",
]
