# Fase A — Investigacion de edge offline para cuenta de $20

Rama `research/edge-20usd`. Base reversible: `8181beb`. Solo `tools/`, `core/strategy/triple_tf/`,
`tools/strategy.py`, `core/signals/` (frontera TTF) y tests. Sin cambios en ejecucion, ordenes, reconciliacion.

## Specs

- S1 — Base reversible: commit de los 188 archivos pendientes antes de cambiar nada.
- S2 — Bug 15: "el pre-análisis marca el setup como \"consumido\" y el análisis final devuelve `WAIT`
  (`analyze.py:187`, `strategy.py:362`)". El analisis TTF debe ser puro; el setup se reserva una sola vez
  cuando la senal se acepta para ejecucion.
- S3 — "mismo pipeline TTF que el runtime (incluido el bug 15 del setup \"consumido\"); costes taker;
  stops que se llenan con gap". Runtime y backtest llaman a una unica funcion pura de evaluacion TTF
  (bias 1H, veto RVol, estructura 5M con `TTF_MAX_PULLBACK_AGE_MINUTES`, FVG con `TTF_MIN_FVG_GAP_PCT`,
  gatillo 1M con zona FVG, SL FVG si existe, causalidad, setup consumido). El backtest replica tambien el
  trailing EMA50 1M que el runtime aplica a trades TTF.
- S4 — "un **perfil de $20**: notional entre $5 y $10, solo símbolos operables con ese tamaño".
  Balance $20, leverage 10, margen 5%, riesgo 1.2%, `MAX_RISK_USD`, minimo notional por simbolo (Binance:
  BTC 50, ETH 20, LINK 20, SOL/XRP/DOGE/ADA/BNB 5), sizing igual a `calculate_position_size_by_stop`;
  PnL en USD con fees sobre notional, equity compuesta, conteo de senales no operables.
- S5 — "Dejar escritos el criterio de éxito y la hipótesis **antes** de mirar resultados. El gate:
  expectancy neta > 0 en el holdout 2026-06 a 2026-08, con al menos 200 trades." (ver Pre-registro)
- S6 — "Probar TTF actual. Si no pasa, **un solo** experimento con timeframe más alto (stops más amplios,
  menos coste en R), con la misma regla. Si tampoco pasa, se para y se replantea."
- S7 — "si encuentras errores corrigelos quiero documentar los erroes corregisdo para no cometerlos
  nuevamnete en el futuro": cada error corregido se registra en `.opencode/context/known-bugs.md`
  (max 10, lo antiguo a `known-bugs-archive.md`) con causa raiz y regla preventiva.

## Pre-registro (fijado antes de ejecutar, no se modifica tras ver resultados)

- Universo $20: simbolos con minimo notional <= $10 y datos disponibles: SOLUSDT, XRPUSDT, DOGEUSDT,
  BNBUSDT, ADAUSDT. BTC/ETH excluidos (minimo > notional maximo $10).
- Costes: taker 0.05% por lado, slippage 0.05% por lado, stop con gap a la apertura. Sin maker.
- Desarrollo: 2025-09 → 2026-05 (solo diagnostico, no se ajustan parametros). Holdout: 2026-06 → 2026-08,
  se ejecuta UNA vez por hipotesis.
- PASA si en holdout: expectancy neta > 0 R, >= 200 trades, PF >= 1.1 y retorno USD del perfil $20 > 0.
  Con < 200 trades el veredicto es `MUESTRA_INSUFICIENTE` (no pasa).
- H0: TTF actual (1H/5M/1M) con parametros por defecto del runtime.
- H1 (solo si H0 no pasa): mismo pipeline escalado x4 en timeframe (4H/15M/5M ⇒ bias 4H, estructura 15M,
  gatillo 5M; ventanas en velas identicas). Hipotesis: el stop mas amplio reduce el coste en R por debajo
  del edge bruto. Sin otros cambios.
- Si H1 no pasa: STOP. No se prueban mas variantes; se replantea con el humano.

## Tasks

| ID | Specs | Ruta | Estado | Commit |
|---|---|---|---|---|
| T1 | S1 | inline | done | 8181beb |
| T2 | S2, S3 | worker (cancelado) + inline | done | 6fc299f |
| T3 | S4 | worker (cancelado) + inline | done | 6fc299f |
| T4 | S5, S6 | inline (ejecucion) | in_progress | |
| T5 | S7 | inline | in_progress | |

Evidencia T2/T3: RED observado (doble analyze → WAIT; filtro de sesion ausente → `0 != 6`), GREEN.
Suite 1380 OK (2 skipped), ruff check/format OK, no-silent-pass OK, contratos OK, smoke modular OK.
Reportes en `reports/edge20/` (ignorado por git); combinacion con `/tmp/edge20/combine.py`.

## Log

- L1 (usuario): "impelementa la fase como recomiendas si encuentras errores corrigelos quiero documentar
  los erroes corregisdo para no cometerlos nuevamnete en el futuro"
- L2: Fase A aprobada = plan del asistente: base reversible; backtest confiable (pipeline igual al runtime,
  bug 15, taker, gap); perfil $20; pre-registro; H0 y como maximo H1; parar si falla.
- L4: H0 desarrollo (2025-09→2026-05, 5 simbolos): 1793 trades, E neta -0.492R, E bruta -0.219R, PF 0.436,
  coste 0.273R; cuenta $20 → $9.99 (-50%), ruined. SIN_EDGE (solo diagnostico).
- L5: Hallazgos runtime para Fase B (no corregidos: fuera de alcance, sizing usado por REAL; fallan seguro):
  (a) `trade_entry.py:333`/`risk_engine.py` usan `MIN_NOTIONAL_VALUE` global, no el minimo por simbolo del
  exchange (BTC 50, ETH 20) → orden REAL rechazada por Binance; (b) `risk_engine.py:360-366` sube al minimo
  exacto y `amount_to_precision` trunca → post-round < minimo → rechazo (-1); 263 trades perdidos en H0 dev.
  Fix propuesto: minimo por simbolo desde `exchange.markets[...]['limits']` y redondeo HACIA ARRIBA al step al
  forzar el minimo, revalidando MAX_RISK_USD y margen.
- L3: Minimos notional consultados en `fapi/v1/exchangeInfo` 2026-11-01: BTC 50, ETH 20, LINK 20,
  SOL/XRP/DOGE/ADA/BNB 5.
