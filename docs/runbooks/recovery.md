# Runbook: Recovery y HALT

La regla principal: el exchange manda. La DB local ayuda a recuperar, pero no decide exposición real.

## Cuando el Bot Entra en HALT

1. No reinicies inmediatamente.
2. Revisa Binance Futures: posiciones abiertas, órdenes stop, órdenes reduce-only.
3. Revisa `logs/execution_events.jsonl` buscando `HALT`, `EXIT_STUCK`, `ACTIVE_STATE_PERSIST_FAILED`, `ORDER_LOOKUP_FAILED`.
4. Si hay posición abierta sin HARD SL, adjunta protección manual o cierra manualmente.
5. Solo después de exposición cero o protegida, evalúa reinicio.

## Posición Existe en Binance Pero No en DB

- Considera exposición real como válida.
- No abras nuevas posiciones.
- Ejecuta reconciliación bootstrap arrancando en modo seguro.
- Si la adopción de huérfanas falla, mantener HALT y operar manualmente.

## DB Dice OPEN Pero Binance Está Flat

- No inventes exposición.
- Guarda snapshot de error si aplica.
- Elimina/cierra estado local solo tras confirmar `fetch_positions` y órdenes abiertas.
- Si `fetch_positions` falla o devuelve vacío ambiguo, mantener HALT.

## HARD SL Falló

Resultado aceptable:

- SL exchange-side adjuntado.
- posición cerrada por emergency close.
- HALT con alerta y exposición manualmente gestionada.

Resultado inaceptable:

- posición abierta sin SL mientras el bot sigue buscando entradas.

## Reintentos

- No hagas retries manuales de entry.
- Los retries de cierre/protección deben ser idempotentes o reduce-only.
- Si hay duda de duplicación, cancela órdenes abiertas y reconcilia antes de actuar.

## Evidencia Mínima Para Cerrar Incidente

- Captura de Binance sin exposición inesperada.
- Evento o log que explique causa raíz.
- Estado local consistente con exchange.
- Si hubo bug, test de regresión antes de volver a REAL.
