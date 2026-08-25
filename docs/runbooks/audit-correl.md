# Runbook: Auditoría de Correlación Agente G

## Objetivo
Asegurar que el agente de Machine Learning (G) mantenga independencia estadística del agente de Tendencia (MT). El consenso Trinity depende de la diversidad de opiniones.

## Frecuencia Recomendada
- **Diaria:** Monitoreo preventivo.
- **Pre-Promoción:** Obligatorio antes de mover modelos de `shadow` a `real`.

## Procedimiento
Ejecutar el script de auditoría:
```bash
python tools/audit_correl.py --limit 100
```

## Interpretación de Resultados
- **< 0.60 (Aceptable):** Operación normal.
- **0.60 - 0.75 (Warning):** Investigar si el agente G está usando features demasiado similares a MT (ej. RSI/EMA sin procesamiento extra).
- **> 0.75 (Crítico):** Riesgo de sesgo de confirmación. 

## Acciones Ante Fallo Crítico
1. **Revisar `ghost_agent.py`:** Verificar si hay fuga de datos de tendencia.
2. **Ajustar Pesos:** En `core/strategy/orchestrator.py`, reducir temporalmente la influencia de G hasta recalibrar.
3. **Reentrenamiento:** Generar un nuevo modelo con un set de features más ortogonal.