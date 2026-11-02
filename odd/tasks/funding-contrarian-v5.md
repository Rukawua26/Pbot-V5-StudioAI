# Funding-Rate Contrarian v5 — estrategia basada en microestructura

Rama `research/edge-20usd`. Sucede a `regime-adaptive-v4.md` (5 familias de velas fallaron).
Nueva fuente de datos: funding rate de futuros (no indicadores de precio).

## Specs

- S1 — "diseña lo que necesites": estrategia basada en funding rate extremo como señal contrarian.
  No usa velas de 1m para decidir dirección; las usa solo para entrada y gestión.
- S2 — Funding rate extremo = mercado sobre-apalancado en una dirección. Reversión probable.
- S3 — Costes realistas: taker 0.05% + slippage 0.05% por lado, stop con gap, TP exacto.
- S4 — Perfiles $20 y $100, gate pre-registrado, holdout limpio si pasa el descarte.

## Pre-registro (fijado 2026-11-03 antes de ejecutar)

Reglas:
1. Señal: funding rate de 8h extremo. LONG si funding < -0.01% (demasiados shorts). SHORT si funding > +0.01% (demasiados longs). Entre -0.01% y +0.01%: sin operación.
2. Entrada: primera vela 1H cerrada después del funding extremo. Entrada a la apertura de la vela 1H siguiente + slippage.
3. Stop: 1.5 x ATR14(1H) desde la entrada. Valido si 0.5% <= stop <= 5.0% del precio.
4. Objetivo: 1.0R (más cercano que 1.5R para aumentar win rate). Salida: TP, SL, o cierre por tiempo a las 24h.
5. Un funding extremo solo se usa una vez. Una posición por símbodo. Sesion 07-22 UTC.
6. Costes: taker 0.05% por lado, slippage 0.05% por lado, stop con gap a la apertura, TP al precio exacto.

Universo: SOL, XRP, DOGE, BNB, ADA, ETH, LINK, BTC.
Perfiles: $20 (max notional $10 → SOL/XRP/DOGE/BNB/ADA), $100 (max notional $50 → + ETH, LINK).
Periodos: desarrollo 2025-09 → 2026-08; holdout 2026-09 → 2026-10 (octubre diario).
Gate: E neta > 0 R, >= 200 trades operables, PF >= 1.1, retorno USD > 0.

## Tasks

| ID | Specs | Ruta | Estado | Commit |
|---|---|---|---|---|
| T1 | S1, S2 | inline: fetcher de funding + evaluador + backtest + tests | done | (commit pendiente) |
| T2 | S1 | ejecucion desarrollo (+ holdout si pasa descarte) | done (STOP) | |
| T3 | S4 | known-bugs + cierre | done | |

## Log

- L2: DESARROLLO FC v5 (2025-09→2026-08, 8 simbolos): 636 trades, WR 46.1%, E BRUTA -0.124R, E neta -0.194R,
  PF 0.669, coste 0.07R. Negativo antes de costes en 7 de 8 simbolos (solo DOGE +0.11R con 52 trades).
  $20 → $11.46 (-42.7%); $100 → $42.86 (-57.1%). Control de descarte → STOP. Holdout sep-oct 2026 sigue limpio.
- L3: Problema estructural: funding rates son pequeños (0.01% tipico). Threshold de 0.01% produce solo 636 trades
  en 12 meses (53/mes). Insuficiente para significancia estadistica. Funding rate como señal standalone no
  produce suficientes trades.
- L4: Conclusion acumulada (6 hipotesis): velas 1M-1H, funding rate, y combinaciones de indicadores clasicos
  sobre estos 8 pares no muestran ventaja antes de costes. 6 estrategias, 6 fallos.
- L1 (usuario): "continua con el siguiente paso si diseña lo que necesites"
