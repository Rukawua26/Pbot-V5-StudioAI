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
* Salidas: solo SL/TP fijos (más breakeven opcional). No simula trailing,
  salida por degradación ni los vetos extra de ``core/signals/filters.py``.
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
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from core.strategy.triple_tf.bias_1h import evaluate_bias_1h
from core.strategy.triple_tf.structure_5m import evaluate_structure_5m
from core.strategy.triple_tf.trigger_1m import evaluate_trigger_1m

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
    risk_per_trade_pct: float = field(
        default_factory=lambda: _live_default("RISK_PER_TRADE_PERCENT", 1.2)
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
) -> tuple[int, float, str, float, float]:
    """Recorre velas 1M desde la de entrada. Devuelve (idx_salida, precio, motivo, mfe, mae)."""
    direction = 1.0 if side == "BUY" else -1.0
    risk = abs(entry_price - sl)
    stop = sl
    be_armed = False
    mfe = 0.0
    mae = 0.0
    n = len(c)
    last = n - 1
    if params.max_hold_minutes:
        last = min(last, entry_idx + int(params.max_hold_minutes) - 1)
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
    df_1m = normalize_candles(df_1m)
    df_5m = resample_closed(df_1m, "5min")
    df_1h = resample_closed(df_1m, "1h")

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
    close_5m = _ns(df_5m["time"] + pd.Timedelta(minutes=5))
    close_1h = _ns(df_1h["time"] + pd.Timedelta(hours=1))
    close_1m = t1 + 60_000_000_000

    trades: list[TTFTrade] = []
    bias_cache: dict[int, object] = {}
    struct_cache: dict[tuple[int, str], object] = {}
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

        bias = bias_cache.get(n1h)
        if bias is None:
            bias = evaluate_bias_1h(df_1h.iloc[max(0, n1h - WINDOW_BARS) : n1h])
            bias_cache[n1h] = bias
            if len(bias_cache) > 100:
                bias_cache.pop(next(iter(bias_cache)))
        if bias.bias not in {"BUY", "SELL"}:
            continue

        key = (n5m, bias.bias)
        struct = struct_cache.get(key)
        if struct is None:
            struct = evaluate_structure_5m(
                df_5m.iloc[max(0, n5m - WINDOW_BARS) : n5m], bias_1h=bias.bias
            )
            struct_cache[key] = struct
            if len(struct_cache) > 200:
                struct_cache.pop(next(iter(struct_cache)))
        if not struct.valid_setup:
            continue

        trig = evaluate_trigger_1m(
            df_1m.iloc[i + 1 - WINDOW_BARS : i + 1],
            bias_1h=bias.bias,
            setup_5m_valid=True,
            spread=params.spread_pct,
        )
        if not (trig.triggered and trig.side in {"BUY", "SELL"}):
            continue

        side = trig.side
        signal_price = float(c[i])
        levels = compute_exit_levels(
            side, signal_price, float(struct.suggested_sl), params
        )
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

        exit_idx, exit_price, reason, mfe, mae = _simulate_exit(
            side, entry_idx, entry_price, sl, tp, o, h, low, c, params
        )
        gross_r = (exit_price - entry_price) * direction / risk_at_fill
        cost_r = params.fee_rate * (entry_price + exit_price) / risk_at_fill
        trades.append(
            TTFTrade(
                symbol=symbol,
                side=side,
                signal_time=str(pd.Timestamp(int(t1[i]), tz="UTC")),
                entry_time=str(pd.Timestamp(int(t1[entry_idx]), tz="UTC")),
                exit_time=str(pd.Timestamp(int(t1[exit_idx]), tz="UTC")),
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


def build_report(all_trades: list[TTFTrade], params: TTFBacktestParams) -> dict:
    first, second = split_chronological(all_trades)
    per_symbol = {}
    for sym in sorted({t.symbol for t in all_trades}):
        per_symbol[sym] = summarize(
            [t for t in all_trades if t.symbol == sym], params.risk_per_trade_pct
        )
    return {
        "params": asdict(params),
        "overall": summarize(all_trades, params.risk_per_trade_pct),
        "first_70pct": summarize(first, params.risk_per_trade_pct),
        "last_30pct": summarize(second, params.risk_per_trade_pct),
        "per_symbol": per_symbol,
        "monthly": monthly_table(all_trades),
        "assumptions": [
            "Solo velas cerradas; entrada en la apertura de la vela 1M siguiente.",
            "SL/TP replicados de core/trade_entry.py (rama triple_tf).",
            "SL y TP en la misma vela = SL.",
            "Sin trailing, sin salida por degradación, sin vetos de core/signals/filters.py.",
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
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
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
    args = parser.parse_args(argv)

    params = TTFBacktestParams(
        fee_rate=args.fee,
        slippage_pct=args.slippage,
        spread_pct=args.spread,
        breakeven_at_r=args.breakeven_at_r,
        max_hold_minutes=args.max_hold_minutes,
    )

    datasets: dict[str, pd.DataFrame] = {}
    if args.csv:
        for path in args.csv:
            datasets[path.stem.split("-")[0].upper()] = load_candles_file(path)
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
