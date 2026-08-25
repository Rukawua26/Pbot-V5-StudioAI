#!/usr/bin/env python3
"""Reporte de checklist 24h para Sniper AI.

Métricas obligatorias:
- Memory Leak Test (h1 vs h24)
- Latencia Smart Exit (<450ms)
- Win Rate 24h (shadow/real)
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


LATENCY_RE = re.compile(
    r"SMART_EXIT_LATENCY\s+(?P<symbol>\S+)\s+.*total_ms=(?P<total>[0-9]+\.?[0-9]*)"
)


def load_runtime_metrics(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def parse_latency(log_path: Path) -> list[float]:
    if not log_path.exists():
        return []
    vals: list[float] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LATENCY_RE.search(line)
        if not m:
            continue
        vals.append(float(m.group("total")))
    return vals


def db_wr_24h(db_path: Path) -> dict:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    since = (datetime.now() - timedelta(hours=24)).isoformat()
    c.execute(
        """
        SELECT
            COUNT(*) total,
            SUM(CASE WHEN pnl_percent > 0 THEN 1 ELSE 0 END) wins,
            SUM(CASE WHEN is_shadow = 1 THEN 1 ELSE 0 END) shadow_total,
            SUM(CASE WHEN is_shadow = 1 AND pnl_percent > 0 THEN 1 ELSE 0 END) shadow_wins,
            SUM(CASE WHEN is_shadow = 0 THEN 1 ELSE 0 END) real_total,
            SUM(CASE WHEN is_shadow = 0 AND pnl_percent > 0 THEN 1 ELSE 0 END) real_wins
        FROM trades
        WHERE timestamp >= ?
          AND pnl_percent IS NOT NULL
        """,
        (since,),
    )
    row = dict(c.fetchone())
    conn.close()

    def rate(wins: int | None, total: int | None) -> float:
        w = wins or 0
        t = total or 0
        return (w / t) * 100.0 if t else 0.0

    row["wr_total"] = rate(row.get("wins"), row.get("total"))
    row["wr_shadow"] = rate(row.get("shadow_wins"), row.get("shadow_total"))
    row["wr_real"] = rate(row.get("real_wins"), row.get("real_total"))
    row["since"] = since
    return row


def summarize_runtime(metrics: list[dict]) -> dict:
    if not metrics:
        return {}

    rss_values = [float(m.get("rss_mb", 0.0)) for m in metrics]
    cpu_values = [float(m.get("cpu_pct", 0.0)) for m in metrics]
    busy_values = [float(m.get("guardian_busy_pct", 0.0)) for m in metrics]

    h1 = next((m for m in metrics if float(m.get("uptime_s", 0.0)) >= 3600), None)
    h24 = next((m for m in metrics if float(m.get("uptime_s", 0.0)) >= 86400), None)

    return {
        "samples": len(metrics),
        "rss_start": rss_values[0],
        "rss_last": rss_values[-1],
        "rss_max": max(rss_values),
        "cpu_avg": sum(cpu_values) / max(len(cpu_values), 1),
        "cpu_max": max(cpu_values),
        "guardian_busy_avg": sum(busy_values) / max(len(busy_values), 1),
        "guardian_busy_max": max(busy_values),
        "h1_rss": float(h1.get("rss_mb")) if h1 else None,
        "h24_rss": float(h24.get("rss_mb")) if h24 else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reporte 24h Sniper AI")
    parser.add_argument("--root", default=".", help="Ruta raíz del bot")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    metrics_path = root / "logs" / "runtime_metrics.jsonl"
    log_path = root / "sniper.log"
    db_path = root / "sniper_brain.db"

    metrics = load_runtime_metrics(metrics_path)
    runtime = summarize_runtime(metrics)
    latency = parse_latency(log_path)
    wr = db_wr_24h(db_path)

    print("=" * 72)
    print("SNIPER AI - CHECKLIST 24H")
    print("=" * 72)

    if runtime:
        print("[RUNTIME]")
        print(f"  samples: {runtime['samples']}")
        print(
            f"  rss_start: {runtime['rss_start']:.1f}MB | rss_last: {runtime['rss_last']:.1f}MB | rss_max: {runtime['rss_max']:.1f}MB"
        )
        print(
            f"  cpu_avg: {runtime['cpu_avg']:.1f}% | cpu_max: {runtime['cpu_max']:.1f}%"
        )
        print(
            f"  guardian_busy_avg: {runtime['guardian_busy_avg']:.1f}% | guardian_busy_max: {runtime['guardian_busy_max']:.1f}%"
        )
        if runtime["h1_rss"] is not None:
            print(f"  h1_rss: {runtime['h1_rss']:.1f}MB")
        else:
            print("  h1_rss: n/a (aún no cumple 1h)")
        if runtime["h24_rss"] is not None:
            print(f"  h24_rss: {runtime['h24_rss']:.1f}MB")
        else:
            print("  h24_rss: n/a (aún no cumple 24h)")
    else:
        print("[RUNTIME] sin métricas (logs/runtime_metrics.jsonl no existe)")

    if latency:
        under_450 = sum(1 for x in latency if x < 450.0)
        ratio = under_450 / len(latency) * 100.0
        print("[SMART EXIT LATENCY]")
        print(
            f"  events: {len(latency)} | min: {min(latency):.1f}ms | avg: {sum(latency)/len(latency):.1f}ms | max: {max(latency):.1f}ms"
        )
        print(f"  <450ms: {under_450}/{len(latency)} ({ratio:.1f}%)")
    else:
        print("[SMART EXIT LATENCY] sin eventos registrados")

    if wr:
        print("[WIN RATE 24H]")
        print(f"  since: {wr['since']}")
        print(
            f"  total: {wr.get('total', 0)} | wr_total: {wr.get('wr_total', 0.0):.1f}%"
        )
        print(
            f"  shadow: {wr.get('shadow_total', 0)} | wr_shadow: {wr.get('wr_shadow', 0.0):.1f}%"
        )
        print(
            f"  real: {wr.get('real_total', 0)} | wr_real: {wr.get('wr_real', 0.0):.1f}%"
        )
    else:
        print("[WIN RATE 24H] base de datos no disponible")

    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
