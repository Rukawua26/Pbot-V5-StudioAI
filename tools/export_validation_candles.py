#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import ccxt
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data_service import DataService


def _load_event_time_range(events_path: Path, symbol: str) -> tuple[datetime, datetime]:
    symbol_norm = symbol.upper()
    timestamps: list[datetime] = []
    if not events_path.exists():
        raise FileNotFoundError(f"events file not found: {events_path}")
    with events_path.open("r", encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = row.get("payload") or {}
            if str(payload.get("symbol") or "").upper() != symbol_norm:
                continue
            raw_ts = row.get("ts")
            if not raw_ts:
                continue
            try:
                ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            timestamps.append(ts.astimezone(UTC))
    if not timestamps:
        raise ValueError(f"no events found for symbol {symbol} in {events_path}")
    return min(timestamps), max(timestamps)


def _days_covering_event_range(
    events_path: Path,
    symbol: str,
    *,
    padding_days: int = 2,
    now: datetime | None = None,
) -> int:
    start, _end = _load_event_time_range(events_path, symbol)
    now = (now or datetime.now(UTC)).astimezone(UTC)
    age_seconds = max(0.0, (now - start).total_seconds())
    return max(1, int(math.ceil(age_seconds / 86400.0)) + int(padding_days))


def export_validation_candles(
    *,
    symbol: str,
    timeframe: str,
    days: int,
    output: Path,
) -> Path:
    exchange = ccxt.binance({"enableRateLimit": True})
    data_service = DataService(exchange)
    df = data_service.download_historical_data(symbol, timeframe, days)
    export_df = df.copy()
    if pd.api.types.is_numeric_dtype(export_df["time"]):
        export_df["time"] = pd.to_datetime(export_df["time"], unit="ms", utc=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    export_df.to_csv(output, index=False)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Export OHLCV candles for strategy validation")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument(
        "--from-events",
        action="store_true",
        help="Calculate the required days from logs/execution_events.jsonl for the selected symbol.",
    )
    parser.add_argument("--events", default="logs/execution_events.jsonl")
    parser.add_argument("--padding-days", type=int, default=2)
    parser.add_argument("--output", default="data_storage/validation_candles.csv")
    args = parser.parse_args()

    days = args.days
    if args.from_events:
        start, end = _load_event_time_range(Path(args.events), args.symbol)
        days = _days_covering_event_range(
            Path(args.events),
            args.symbol,
            padding_days=args.padding_days,
        )
        print(
            f"event_range: {start.isoformat()} -> {end.isoformat()} | days={days}",
            file=sys.stderr,
        )

    output = export_validation_candles(
        symbol=args.symbol,
        timeframe=args.timeframe,
        days=days,
        output=Path(args.output),
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
