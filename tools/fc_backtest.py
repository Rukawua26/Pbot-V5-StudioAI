#!/usr/bin/env python3
"""Backtest offline de Funding-Rate Contrarian v5."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from core.strategy.funding_contrarian import FCParams, build_features, signal_at
from tools.mtf_backtest import (
    PROFILES,
    load_candles as _load,
    TTFBacktestParams,
    TTFTrade,
    _month_range,
    _simulate_exit,
    build_report,
    download_month,
    normalize_candles,
    preregistered_gate,
    replace,
    resample_closed,
    simulate_account,
    monthly_table,
    split_chronological,
    summarize,
)

FUNDING_CACHE = Path("data/funding_cache")


def fetch_funding(symbol: str, start: str, end: str, cache_dir: Path = FUNDING_CACHE) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{symbol}-funding-{start}-{end}.csv"
    if cache_file.exists():
        return pd.read_csv(cache_file)
    # Binance funding rate history (max 1000 per call)
    all_rows = []
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000) + 86400000
    cursor = start_ms
    while cursor < end_ms:
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&startTime={cursor}&limit=1000"
        with urllib.request.urlopen(url, timeout=30) as r:
            data = __import__("json").loads(r.read())
        if not data:
            break
        all_rows.extend(data)
        cursor = int(data[-1]["fundingTime"]) + 1
        time.sleep(0.2)
    df = pd.DataFrame(all_rows)
    if not df.empty:
        df.to_csv(cache_file, index=False)
    return df


def load_candles(symbol, start, end, cache_dir):
    from tools.ttf_backtest import load_symbol_candles
    return load_symbol_candles(symbol, start, end, cache_dir)


def backtest_symbol(symbol, df_1m, fc_params=None, base=None, trade_start=None, trade_end=None):
    fc_params = fc_params or FCParams()
    base = base or TTFBacktestParams()
    df_1h = resample_closed(normalize_candles(df_1m), "1h")
    funding_df = fetch_funding(symbol, trade_start.strftime("%Y-%m") if trade_start else "2025-08",
                               trade_end.strftime("%Y-%m") if trade_end else "2026-09")
    feat = build_features(df_1h, funding_df, fc_params)
    close = df_1h["close"].astype(float).to_numpy()
    # 1H bars
    o = df_1h["open"].to_numpy(float)
    h = df_1h["high"].to_numpy(float)
    low = df_1h["low"].to_numpy(float)
    c = close
    # map 1H signal to entry at next 1H open
    lo_ns = trade_start.value if trade_start is not None else np.iinfo(np.int64).min
    hi_ns = trade_end.value if trade_end is not None else np.iinfo(np.int64).max
    close_ns = feat.close_time_ns
    trades = []
    next_free = 0
    used = set()
    n = len(c)
    for i in range(fc_params.atr_period_1h + 1, n - 1):
        if i < next_free:
            continue
        if not lo_ns <= close_ns[i] < hi_ns:
            continue
        sig = signal_at(feat, i, fc_params, symbol)
        if sig.side not in {"BUY", "SELL"} or sig.setup_id in used:
            continue
        direction = 1.0 if sig.side == "BUY" else -1.0
        entry_idx = i + 1
        entry = float(o[entry_idx]) * (1.0 + direction * base.slippage_pct)
        risk = (entry - sig.stop) * direction
        if risk <= 0:
            continue
        tp = sig.target
        if (tp - entry) * direction <= 0:
            continue
        used.add(sig.setup_id)
        # simulate on 1H bars
        exit_idx = entry_idx
        exit_price = entry
        reason = "END_OF_DATA"
        mfe = mae = 0.0
        last = min(n - 1, entry_idx + fc_params.max_hold_hours - 1)
        for j in range(entry_idx, last + 1):
            hi_, lo_ = h[j], low[j]
            fav = (hi_ - entry) if direction > 0 else (entry - lo_)
            adv = (entry - lo_) if direction > 0 else (hi_ - entry)
            mfe = max(mfe, fav / risk)
            mae = max(mae, adv / risk)
            hit_sl = (lo_ <= sig.stop) if direction > 0 else (hi_ >= sig.stop)
            hit_tp = (hi_ >= tp) if direction > 0 else (lo_ <= tp)
            if hit_sl:
                gap = o[j] if (o[j] < sig.stop if direction > 0 else o[j] > sig.stop) else sig.stop
                exit_price = gap * (1.0 - direction * base.slippage_pct)
                exit_idx = j
                reason = "SL"
                break
            if hit_tp:
                exit_price = tp
                exit_idx = j
                reason = "TP"
                break
        else:
            exit_price = c[last] * (1.0 - direction * base.slippage_pct)
            exit_idx = last
            reason = "TIME" if last < n - 1 else "END_OF_DATA"
        gross = (exit_price - entry) * direction / risk
        cost = base.fee_rate * (entry + exit_price) / risk
        trades.append(TTFTrade(
            symbol=symbol, side=sig.side,
            signal_time=str(pd.Timestamp(int(feat.close_time_ns[i]), tz="UTC")),
            entry_time=str(pd.Timestamp(int(feat.close_time_ns[entry_idx]), tz="UTC")),
            exit_time=str(pd.Timestamp(int(feat.close_time_ns[exit_idx]), tz="UTC")),
            signal_price=sig.entry_ref, entry_price=entry,
            stop_loss=float(sig.stop), take_profit=float(tp),
            exit_price=float(exit_price), exit_reason=reason,
            risk_pct=float(risk / entry * 100.0),
            gross_r=float(gross), cost_r=float(cost), net_r=float(gross - cost),
            bars_held=int(exit_idx - entry_idx + 1), mfe_r=float(mfe), mae_r=float(mae),
        ))
        next_free = exit_idx + 1
    return trades


def build_report(trades, base):
    first, second = split_chronological(trades)
    overall = summarize(trades, base.risk_per_trade_pct)
    profiles = {}
    for name, balance in PROFILES.items():
        params = replace(base, account_balance=balance)
        account = simulate_account(trades, params)
        taken = account.pop("taken_trades", None)
        tradeable = summarize(taken if taken is not None else trades, base.risk_per_trade_pct)
        profiles[name] = {
            "account": account,
            "tradeable_summary": tradeable,
            "preregistered_gate": preregistered_gate(tradeable, account) if tradeable.get("trades") else "MUESTRA_INSUFICIENTE",
        }
    return {
        "strategy": "FUNDING_CONTRARIAN_V5",
        "cost_params": {"fee_rate": base.fee_rate, "slippage_pct": base.slippage_pct},
        "overall": overall,
        "first_70pct": summarize(first, base.risk_per_trade_pct),
        "last_30pct": summarize(second, base.risk_per_trade_pct),
        "per_symbol": {s: summarize([t for t in trades if t.symbol == s], base.risk_per_trade_pct) for s in sorted({t.symbol for t in trades})},
        "monthly": monthly_table(trades),
        "profiles": profiles,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--warmup-start", required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("data/ttf_backtest"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    base = TTFBacktestParams()
    trade_start = pd.Timestamp(args.start, tz="UTC")
    trade_end = pd.Timestamp(args.end, tz="UTC") + pd.offsets.MonthBegin(1)
    trades = []
    for sym in args.symbols:
        df = _load(sym, args.warmup_start, args.end, args.cache_dir)
        print(f"Simulando {sym} ({len(df):,} velas)", file=__import__("sys").stderr)
        trades.extend(backtest_symbol(sym, df, FCParams(), base, trade_start, trade_end))
    report = build_report(trades, base)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    pd.DataFrame([asdict(t) for t in trades]).to_csv(args.out / "trades.csv", index=False)
    o = report["overall"]
    print(json.dumps({k: o.get(k) for k in ("trades", "win_rate_pct", "expectancy_r", "gross_expectancy_r", "profit_factor", "avg_cost_r", "exit_reasons")}))
    for name, prof in report["profiles"].items():
        a = prof["account"]; t = prof["tradeable_summary"]
        print(name, prof["preregistered_gate"], json.dumps({"trades": t.get("trades"), "E": t.get("expectancy_r"), "final": round(a["final_equity"], 2), "ret%": round(a["return_pct"], 2)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
