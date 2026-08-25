# Changelog — Sniper AI

## v118.7-PRO (Mayo 2026)

- Fase 17: Recalibración de regímenes HMM y pesos de agentes
- Optimización de hiperparámetros vía Optuna (config_hyperopt.json)
- Mejoras en reconciliation y adopción de órdenes huérfanas
- Guardrails de seguridad para modo REAL
- Cobertura de tests: 89 archivos, 623 tests

## v118.6-PRO (Abril 2026)

- Breakout Hunter pasivo con watch + semi-active shadow
- Filtro CVD (Order Flow) y OI Delta
- Correlation Risk reducer (Fase 12.1)
- Regime Auto-Tuning de SL/TP (Fase 12.2)
- Shadow execution adapter con simulación realista de latency/rejection/partial fills
- Release freeze y soak test (ver RELEASE_FREEZE_REPORT_2026-04-01.md)

## v118.5-PRO (Marzo 2026)

- Multi-timeframe signal confirmation (MTF Filter)
- Exit Engine v1 dinámico con time decay, trailing, breakeven
- HMM regime detection con Markov snapshot
- Sistema de triage cinético (escudo térmico + gatillo seguro)
- Modularización del runtime: BotFacade, bot_connection, execution_adapters
- Primeros tests de invarianza temporal
- CI/CD con GitHub Actions: ruff, mypy, pip-audit, coverage

## v118.0-PRO (Febrero 2026)

- Arquitectura modular: core/config, core/signals, core/strategy
- 3 modos de operación: PAPER, SHADOW, REAL
- Sistema de multi-agente: MT, SR, G, breakout, correlation, ghost, judging, lb, sentiment, visual
- Ablation framework para perfiles BASELINE / FULL_INSTITUTIONAL
- Sistema de watchdog con latido externo
- Docker + systemd deployment
- Dashboard FastAPI
