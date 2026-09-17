# Plan de Consolidacion del Bot

## Objetivo

Consolidar seguridad, medicion y edge sin reescribir la arquitectura ni agregar
complejidad antes de demostrar su necesidad.

## Regla de cierre y no regresion

- Estados permitidos: `PENDIENTE`, `EN_PROGRESO`, `BLOQUEADO`, `FINALIZADO`.
- Un bloque solo pasa a `FINALIZADO` con criterios de aceptacion y validaciones
  registradas en este documento.
- Un bloque `FINALIZADO` constituye una linea base protegida: no se cambia salvo
  para corregir una regresion demostrada o aplicar una mejora medible, reversible
  y cubierta por tests.
- Una mejora posterior debe conservar los invariantes y ampliar la evidencia; no
  puede borrar el historial de cierre anterior.
- Los cambios funcionales se mantienen pequenos y separados. No se ajustan varios
  componentes de estrategia en un mismo experimento.

## Bloque 1 - Coherencia operativa y de calculo

**Estado:** `FINALIZADO`

Alcance aprobado:

1. Recovery de `HALT`: solo liberar con snapshots validos y consecutivos que
   acrediten ausencia de posiciones y ordenes abiertas.
2. TP1 REAL: solicitar contratos desde la posicion y persistir la cantidad
   restante a partir del fill confirmado.
3. Gate de estrategia: conservar correctamente un drawdown valido de `0.0`.
4. Reputacion: atribuir todos los votos directos MT/SR/G presentes en cada
   snapshot, sin doble conteo por compatibilidad legacy.

Fuera de alcance:

- Normalizacion o formula del consenso.
- Nuevos modelos, indicadores o filtros.
- Ajustes de thresholds, trailing, RRR o politica de minimo notional.
- Refactors amplios.

Criterios de cierre:

- Estado live desconocido mantiene `HALT`.
- TP1 ambiguo mantiene `HALT` y no muta cantidad local como si estuviera cerrado.
- TP1 confirmado usa `filled` verificable para actualizar estado.
- Drawdown cero supera el gate cuando los demas criterios son validos.
- Un snapshot con MT/SR/G actualiza los tres agentes una vez.
- Tests enfocados, gates runtime aplicables y suite unitaria en verde.

Evidencia de cierre:

- Recovery rechaza snapshots de posiciones/ordenes ausentes o malformados,
  cantidades no finitas o contradictorias, exposicion sin simbolo y balance no
  finito.
- TP1 REAL calcula contratos desde `amount`, exige estado terminal y `filled`
  positivo/finito/no superior al solicitado, y actualiza el remanente desde el
  fill confirmado. Cualquier ambiguedad activa `HALT` sin acreditar el parcial.
- El gate conserva `max_validation_drawdown=0.0`.
- Reputacion atribuye una vez todos los votos MT/SR/G presentes.
- Tests enfocados: 16 runtime/recovery y 83 pruebas relacionadas, OK.
- Suite completa: 1306 tests OK, 2 skipped.
- `ruff check` de archivos modificados, `compileall`, smoke modular, contratos,
  chaos matrix 8/8 y recovery drill 3/3, OK.
- Limitacion preexistente: `ruff format --check core/ tests/` propone reformatear
  172 archivos ajenos al bloque. No se mezclo ese refactor masivo con estos fixes.

Linea base protegida desde este cierre. Solo reabrir por regresion demostrada o
mejora medible, reversible y cubierta por tests.

## Bloque 2 - Referencia SHADOW confiable

**Estado:** `FINALIZADO`

1. Identificar cada campana por periodo, version, configuracion relevante, modo y
   modelo activo/fallback heuristico.
2. Evitar mezclar silenciosamente configuraciones distintas.
3. Reportar resultado neto, profit factor, drawdown de cartera, exposicion,
   MAE/MFE, costes, embudo de vetos, latencia y timeouts.
4. Congelar una configuracion SHADOW y revisar primero integridad de datos y luego
   resultado economico.

