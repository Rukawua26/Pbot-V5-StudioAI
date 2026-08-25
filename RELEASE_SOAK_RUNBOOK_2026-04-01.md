# Release Soak Runbook - 2026-04-01

## Preconditions

- Branch: `freeze/2026-04-01-api-weight-stability`
- API credentials set in environment or `.env`
- Paper mode enabled

## 1) Preflight

```bash
git branch --show-current
python -m py_compile main.py core/api_weight_tracker.py core/execution_service.py core/data_service.py
python - <<'PY'
import os
required = ["BINANCE_API_KEY", "BINANCE_API_SECRET"]
missing = [k for k in required if not os.getenv(k)]
print("MISSING:", ", ".join(missing) if missing else "none")
PY
```

## 2) Run 30-min paper soak

```bash
PAPER_MODE=true USE_TESTNET=true ENABLE_UI=false python main.py
```

Let it run 20-30 minutes.

## 3) Live checks during soak

Watch for these lines in logs:

- `API Weight (1 min):`
- `API Usage:`
- `Saltando refresh mercado por presión de API Weight`
- `Error recuperado:` (occasional is acceptable, persistent is not)

## 4) Pass / fail criteria

Pass if all are true:

- Bot loop stays alive for full soak window.
- No uncaught fatal crash.
- API usage remains mostly below emergency.
- When pressure increases, non-essential calls are skipped.
- No repeated reconnect storm.

Fail if any occurs:

- Process exits unexpectedly.
- API usage remains pinned near limit without recovery.
- Repeated hard failures in order/account endpoints.

## 5) Go / no-go

- GO: pass all criteria, then promote to controlled real-mode window.
- NO-GO: keep in paper mode and inspect error clusters first.
