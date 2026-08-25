# Release Freeze Report - 2026-04-01

## Scope

- Binance API weight tracking integration end-to-end.
- Service-layer unification for exchange access from `main.py`.
- Protective throttling behavior under high request pressure.

## Files included

- `main.py`
- `core/api_weight_tracker.py`
- `core/execution_service.py`
- `core/data_service.py`

## Key outcomes

- Full API weight visibility with sliding 60s window and threshold levels.
- Market call blocking when usage reaches critical ranges.
- `main.py` no longer uses direct `self.execution.exchange.*` calls.
- `DataService` and `ExecutionService` both publish to one weight tracker.

## Validation

- Syntax validation passed:
  - `python -m py_compile main.py core/api_weight_tracker.py core/execution_service.py core/data_service.py`
- Simulated stress checks executed:
  - Tracker entered warning/critical ranges as expected.
  - Non-essential market calls were blocked under pressure.

## Release recommendation

- Status: **GO for paper-mode soak**.
- Run 20-30 min in paper mode before enabling real trading.
