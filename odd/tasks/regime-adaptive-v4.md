# Regime-Adaptive v4 — estrategia que se adapta al mercado

Rama `research/edge-20usd`. Sucede a `mean-reversion-v3.md` (4 familias fallaron el gate).
Parte A offline (`core/strategy/regime_adaptive.py`, `tools/ra_backtest.py`, tests). Parte B SHADOW si pasa.

## Specs

- S1 — "quiero que el bot se adapte al mercado": detectar regimen (trending vs ranging) y enrutar a la
  estrategia con mayor probabilidad en ese regimen: trend-following en tendencia, mean reversion en rango.
- S2 — Temporalidades 1H/15M/5M/1M (como pidió el usuario). 1H para regimen y contexto, 15M para setup,
  5M para confirmacion, 1M para entrada.
- S3 — Costes realistas: taker 0.05% + slippage 0.05% por lado, stop con gap, TP exacto.
- S4 — Perfiles $20 y $100, gate pre-registrado, holdout limpio si pasa el descarte.

## Pre-registro (fijado 2026-11-02 antes de ejecutar)

1. Regimen 1H: ADX14(1H) >= 25 Y |EMA50 ahora vs 6 velas atras| >= 0.3% → TRENDING. ADX14 < 20 Y ese cambio < 0.3% → RANGING. Cualquier otro caso → NEUTRAL (sin operacion).
2. TRENDING → TTF pullback: bias 1H (EMA50 vs EMA200 + slope), pullback 15M a EMA20 con MSS, confirmacion 5M (break prev extreme), entrada 1M (close > EMA9). Stop: swing 15M -/+ 0.1*ATR. TP: 1.5R. Max hold: 8h.
3. RANGING → Mean Reversion: estiramiento 15M fuera de Bollinger(20,2.0), confirmacion 5M (break prev extreme), entrada 1M (close > open para long). Stop: min/max de 4 velas 15M -/+ 0.1*ATR. TP: SMA20(15M). Max hold: 4h. Solo si distancia al target >= 1.0R.
4. Stop valido: 0.4% <= stop <= 2.5% del precio.
5. Sesion 07-22 UTC. Un setup por identidad. Una posicion por simbodo.

Universo, perfiles, periodos, gate: identicos a mean-reversion-v3.md.
- Desarrollo 2025-09 → 2026-08: control de descarte E BRUTA <= 0 → STOP sin gastar holdout.
- Holdout 2026-09 → 2026-10 (octubre desde archivos diarios): una sola corrida.
- PASS por perfil: E neta > 0 R, >= 200 trades operables, PF >= 1.1, retorno USD > 0.

## Tasks

| ID | Specs | Ruta | Estado | Commit |
|---|---|---|---|---|
| T1 | S1, S2 | inline: evaluador + backtest + tests con mutacion | pending | |
| T2 | S1 | ejecucion desarrollo (+ holdout si pasa descarte) | pending | |
| T3 | S4 | known-bugs + cierre | pending | |

## Log

- L2: Pre-registro corregido ANTES de ejecutar: la regla 1 citaba un rango 0.3-0.5% que no se usa; queda un solo umbral 0.3%. Advertencia: ambos componentes (MTF v2, MR v3) ya se vieron negativos en el periodo de desarrollo; solo el holdout sep-oct 2026 es evidencia limpia.
- L1 (usuario): "quiero que el bot se adapte al mercado es decir que cuando este lateral se adapte a lateral cuando este bajista que se adapte a bajista y cuando este alcista que se adapte claro siguiendo la estrategia correcta o con mayor probavilidad me entiendes la idea"
