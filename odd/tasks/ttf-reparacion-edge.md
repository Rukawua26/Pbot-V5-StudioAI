# TTF Reparación de Edge — Bloques 1-3 (corte aprobado)

## Objetivo

Reparar la estrategia Triple Timeframe por cortes verticales con puertas de
descarte: primero certeza temporal y contención, después la entrada causal.
Medir con `tools/ttf_backtest.py` antes de tocar salidas (Bloque 4).

## Problema y por que

Backtest 12 meses x 3 simbolos (2025-09→2026-08): 2818 trades, expectancy
-0.476R, PF 0.528, WR 26.5%, coste 0.25R/trade, 12/12 meses negativos.
Ademas el runtime decide con velas abiertas (`DataService` entrega la vela en
formacion y los evaluadores TTF usan `iloc[-1]`), TTF bypasea el veto de
regimen (`core/signals/filters.py:456-465`) y no hay gate REAL para TTF.

## Alcance (aprobado por el humano: "implementa el plan")

- Bloque 1: gate `TTF_REAL_ENABLED=false`, velas cerradas en la frontera TTF,
  deduplicacion de senales por vela 1M cerrada.
- Fixes de bugs hallados durante revision: cache del backtester pisada
  (`bias_cache`/`struct_cache`), unidades de `spread` en `min_dist` de
  `core/trade_entry.py`.
- Bloque 2: secuencia causal MSS → pullback → cruce, trigger de cruce real,
  orden pullback→trigger con timestamps.
- T4: validacion CI completa.
- T5: backtest en periodo de desarrollo (2025-09→2026-05) y evaluacion del
  kill gate (expectancy bruta > 0).

## Excluido

- Bloque 3 (veto RANGE para TTF), Bloque 4 (TP estructural / SL con ATR),
  holdout 2026-06→2026-08, SHADOW, REAL, limpieza legacy, refactors amplios.
  Solo si T5 pasa el kill gate y hay autorizacion nueva.

## Restricciones

- No commitear, no push, no rama, no deploy.
- No tocar `core/execution_adapters.py`, reconciliacion, guardian, wallet sync.
- Flags nuevos con default conservador y evento/log visible.
- No romper separacion PAPER/SHADOW/REAL ni invariantes de `AGENTS.md`.

## No romper

- Contratos: `tools/regression_contracts.py` (main.py, Bot, BotFacade).
- Tests existentes TTF: `tests/test_strategy_triple_tf.py`,
  `tests/test_triple_tf_end_to_end.py`, `tests/test_ttf_backtest.py`.
- `similarity_boost` antes del sizing en `core/trade_entry.py`.
- `MAX_ENTRY_SL_PCT >= 3.0`, `SHOCK_MIN_DIST_PCT <= 0.2`.
- `tools/check_no_silent_pass.py` sin `pass` silenciosos en `core/`.
- Separacion de modos y HARD SL intactos.

## TDD

- Modo: off
- Fuente: default (sin politica explicita TDD en AGENTS.md ni instruccion del usuario)
- Runner: `SNIPER_DISABLE_FILE_TELEMETRY=1 ./.venv/bin/python -m unittest tests/<foco>`
  (checks funcionales obligatorios: tests enfocados + suite completa)

## Tareas

- [ ] T1 — Bloque 1 completo: helper de velas cerradas + gate
      `TTF_REAL_ENABLED` + dedup por vela 1M cerrada, con tests enfocados.
- [ ] T2 — Fixes: cache pisada en `tools/ttf_backtest.py` (asignacion que
      reemplaza el dict) y unidades de `spread` en `min_dist` de
      `core/trade_entry.py`, con tests que fallen antes (RED) y pasen despues.
- [ ] T3 — Bloque 2: orden MSS→pullback en `structure_5m` con
      `pullback_time`, cruce real en `trigger_1m`, trigger posterior al
      pullback en `tools/strategy.py`, actualizacion de tests TTF afectados.
- [ ] T4 — Validacion CI completa (ruff, compileall, smoke, contratos,
      no-silent-pass, suite completa, chaos, recovery).
- [ ] T5 — Backtest periodo desarrollo + evaluacion kill gate.

## Criterios de aceptacion

- [ ] T1: vela abierta nunca evalua; misma vela cerrada = una sola senal;
      TTF no puede entrar en REAL con `TTF_REAL_ENABLED=false`; tests en verde.
- [ ] T2: test RED previo observado y GREEN tras fix; sin cambios de
      comportamiento esperado salvo correccion documentada.
- [ ] T3: MSS estrictamente anterior al pullback; trigger = cruce real
      previo/cierre; trigger temporalmente posterior al pullback cuando hay
      timestamps; tests TTF actualizados en verde.
- [ ] T4: toda la validacion CI en verde (evidencia con comando y salida).
- [ ] T5: `summary.json` del periodo desarrollo con expectancy bruta; si
      <= 0 el kill gate cierra el experimento y se reporta (no se toca Bloque 4).

## Decisiones aceptadas

- Helper de velas cerradas aplica solo en la frontera de entrada TTF, no en
  `DataService` global (dashboard/trailing podrian necesitar la vela actual).
- Dedup en memoria por proceso (dict en `Strategy`), con la limitacion de
  reinicio documentada.
- Gate REAL por flag en config; no depende solo de `ALLOW_REAL_TRADING`.
- TDD off con checks funcionales obligatorios (fuente: default).

## Reutilizacion investigada

- Helper de cierre: no existe equivalente; se crea en
  `core/strategy/triple_tf/closed_candles.py` (canonico, compartible con
  backtester futuro).
- Deteccion de regimen: ya existe (`bot._get_market_regime`, HMM/heuristica);
  no se crea otra (aplicable en Bloque 3, fuera de este corte).
- Backtester: `tools/ttf_backtest.py` ya integra el repo; se reutiliza tal
  cual para T5.
- Alternativas descartadas: filtrar vela abierta globalmente en
  `DataService` (romperia consumidores); dedup via DB (pesado para el hot path).

## Evidencia

- T1: pending
- T2: pending
- T3: pending
- T4: pending
- T5: pending

## Progreso

- Estado: implementacion
- Ultima tarea: creacion del documento
- Siguiente paso: ejecutar T1 via worker + verifier
- Bloqueos: ninguno
