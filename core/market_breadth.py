from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class MarketBreadth:
    sentiment: str
    dump_ratio: float
    pump_ratio: float
    dump_count: int
    pump_count: int
    total_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "sentiment": self.sentiment,
            "dump_ratio": self.dump_ratio,
            "pump_ratio": self.pump_ratio,
            "dump_count": self.dump_count,
            "pump_count": self.pump_count,
            "total_count": self.total_count,
        }


def _last_float(df, candidates: tuple[str, ...], default: float | None = None):
    for column in candidates:
        try:
            if df is not None and column in df.columns and len(df) > 0:
                value = float(df[column].iloc[-1])
                if pd.notna(value):
                    return value
        except Exception:
            continue
    return default


def _resolve_ema_200(df):
    value = _last_float(df, ("ema_200", "EMA_200"), None)
    if value is not None:
        return value
    try:
        if df is not None and "close" in df.columns and len(df) >= 200:
            return float(df["close"].rolling(200).mean().iloc[-1])
    except Exception:
        return None
    return None


def calculate_market_breadth(
    results: dict,
    *,
    fear_threshold: float = 0.70,
    greed_threshold: float = 0.70,
) -> MarketBreadth:
    """Calcula sentimiento interno usando solo velas ya descargadas.

    Dump: RSI<30 o close<EMA200. Pump: RSI>70 o close>EMA200.
    Si no hay suficientes datos, la fila se ignora para no inventar señal.
    """
    dump_count = 0
    pump_count = 0
    total_count = 0

    for row in (results or {}).values():
        try:
            data = row.get("data") if isinstance(row, dict) else None
            if not data:
                continue
            df_main = data[0]
            if df_main is None or getattr(df_main, "empty", True):
                continue

            close = _last_float(df_main, ("close",), None)
            rsi = _last_float(df_main, ("rsi", "RSI_14", "rsi_raw"), None)
            ema_200 = _resolve_ema_200(df_main)
            if close is None or rsi is None or ema_200 is None or ema_200 <= 0:
                continue

            total_count += 1
            if rsi < 30.0 or close < ema_200:
                dump_count += 1
            elif rsi > 70.0 or close > ema_200:
                pump_count += 1
        except Exception:
            continue

    if total_count <= 0:
        return MarketBreadth("NEUTRAL", 0.0, 0.0, 0, 0, 0)

    dump_ratio = dump_count / total_count
    pump_ratio = pump_count / total_count
    sentiment = "NEUTRAL"
    if dump_ratio >= fear_threshold:
        sentiment = "FEAR"
    elif pump_ratio >= greed_threshold:
        sentiment = "GREED"

    return MarketBreadth(
        sentiment=sentiment,
        dump_ratio=dump_ratio,
        pump_ratio=pump_ratio,
        dump_count=dump_count,
        pump_count=pump_count,
        total_count=total_count,
    )
