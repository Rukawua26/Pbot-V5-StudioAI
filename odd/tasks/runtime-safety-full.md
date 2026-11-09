# Correccion completa de errores de auditoria (runtime safety + strategy + config)

Rama `research/edge-20usd`. Origen: auditoria 2026-11-01 (hallazgos 1-10 y medios). Contencion ya hecha:
dashboard auth/IPC (d6ee515) y nan/inf en config (db36f67). Falta el bloque REAL y los medios/estrategia.

## Specs

- S1 — Los invariantes de AGENTS.md se cumplen siempre: una posicion REAL nunca queda sin HARD SL; estado
  live ambiguo => HALT; no retries no idempotentes; separacion PAPER/SHADOW/REAL.
- S2 — Cada error se corrige con test RED/GREEN (o justificacion documentada si no hay runner) y se registra
  en `.opencode/context/known-bugs.md`.
- S3 — Trabajo por unidades pequenas: un commit por hallazgo, sin mezclar refactors con fixes funcionales.
- S4 — Bloque REAL antes de poner dinero: #2, #3, #4, #5, #6, #7, #8, #10.

## Tasks

| ID | Hallazgo | Ruta | Estado | Commit |
|---|---|---|---|---|
| R1 | #2 cierre borra HARD SL antes de confirmar salida | `core/execution_service.py` | done | 2b23ad2 |
| R2 | #3 TP1 ambiguo se repite | `core/bot_guardian.py`, `core/execution_service.py` | done | cfe4350 |
| R3 | #4 testnet sandbox falla en silencio | `core/execution_adapters.py` | done | 0d735f4 |
| R4 | #6 STOP_LIMIT aceptado como HARD SL | `core/execution_safety.py`, `core/bot_wallet_sync.py`, `core/reconciliation.py` | done | 6b0f438 |
| R5 | #5 SL insuficiente nunca se repara | `core/bot_wallet_sync.py` | done | 235829d |
| R6 | #8 HALT se libera con snapshots no consecutivos | `core/reconciliation.py` | done | dafc1b2 |
| R7 | #7 wallet sync mantiene bot.lock durante red | `core/bot_wallet_sync.py` | done | 2196542 |
| R8 | #10 min-notional puede superar % de riesgo por trade | `core/risk_engine.py` | pending | |
| M1 | nan/inf config | `core/config/env_helpers.py` | done | db36f67 |
| M2 | dashboard auth | `tools/dashboard_api_server.py` | done | d6ee515 |
| M3 | dashboard IPC | `core/cmd_consumer.py`, `tools/dashboard_api_server.py` | done | d6ee515 |
| M4 | security regression test mock metodo equivocado | `tests/test_bot_security_runtime.py` | pending | |
| M5 | dashboard tests bypass auth | `tests/test_dashboard_ipc.py` | done | d6ee515 |
| M6 | npm monitor fabrica estado | `server.js`, `package.json` | done | 88a7f6f |
| M7 | MT agent score interpretado como BUY | `core/strategy/agents/mt_agent.py` | done | (commit pendiente) |
| M8 | veto correlacion sin renormalizar | `core/strategy/orchestrator.py` | done | (commit pendiente) |
| M9 | SR kinetic scaling invierte voto | `core/strategy/agents/sr_agent.py` | done | (commit pendiente) |
| M10 | HMM descarta secuencia | `core/strategy/regime_hmm.py` | done | (commit pendiente) |
| M11 | backtester asume fill exacto del stop | `core/backtester.py` | done | (commit pendiente) |

## Log

- L1 (usuario): "primero corrijamos todos los erroes antes de continuar me entiendes la idea"
- L2: Contencion ya hecha (dashboard auth/IPC, nan/inf). Bloque REAL y medios siguen.
- L3: Prioridad por invariante: #2, #3, #4 (posicion sin SL / TP duplicado / live en testnet) van primero.
