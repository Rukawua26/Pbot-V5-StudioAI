#!/usr/bin/env python3
"""Research script to detect liquidity pools (SHOCK zones) on BTC/USDT.

This script is intentionally isolated from trading/orchestration code.
It fetches 30 days of 1H candles, detects support/resistance SHOCK zones
using pivot clustering + volume weighting, prints distance metrics,
exports a temporary PNG, sends it to Telegram, and cleans up the file.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import ccxt
import pandas as pd
import requests
from dotenv import load_dotenv
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

try:
    import plotly.graph_objects as go
except ImportError:
    print("Missing dependency: plotly. Install it with: pip install plotly")
    sys.exit(1)


SYMBOL = "BTC/USDT"
TIMEFRAME = "1h"
DAYS = 30
PIVOT_WINDOW = 3
MAX_CLUSTERS = 7
MIN_CLUSTERS = 2
RANDOM_STATE = 42

load_dotenv()


@dataclass
class ShockZone:
    level: float
    y0: float
    y1: float
    count: int
    side: str


def fetch_ohlcv(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    exchange = ccxt.binance({"enableRateLimit": True})
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    since_ms = int(start_time.timestamp() * 1000)

    rows: list[list[float]] = []
    next_since = since_ms
    limit = 1000

    while True:
        batch = exchange.fetch_ohlcv(
            symbol, timeframe=timeframe, since=next_since, limit=limit
        )
        if not batch:
            break

        rows.extend(batch)

        last_ts = batch[-1][0]
        next_since = last_ts + 1

        if len(batch) < limit:
            break
        if last_ts >= int(end_time.timestamp() * 1000):
            break

    if not rows:
        raise RuntimeError("No se pudieron descargar velas OHLCV.")

    df = pd.DataFrame(
        rows, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df = df.drop_duplicates(subset="timestamp")
    df = df.sort_values("timestamp")
    df = df.reset_index(drop=True)
    df = df.copy()
    df.loc[:, "datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

    cutoff = pd.Timestamp(start_time)
    return df[df["datetime"] >= cutoff].reset_index(drop=True)


def find_pivots(df: pd.DataFrame, window: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    highs = []
    lows = []

    for i in range(window, len(df) - window):
        slice_df = df.iloc[i - window : i + window + 1]
        center = df.iloc[i]

        if center["high"] >= slice_df["high"].max():
            highs.append(
                {
                    "idx": i,
                    "price": float(center["high"]),
                    "volume": float(center["volume"]),
                }
            )

        if center["low"] <= slice_df["low"].min():
            lows.append(
                {
                    "idx": i,
                    "price": float(center["low"]),
                    "volume": float(center["volume"]),
                }
            )

    return pd.DataFrame(highs), pd.DataFrame(lows)


def _pick_k(n_points: int) -> int:
    if n_points < 8:
        return 1
    heuristic = int(math.sqrt(n_points) / 1.8)
    return max(MIN_CLUSTERS, min(MAX_CLUSTERS, heuristic))


def _pick_k_silhouette(prices, weights) -> int:
    n_points = len(prices)
    if n_points < 8:
        return 1

    k_min = MIN_CLUSTERS
    k_max = min(MAX_CLUSTERS, n_points - 1)
    if k_max < k_min:
        return _pick_k(n_points)

    best_k = None
    best_score = -1.0

    for k in range(k_min, k_max + 1):
        model = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=20)
        labels = model.fit_predict(prices, sample_weight=weights)

        if len(set(labels)) < 2:
            continue

        try:
            score = silhouette_score(prices, labels)
        except ValueError:
            continue

        if score > best_score:
            best_score = score
            best_k = k

    if best_k is None:
        return _pick_k(n_points)
    return int(best_k)


def cluster_zones(
    pivots: pd.DataFrame, side: str, band_pct_floor: float = 0.0018
) -> tuple[list[ShockZone], int]:
    if pivots.empty:
        return [], 0

    prices = pivots[["price"]].values
    weights = pivots["volume"].astype(float).values
    k = _pick_k_silhouette(prices, weights)

    if k == 1:
        center = float(pivots["price"].mean())
        std = float(
            pivots["price"].std() if len(pivots) > 1 else center * band_pct_floor
        )
        half_band = max(center * band_pct_floor, std)
        return [
            ShockZone(
                level=center,
                y0=center - half_band,
                y1=center + half_band,
                count=len(pivots),
                side=side,
            )
        ], 1

    km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=20)
    labels = km.fit_predict(prices, sample_weight=weights)
    pivots = pivots.copy()
    pivots["cluster"] = labels

    zones: list[ShockZone] = []
    for c in sorted(pivots["cluster"].unique()):
        group = pivots[pivots["cluster"] == c]
        level = float(group["price"].mean())
        dispersion = (
            float(group["price"].std()) if len(group) > 1 else level * band_pct_floor
        )
        half_band = max(level * band_pct_floor, dispersion)

        zones.append(
            ShockZone(
                level=level,
                y0=level - half_band,
                y1=level + half_band,
                count=int(len(group)),
                side=side,
            )
        )

    zones.sort(key=lambda z: z.level)
    return zones, k


def nearest_distances(
    current_price: float, zones: list[ShockZone], side: str, n: int = 2
) -> list[tuple[ShockZone, float]]:
    if side == "resistance":
        candidates = [z for z in zones if z.level > current_price]
        candidates.sort(key=lambda z: z.level)
    else:
        candidates = [z for z in zones if z.level < current_price]
        candidates.sort(key=lambda z: z.level, reverse=True)

    out = []
    for zone in candidates[:n]:
        dist_pct = abs(zone.level - current_price) / current_price * 100
        out.append((zone, dist_pct))
    return out


def build_chart_png(
    df: pd.DataFrame,
    supports: list[ShockZone],
    resistances: list[ShockZone],
    current_price: float,
) -> Path:
    fig = go.Figure()

    fig.add_trace(
        go.Candlestick(
            x=df["datetime"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=SYMBOL,
        )
    )

    x0 = df["datetime"].min()
    x1 = df["datetime"].max()

    for zone in supports:
        fig.add_shape(
            type="rect",
            xref="x",
            yref="y",
            x0=x0,
            x1=x1,
            y0=zone.y0,
            y1=zone.y1,
            fillcolor="rgba(28, 161, 108, 0.18)",
            line={"width": 0},
            layer="below",
        )

    for zone in resistances:
        fig.add_shape(
            type="rect",
            xref="x",
            yref="y",
            x0=x0,
            x1=x1,
            y0=zone.y0,
            y1=zone.y1,
            fillcolor="rgba(195, 65, 82, 0.18)",
            line={"width": 0},
            layer="below",
        )

    fig.add_hline(
        y=current_price, line_dash="dot", line_color="rgba(31, 120, 180, 0.9)"
    )

    fig.update_layout(
        title=f"{SYMBOL} SHOCK Research (1H, {DAYS}d)",
        xaxis_title="Fecha",
        yaxis_title="Precio",
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        height=800,
    )

    with tempfile.NamedTemporaryFile(
        prefix="shocks_", suffix=".png", delete=False
    ) as tmp_file:
        output_path = Path(tmp_file.name)

    fig.write_image(str(output_path), format="png", width=1600, height=900, scale=2)
    return output_path


def _format_zone_line(
    label: str, zone_dist: tuple[ShockZone, float] | None, emoji: str
) -> str:
    if zone_dist is None:
        return f"{emoji} {label}: N/A"

    zone, dist = zone_dist
    return (
        f"{emoji} {label}: ${zone.level:,.2f} | 📏 DIST: {dist:.2f}% | "
        f"🔄 Toques: {zone.count}"
    )


def build_report_text(
    current_price: float,
    near_res: list[tuple[ShockZone, float]],
    near_sup: list[tuple[ShockZone, float]],
) -> str:
    ny_now = datetime.now(ZoneInfo("America/New_York"))
    ny_time = ny_now.strftime("%Y-%m-%d %H:%M:%S %Z")

    r1 = near_res[0] if len(near_res) > 0 else None
    r2 = near_res[1] if len(near_res) > 1 else None
    s1 = near_sup[0] if len(near_sup) > 0 else None
    s2 = near_sup[1] if len(near_sup) > 1 else None

    lines = [
        f"📊 SHOCK RESEARCH: {SYMBOL}",
        f"⏱️ Marco: {TIMEFRAME.upper()} | 🗽 Hora NY: {ny_time}",
        "",
        f"📍 PRECIO ACTUAL: ${current_price:,.2f}",
        "",
        "🧱 RESISTENCIAS (Techos invisibles)",
        _format_zone_line("R1", r1, "🔴"),
        _format_zone_line("R2", r2, "🔴"),
        "",
        "🟢 SOPORTES (Pisos institucionales)",
        _format_zone_line("S1", s1, "🟩"),
        _format_zone_line("S2", s2, "🟩"),
    ]
    return "\n".join(lines)


def send_png_to_telegram(image_path: Path, caption: str) -> bool:
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("⚠️ Telegram no configurado: faltan TELEGRAM_TOKEN y/o TELEGRAM_CHAT_ID")
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    data = {"chat_id": chat_id, "caption": caption}

    with image_path.open("rb") as img_file:
        files = {"photo": (image_path.name, img_file, "image/png")}
        response = requests.post(url, data=data, files=files, timeout=20)

    if response.status_code != 200:
        print(f"⚠️ Error enviando Telegram: {response.text}")
        return False

    return True


def main() -> None:
    df = fetch_ohlcv(SYMBOL, TIMEFRAME, DAYS)
    if len(df) < 100:
        raise RuntimeError(f"Histórico insuficiente: {len(df)} velas")

    pivot_highs, pivot_lows = find_pivots(df, PIVOT_WINDOW)
    resistances, k_res = cluster_zones(pivot_highs, side="resistance")
    supports, k_sup = cluster_zones(pivot_lows, side="support")

    current_price = float(df.iloc[-1]["close"])
    near_res = nearest_distances(current_price, resistances, side="resistance", n=2)
    near_sup = nearest_distances(current_price, supports, side="support", n=2)

    print(
        f"Mercado consolidado en {max(k_res, k_sup)} clusters SHOCK (k_res={k_res}, k_sup={k_sup})"
    )

    report_text = build_report_text(
        current_price=current_price, near_res=near_res, near_sup=near_sup
    )
    print(report_text)

    image_path = build_chart_png(
        df, supports=supports, resistances=resistances, current_price=current_price
    )

    try:
        sent = send_png_to_telegram(image_path=image_path, caption=report_text)
        if sent:
            print(f"✅ PNG enviado a Telegram: {image_path}")
        else:
            print(f"⚠️ PNG generado pero no enviado: {image_path}")
    finally:
        if image_path.exists():
            image_path.unlink()
            print(f"🧹 PNG temporal eliminado: {image_path}")


if __name__ == "__main__":
    main()
