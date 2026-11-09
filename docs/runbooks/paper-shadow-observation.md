# PAPER/SHADOW Observation Runbook

Guia para validar mejoras pendientes sin tocar trading real.

## Alcance

- `FVG_TRACKER_ENABLED`: medir gaps como modulo satelite read-only.
- `GLOBAL_MARKET_PROVIDER_ENABLED`: enriquecer contexto con datos macro read-only.
- `GLOBAL_FEAR_GREED_FILTER_ENABLED` y `GLOBAL_BTC_DOM_FILTER_ENABLED`: validar thresholds macro.
- `SIGNAL_AGENT_OVERRIDE_ENABLED`: observar direccion por consenso de agentes.
- `SHADOW_VALIDATION_ENABLED`: escribir metricas observacionales para el reporte semanal.
- Dashboard API: requiere `SNIPER_API_KEY` de al menos 16 caracteres.

## Reglas

- Ejecutar solo con `PAPER_MODE=true` o SHADOW sin `ALLOW_REAL_TRADING=true`.
- No integrar FVG, macro o consenso al Risk Engine ni sizing sin evidencia estadistica.
- No ajustar thresholds por intuicion; comparar contra baseline previo.
- Si aparece estado ambiguo en `REAL`, priorizar `HALT` y reconciliacion, no observacion.

## Preflight

```bash
SNIPER_DISABLE_FILE_TELEMETRY=1 ./.venv/bin/python tools/pending_improvements_readiness.py
```

El script no llama a Binance, CoinGecko ni arranca el bot. Solo lee `.env` y variables de entorno.

## Configuracion PAPER sugerida

```env
PAPER_MODE=true
ALLOW_REAL_TRADING=false
FVG_TRACKER_ENABLED=true
GLOBAL_MARKET_PROVIDER_ENABLED=true
GLOBAL_FEAR_GREED_FILTER_ENABLED=true
GLOBAL_BTC_DOM_FILTER_ENABLED=true
SIGNAL_AGENT_OVERRIDE_ENABLED=true
SHADOW_VALIDATION_ENABLED=true
SHADOW_VALIDATION_CAMPAIGN=shadow_macro_fvg_consensus_v1
```

## SHADOW como maestro de REAL (cuenta pequena)

Objetivo: que cada trade SHADOW sea uno que una cuenta REAL del mismo tamano podria abrir.
Con `SHADOW_MIRROR_REAL_LIMITS=true`, SHADOW aplica los mismos limites que REAL:

- margen maximo (`MAX_MARGIN_PERCENT` x leverage fijo 10x de `core/config/strategy.py`) y `MAX_RISK_USD`, tambien en el veto final;
- minimo notional por simbolo del exchange (`markets[...]['limits']['cost']['min']`), que gana
  sobre `MIN_NOTIONAL_VALUE`;
- precision de cantidad del exchange; si la orden se sube al minimo, se redondea HACIA ARRIBA un
  step y se revalidan riesgo y margen (nunca queda por debajo del minimo).

SHADOW sigue sin enviar ordenes: solo cambia el sizing. Con el flag en `false` (default) SHADOW
conserva el sizing permisivo anterior. REAL no depende del flag.

```env
PAPER_MODE=true
ALLOW_REAL_TRADING=false
PAPER_INITIAL_BALANCE=20
SHADOW_MIRROR_REAL_LIMITS=true
MAX_MARGIN_PERCENT=5
RISK_PER_TRADE_PERCENT=1.2
MAX_RISK_USD=2.0
MAX_OPEN_TRADES=3
SHADOW_VALIDATION_ENABLED=true
SHADOW_VALIDATION_CAMPAIGN=shadow_mirror_real_20usd_v1
```

Con $20 el notional maximo es $10: BTC (min $50), ETH (min $20) y LINK (min $20) se rechazan
con `RISK_SIZE_MIN_MARGIN` (-6), igual que en REAL. Reglas offline equivalentes: `tools/ttf_backtest.py`
(`size_account_trade`).

