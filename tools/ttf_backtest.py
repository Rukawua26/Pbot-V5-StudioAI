#!/usr/bin/env python3
"""Backtest histórico de la estrategia Triple Timeframe (1H / 5M / 1M).

Herramienta OFFLINE y de solo lectura: no toca el runtime, no envía órdenes y no
modifica configuración. Reutiliza exactamente las funciones de señal de
``core/strategy/triple_tf`` (las mismas que llama ``tools/strategy.py`` en vivo)
y replica la fijación de SL/TP de ``core/trade_entry.py`` para TTF.

Supuestos (explícitos, para no sobreestimar resultados):

* Solo se usan velas CERRADAS en los tres marcos temporales. Las velas de 5M y 1H
  se construyen a partir de las de 1M, así que todo es coherente en el tiempo.
* La señal se evalúa al cierre de cada vela de 1M y la entrada se ejecuta en la
  APERTURA de la vela siguiente, más deslizamiento (sin mirar el futuro).
* SL/TP se calculan con el precio de la señal, igual que en vivo
  (SL estructural de 5M, distancia mínima 0.2%, tope MAX_ENTRY_SL_PCT*0.95,
  TP = max(2.5R, (RRR+0.05)R + (RRR+1)*penalización)).
* Si en la misma vela de 1M se tocan SL y TP, se asume que salió por SL.
* Salidas: SL/TP fijos, trailing EMA50 del marco gatillo (por defecto activo),
  más breakeven opcional. No simula degradación ni vetos extra de ``core/signals/filters.py``.
  Mide el núcleo de la señal, no el bot completo.
* Una sola posición por símbolo a la vez. Resultados en R (múltiplos del riesgo)
  netos de comisiones y deslizamiento.

Uso:
    python -m tools.ttf_backtest --symbols BTCUSDT ETHUSDT SOLUSDT \\
        --start 2025-09 --end 2026-08 --out reports/ttf_backtest

Los datos se descargan de data.binance.vision (futuros USDⓈ-M) y se guardan en
caché en ``data/ttf_backtest/``. También acepta CSV propios con ``--csv``.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, ROUND_DOWN
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pandas as pd

from core.strategy.triple_tf.pipeline import (
    TTFSignalParams,
    evaluate_ttf_signal,
    reserve_setup,
)
from core.strategy.triple_tf.trailing_1m import evaluate_trailing_1m

BINANCE_VISION_URL = (
    "https://data.binance.vision/data/futures/um/monthly/klines/"
    "{symbol}/1m/{symbol}-1m-{month}.zip"
)
DEFAULT_CACHE_DIR = Path("data/ttf_backtest")
CANDLE_COLUMNS = ["time", "open", "high", "low", "close", "volume"]
# Ventana de velas que se pasa a cada evaluador. EMA50 con 300 velas converge
# (peso residual de la semilla ~e^-12), y en vivo se usan hasta 500.
WINDOW_BARS = 300


def _live_default(name: str, fallback: float) -> float:
    """Lee el valor de la configuración del bot para replicar el comportamiento en vivo."""
    try:
        from config import Config

        value = getattr(Config, name, fallback)
        return float(value if value is not None else fallback)
    except Exception:  # noqa: BLE001 - herramienta offline: si config falla, usa el default
        return float(fallback)


@dataclass
class TTFBacktestParams:
    fee_rate: float = 0.0005  # comisión taker por lado (Binance Futures estándar)
    slippage_pct: float = 0.0005  # deslizamiento real por lado en órdenes a mercado
    spread_pct: float = 0.0  # spread asumido para el filtro del gatillo 1M
    min_rrr: float = field(
        default_factory=lambda: _live_default("MIN_RISK_REWARD_RATIO", 1.8)
    )
    entry_penalty_slippage: float = field(
        default_factory=lambda: _live_default("MAX_SLIPPAGE", 0.001)
    )
    max_entry_sl_pct: float = field(
        default_factory=lambda: _live_default("MAX_ENTRY_SL_PCT", 3.0)
    )
    min_sl_pct: float = 0.002  # igual que trade_entry: max(price*0.002, spread*1.5)
    tp_min_r: float = 2.5  # trade_entry: target_dist = max(risk*2.5, ...)
    breakeven_at_r: float | None = None  # opcional: mover SL a entrada al alcanzar +xR
    max_hold_minutes: int | None = None  # opcional: cierre por tiempo
    risk_per_trade_pct: float = 1.2
    trailing_enabled: bool = True
    tf_bias: str = "1h"
    tf_struct: str = "5min"
    tf_trigger: str = "1min"
    max_setup_minutes: int | None = None
    account_balance: float = 20.0
    leverage: int = 10
    max_margin_percent: float = 5.0
    max_risk_usd: float = 2.0
    max_open_trades: int = 3
    # Runtime TTF_REQUIRE_SESSION_FILTER (core/signals/filters.py): 07:00-22:00 UTC.
    session_filter: bool = field(
        default_factory=lambda: bool(_live_default("TTF_REQUIRE_SESSION_FILTER", 1.0))
    )

    def signal_params(self) -> TTFSignalParams:
        from config import Config

        base = TTFSignalParams.from_config(Config)
        struct_minutes = pd.Timedelta(self.tf_struct).total_seconds() / 60
        # Pre-registered H1 explicitly uses 60 minutes at 15min structure.
        age = (
            60
            if struct_minutes == 15
            else round(base.max_setup_minutes * struct_minutes / 5)
        )
        trigger_minutes = int(pd.Timedelta(self.tf_trigger).total_seconds() / 60)
        return replace(
            base,
            max_setup_minutes=self.max_setup_minutes
            if self.max_setup_minutes is not None
            else age,
            trigger_timeframe=f"{trigger_minutes}m",
        )


@dataclass
class TTFTrade:
    symbol: str
    side: str
    signal_time: str
    entry_time: str
    exit_time: str
    signal_price: float
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    exit_reason: str
    risk_pct: float
    gross_r: float
    cost_r: float
    net_r: float
    bars_held: int
    mfe_r: float
    mae_r: float


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------


def _month_range(start: str, end: str) -> list[str]:
    periods = pd.period_range(pd.Period(start, "M"), pd.Period(end, "M"), freq="M")
    return [str(p) for p in periods]


def _parse_binance_csv(raw: bytes) -> pd.DataFrame:
    text = raw.decode("utf-8")
    first = text.split("\n", 1)[0]
    has_header = not first.split(",")[0].strip().isdigit()
    df = pd.read_csv(io.StringIO(text), header=0 if has_header else None)
    df = df.iloc[:, :6]
    df.columns = CANDLE_COLUMNS
    return df


def download_month(
    symbol: str, month: str, cache_dir: Path = DEFAULT_CACHE_DIR
) -> pd.DataFrame | None:
    """Descarga (o lee de caché) un mes de velas 1M de futuros USDⓈ-M."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{symbol}-1m-{month}.csv"
    if cache_file.exists():
        return pd.read_csv(cache_file)
    url = BINANCE_VISION_URL.format(symbol=symbol, month=month)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(
                f"  ! {symbol} {month}: no publicado todavía en data.binance.vision",
                file=sys.stderr,
            )
            return None
        raise
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        name = zf.namelist()[0]
        df = _parse_binance_csv(zf.read(name))
    df.to_csv(cache_file, index=False)
    return df


