#!/usr/bin/env python3
"""
Research offline de vetos SHOCK y ruptura posterior.

Fuente de datos:
- sniper.log (eventos de veto SHOCK)
- data_storage/candles/*.parquet (OHLCV local)

No realiza llamadas a Binance API.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


LINE_RE = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?⛔ (?P<symbol>[A-Z0-9]+/USDT) vetado: SHOCK DEMASIADO CERCA \((?P<dist>[0-9.]+)% < (?P<th>[0-9.]+)%\)"
)


@dataclass
class ShockVeto:
    ts: pd.Timestamp
    symbol: str
    dist_pct: float
    threshold_pct: float


def parse_vetos(log_file: Path) -> List[ShockVeto]:
    out: List[ShockVeto] = []
    if not log_file.exists():
        return out

    for line in log_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = LINE_RE.search(line)
        if not m:
            continue
        out.append(
            ShockVeto(
                ts=pd.to_datetime(m.group("date"), errors="coerce"),
                symbol=m.group("symbol"),
                dist_pct=float(m.group("dist")),
                threshold_pct=float(m.group("th")),
            )
        )
    return [v for v in out if pd.notna(v.ts)]


def candle_path(candle_dir: Path, symbol: str, timeframe: str) -> Path:
    safe_symbol = symbol.replace("/", "_").replace(":", "_")
    safe_tf = timeframe.replace("/", "_").replace(":", "_")
    return candle_dir / f"{safe_symbol}_{safe_tf}.parquet"


def load_df(candle_dir: Path, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
    path = candle_path(candle_dir, symbol, timeframe)
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    required = {"time", "close", "volume", "high", "low"}
    if df is None or df.empty or not required.issubset(set(df.columns)):
        return None
    df = df.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)
    return df


def eval_breakout(
    df: pd.DataFrame,
    veto_ts: pd.Timestamp,
    dist_pct: float,
    threshold_pct: float,
    breakout_buffer_pct: float,
    vol_mult: float,
    window_bars: int,
) -> Tuple[bool, Dict[str, float]]:
    # Aproximación offline: usamos distancia reportada para reconstruir nivel SHOCK
    # shock_level ≈ close_at_veto * (1 + dist)
    ts_ms = int(veto_ts.timestamp() * 1000)
    idx = df[df["time"] <= ts_ms].index
    if len(idx) == 0:
        return False, {"reason": -1.0}

    i0 = int(idx[-1])
    close0 = float(df["close"].iloc[i0])
    shock_level = close0 * (1.0 + dist_pct / 100.0)
    target = shock_level * (1.0 + breakout_buffer_pct / 100.0)

    end = min(len(df) - 1, i0 + max(1, window_bars))
    if end <= i0:
        return False, {"reason": -2.0}

    for i in range(i0 + 1, end + 1):
        close_i = float(df["close"].iloc[i])
        vol_i = float(df["volume"].iloc[i])
        avg_i = float(df["volume"].iloc[max(0, i - 20) : i].mean() or 0.0)
        vol_ok = avg_i > 0 and vol_i >= (avg_i * vol_mult)
        if close_i > target and vol_ok:
            return True, {
                "bars_to_break": float(i - i0),
                "close_break": close_i,
                "target": target,
                "vol_now": vol_i,
                "vol_avg20": avg_i,
                "dist_pct": dist_pct,
                "threshold_pct": threshold_pct,
            }

    return False, {
        "dist_pct": dist_pct,
        "threshold_pct": threshold_pct,
        "target": target,
    }


def main() -> None:
    p = argparse.ArgumentParser(
        description="Research offline de vetos SHOCK vs ruptura"
    )
    p.add_argument("--log", default="sniper.log")
    p.add_argument("--candles", default="data_storage/candles")
    p.add_argument("--timeframe", default="1h", choices=["15m", "1h"])
    p.add_argument("--window-bars", type=int, default=1)
    p.add_argument("--breakout-buffer-pct", type=float, default=0.5)
    p.add_argument("--volume-mult", type=float, default=1.5)
    p.add_argument("--limit", type=int, default=300)
    args = p.parse_args()

    vetos = parse_vetos(Path(args.log))
    if not vetos:
        print("No se encontraron vetos SHOCK en el log.")
        return

    vetos = vetos[-args.limit :]
    candle_dir = Path(args.candles)

    cache: Dict[str, Optional[pd.DataFrame]] = {}
    total = 0
    hits = 0
    missing = 0

    for v in vetos:
        if v.symbol not in cache:
            cache[v.symbol] = load_df(candle_dir, v.symbol, args.timeframe)
        df = cache[v.symbol]
        if df is None:
            missing += 1
            continue
        total += 1
        ok, _ = eval_breakout(
            df=df,
            veto_ts=v.ts,
            dist_pct=v.dist_pct,
            threshold_pct=v.threshold_pct,
            breakout_buffer_pct=args.breakout_buffer_pct,
            vol_mult=args.volume_mult,
            window_bars=args.window_bars,
        )
        if ok:
            hits += 1

    rate = (hits / total * 100.0) if total > 0 else 0.0
    print("=== Research Breakout (offline) ===")
    print(f"Vetos leidos: {len(vetos)}")
    print(f"Vetos evaluables (con velas): {total}")
    print(f"Faltantes por cache local: {missing}")
    print(f"Rupturas confirmadas: {hits}")
    print(f"Hit Rate: {rate:.2f}%")
    print(
        f"Params -> tf={args.timeframe}, window={args.window_bars}, "
        f"buffer={args.breakout_buffer_pct}%, vol_mult={args.volume_mult}"
    )


if __name__ == "__main__":
    main()
