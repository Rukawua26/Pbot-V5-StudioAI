# Mean Reversion v3 + SHADOW maestro de REAL

Rama `research/edge-20usd`. Sucede a `odd/tasks/mtf-pullback-v2.md` (tendencia descartada 3 veces).
Parte A offline (`core/strategy/mean_reversion.py`, `tools/mr_backtest.py`, tests). Parte B SHADOW realista.

## Specs

- S1 — "si vamos a cambiar de enfoque si es necesario a ver si mejoramos": una hipotesis de otra familia
  (reversion a la media en rango), pre-registrada, con las mismas temporalidades 1H/15M/5M/1M.
- S2 — "ok si vamos con solo shadow como practica pero con la intencion que sirva como maestro de real":
  SHADOW aplica los mismos limites que REAL para una cuenta de $20 (balance inicial propio, margen,
  MAX_RISK_USD, minimo notional y precision por simbolo), sin enviar ordenes reales.
- S3 — "ok si si es para aprender puedes hacer la rama": publicar la rama de investigacion (sin PR/merge).
- S4 — "recuerda hacer correcciones si es necesario y guardar los cambios a para que no cometamos los
  mismos errores": errores corregidos con test y registrados en `.opencode/context/known-bugs.md`.

## Pre-registro Parte A (fijado 2026-11-02 antes de ejecutar; no se modifica tras ver resultados)

Reglas (velas CERRADAS agregadas desde 1M):

1. Regimen 1H de rango: ADX14(1H) < 20 y |EMA50(1H) ahora vs 6 velas atras| < 0.5%. Si no, sin operacion.
2. Estiramiento 15M: la ultima vela 15M cerrada cierra fuera de Bollinger(20, 2.0) (LONG si bajo la banda
   inferior; SHORT si sobre la superior).
3. Confirmacion 5M: dentro de los 30 min posteriores al cierre de esa vela 15M, una vela 5M cierra por encima
   del high de la 5M anterior (LONG; por debajo del low en SHORT).
4. Entrada 1M: la vela 1M que cierra junto con la confirmacion (o la primera posterior, dentro de la ventana)
   con close > open (LONG; < en SHORT). Entrada a la apertura de la 1M siguiente + slippage.
5. Stop: min low (LONG) / max high (SHORT) de las ultimas 4 velas 15M -/+ 0.1 x ATR14(15M); valido si
   0.4% <= stop <= 2.5% del precio.
6. Objetivo: SMA20(15M) (banda media) de la vela de estiramiento. Solo se opera si la distancia al objetivo
   >= 1.0 x riesgo. Salida: TP en el objetivo, SL, o cierre por tiempo a las 4 horas.
7. Un estiramiento 15M solo se usa una vez. Una posicion por simbolo. Sesion 07-22 UTC.
8. Costes: taker 0.05% por lado, slippage 0.05% por lado, stop con gap a la apertura, TP al precio exacto.

Universo, perfiles ($20, $100), periodos y gate: identicos a `mtf-pullback-v2.md`.
- Desarrollo 2025-09 → 2026-08: control de descarte E BRUTA <= 0 → STOP sin gastar holdout.
- Holdout 2026-09 → 2026-10 (octubre desde archivos diarios): una sola corrida.
- PASS por perfil: E neta > 0 R, >= 200 trades operables, PF >= 1.1, retorno USD > 0.

## Tasks

| ID | Specs | Ruta | Estado | Commit |
|---|---|---|---|---|
| T1 | S3 | inline: push de la rama | blocked: credencial GitHub sin permiso | |
| T2 | S1 | inline: evaluador + backtest + tests con mutacion | done | c4a89fc |
| T3 | S1 | ejecucion desarrollo (+ holdout si pasa el descarte) | done (STOP, holdout no usado) | |
| T4 | S2 | SHADOW realista: balance inicial, limites y precision iguales a REAL | pending | |
| T5 | S4 | known-bugs + cierre | pending | |

## Log

- L1 (usuario): "1 si vamos a cambiar de enfoque si es necesario a ver si mejoramos / 2 ok si vamos con solo
  shadow como practica pero con la intencion que sirva como maestro de real / 3 ok si si es para aprender
  puedes hacer la rama / recuerda hacer correcciones si es necesario y guardar los cambios a para que no
  cometamos los mismos errores"
- L3: Evidencia T2: 14 tests evaluador + 4 backtest MR; 10 mutaciones detectadas (ADX, EMA plana, banda
  Bollinger, ruptura 5M, ventana, vela 1M, objetivo >= 1R, signo del stop, regimen, expiracion). Refactor
  `StrategySpec` en `tools/mtf_backtest.py`: trades MTF de SOL identicos antes/despues (462 = 462).
- L4: DESARROLLO MR v3 (2025-09→2026-08, 8 simbolos): 1718 trades, WR 37.2%, E BRUTA -0.164R, E neta
  -0.327R, PF 0.55, coste 0.163R, stop medio 0.68%. Negativo antes de costes en los 8 simbolos.
  $20 → $9.98 (-50%); $100 → $28.20 (-72%). Control de descarte → STOP. Holdout sep-oct 2026 sigue limpio.
- L5: Conclusion acumulada: 4 hipotesis (TTF, TTF x4, pullback en tendencia, reversion en rango) pierden
  antes de costes con velas de 1M-1H en estos 8 pares. Reglas de indicadores clasicos sobre precio no dan
  ventaja aqui; seguir variando reglas es buscar ruido (el error de las 66 variantes).
- L2: `git push -u origin research/edge-20usd` → 403: "Permission to Rukawua26/Pbot-V5-StudioAI.git denied to
  TecnoDAY". No se tocan credenciales; decision del humano.