def load_symbol_candles(
    symbol: str,
    start: str,
    end: str,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> pd.DataFrame:
    frames = []
    for month in _month_range(start, end):
        print(f"  · {symbol} {month}", file=sys.stderr)
        df = download_month(symbol, month, cache_dir)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        raise RuntimeError(f"Sin datos para {symbol} entre {start} y {end}")
    return normalize_candles(pd.concat(frames, ignore_index=True))


def load_candles_file(path: Path) -> pd.DataFrame:
    df = (
        pd.read_parquet(path)
        if path.suffix.lower() == ".parquet"
        else pd.read_csv(path)
    )
    missing = set(CANDLE_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas en {path}: {sorted(missing)}")
    return normalize_candles(df)


def normalize_candles(df: pd.DataFrame) -> pd.DataFrame:
    df = df[CANDLE_COLUMNS].copy()
    t = df["time"]
    if pd.api.types.is_numeric_dtype(t):
        # Binance usa ms (y µs en archivos desde 2025); normalizamos ambos.
        unit = "us" if float(t.max()) > 1e14 else "ms"
        df["time"] = pd.to_datetime(t, unit=unit, utc=True)
    else:
        df["time"] = pd.to_datetime(t, utc=True, errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().drop_duplicates(subset=["time"]).sort_values("time")
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    return df.reset_index(drop=True)


def resample_closed(df_1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Agrega velas 1M a un marco mayor. 'time' es la apertura de la vela agregada."""
    agg = (
        df_1m.set_index("time")
        .resample(rule, label="left", closed="left")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
        .reset_index()
    )
    return agg


# ---------------------------------------------------------------------------
# Niveles de salida (réplica de core/trade_entry.py rama triple_tf)
# ---------------------------------------------------------------------------


def compute_exit_levels(
    side: str, price: float, suggested_sl: float, params: TTFBacktestParams
) -> tuple[float, float, float] | None:
    if suggested_sl <= 0 or price <= 0:
        return None
    risk_dist = abs(price - suggested_sl)
    sl_val = suggested_sl
    min_dist = max(price * params.min_sl_pct, params.spread_pct * price * 1.5)
    if risk_dist < min_dist:
        risk_dist = min_dist
        sl_val = price - risk_dist if side == "BUY" else price + risk_dist
    if (
        params.max_entry_sl_pct > 0
        and risk_dist / price * 100.0 > params.max_entry_sl_pct
    ):
        risk_dist = price * (params.max_entry_sl_pct * 0.95 / 100.0)
        sl_val = price - risk_dist if side == "BUY" else price + risk_dist
    if side == "BUY" and sl_val >= price:
        sl_val = price - risk_dist
    elif side == "SELL" and sl_val <= price:
        sl_val = price + risk_dist

    entry_penalty = (params.spread_pct + params.entry_penalty_slippage) * price
    target_rrr = params.min_rrr + 0.05
    min_target_dist = target_rrr * risk_dist + (target_rrr + 1.0) * entry_penalty
    target_dist = max(risk_dist * params.tp_min_r, min_target_dist)
    tp_val = price + target_dist if side == "BUY" else price - target_dist
    return sl_val, tp_val, risk_dist


# ---------------------------------------------------------------------------
# Simulación
# ---------------------------------------------------------------------------


def _simulate_exit(
    side: str,
    entry_idx: int,
    entry_price: float,
    sl: float,
    tp: float,
    o: np.ndarray,
    h: np.ndarray,
    low: np.ndarray,
    c: np.ndarray,
    params: TTFBacktestParams,
    df_trigger: pd.DataFrame | None = None,
) -> tuple[int, float, str, float, float]:
    """Recorre velas 1M desde la de entrada. Devuelve (idx_salida, precio, motivo, mfe, mae)."""
    direction = 1.0 if side == "BUY" else -1.0
    risk = abs(entry_price - sl)
    stop = sl
    be_armed = False
    mfe = 0.0
    mae = 0.0
    n = len(c)
    trailing_active = False
    if df_trigger is None:
        df_trigger = pd.DataFrame({"close": c})
    last = n - 1
    if params.max_hold_minutes:
        minutes = pd.Timedelta(params.tf_trigger).total_seconds() / 60
        last = min(
            last, entry_idx + max(1, math.ceil(params.max_hold_minutes / minutes)) - 1
        )
    for j in range(entry_idx, last + 1):
        hi, lo = h[j], low[j]
        fav = (hi - entry_price) if side == "BUY" else (entry_price - lo)
        adv = (entry_price - lo) if side == "BUY" else (hi - entry_price)
        mfe = max(mfe, fav / risk)
        mae = max(mae, adv / risk)
        hit_sl = lo <= stop if side == "BUY" else hi >= stop
        hit_tp = hi >= tp if side == "BUY" else lo <= tp
        if hit_sl:
            # Stop a mercado: si la vela abre más allá del stop (gap), se llena en la apertura.
            gap_fill = o[j] if (o[j] < stop if side == "BUY" else o[j] > stop) else stop
            fill = gap_fill * (1.0 - direction * params.slippage_pct)
            return j, fill, ("BREAKEVEN" if be_armed else "SL"), mfe, mae
        if hit_tp:
            return j, tp, "TP", mfe, mae
        if params.trailing_enabled:
            trailing = evaluate_trailing_1m(
                df_1m=df_trigger.iloc[max(0, j + 1 - WINDOW_BARS) : j + 1],
                side=side,
                entry_price=entry_price,
                sl_price=stop,
                current_price=float(c[j]),
                trailing_already_activated=trailing_active,
            )
            trailing_active = trailing.is_activated
            if trailing.should_exit:
                return (
                    j,
                    c[j] * (1.0 - direction * params.slippage_pct),
                    "TRAILING",
                    mfe,
                    mae,
                )
        if (
            params.breakeven_at_r
            and not be_armed
            and fav / risk >= params.breakeven_at_r
        ):
            stop = entry_price
            be_armed = True
    fill = c[last] * (1.0 - direction * params.slippage_pct)
    reason = "TIME" if params.max_hold_minutes and last < n - 1 else "END_OF_DATA"
    return last, fill, reason, mfe, mae


def backtest_symbol(
    symbol: str, df_1m: pd.DataFrame, params: TTFBacktestParams | None = None
) -> list[TTFTrade]:
    params = params or TTFBacktestParams()
    source = normalize_candles(df_1m)
    df_5m = resample_closed(source, params.tf_struct)
    df_1h = resample_closed(source, params.tf_bias)
    df_1m = resample_closed(source, params.tf_trigger)
    # Exclude incomplete final aggregates (the input rows are closed 1M candles).
    if source.empty:
        return []
    source_end = source["time"].iloc[-1] + pd.Timedelta(minutes=1)
    df_1m = df_1m[
        df_1m["time"] + pd.Timedelta(params.tf_trigger) <= source_end
    ].reset_index(drop=True)
    signal_params = params.signal_params()
    consumed = SimpleNamespace()

    def _ns(series: pd.Series) -> np.ndarray:
        # Nanosegundos UTC como int64: evita arrays object con fechas tz-aware.
        return (
            series.dt.tz_convert("UTC")
            .dt.tz_localize(None)
            .to_numpy("datetime64[ns]")
            .astype(np.int64)
        )

    t1 = _ns(df_1m["time"])
    o = df_1m["open"].to_numpy(float)
    h = df_1m["high"].to_numpy(float)
    low = df_1m["low"].to_numpy(float)
    c = df_1m["close"].to_numpy(float)

    # Momento de CIERRE de cada vela agregada: solo es utilizable cuando ya cerró.
    close_5m = _ns(df_5m["time"] + pd.Timedelta(params.tf_struct))
    close_1h = _ns(df_1h["time"] + pd.Timedelta(params.tf_bias))
    close_1m = t1 + pd.Timedelta(params.tf_trigger).value

    trades: list[TTFTrade] = []
    next_free_idx = 0  # índice 1M a partir del cual se permite una nueva entrada
    n = len(df_1m)

    for i in range(WINDOW_BARS, n - 1):
        if i < next_free_idx:
            continue
        now = close_1m[i]
        n1h = int(np.searchsorted(close_1h, now, side="right"))
        n5m = int(np.searchsorted(close_5m, now, side="right"))
        if n1h < 50 or n5m < 50:
            continue

        decision = evaluate_ttf_signal(
            df_1h.iloc[max(0, n1h - WINDOW_BARS) : n1h],
            df_5m.iloc[max(0, n5m - WINDOW_BARS) : n5m],
            df_1m.iloc[max(0, i + 1 - WINDOW_BARS) : i + 1],
            symbol=symbol,
            spread=params.spread_pct,
            params=signal_params,
            consumed_setups=getattr(consumed, "_ttf_consumed_setups", ()),
        )
        if decision.side not in {"BUY", "SELL"}:
            continue
        if params.session_filter:
            hour_utc = int((int(now) // 3_600_000_000_000) % 24)
            if not 7 <= hour_utc < 22:
                continue

        side = decision.side
        signal_price = decision.entry_price or float(c[i])
        levels = compute_exit_levels(side, signal_price, decision.suggested_sl, params)
        if levels is None:
            continue
        sl, tp, _ = levels

        entry_idx = i + 1
        direction = 1.0 if side == "BUY" else -1.0
        entry_price = float(o[entry_idx]) * (1.0 + direction * params.slippage_pct)
        risk_at_fill = (entry_price - sl) * direction
        if risk_at_fill <= 0 or (tp - entry_price) * direction <= 0:
            # La apertura siguiente ya saltó el SL o el TP: en vivo sería una entrada inválida.
            continue

        if not reserve_setup(consumed, decision.setup_key):
            continue
        exit_idx, exit_price, reason, mfe, mae = _simulate_exit(
            side, entry_idx, entry_price, sl, tp, o, h, low, c, params, df_1m
        )
        gross_r = (exit_price - entry_price) * direction / risk_at_fill
        cost_r = params.fee_rate * (entry_price + exit_price) / risk_at_fill
        trades.append(
            TTFTrade(
                symbol=symbol,
                side=side,
                signal_time=str(pd.Timestamp(int(t1[i]), tz="UTC")),
                entry_time=str(pd.Timestamp(int(t1[entry_idx]), tz="UTC")),
                exit_time=str(
                    pd.Timestamp(
                        int(
                            close_1m[exit_idx]
                            if reason in {"TRAILING", "TIME", "END_OF_DATA"}
                            else t1[exit_idx]
                        ),
                        tz="UTC",
                    )
                ),
                signal_price=signal_price,
                entry_price=entry_price,
                stop_loss=float(sl),
                take_profit=float(tp),
                exit_price=float(exit_price),
                exit_reason=reason,
                risk_pct=float(risk_at_fill / entry_price * 100.0),
                gross_r=float(gross_r),
                cost_r=float(cost_r),
                net_r=float(gross_r - cost_r),
                bars_held=int(exit_idx - entry_idx + 1),
                mfe_r=float(mfe),
                mae_r=float(mae),
            )
        )
        next_free_idx = exit_idx + 1
    return trades


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------


def summarize(trades: Iterable[TTFTrade], risk_per_trade_pct: float = 1.2) -> dict:
    rows = list(trades)
    if not rows:
        return {"trades": 0, "verdict": "SIN_OPERACIONES"}
    df = pd.DataFrame([asdict(t) for t in rows]).sort_values("exit_time")
    net = df["net_r"].to_numpy(float)
    wins = net[net > 0]
    losses = net[net <= 0]
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    equity = np.cumsum(net)
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    max_dd_r = float((peak - equity).max()) if len(equity) else 0.0
    streak = worst = 0
    for value in net:
        streak = streak + 1 if value <= 0 else 0
        worst = max(worst, streak)
    pf = gross_profit / gross_loss if gross_loss > 0 else math.inf
    expectancy = float(net.mean())
    summary = {
        "trades": len(df),
        "win_rate_pct": round(float((net > 0).mean() * 100.0), 2),
        "expectancy_r": round(expectancy, 4),
        "total_r": round(float(net.sum()), 2),
        "profit_factor": round(pf, 3) if math.isfinite(pf) else None,
        "avg_win_r": round(float(wins.mean()), 3) if len(wins) else 0.0,
        "avg_loss_r": round(float(losses.mean()), 3) if len(losses) else 0.0,
        "avg_cost_r": round(float(df["cost_r"].mean()), 3),
        "gross_expectancy_r": round(float(df["gross_r"].mean()), 4),
        "max_drawdown_r": round(max_dd_r, 2),
        "max_losing_streak": int(worst),
        "avg_risk_pct": round(float(df["risk_pct"].mean()), 3),
        "median_bars_held": float(df["bars_held"].median()),
        "approx_account_return_pct": round(float(net.sum()) * risk_per_trade_pct, 2),
        "approx_account_max_dd_pct": round(max_dd_r * risk_per_trade_pct, 2),
        "exit_reasons": df["exit_reason"].value_counts().to_dict(),
        "by_side": {
            side: {
                "trades": len(g),
                "win_rate_pct": round(float((g["net_r"] > 0).mean() * 100.0), 2),
                "expectancy_r": round(float(g["net_r"].mean()), 4),
            }
            for side, g in df.groupby("side")
        },
    }
    summary["verdict"] = verdict(summary)
    return summary


def verdict(s: dict) -> str:
    n = s["trades"]
    pf = s.get("profit_factor") or 0.0
    if n < 100:
        return "MUESTRA_INSUFICIENTE"
    if s["expectancy_r"] <= 0:
        return "SIN_EDGE"
    if pf >= 1.3 and s["expectancy_r"] >= 0.1:
        return "EDGE_PROMETEDOR"
    return "EDGE_DEBIL"


def split_chronological(
    trades: list[TTFTrade], train_frac: float = 0.7
) -> tuple[list, list]:
    ordered = sorted(trades, key=lambda t: t.entry_time)
    cut = int(len(ordered) * train_frac)
    return ordered[:cut], ordered[cut:]


def monthly_table(trades: list[TTFTrade]) -> list[dict]:
    if not trades:
        return []
    df = pd.DataFrame([asdict(t) for t in trades])
    df["month"] = pd.to_datetime(df["exit_time"]).dt.strftime("%Y-%m")
    out = []
    for month, g in df.groupby("month"):
        out.append(
            {
                "month": month,
                "trades": len(g),
                "win_rate_pct": round(float((g["net_r"] > 0).mean() * 100.0), 1),
                "total_r": round(float(g["net_r"].sum()), 2),
            }
        )
    return out


# Binance Futures exchangeInfo 2026-11-01: min notional USD / quantity step.
SYMBOL_FILTERS = {
    "BTCUSDT": (50.0, 0.001),
    "ETHUSDT": (20.0, 0.001),
    "LINKUSDT": (20.0, 0.01),
    "SOLUSDT": (5.0, 0.01),
    "XRPUSDT": (5.0, 0.1),
    "DOGEUSDT": (5.0, 1.0),
    "ADAUSDT": (5.0, 1.0),
    "BNBUSDT": (5.0, 0.01),
}


def size_account_trade(
    trade: TTFTrade, equity: float, params: TTFBacktestParams
) -> tuple[float, str]:
    """NON-shadow risk_engine sizing with immutable offline, per-symbol filters.

    The runtime method is Config-bound; never patch global live Config for a report.
    Quantity precision is rounded DOWN, then minimum notional is checked again.
    """
    filters = SYMBOL_FILTERS.get(trade.symbol)
    if filters is None:
        return 0.0, "UNKNOWN_SYMBOL"
    minimum, step = filters
    entry, distance = trade.entry_price, abs(trade.entry_price - trade.stop_loss)
    if not all(
        math.isfinite(v) and v > 0
        for v in (equity, entry, distance, params.risk_per_trade_pct)
    ):
        return 0.0, "INVALID_INPUT_-2"
    lev = max(1, int(params.leverage))
    fraction = params.max_margin_percent
    if fraction > 1:
        fraction /= 100
    cap = equity * fraction * lev
    budget = equity * params.risk_per_trade_pct / 100
    if params.max_risk_usd > 0:
        budget = min(budget, params.max_risk_usd)
    amount = budget / distance
    if cap > 0:
        amount = min(amount, cap / entry)
    if amount * entry < minimum:
        if cap > 0 and minimum > cap:
            return 0.0, "MIN_MARGIN_-6"
        if equity * lev < minimum:
            return 0.0, "MIN_NOTIONAL_-1"
        amount = minimum / entry
        if params.max_risk_usd > 0 and amount * distance > params.max_risk_usd:
            return 0.0, "MIN_RISK_-4"
    quantity = (Decimal(str(amount)) / Decimal(str(step))).to_integral_value(
        rounding=ROUND_DOWN
    ) * Decimal(str(step))
    amount = float(quantity)
    if quantity * Decimal(str(entry)) < Decimal(str(minimum)):
        return 0.0, "POST_ROUND_MIN_NOTIONAL"
    if params.max_risk_usd > 0 and amount * distance > params.max_risk_usd:
        return 0.0, "POST_ROUND_RISK_-4"
    return amount, "TAKEN"


def simulate_account(trades: Iterable[TTFTrade], params: TTFBacktestParams) -> dict:
    """Realized account equity, entry/exit fees, chronological exits before entries.

    Open positions are not marked to market: drawdown is on realized/fee equity.
    """
    equity = peak = float(params.account_balance)
    drawdown = 0.0
    active = []
    rejected = Counter()
    taken = skipped = 0
    taken_trades: list[TTFTrade] = []

    def update(change):
        nonlocal equity, peak, drawdown
        equity += change
        peak = max(peak, equity)
        if peak > 0:
            drawdown = max(drawdown, (peak - equity) / peak * 100)

    def settle(until):
        nonlocal active
        remaining = []
        for exit_time, trade, amount in sorted(active, key=lambda row: row[0]):
            if until is None or exit_time <= until:
                direction = 1 if trade.side == "BUY" else -1
                update(
                    amount * (trade.exit_price - trade.entry_price) * direction
                    - params.fee_rate * amount * trade.exit_price
                )
            else:
                remaining.append((exit_time, trade, amount))
        active = remaining

    for trade in sorted(
        trades, key=lambda t: (pd.Timestamp(t.entry_time), t.symbol, t.side)
    ):
        settle(pd.Timestamp(trade.entry_time))
        if len(active) >= params.max_open_trades:
            skipped += 1
            continue
        amount, reason = size_account_trade(trade, equity, params)
        if not amount:
            rejected[reason] += 1
            continue
        update(-params.fee_rate * amount * trade.entry_price)
        active.append((pd.Timestamp(trade.exit_time), trade, amount))
        taken += 1
        taken_trades.append(trade)
    settle(None)
    margin = (
        params.max_margin_percent / 100
        if params.max_margin_percent > 1
        else params.max_margin_percent
    )
    capacity = (
        equity * max(1, params.leverage) * min(1.0, margin)
        if margin > 0
        else equity * max(1, params.leverage)
    )
    return {
        "start_equity": params.account_balance,
        "final_equity": equity,
        "return_pct": (equity / params.account_balance - 1) * 100,
        "max_drawdown_pct": drawdown,
        "drawdown_basis": "realized equity including entry fees",
        "trades_taken": taken,
        "untradeable_count": sum(rejected.values()),
        "untradeable_by_reason": dict(rejected),
        "skipped_by_concurrency": skipped,
        "taken_trades": taken_trades,
        "ruined": capacity < min(v[0] for v in SYMBOL_FILTERS.values()),
    }


def preregistered_gate(summary: dict, account: dict) -> str:
    """PASS iff >=200 trades, positive net expectancy/return, PF >=1.1."""
    if summary["trades"] < 200:
        return "MUESTRA_INSUFICIENTE"
    pf = summary.get("profit_factor")
    if (
        summary.get("expectancy_r", 0) > 0
        and (pf is None or pf >= 1.1)
        and account["return_pct"] > 0
    ):
        return "PASS"
    return "SIN_EDGE"


def build_report(all_trades: list[TTFTrade], params: TTFBacktestParams) -> dict:
    first, second = split_chronological(all_trades)
    per_symbol = {}
    for sym in sorted({t.symbol for t in all_trades}):
        per_symbol[sym] = summarize(
            [t for t in all_trades if t.symbol == sym], params.risk_per_trade_pct
        )
    account = simulate_account(all_trades, params)
    account.pop("taken_trades", None)  # report stays JSON-plain
    overall = summarize(all_trades, params.risk_per_trade_pct)
    gate_summary = dict(overall)
    if all_trades:
        # Gate uses unrounded measurements, not presentation-rounded metrics.
        net = [t.net_r for t in all_trades]
        loss = -sum(v for v in net if v < 0)
        gate_summary.update(
            expectancy_r=sum(net) / len(net),
            profit_factor=sum(v for v in net if v > 0) / loss if loss else None,
        )
    return {
        "params": asdict(params),
        "account_profile": account,
        "preregistered_gate": preregistered_gate(gate_summary, account),
        "overall": overall,
        "first_70pct": summarize(first, params.risk_per_trade_pct),
        "last_30pct": summarize(second, params.risk_per_trade_pct),
        "per_symbol": per_symbol,
        "monthly": monthly_table(all_trades),
        "assumptions": [
            "Solo velas cerradas; entrada en la apertura del marco gatillo siguiente.",
            "SL/TP replicados de core/trade_entry.py (rama triple_tf).",
            "SL y TP en la misma vela = SL.",
            "Trailing EMA50 al cierre del marco gatillo si trailing_enabled; sin degradación ni vetos extra de core/signals/filters.py.",
            "Resultados en R netos de comisiones y deslizamiento.",
        ],
    }


def print_report(report: dict) -> None:
    def line(label: str, s: dict) -> str:
        if not s.get("trades"):
            return f"{label:<14} sin operaciones"
        pf = s["profit_factor"]
        return (
            f"{label:<14} trades={s['trades']:<5} WR={s['win_rate_pct']:>5.1f}%  "
            f"E={s['expectancy_r']:+.3f}R  PF={pf if pf is not None else 'inf'}  "
            f"totalR={s['total_r']:+.1f}  maxDD={s['max_drawdown_r']:.1f}R  "
            f"coste={s['avg_cost_r']:.2f}R  -> {s['verdict']}"
        )

    print("\n=== Backtest Triple Timeframe ===")
    print(line("TOTAL", report["overall"]))
    print(line("Primer 70%", report["first_70pct"]))
    print(line("Último 30%", report["last_30pct"]))
    print("\nPor símbolo:")
    for sym, s in report["per_symbol"].items():
        print("  " + line(sym, s))
    ov = report["overall"]
    if ov.get("trades"):
        print(f"\nSalidas: {ov['exit_reasons']}")
        print(f"Por lado: {ov['by_side']}")
        print(
            f"Riesgo medio por operación: {ov['avg_risk_pct']:.2f}% del precio | "
            f"Retorno aprox. cuenta con {report['params']['risk_per_trade_pct']}% de riesgo: "
            f"{ov['approx_account_return_pct']:+.1f}% (maxDD aprox. {ov['approx_account_max_dd_pct']:.1f}%)"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Gate pre-registrado (use --start/--end para holdout): PASS solo con expectancy neta > 0, trades >= 200, PF >= 1.1 y retorno de cuenta > 0; si no SIN_EDGE, o MUESTRA_INSUFICIENTE con < 200 trades. verdict legacy se conserva.",
    )
    parser.add_argument(
        "--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    )
    parser.add_argument("--start", default=None, help="Mes inicial YYYY-MM")
    parser.add_argument("--end", default=None, help="Mes final YYYY-MM")
    parser.add_argument(
        "--csv",
        nargs="*",
        type=Path,
        default=None,
        help="Archivos CSV/parquet 1M propios (uno por símbolo; nombre = símbolo)",
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--out", type=Path, default=Path("reports/ttf_backtest"))
    parser.add_argument(
        "--fee", type=float, default=0.0005, help="Comisión por lado (0.0005 = 0.05%%)"
    )
    parser.add_argument(
        "--slippage", type=float, default=0.0005, help="Deslizamiento por lado"
    )
    parser.add_argument("--spread", type=float, default=0.0)
    parser.add_argument("--breakeven-at-r", type=float, default=None)
    parser.add_argument("--max-hold-minutes", type=int, default=None)
    parser.add_argument("--tf-bias", default="1h", help="Marco sesgo (default 1h)")
    parser.add_argument(
        "--tf-struct",
        default="5min",
        help="Marco estructura (default 5min; 15min usa edad 60min)",
    )
    parser.add_argument(
        "--tf-trigger", default="1min", help="Marco gatillo y trailing (default 1min)"
    )
    parser.add_argument(
        "--max-setup-minutes",
        type=int,
        default=None,
        help="Override edad setup (default runtime; 60 en 15min)",
    )
    parser.add_argument(
        "--trailing-enabled",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Trailing EMA50 al cierre (default activo)",
    )
    parser.add_argument("--account-balance", type=float, default=20.0)
    parser.add_argument("--leverage", type=int, default=10)
    parser.add_argument("--max-margin-percent", type=float, default=5.0)
    parser.add_argument("--risk-per-trade-percent", type=float, default=1.2)
    parser.add_argument("--max-risk-usd", type=float, default=2.0)
    parser.add_argument("--max-open-trades", type=int, default=3)
    args = parser.parse_args(argv)
    for name in ("tf_bias", "tf_struct", "tf_trigger"):
        value = getattr(args, name)
        try:
            delta = pd.Timedelta(value)
            if (
                delta < pd.Timedelta(minutes=1)
                or delta.value % pd.Timedelta(minutes=1).value
            ):
                raise ValueError("must be whole minutes >=1")
        except ValueError as exc:
            parser.error(f"--{name.replace('_', '-')}: {exc}")
    if (
        args.account_balance <= 0
        or args.leverage < 1
        or args.max_open_trades < 1
        or args.risk_per_trade_percent <= 0
    ):
        parser.error("balance/risk must be positive; leverage and max-open-trades >=1")

    params = TTFBacktestParams(
        fee_rate=args.fee,
        slippage_pct=args.slippage,
        spread_pct=args.spread,
        breakeven_at_r=args.breakeven_at_r,
        max_hold_minutes=args.max_hold_minutes,
        tf_bias=args.tf_bias,
        tf_struct=args.tf_struct,
        tf_trigger=args.tf_trigger,
        max_setup_minutes=args.max_setup_minutes,
        trailing_enabled=args.trailing_enabled,
        account_balance=args.account_balance,
        leverage=args.leverage,
        max_margin_percent=args.max_margin_percent,
        risk_per_trade_pct=args.risk_per_trade_percent,
        max_risk_usd=args.max_risk_usd,
        max_open_trades=args.max_open_trades,
    )

    datasets: dict[str, pd.DataFrame] = {}
    if args.csv:
        for path in args.csv:
            candles = load_candles_file(path)
            if args.start:
                candles = candles[candles["time"] >= pd.Timestamp(args.start, tz="UTC")]
            if args.end:
                end_exclusive = pd.Timestamp(
                    args.end, tz="UTC"
                ) + pd.offsets.MonthBegin(1)
                candles = candles[candles["time"] < end_exclusive]
            datasets[path.stem.split("-")[0].upper()] = candles
    else:
        today = pd.Timestamp.now(tz="UTC")
        end = args.end or str((today - pd.offsets.MonthBegin(1)).to_period("M") - 1)
        start = args.start or str(pd.Period(end, "M") - 11)
        print(f"Descargando velas 1M {start} → {end}", file=sys.stderr)
        for sym in args.symbols:
            datasets[sym] = load_symbol_candles(sym, start, end, args.cache_dir)

    all_trades: list[TTFTrade] = []
    for sym, df in datasets.items():
        print(f"Simulando {sym} ({len(df):,} velas 1M)…", file=sys.stderr)
        all_trades.extend(backtest_symbol(sym, df, params))

    report = build_report(all_trades, params)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    pd.DataFrame([asdict(t) for t in all_trades]).to_csv(
        args.out / "trades.csv", index=False
    )
    print_report(report)
    print(f"\nDetalle guardado en {args.out}/summary.json y {args.out}/trades.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
