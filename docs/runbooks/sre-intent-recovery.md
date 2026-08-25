# Sniper SRE Runbook: Intent Recovery and Temporal Reliability

## Scope

This runbook defines production operations for:

- temporal invariance (`monotonic` runtime + `UTC` persisted state),
- stale intent cleanup (`PENDING_SEND`),
- manual unblock (`/force_clear`),
- dynamic tuning of `PENDING_SEND_STALE_SECONDS`.

## SLI/SLO and Alert Thresholds

Primary reliability SLI:

- `IntentExpiryRatio = INTENT_EXPIRED / ENTRY_ORDER_ACK`

Windowing:

- compute over rolling 1h and 24h windows.

SLO targets:

- healthy: `IntentExpiryRatio < 0.5%`
- warning: `0.5% <= ratio < 1.0%`
- critical: `ratio >= 1.0%`

Guardrails:

- if `ENTRY_ORDER_ACK < 20` in window, treat as low-sample and do not page on ratio alone,
- page only when ratio breach is sustained for 2 consecutive windows (1h x2),
- always page if `INTENT_EXPIRED >= 5` in 10 minutes.

Operational interpretation:

- ratio increase with normal exchange latency usually indicates network instability or API contention,
- ratio increase with high volatility may require stale-window widening.

## How to Measure Quickly

Source: `logs/execution_events.jsonl`.

Example (last 24h) using Python:

```bash
python - <<'PY'
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

path = Path("logs/execution_events.jsonl")
cut = datetime.now(timezone.utc) - timedelta(hours=24)
ack = exp = 0
for line in path.read_text(encoding="utf-8").splitlines():
    try:
        row = json.loads(line)
        ts = datetime.fromisoformat(row.get("ts"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cut:
            continue
        ev = row.get("event")
        if ev == "ENTRY_ORDER_ACK":
            ack += 1
        elif ev == "INTENT_EXPIRED":
            exp += 1
    except Exception:
        pass

ratio = (exp / ack * 100.0) if ack else 0.0
print(f"ENTRY_ORDER_ACK={ack} INTENT_EXPIRED={exp} ratio={ratio:.2f}%")
PY
```

## Manual Unblock Procedure (`/force_clear`)

Purpose:

- release a symbol stuck in `RECOVERY_PENDING_STATE` when reconciliation cannot clear it.

Command:

- `/force_clear BTC/USDT`

Safety contract implemented by command handler:

- checks open orders for symbol,
- checks by `entry_client_order_id` when available,
- checks live position contracts,
- clears local+DB state only when no exchange evidence exists.

If exchange evidence exists, command aborts and instructs operator to reconcile (no destructive clear).

Escalation sequence:

1. wait one reconciliation cycle,
2. run `/force_clear <SYMBOL>`,
3. if still blocked and exchange has order/position evidence, escalate as exchange-sync incident; do not force-delete DB rows manually.

## Dynamic Tuning: `PENDING_SEND_STALE_SECONDS`

Default:

- `90` seconds.

When to widen (reduce false positives):

- high market stress (rapid volatility expansion),
- exchange latency spike,
- elevated websocket reconnect churn.

Recommended profile:

- normal conditions: `90s`
- elevated volatility or intermittent API delays: `120-150s`
- severe stress window: `180s` (temporary only)

When to tighten:

- stable latency and low volatility for >= 24h,
- `IntentExpiryRatio < 0.3%` sustained.

Change process:

1. set env var `PENDING_SEND_STALE_SECONDS` in deployment config,
2. restart bot service,
3. monitor 1h `IntentExpiryRatio` and reject count,
4. keep rollback note to previous value.

## Incident Classification

- SEV-3: ratio warning (`>=0.5%`), no active trade impact,
- SEV-2: ratio critical (`>=1%`) with repeated `RECOVERY_PENDING_STATE` blocks,
- SEV-1: persistent stale-intent churn plus inability to open real trades.

## Non-Negotiable Rules

- do not edit SQLite rows manually during live operation,
- use `/force_clear` or reconciliation only,
- keep persisted state in UTC and runtime intervals in monotonic time.
