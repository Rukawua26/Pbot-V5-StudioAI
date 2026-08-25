# Runbook: Risk Governance Matrix

Este documento define quién manda cuando el bot detecta una condición de riesgo.

## Prioridad de decisiones

1. `SHUTDOWN_IN_PROGRESS`
2. `HALT_SYSTEM_ACTIVE`
3. `INTEGRITY_LOCK_ACTIVE`
4. `TRADING_HALTED_DB_ERROR`
5. `CIRCUIT_BREAKER_PANIC`
6. `BOT_PAUSED`
7. `RECOVERY_PENDING_STATE`
8. `CONFIDENCE_STAGNATION_LOCK`
9. `SYMBOL_QUARANTINED`

## Taxonomía

- `ALLOW`: la estrategia puede seguir evaluando/operando
- `BLOCK`: se rechaza la entrada, pero no implica estado terminal del runtime
- `HALT`: se bloquean nuevas entradas hasta intervención manual o reset explícito
- `QUARANTINE`: bloqueo acotado al símbolo o causa degradada

## Fuente de verdad por capa

- `entry_preconditions`: evita aperturas inválidas por shutdown, recovery o locks estructurales
- `runtime_entry_guard`: aplica frenos runtime (`halt`, `breaker`, `pause`, `quarantine`) antes de crear intención
- `runtime_safety`: protege cuenta por trailing y daily loss
- `daily_drawdown_breaker`: protege cuenta por drawdown UTC verificable o unverifiable

## Regla operativa

Si dos capas discrepan, manda la de mayor prioridad. La estrategia no puede sobrepasar una decisión `HALT` o `BLOCK` ya emitida por riesgo.