Importante: ninguna estrategia probada hasta ahora tiene ventaja (ver `odd/tasks/edge-20usd.md`,
`mtf-pullback-v2.md`, `mean-reversion-v3.md`). Esta campana valida la operativa (sizing, ordenes,
stops, reconciliacion), no la rentabilidad.

## Reporte semanal

```bash
./.venv/bin/python tools/shadow_validation_report.py
```

El reporte usa `logs/runtime_metrics.jsonl` y resume vetos, boosts, overrides, trades SHADOW cerrados y ciclos FVG.

## Evidencia minima

- FVG: alertas totales, falsos positivos, fills posteriores, timing util.
- Global Market: frecuencia de huecos de datos, cache hits, errores de rate limit.
- Macro filters: cantidad de vetos/boosts y resultado de trades evitados o potenciados.
- Consenso/trailing: al menos 10 trades SHADOW cerrados post-cambio.
- Reporte: conservar salida semanal de `tools/shadow_validation_report.py` antes de ajustar thresholds.

## Criterios de avance

- FVG solo puede pasar de observacional a candidato si aporta informacion incremental medible.
- Global Market queda aceptado si no introduce huecos frecuentes ni latencia operativa relevante.
- Macro filters requieren evidencia de mejora sin degradar drawdown.
- Consenso/trailing requiere winrate SHADOW >45% y mejor relacion avg win/avg loss contra baseline.

## Plan de corrida de 1 semana (cronograma)

El objetivo es recolectar >=20 trades SHADOW cerrados con todos los flags activos,
sin tocar thresholds ni logica de ejecucion.

### Dia 0 - Preflight y arranque
1. Confirmar modo seguro (PAPER o SHADOW sin ALLOW_REAL_TRADING).
2. Ejecutar preflight:
   ```bash
   SNIPER_DISABLE_FILE_TELEMETRY=1 ./.venv/bin/python tools/pending_improvements_readiness.py
   ```
3. Arrancar el bot con los flags del bloque "Configuracion PAPER sugerida".
4. Verificar que `logs/runtime_metrics.jsonl` recibe eventos `shadow_validation`
   (debe aparecer `config_snapshot` al iniciar).

### Dia 1-2 - Baseline limpio
- Dejar correr sin tocar nada.
- Al final del dia 2, ejecutar el reporte y guardar salida como `baseline_d2.md`.

### Dia 3-4 - Observacion macro + FVG + consenso
- Los flags ya estan activos desde el dia 0; estos dias solo acumulan datos.
- Revisar `fvg_cycle` y `filter_decision` en el reporte diario (sin ajustar thresholds).

### Dia 5-7 - Acumulacion y cierre
- Objetivo: >=20 trades SHADOW cerrados en `shadow_trade_closed`.
- Al final del dia 7, ejecutar reporte final y comparar contra baseline del roadmap
  (17 SHADOW trades, 35.3% WR, -12.17% PnL).

### Comando de arranque sugerido
```bash
SNIPER_DISABLE_FILE_TELEMETRY=1 ./.venv/bin/python main.py
```
(requiere `.env` con los flags del bloque "Configuracion PAPER sugerida")

### Gates de decision (post-semana)
- Si `shadow_trades.closed >= 20` y `winrate_pct > 45` y `avg_win_pct/abs(avg_loss_pct)` mejora:
  candidato a ajuste fino de thresholds (Fase 5).
- Si `agent_override_rate_pct` es 0 o ~100% sistematicamente: revisar
  `SIGNAL_AGENT_OVERRIDE_THRESHOLD`.
- Si FVG `new_gaps` alto pero no correlaciona con trades buenos: dejar observacional.
- Si `macro_vetoes` mata senales utiles o `macro_boosts` no mejoran PnL: ajustar
  `GLOBAL_FEAR_VETO_THRESHOLD` / `GLOBAL_BTC_DOM_BOOST_THRESHOLD` solo con evidencia.

