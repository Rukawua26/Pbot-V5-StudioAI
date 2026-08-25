# SPEC: Adopción Robusta de Posiciones Huérfanas

## 1. Resumen

Mejorar el mecanismo de adopción de posiciones huérfanas en `reconcile_bootstrap_state` para:
- Validar tamaño antes de adoptar (mín/máx configurable)
- Verificar desde múltiples endpoints antes de confirmar huérfano
- Usar precio de mercado para calcular SL dinámico en lugar de porcentaje fijo

## 2. Contexto

### Código existente
- `core/reconciliation.py`: función `reconcile_bootstrap_state` líneas 136-189
- Adoptación actual: usa porcentaje fijo 0.995/1.005 para SL
- No hay validación de tamaño
- No hay verificación múltiple

## 3. Requisitos Funcionales

### 3.1 Validación de Tamaño
- Obtener configuración de `Config`:
  - `ORPHAN_ADOPTION_MIN_SIZE_USD` (default: 10.0)
  - `ORPHAN_ADOPTION_MAX_SIZE_USD` (default: 10000.0)
- Calcular `size_usd = entry * amount`
- Si `size_usd` fuera del rango, loggear warning y **no adoptar**

### 3.2 Verificación Múltiple
- Antes de adoptar, verificar contra:
  1. `fetch_positions()` (ya usado)
  2. `fetch_position(symbol)` si existe
  3. `fetch_open_orders()` para verificar no hay orden abierta del trade
- Si (1) confirmado Y (2) no contradictorio, proceder
- Si contradictorio, registrar y no adoptar

### 3.3 SL Dinámico con Precio de Mercado
- Antes de adoptar, obtener precio de mercado:
  - Usar `bot.execution.fetch_ticker(symbol)` o equivalente
- Calcular SL basado en ATR o porcentaje configurable:
  - `ORPHAN_SL_ATR_MULTIPLIER` (default: 2.0)
  - o fallback `ORPHAN_SL_PERCENTAGE` (default: 0.02 = 2%)
- Calcular: `sl = entry - (price * multiplier)` para LONG
- Calcular: `sl = entry + (price * multiplier)` para SHORT

### 3.4 Logging Mejorado
- Incluir en notificación Telegram:
  - Precio de mercado usado
  - Tamaño en USD
  - SL calculado

## 4. Casos de Bordecaso

| Caso | Comportamiento |
|------|----------------|
| Fetch ticker falla | Usar fallback con porcentaje fijo (comportamiento actual) |
| Tamaño < min | Warning, no adoptar, no error |
| Tamaño > max | Warning, no adoptar, no error |
| Verificación contradictoria | Warning, no adoptar, loggear detalles |
| Todas las verificaciones fallan | Warning, no adoptar (fail-secure) |

## 5. Métricas a Registrar

- `orphan_adoption_attempted`
- `orphan_adoption_rejected_size`
- `orphan_adoption_rejected_verification`
- `orphan_adoption_success`

## 6. No Requisitos

- No cambiar adopción en otros contextos (solo bootstrap)
- No agregar retry automático
- No modificar lógica de sync_wallet

## 7. Tests Requeridos

- `test_orphan_rejected_below_min_size`
- `test_orphan_rejected_above_max_size`
- `test_orphan_rejected_contradiction`
- `test_orphan_adopted_with_dynamic_sl`
- `test_orphan_fallback_to_fixed_percentage`