Criterio de cierre: informe reproducible que identifique un problema dominante o
declare expresamente que la muestra aun no permite concluir.

Evidencia de cierre:

- Cada evento nuevo incluye `campaign`, `run_id`, huella de configuracion, modo,
  version declarada y estado/modelo ML. El informe separa identidades y selecciona
  solo la ultima por defecto; nunca las agrega silenciosamente.
- El cierre SHADOW registra costes observados, exposicion, slippage/funding cuando
  estan disponibles, MAE/MFE, regimen y direccion.
- El scan registra duracion y numero de llamadas de analisis pesado.
- El informe calcula expectativa y profit factor desde PnL monetario comparable.
  Retorno y drawdown de cuenta solo se publican cuando existe una curva de wallet
  completa, cronologica y continua; nunca se infieren componiendo porcentajes de
  trades. Tambien reporta costes, exposicion, vetos y metricas operativas.
- Diagnostico de datos historicos existentes: 12 cierres, identidad/costes
  incompletos y conclusion `INSUFFICIENT_SAMPLE`. La muestra observada es negativa,
  pero no habilita cambios de estrategia ni el Bloque 3.
- Para la siguiente campana se debe definir `SHADOW_VALIDATION_CAMPAIGN` y
  `SNIPER_CODE_VERSION`, mantener configuracion fija y acumular al menos 20 cierres
  identificados antes de reevaluar. Veinte es un gate minimo, no prueba definitiva.
- Suite completa: 1317 tests OK, 2 skipped. Tests enfocados, `compileall`, smoke
  modular, contratos, chaos matrix 8/8 y recovery drill 3/3, OK.
- Limitaciones preexistentes conservadas: lint/formato global y mypy tienen deuda
  fuera de los archivos y dependencias de este bloque; no se mezclo su saneamiento.
- Una ejecucion intermedia sufrio `Directory not empty` al limpiar un temporal en
  un test ajeno; el test aislado y la repeticion completa pasaron. Se clasifico
  como intermitencia no reproducible y no se altero codigo no relacionado.

Linea base protegida desde este cierre. Solo reabrir por regresion demostrada o
mejora medible, reversible y cubierta por tests.

## Bloque 3 - Un experimento sobre el problema dominante

**Estado:** `PENDIENTE`

**Gate actual:** bloqueado operacionalmente hasta disponer de una campana nueva,
identificada y con muestra suficiente. No elegir hipotesis usando los 12 cierres
legacy mezclados/incompletos.

1. Formular una sola hipotesis a partir del Bloque 2.
2. Comparar baseline y candidato con evaluacion cronologica separada del ajuste.
3. Evaluar resultado neto y riesgo, no solo winrate o numero de operaciones.
4. Decidir `KEEP`, `ROLLBACK` o `CONTINUE_OBSERVING` antes de otro experimento.

Criterio de cierre: decision respaldada por evidencia y configuracion reversible.

## Despues de los tres bloques

1. Repetir experimentos de uno en uno solo si existe un problema medido.
2. Auditar en este orden: entradas por regimen/direccion, calibracion del score,
   aporte incremental del consenso, ML, macro/FVG y finalmente salidas/trailing.
3. Mantener desactivada cualquier capa sin valor incremental demostrado.
4. Considerar una campana REAL limitada solo con seguridad runtime validada,
   resultados fuera de muestra favorables, costes incluidos, drawdown aceptado y
   rollback definido. La promocion nunca sera automatica.
5. Aplazar auto-replicacion, nuevos modelos, nueva infraestructura y refactors
   amplios hasta que la evidencia los justifique.

## Invariantes protegidos

- El exchange manda sobre la DB para exposicion real.
- Una posicion REAL no queda sin `HARD SL`.
- Estado live ambiguo implica `HALT` y reconciliacion.
- No hay retries no idempotentes que puedan duplicar exposicion.
- Separacion estricta `PAPER`/`SHADOW`/`REAL`.
- Se conservan fronteras de ejecucion, orden de locks, contratos publicos,
  similarity antes del sizing y gates de publicacion de modelos.
