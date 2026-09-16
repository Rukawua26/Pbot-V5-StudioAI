<div align="center">

# ⚡ SNIPER AI · QUANTITATIVE EXECUTION ENGINE
### *Institutional-Grade Algorithmic Trading Infrastructure for Binance USDⓈ-M Futures*

[![Engine Version](https://img.shields.io/badge/Version-v118.8--PRO%20%7C%20Enterprise-00f2fe?style=for-the-badge&logo=codeforces&logoColor=white)](https://github.com/Rukawua26/Pbot-V5-StudioAI)
[![Python Runtime](https://img.shields.io/badge/Python-3.12%20%7C%20AsyncIO-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Exchange](https://img.shields.io/badge/Exchange-Binance%20Futures-F3BA2F?style=for-the-badge&logo=binance&logoColor=black)](https://binance.com)
[![CI Build](https://img.shields.io/badge/CI%2FCD-Passing%20%7C%201297%20Tests-22c55e?style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/Rukawua26/Pbot-V5-StudioAI/actions)
[![Coverage](https://img.shields.io/badge/Test%20Coverage-78%25%20Verified-0ea5e9?style=for-the-badge&logo=codecov&logoColor=white)]()
[![Security Audit](https://img.shields.io/badge/Security-Pip--Audit%20Clean-10b981?style=for-the-badge&logo=securityscorecard&logoColor=white)]()

<br/>

```
[ Market Microstructure ] ──▶ [ Triple TF Engine (1H/5M/1M) ] ──▶ [ Multi-Agent Alpha ]
                                                                        │
[ Real-Time Cockpit BI ] ◀── [ Hardened Execution Router ] ◀── [ Dynamic Risk Governance ]
```

<p align="center">
  <b>Plataforma cuantitativa determinista de alta disponibilidad con motor multi-temporalidad (Triple Timeframe 1H/5M/1M), análisis de microestructura (CVD / Order Flow / Open Interest), gobernanza estricta de riesgo y Dashboard Cockpit interactivo.</b>
</p>

---

[Resumen Ejecutivo](#-resumen-ejecutivo) •
[Motor Triple Timeframe](#-motor-de-estrategia-triple-timeframe-1h--5m--1m) •
[Arquitectura del Sistema](#-arquitectura-del-sistema) •
[Dashboard & Cockpit BI](#-dashboard-institucional--3-tf-cockpit) •
[Gobernanza de Riesgo](#-gobernanza-de-riesgo-y-seguridad-operativa) •
[Despliegue & Operación](#-despliegue--operación) •
[CI/CD & Calidad](#-aseguramiento-de-calidad-y-validación)

---

</div>

## 📌 Resumen Ejecutivo

**Sniper AI** es una infraestructura cuantitativa modular de nivel institucional desarrollada para la ejecución autónoma de estrategias de trading en el mercado de derivados **Binance USDⓈ-M Futures**. Diseñada bajo los principios de **State-Locking, Determinismo Quirúrgico y Zero-Trust Execution**, la plataforma prioriza la preservación de capital, la colocación estricta de **Hard Stop Loss** en el exchange y el monitoreo continuo en vivo.

### Capacidades Nucleares

- **Motor Triple Timeframe (1H / 5M / 1M)**: Alineación estricta de 3 marcos temporales: Sesgo Macro 1H, Estructura & Pullback 5M y Gatillo 1M con corredor de protección **Anti-Chasing ($\pm 0.6\%$)**.
- **Dashboard Interactivo 3-TF Cockpit**: Interfaz de control en vivo basada en canvas de alta densidad (High-DPI 2D) con sincronización dinámica al hacer clic en los pares del Radar.
- **Clasificación Estocástica de Regímenes (HMM Markov)**: Filtro de régimen de mercado sobre Bitcoin (`BULLISH`, `BEARISH`, `RANGE`) con matrices de transición de probabilidad.
- **Microestructura & Order Flow (CVD / OI)**: Análisis de transacciones agresoras tick-a-tick (Cumulative Volume Delta) y variaciones de apalancamiento en Open Interest.
- **Gobernanza Cuantitativa de Riesgo**: Sizing adaptativo por ATR y balance, matriz de correlación cruzada, circuit breaker por drawdown diario y Hard Stop Loss obligatorio.
- **Aislamiento Estricto de Modos**: Separación garantizada entre `PAPER` (simulación virtual de $1,000), `SHADOW` (telemetría y aprendizaje observacional) y `REAL` (autenticación HMAC con firma de claves y permisos Futures).

---

## 📐 Motor de Estrategia Triple Timeframe (1H / 5M / 1M)

El motor principal `triple_tf` opera mediante una cadena jerárquica de decisión que elimina las entradas impulsivas y garantiza una alta esperanza matemática:

```text
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                                TRIPLE TIMEFRAME DECISION CHAIN                       │
│                                                                                      │
│   [ MARCO 1H: SESGO MACRO ]                                                          │
│   Determina la dirección dominante (BUY / SELL / NEUTRAL) evaluando la posición del  │
│   precio respecto a la EMA 50 1H y filtros de mechas de rechazo.                     │
│         │                                                                            │
│         ▼ (Si 1H es BUY o SELL)                                                      │
│   [ MARCO 5M: ESTRUCTURA & PULLBACK ]                                                │
│   Verifica la ruptura de estructura (MSS) y el retroceso/toque a la EMA 50 5M.      │
│   Establece el Stop Loss sugerido en el Swing High / Swing Low.                      │
│         │                                                                            │
│         ▼ (Si 5M confirma Setup)                                                     │
│   [ MARCO 1M: GATILLO & ANTI-CHASING ]                                               │
│   Confirma el rebote o cruce favorable en 1M dentro del corredor de protección       │
│   Anti-Chasing (máximo ±0.6% de distancia a la EMA 50 1M).                           │
│         │                                                                            │
│         ▼ (Alineación Completa de los 3 Marcos)                                      │
│   [ VEREDICTO FINAL: 🚀 EJECUTABLE ] ──▶ Disparo de Orden + Hard Stop Loss           │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Marco 1H (Sesgo Dominante)**: Si el precio está por encima de la EMA 50 1H y la pendiente es positiva, se establece sesgo `BUY`. Si está por debajo, `SELL`. Si existe rechazo por mechas contra la tendencia, se declara `NEUTRAL` y se aborta el ciclo para evitar operar contra la fuerza macro.
2. **Marco 5M (Estructura y Retroceso)**: Valida la presencia de un toque de retroceso a la EMA 50 5M tras una confirmación de estructura. Calcula el nivel óptimo de Stop Loss en el último extremo (Swing).
3. **Marco 1M (Gatillo Preciso & Anti-Chasing)**: Exige la confirmación de giro en 1M y verifica que el precio no haya extendido más de un **$0.6\%$** respecto a la EMA 50 1M, previniendo el "chasing" (comprar techos o vender suelos).

---

## 🏛️ Arquitectura del Sistema

El flujo de procesamiento opera como una tubería determinista desacoplada, garantizando que ninguna orden se envíe al exchange sin la validación previa de todas las capas de seguridad y riesgo.

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 MARKET DATA INGESTION                                  │
│   Binance Futures WebSocket (Mark Price / Tickers / Klines) + REST API (Open Interest) │
│   WebSocket AggTrade Stream (Order Flow / Cumulative Volume Delta - CVD)               │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              MARKET REGIME & INTELLIGENCE                              │
│   Hidden Markov Model (HMM) ──▶ Probabilidades de Transición [BULL / BEAR / RANGE]     │
│   Dynamic Liquidity Guard   ──▶ Spread Filter + 30-Pair Real-Time Triage Matrix        │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              TRIPLE TIMEFRAME STRATEGY ENGINE                          │
│   ┌────────────────────────┬─────────────────────────┬─────────────────────────────┐   │
│   │ 1H Macro Bias (EMA 50) │ 5M Structure & Pullback │ 1M Trigger & Anti-Chasing   │   │
│   └────────────────────────┴─────────────────────────┴─────────────────────────────┘   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        QUANTITATIVE RISK ENGINE & GOVERNANCE                           │
│   • Pairwise Correlation Matrix (Veto a sobreexposición > 0.80)                        │
│   • Open Interest Delta Filter (Protección contra Squeezes y Liquidaciones)            │
│   • Sizing Adaptativo por Volatilidad (ATR) y Drawdown Diario UTC Circuit Breaker      │
│   • Hard Stop Loss Pre-Execution Calculation & Trailing Stop Invariants                │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              EXECUTION ROUTER & TELEMETRY                              │
│   ┌────────────────────────────────────────┬───────────────────────────────────────┐   │
│   │ LIVE EXECUTION ADAPTER (REAL / PAPER)  │ SHADOW EXECUTION LAB (Virtual Sandbox)│   │
│   └────────────────────────────────────────┴───────────────────────────────────────┘   │
│   Atomic Guardian Vigilance ──▶ Emergency Market Close ──▶ State Reconciler            │
│   3-TF Cockpit Dashboard (FastAPI / Node.js) + Telegram Control + Recovery Drill       │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🖥️ Dashboard Institucional & 3-TF Cockpit

El sistema incluye una consola de monitoreo web interactiva con 4 vistas principales:

1. ⚡ **Terminal & Operaciones**: Métricas de balance (Equity, PnL No Realizado, PnL Diario), estado del Circuit Breaker, posiciones abiertas con botón de cierre de emergencia y consola de comandos en tiempo real.
2. 🎯 **Radar de Pares (Top 10 / 30)**: Matriz de liquidez ordenada en tiempo real. **Al hacer clic en cualquier fila de la tabla Radar, el dashboard conmuta automáticamente al visor 3-TF Cockpit sincronizado con ese par.**
3. 📈 **Cockpit Triple TF**: Visor simultáneo de **3 gráficos Canvas HTML5 (1H, 5M, 1M)** renderizando velas, EMA 50 y la franja verde del corredor **Anti-Chasing ($\pm 0.6\%$)**, junto a un banner de veredicto final (`EJECUTABLE` / `EN ESPERA`).
4. 📊 **Historial & Equity**: Registro detallado de operaciones cerradas, auditoría PnL paginada, exportación CSV y gráfico de curva de equidad.

---

## 🛡️ Gobernanza de Riesgo y Seguridad Operativa

> **Invariante Nuclear:** *El exchange es la única fuente de verdad para posiciones reales. Ninguna posición en modo REAL puede permanecer descubierta sin un `HARD STOP LOSS` activo en Binance Futures.*

```text
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                                ESTADOS DEL TRADE EN RUNTIME                          │
│                                                                                      │
│   [PENDING_SEND]                                                                     │
│         │                                                                            │
│         ▼                                                                            │
│   [PENDING_EXCHANGE_OPEN] ──▶ ACK de Orden Confirmado por Exchange                   │
│         │                                                                            │
│         ▼                                                                            │
│   [ENTRY_FILLED_AWAITING_POSITION_SYNC] ──▶ Reconciliación Inmediata con Wallet     │
│         │                                                                            │
│         ▼                                                                            │
│   [OPEN (HARD SL CONFIRMADO)] ──▶ Hard Stop Loss Activo en el Orderbook              │
│         │                                                                            │
│         ▼                                                                            │
│   [CLOSING_INITIATED] ──▶ Cierre por TP / Trailing SL / Emergency Fail-Safe          │
│         │                                                                            │
│         ▼                                                                            │
│   [CLOSED (FLAT)] ──▶ Auditoría JSONL + Reconciliación de Balance Final              │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### Reglas Preventivas Operativas

- **Orden Ascendente de Locks (Prevención de Deadlocks)**:
  `bot.lock` < `execution._exchange_call_lock` < `execution._account_lock` < `shadow._lock` < `bot.db_lock` < `bot.price_lock`
- **Límite de Stop Loss Extremo**: Guardrail de `MAX_ENTRY_SL_PCT = 3.0%`. Ninguna entrada se ejecutará con un SL porcentual superior a este límite.
- **Protección contra Pass Silenciosos**: Bloqueo estricto por CI mediante `tools/check_no_silent_pass.py`. Ningún bloque `try/except` en `core/` puede contener `pass` sin manejo o log explícito.

---

## 🚀 Despliegue & Operación

### 1. Requisitos Previos

- **Python**: 3.12+ con entorno virtual local (`./.venv/`)
- **Node.js**: (Opcional) v18+ para servidor estático de desarrollo
- **Binance API Keys**: (Requerido solo para modo `REAL`) Claves con permisos de **Futures Trading** habilitados.

### 2. Instalación

```bash
# Clonar el repositorio
git clone https://github.com/Rukawua26/Pbot-V5-StudioAI.git
cd Pbot-V5-StudioAI

# Crear e inicializar el entorno virtual Python
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias exactas del lockfile
./.venv/bin/python -m pip install -r requirements.lock -r requirements-dev.lock
```

### 3. Configuración (`.env`)

Copia el archivo de ejemplo e ingresa tus credenciales y parámetros de riesgo:

```bash
cp .env.example .env
```

Parámetros clave recomendados:

```ini
PAPER_MODE=true
ALLOW_REAL_TRADING=false
STRATEGY_ENGINE=triple_tf
TOP_TRIAGE_COUNT=10
SNIPER_API_KEY=sniper_secret_key_local_12345
```

### 4. Ejecución del Bot & Dashboard

```bash
# Opción A: Ejecución Principal del Bot
./.venv/bin/python main.py

# Opción B: Dashboard Servidor API (FastAPI en Producción)
SNIPER_DISABLE_FILE_TELEMETRY=1 ./.venv/bin/python tools/dashboard_api_server.py

# Opción C: Dashboard Servidor Node.js (Modo Dev / Demo)
node server.js
```

---

## 🧪 Aseguramiento de Calidad y Validación

El repositorio cuenta con una suite completa de validación que garantiza la estabilidad del runtime crítico antes de cada commit:

```bash
# 1. Verificación de dependencias
./.venv/bin/python -m pip check

# 2. Compilación de código bytecode
./.venv/bin/python -m compileall -q main.py core tools

# 3. Linter y formato con Ruff
./.venv/bin/ruff check core/ tests/ tools/
./.venv/bin/ruff format --check core/ tests/ tools/

# 4. Verificación de tipos con Mypy
MYPYPATH=. ./.venv/bin/mypy --explicit-package-bases core/config/ core/types.py core/bot_facade.py core/execution_adapters.py

# 5. Smoke de imports modulares
PYTHON_BIN=./.venv/bin/python bash scripts/smoke_modular_imports.sh

# 6. Detección de pass silenciosos
./.venv/bin/python tools/check_no_silent_pass.py

# 7. Validación de contratos arquitectónicos
SNIPER_DISABLE_FILE_TELEMETRY=1 ./.venv/bin/python tools/regression_contracts.py

# 8. Matriz de Simulación de Caos (8 escenarios)
SNIPER_DISABLE_FILE_TELEMETRY=1 ./.venv/bin/python tools/chaos_matrix.py

# 9. Drill de Recuperación de Posiciones Huérfanas (3 escenarios)
SNIPER_DISABLE_FILE_TELEMETRY=1 ./.venv/bin/python tools/recovery_drill.py

# 10. Suite Completa de Pruebas Unitarias (1,297 Tests)
SNIPER_DISABLE_FILE_TELEMETRY=1 ./.venv/bin/python -m unittest discover -s tests -p "test_*.py"

# 11. Cobertura de Código
SNIPER_DISABLE_FILE_TELEMETRY=1 ./.venv/bin/python -m coverage run -m unittest discover -s tests -p "test_*.py"
./.venv/bin/python -m coverage report --fail-under=75
```

---

## 📑 Gobernanza Técnica y Runbooks

Para más detalles técnicos sobre el funcionamiento del bot y sus componentes:
- 📖 [Memoria Técnica del Proyecto](docs/engineering/memoria-tecnica.md) — Registro de decisiones arquitectónicas y salvaguardas.
- 📋 [Mejoras Pendientes & Roadmap](docs/roadmap/mejoras-pendientes.md) — Estado de integraciones y funciones en desarrollo.
- 🤖 [Manual de Agentes (AGENTS.md)](AGENTS.md) — Reglas operativas e invariantes del sistema.

---

<div align="center">
  <sub>Desarrollado para ejecución cuantitativa segura en Binance Futures. © 2026 Sniper AI.</sub>
</div>
