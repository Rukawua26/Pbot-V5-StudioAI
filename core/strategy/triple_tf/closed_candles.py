"""Velas cerradas para la frontera de entrada Triple Timeframe."""

from __future__ import annotations

import numbers
from datetime import datetime

import pandas as pd

from core.time_utils import parse_datetime_utc, utc_now

_TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
}

# >= 1e14 solo cabe en microsegundos (ms ese valor serían el año 5138).
_US_THRESHOLD = 100_000_000_000_000


def _int_to_ms(value: int) -> int:
    if abs(value) >= _US_THRESHOLD:
        return value // 1000
    return value


def _to_ms(value) -> int | None:
    """Convierte una apertura de vela a ms UTC; None si no es parseable."""
    if value is None or value is pd.NaT or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return int(parse_datetime_utc(value).timestamp() * 1000)
    if isinstance(value, numbers.Integral):
        return _int_to_ms(int(value))
    if isinstance(value, numbers.Real):
        num = float(value)
        if num != num or num in (float("inf"), float("-inf")):
            return None
        return _int_to_ms(int(num))
    return None


def closed_candles(df, timeframe, evaluation_time=None):
    """Devuelve solo las velas cerradas de `timeframe` respecto a `evaluation_time`.

    `time` es apertura en ms/us enteros o datetime (naive = UTC). Vela cerrada
    si `open_time + duracion(timeframe) <= evaluation_time` (default: ahora UTC).
    Fail-closed: si `time` falta o no es parseable devuelve DataFrame vacio,
    nunca asume cerrada.
    """
    if df is None:
        return pd.DataFrame()
    if getattr(df, "empty", True) or "time" not in df.columns:
        return df.iloc[0:0]
    duration_ms = _TIMEFRAME_MS.get(str(timeframe).lower())
    if duration_ms is None:
        return df.iloc[0:0]
    if evaluation_time is None:
        evaluation_time = utc_now()
    eval_ms = _to_ms(evaluation_time)
    if eval_ms is None:
        return df.iloc[0:0]
    opens_ms = [_to_ms(value) for value in df["time"]]
    if any(value is None for value in opens_ms):
        return df.iloc[0:0]
    mask = [(value + duration_ms) <= eval_ms for value in opens_ms]
    return df[mask]


def last_close_ms(df, timeframe) -> int | None:
    """Cierre en ms UTC de la ultima vela de `df`; None si no hay vela utilizable."""
    if df is None or getattr(df, "empty", True) or "time" not in df.columns:
        return None
    duration_ms = _TIMEFRAME_MS.get(str(timeframe).lower())
    if duration_ms is None:
        return None
    open_ms = _to_ms(df["time"].iloc[-1])
    if open_ms is None:
        return None
    return open_ms + duration_ms
