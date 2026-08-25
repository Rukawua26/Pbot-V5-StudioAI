# core/ — Grouping Guide

> 86 files in one directory is hard to navigate. This guide shows logical
> groupings so new files go in the right place and refactors are planned.

## 1. Bootstrap / Runtime Core

Files that define the application lifecycle.

| File | Role |
|------|------|
| `bot_app.py` | `Bot` class, entrypoint, wiring |
| `bot_facade.py` | Public contract (`BotFacade`) |
| `bot_initialization.py` | Startup init tasks |
| `bot_core_setup.py` | Core service engines setup |
| `bot_runtime.py` | Main runtime loop |
| `bot_main_loop.py` | Trading logic loop |
| `bot_runtime_monitor.py` | Memory/health RSS monitor |
| `bot_runtime_safety.py` | Safety gates |
| `bot_runtime_ops.py` | Runtime operations helpers |
| `bot_shutdown.py` | Graceful shutdown |
| `bot_guardian.py` | Position guardian watchdog |
| `process_lock.py` | Single-instance lock |

## 2. Connection / External IO

| File | Role |
|------|------|
| `bot_connection.py` | Binance connection by mode |
| `bot_io_loops.py` | Event IO loops |
| `ws_manager.py` → `tools/ws_manager.py` | WebSocket management |
| `data_service.py` | Data fetching |
| `bot_pair_fetch.py` | Pair data |
| `candle_close_cache.py` | Candle cache |

## 3. Execution / Order Management

| File | Role |
|------|------|
| `execution_adapters.py` | `live` / `shadow_live` backends |
| `execution_service.py` | Exchange execution port |
| `execution_port.py` | Port abstraction |
| `execution_order_helpers.py` | Order helpers |
| `execution_runtime_state.py` | State persistence |
| `execution_telemetry.py` | JSONL execution events |
| `trade_entry.py` | Order placement |
| `trade_exit.py` | Close trades |
| `trade_helpers.py` | Emergency close, MARKET fallback |
| `trade_manager.py` | Core trade manager |
| `trade_state.py` | Trade state machine |
| `active_trade_store.py` | Active trades storage / DB |

## 4. Trading Logic / Signals / Strategy

| File | Role |
|------|------|
| `bot_signals.py` | Signal scan cycles |
| `bot_market_state.py` | BTC HMM regime |
| `bot_radar.py` | Market radar |
| `bot_cycles.py` | Scan/triage cycles |
| `bot_risk_cycles.py` | Risk cycles |
| `bot_trade_entry.py` | Trade entry delegate |
| `bot_trade_monitor.py` | Open trade monitoring |
| `bot_consensus_display.py` | Consensus visualization |
| `signals/` (dir) | Signal pipeline |
| `strategy/` (dir) | Strategy orchestration, HMM, agents |

## 5. Risk

| File | Role |
|------|------|
| `risk_engine.py` | RiskEngine, drawdown, sizing |
| `risk_policy.py` | Entry risk decisions |
| `risk/` (dir) | Correlation risk, exit engine |
| `regime_tuning.py` | Regime-based SL/TP tuning |
| `cooldown_state.py` | Cooldown state |

## 6. Monitoring / Observability

| File | Role |
|------|------|
| `bot_telemetry.py` | Telemetry collection |
| `bot_scorecard.py` | Daily scorecards |
| `metrics_export.py` | Periodic metrics |
| `state_snapshot.py` | Runtime state snapshots |
| `bot_runtime_monitor.py` | Memory/RSS monitor |
| `bot_ml_health.py` | ML model health checks |
| `bot_ml_runtime.py` | ML runtime health |
| `bot_post_exit_analysis.py` | Post-exit drift |
| `postmortem.py` | Post-mortem analysis |
| `watchdog.py` | Heartbeat (external watchdog) |

## 7. Wallet / Balance / Performance

| File | Role |
|------|------|
| `bot_wallet_sync.py` | Wallet/capital sync |
| `bot_balance_ops.py` | Balance operations |
| `bot_performance_ops.py` | Performance reporting |
| `bot_scorecard.py` | Daily scorecards |

## 8. Operations / Housekeeping

| File | Role |
|------|------|
| `bot_cli_ops.py` | CLI operations |
| `bot_misc_ops.py` | Misc operations |
| `bot_housekeeping.py` | Periodic housekeeping |
| `bot_maintenance.py` | Maintenance tasks |
| `bot_weekly_ops.py` | Weekly maintenance |
| `bot_symbol_controls.py` | Symbol control matrix |
| `bot_market_intelligence.py` | Market intelligence |
| `market_intelligence.py` | Target acquisition |
| `market_breadth.py` | Market breadth |
| `bot_audit_verdict.py` | Audit decision resolution |
| `bot_quant.py` | Quantitative analysis |
| `intent_deduper.py` | Signal dedup |

## 9. Config

| File | Role |
|------|------|
| `config/` (dir) | All configuration |

## 10. Commands / CLI

| File | Role |
|------|------|
| `cmd_consumer.py` | Command consumer |
| `command_router.py` | Routing |
| `commands/` (dir) | Command handlers |

## 11. Infrastructure / Utilities

| File | Role |
|------|------|
| `api_weight_tracker.py` | Binance rate limit tracker |
| `model_loader.py` | ML model loading |
| `bot_models_startup.py` | Model loading at startup |
| `learning_paths.py` | Learning paths |
| `time_utils.py` | Time utilities |
| `symbol_utils.py` | Symbol normalization |
| `types.py` | Type definitions |
| `cycle_context.py` | Immutable cycle snapshot |
| `shadow_logger.py` | Shadow operations logger |
| `telegram_api.py` | Telegram wrapper |
| `rag_cache.py` | RAG cache |
| `ablation_manager.py` | Ablation study management |
| `backtester.py` | Vectorized backtester |

## Future refactor plan

When ready, move each group into its own subdirectory:

```
core/
├── __init__.py
├── bootstrap/       # bot_app, bot_facade, bot_initialization, etc.
├── connection/      # bot_connection, data_service, ws_manager
├── execution/       # execution_adapters, execution_service, trade_*
├── trading/         # bot_signals, market_state, signals/, strategy/
├── risk/            # risk_engine, risk_policy, regime_tuning
├── observability/   # telemetry, scorecard, metrics, watchdog
├── operations/      # cli, misc, housekeeping, weekly
├── config/
├── commands/
└── infrastructure/  # weight_tracker, model_loader, utils
```

This is intentionally NOT done yet — moving 86 files requires updating
all import paths and is a separate refactor task.
