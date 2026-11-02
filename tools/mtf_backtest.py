#!/usr/bin/env python3
"""Backtest offline de estrategias 1H/15M/5M/1M pre-registradas (MTF Pullback v2, Mean Reversion v3).

Solo lectura: no toca el runtime ni envia ordenes. Reglas pre-registradas en
``odd/tasks/mtf-pullback-v2.md``. Reutiliza de ``tools.ttf_backtest`` la carga de
velas, la simulacion de salidas (SL con gap a la apertura, TP exacto, cierre por
tiempo), las metricas y el perfil de cuenta (sizing de ``risk_engine``, minimos y
step por simbolo de Binance).

Gate pre-registrado por perfil: PASS solo si E neta > 0 R, >= 200 trades,
PF >= 1.1 y retorno USD > 0; < 200 trades = MUESTRA_INSUFICIENTE.

Uso:
    python -m tools.mtf_backtest --symbols SOLUSDT XRPUSDT --start 2025-09 --end 2026-08 \\
        --warmup-start 2025-05 --out reports/mtf/dev
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from core.strategy import mean_reversion
from core.strategy.mtf_pullback import MTFParams, build_features, signal_at
from tools.ttf_backtest import (
    DEFAULT_CACHE_DIR,
    TTFBacktestParams,
    TTFTrade,
    _month_range,
    _simulate_exit,
    download_month,
    monthly_table,
    normalize_candles,
    preregistered_gate,
    resample_closed,
    simulate_account,
    split_chronological,
    summarize,
)

PROFILES = {"usd20": 20.0, "usd100": 100.0}


@dataclass(frozen=True)
class StrategySpec:
    """How a pure strategy plugs into the shared simulation loop.

    ``target(sig, entry, risk, direction)`` returns the take-profit price.
    """

    name: str
    params: object
    build: Callable
    candidates: Callable
    signal: Callable
    target: Callable
    max_hold_minutes: int


def mtf_spec(params: MTFParams | None = None) -> StrategySpec:
    p = params or MTFParams()
    return StrategySpec(
        name="MTF_PULLBACK_V2",
        params=p,
        build=lambda *frames: build_features(*frames, p),
        candidates=lambda f: (
            f.warm & (f.ctx != 0) & (f.setup == f.ctx) & (f.trigger == f.ctx)
        ),
        signal=lambda f, i, sym: signal_at(f, i, p, sym),
        target=lambda sig, entry, risk, d: entry + d * p.take_profit_r * risk,
        max_hold_minutes=p.max_hold_minutes,
    )


def mr_spec(params: mean_reversion.MRParams | None = None) -> StrategySpec:
    p = params or mean_reversion.MRParams()
    return StrategySpec(
        name="MEAN_REVERSION_V3",
        params=p,
        build=lambda *frames: mean_reversion.build_features(*frames, p),
        candidates=lambda f: mean_reversion.candidate_mask(f, p),
        signal=lambda f, i, sym: mean_reversion.signal_at(f, i, p, sym),
        # Rule 6: fixed target = middle band of the stretch bar.
        target=lambda sig, entry, risk, d: sig.target,
        max_hold_minutes=p.max_hold_minutes,
    )


STRATEGIES = {"mtf": mtf_spec, "mr": mr_spec}
PARTIAL_SUFFIX = "-partial"


def load_candles(symbol: str, start: str, end: str, cache_dir: Path) -> pd.DataFrame:
    """Monthly archives; a missing month falls back to ``<SYM>-1m-<YYYY-MM>-partial.csv``."""
    frames = []
    for month in _month_range(start, end):
        df = download_month(symbol, month, cache_dir)
        if df is None:
            partial = cache_dir / f"{symbol}-1m-{month}{PARTIAL_SUFFIX}.csv"
            df = pd.read_csv(partial) if partial.exists() else None
        if df is None or df.empty:
            print(f"  ! {symbol} {month}: sin datos", file=sys.stderr)
            continue
        frames.append(df)
    if not frames:
        raise RuntimeError(f"Sin datos para {symbol} {start}..{end}")
    return normalize_candles(pd.concat(frames, ignore_index=True))


def exit_params(spec, base: TTFBacktestParams) -> TTFBacktestParams:
    # Rule 6/8: fixed SL/TP, time exit, no trailing/breakeven; 1M trigger timeframe.
    return replace(
        base,
        trailing_enabled=False,
        breakeven_at_r=None,
        max_hold_minutes=spec.max_hold_minutes,
        tf_trigger="1min",
    )


def backtest_symbol(
    symbol: str,
    df_1m: pd.DataFrame,
    mtf: MTFParams | StrategySpec | None = None,
    base: TTFBacktestParams | None = None,
    trade_start: pd.Timestamp | None = None,
    trade_end: pd.Timestamp | None = None,
) -> list[TTFTrade]:
    """Trades whose signal bar closes in [trade_start, trade_end). Earlier bars are warmup."""
    spec = mtf if isinstance(mtf, StrategySpec) else mtf_spec(mtf)
    p = exit_params(spec, base or TTFBacktestParams())
    df_1m = normalize_candles(df_1m)
    if df_1m.empty:
        return []
    feat = spec.build(
        resample_closed(df_1m, "1h"),
        resample_closed(df_1m, "15min"),
        resample_closed(df_1m, "5min"),
        df_1m,
    )
    t1 = feat.close_time_ns - pd.Timedelta("1min").value  # 1M open times
    o = df_1m["open"].to_numpy(float)
    h = df_1m["high"].to_numpy(float)
    low = df_1m["low"].to_numpy(float)
    c = df_1m["close"].to_numpy(float)
    lo_ns = trade_start.value if trade_start is not None else np.iinfo(np.int64).min
    hi_ns = trade_end.value if trade_end is not None else np.iinfo(np.int64).max

    candidates = np.where(spec.candidates(feat))[0]
    used_setups: set[tuple] = set()
    trades: list[TTFTrade] = []
    next_free = 0
    n = len(c)
    for i in candidates:
        if i < next_free or i >= n - 1:
            continue
        if not lo_ns <= feat.close_time_ns[i] < hi_ns:
            continue
        sig = spec.signal(feat, int(i), symbol)
        if sig.side not in {"BUY", "SELL"} or sig.setup_id in used_setups:
            continue
        direction = 1.0 if sig.side == "BUY" else -1.0
        entry_idx = int(i) + 1
        entry = float(o[entry_idx]) * (1.0 + direction * p.slippage_pct)
        risk = (entry - sig.stop) * direction
        if risk <= 0:
            continue  # next open already beyond the stop: invalid entry
        tp = float(spec.target(sig, entry, risk, direction))
        if (tp - entry) * direction <= 0:
            continue  # next open already beyond the target: nothing to capture
        used_setups.add(sig.setup_id)
        exit_idx, exit_price, reason, mfe, mae = _simulate_exit(
            sig.side, entry_idx, entry, sig.stop, tp, o, h, low, c, p
        )
        gross = (exit_price - entry) * direction / risk
        cost = p.fee_rate * (entry + exit_price) / risk
        exit_ns = (
            feat.close_time_ns[exit_idx]
            if reason in {"TIME", "END_OF_DATA"}
            else t1[exit_idx]
        )
        trades.append(
            TTFTrade(
                symbol=symbol,
                side=sig.side,
                signal_time=str(pd.Timestamp(int(t1[i]), tz="UTC")),
                entry_time=str(pd.Timestamp(int(t1[entry_idx]), tz="UTC")),
                exit_time=str(pd.Timestamp(int(exit_ns), tz="UTC")),
                signal_price=sig.entry_ref,
                entry_price=entry,
                stop_loss=float(sig.stop),
                take_profit=float(tp),
                exit_price=float(exit_price),
                exit_reason=reason,
                risk_pct=float(risk / entry * 100.0),
                gross_r=float(gross),
                cost_r=float(cost),
                net_r=float(gross - cost),
                bars_held=int(exit_idx - entry_idx + 1),
                mfe_r=float(mfe),
                mae_r=float(mae),
            )
        )
        next_free = exit_idx + 1
    return trades


def build_report(
    trades: list[TTFTrade],
    base: TTFBacktestParams,
    mtf: MTFParams | StrategySpec | None = None,
) -> dict:
    spec = mtf if isinstance(mtf, StrategySpec) else mtf_spec(mtf)
    first, second = split_chronological(trades)
    overall = summarize(trades, base.risk_per_trade_pct)
    profiles = {}
    for name, balance in PROFILES.items():
        params = replace(base, account_balance=balance)
        account = simulate_account(trades, params)
        # The gate is evaluated on the trades the profile could actually take.
        taken = account.pop("taken_trades", None)
        tradeable = summarize(
            taken if taken is not None else trades, base.risk_per_trade_pct
        )
        profiles[name] = {
            "account": account,
            "tradeable_summary": tradeable,
            "preregistered_gate": preregistered_gate(tradeable, account)
            if tradeable.get("trades")
            else "MUESTRA_INSUFICIENTE",
        }
    return {
        "strategy": spec.name,
        "strategy_params": asdict(spec.params),
        "cost_params": {"fee_rate": base.fee_rate, "slippage_pct": base.slippage_pct},
        "overall": overall,
        "first_70pct": summarize(first, base.risk_per_trade_pct),
        "last_30pct": summarize(second, base.risk_per_trade_pct),
        "per_symbol": {
            s: summarize([t for t in trades if t.symbol == s], base.risk_per_trade_pct)
            for s in sorted({t.symbol for t in trades})
        },
        "monthly": monthly_table(trades),
        "profiles": profiles,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True, help="Primer mes con trades YYYY-MM")
    parser.add_argument("--end", required=True, help="Ultimo mes con trades YYYY-MM")
    parser.add_argument(
        "--warmup-start",
        required=True,
        help="Primer mes cargado solo como calentamiento",
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--strategy",
        choices=sorted(STRATEGIES),
        default="mtf",
        help="mtf = MTF Pullback v2 (default), mr = Mean Reversion v3",
    )
    args = parser.parse_args(argv)

    base, mtf = TTFBacktestParams(), STRATEGIES[args.strategy]()
    trade_start = pd.Timestamp(args.start, tz="UTC")
    trade_end = pd.Timestamp(args.end, tz="UTC") + pd.offsets.MonthBegin(1)
    trades: list[TTFTrade] = []
    for sym in args.symbols:
        df = load_candles(sym, args.warmup_start, args.end, args.cache_dir)
        print(f"Simulando {sym} ({len(df):,} velas 1M)", file=sys.stderr)
        trades.extend(backtest_symbol(sym, df, mtf, base, trade_start, trade_end))

    report = build_report(trades, base, mtf)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    pd.DataFrame([asdict(t) for t in trades]).to_csv(
        args.out / "trades.csv", index=False
    )
    o = report["overall"]
    print(
        json.dumps(
            {
                k: o.get(k)
                for k in (
                    "trades",
                    "win_rate_pct",
                    "expectancy_r",
                    "gross_expectancy_r",
                    "profit_factor",
                    "avg_cost_r",
                    "exit_reasons",
                )
            }
        )
    )
    for name, prof in report["profiles"].items():
        a = prof["account"]
        print(
            name,
            prof["preregistered_gate"],
            json.dumps(
                {
                    "trades": prof["tradeable_summary"].get("trades"),
                    "E": prof["tradeable_summary"].get("expectancy_r"),
                    "final": round(a["final_equity"], 2),
                    "ret%": round(a["return_pct"], 2),
                    "dd%": round(a["max_drawdown_pct"], 2),
                    "rejected": a["untradeable_by_reason"],
                }
            ),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
