# Known Bugs — Prevención de Regresiones
> Antes de modificar cualquier archivo listado aquí, verificar reglas preventivas.
> Máximo 10 entradas. Lo antiguo (>30 días) se archiva en `known-bugs-archive.md`.

| Fecha | Bug / Síntoma | Causa Raíz | Archivos | Regla Preventiva |
| :--- | :--- | :--- | :--- | :--- |
| 2026-11-02 | Posicion REAL podia quedar sin HARD SL al cerrar | `_close_position_chase` cancelaba todas las ordenes del simbodo, incluido el HARD SL, antes de pedir el precio | `core/execution_service.py` | Cancelar solo ordenes no protectoras; fail-safe si no se pueden inspeccionar. |
| 2026-11-02 | TP1 ambiguo se podia repetir y reducir la posicion dos veces | `_handle_tp1` dejaba `tp1_triggered=False` y guardian lo reintentaba | `core/bot_guardian.py` | ID estable por trade; reconciliar por clientOrderId; no reintentar si status TP1_EXIT_AMBIGUOUS. |
| 2026-11-02 | Falla de sandbox en testnet seguia contra Binance real | `build_execution_gateway` solo logueaba warning | `core/execution_adapters.py` | Fail closed: raise RuntimeError. |
| 2026-11-02 | STOP_LIMIT se aceptaba como HARD SL | `_is_protective_stop_for_trade` buscaba subcadena 'STOP' | `core/execution_safety.py`, `core/bot_wallet_sync.py`, `core/reconciliation.py` | Validador compartido: solo reduce-only STOP_MARKET. |
| 2026-11-02 | SL insuficiente nunca se reparaba (HALT eterno) | `_ensure_hard_sl_attached` solo halteaba | `core/bot_wallet_sync.py` | Cancelar SL stale y colocar uno nuevo; placement fallido haltea/cierra. |
| 2026-11-02 | HALT se liberaba con snapshots no consecutivos | `recover_halt_if_exchange_consistent` no reseteaba estado en paths bloqueantes | `core/reconciliation.py` | Resetear estado en todo return bloqueante. |
| 2026-11-02 | Wallet sync bloqueaba el guardian hasta 75s | `sync_wallet` mantenia `bot.lock` durante red | `core/bot_wallet_sync.py` | Precios bajo lock; red fuera del lock. |
| 2026-11-02 | Min-notional podia superar % de riesgo por trade | Bump solo verificaba MAX_RISK_USD | `core/risk_engine.py` | Verificar min_risk contra risk_budget_usd. |
| 2026-11-02 | MT score se interpretaba como BUY pressure | MT devolvia scores relativos al lado | `core/strategy/agents/mt_agent.py` | Scores direccionales. |
| 2026-11-02 | Veto de correlacion fabricaba consenso bajista | Ponia pesos en 0 sin renormalizar | `core/strategy/orchestrator.py` | Renormalizar; si ninguno sobrevive, neutral. |
