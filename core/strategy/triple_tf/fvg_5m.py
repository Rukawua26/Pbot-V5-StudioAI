from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class FVGZone:
    bias: str  # "BUY" o "SELL"
    fvg_top: float  # Techo del gap (precio superior)
    fvg_bot: float  # Suelo del gap (precio inferior)
    gap_pct: float  # Tamaño del gap como % del precio
    suggested_sl: float  # SL en extremo opuesto del gap con buffer defensivo
    formed_at_idx: int  # Índice en df_5m donde se completó el patrón


def detect_fvg_5m(
    df_5m: pd.DataFrame | None,
    bias_1h: str,
    lookback_bars: int = 20,
    min_gap_pct: float = 0.30,
    min_body_ratio: float = 0.40,
    sl_buffer_pct: float = 0.0010,
) -> FVGZone | None:
    """Detecta la zona de Fair Value Gap (FVG) más reciente y válida en 5M.

    Patrón de 3 velas cerradas [i-2, i-1, i]:
      - BUY (Bullish FVG): high[i-2] < low[i] con vela [i-1] alcista e impulsiva.
        Zona: [high[i-2], low[i]].
        SL sugerido: extremo opuesto (techo) menos buffer defensivo.
      - SELL (Bearish FVG): low[i-2] > high[i] con vela [i-1] bajista e impulsiva.
        Zona: [high[i], low[i-2]].
        SL sugerido: extremo opuesto (suelo) más buffer defensivo.
    """
    if df_5m is None or len(df_5m) < 3 or bias_1h not in {"BUY", "SELL"}:
        return None

    highs = df_5m["high"].astype(float).to_numpy()
    lows = df_5m["low"].astype(float).to_numpy()
    opens = df_5m["open"].astype(float).to_numpy()
    closes = df_5m["close"].astype(float).to_numpy()
    n = len(highs)

    search_start = max(2, n - lookback_bars)

    for i in range(n - 1, search_start - 1, -1):
        h2, h1, h0 = highs[i - 2], highs[i - 1], highs[i]
        l2, l1, l0 = lows[i - 2], lows[i - 1], lows[i]
        o1, c1 = opens[i - 1], closes[i - 1]

        body1 = abs(c1 - o1)
        rng1 = h1 - l1

        if bias_1h == "BUY":
            gap_bot, gap_top = h2, l0
            if gap_top > gap_bot:
                ref_price = closes[i]
                gap_pct = (
                    (gap_top - gap_bot) / ref_price * 100.0 if ref_price > 0 else 0.0
                )
                is_impulsive = c1 > o1 and rng1 > 0 and (body1 / rng1) >= min_body_ratio
                if is_impulsive and gap_pct >= min_gap_pct:
                    suggested_sl = gap_top * (1.0 - sl_buffer_pct)
                    return FVGZone(
                        bias="BUY",
                        fvg_top=gap_top,
                        fvg_bot=gap_bot,
                        gap_pct=gap_pct,
                        suggested_sl=suggested_sl,
                        formed_at_idx=i,
                    )
        else:  # SELL
            gap_top, gap_bot = l2, h0
            if gap_top > gap_bot:
                ref_price = closes[i]
                gap_pct = (
                    (gap_top - gap_bot) / ref_price * 100.0 if ref_price > 0 else 0.0
                )
                is_impulsive = c1 < o1 and rng1 > 0 and (body1 / rng1) >= min_body_ratio
                if is_impulsive and gap_pct >= min_gap_pct:
                    suggested_sl = gap_bot * (1.0 + sl_buffer_pct)
                    return FVGZone(
                        bias="SELL",
                        fvg_top=gap_top,
                        fvg_bot=gap_bot,
                        gap_pct=gap_pct,
                        suggested_sl=suggested_sl,
                        formed_at_idx=i,
                    )

    return None
