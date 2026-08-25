# 🤖 SNIPER AI v119 - Technical Roadmap & System Manual

Este documento es la guía maestra de arquitectura, lógica y despliegue de **Sniper AI**, un bot de trading cuantitativo avanzado para Binance Futures.

---

## 🗺️ 1. Visión General y Roadmap Arquitectónico

Sniper AI no es un simple script de señales; es un ecosistema de ejecución determinista diseñado para minimizar el riesgo humano y maximizar la captura de tendencias mediante el consenso de múltiples agentes de IA.

### Flujo de Datos (Pipeline de Ejecución)
1. **Triaje Dinámico (Radar):** Escaneo masivo de pares $\rightarrow$ Filtro de Liquidez $\rightarrow$ Filtro de Spread $\rightarrow$ Top 50 candidatos.
2. **Análisis Multitemporal:** Descarga de velas 1H y 4H $\rightarrow$ Cálculo de indicadores técnicos (EMA, RSI, ADX, ATR).
3. **Consenso Trinity:**
   - **MT (Market Trend):** Análisis de tendencia macro.
   - **SR (Support/Resistance):** Identificación de zonas estructurales.
   - **G (Ghost/ML):** Predicción basada en modelos de Machine Learning.
4. **Capa de Validación (RAG + SHOCK):**
   - **RAG:** Búsqueda de patrones similares en el historial para validar la probabilidad.
   - **SHOCK:** Filtro de "espacio operativo" (evita entrar si el precio ya se movió demasiado).
5. **Ejecución & Gestión:** Apertura de posición $\rightarrow$ Gestión dinámica via **Guardian** (Trailing ATR $\rightarrow$ Exit por Degradación de Confianza).

---

## ⚙️ 2. Desglose de Módulos (¿Qué hace cada parte?)

### `core/` (El Cerebro)
- **`bot_app.py`**: El corazón del sistema. Orquestador que inicia los hilos de escaneo, el guardián y la conexión con Telegram.
- **`bot_guardian.py`**: El "vigilante". Monitorea los trades abiertos cada pocos segundos para mover el Stop Loss a Break-Even o ejecutar el Trailing Stop basado en ATR.
- **`bot_signals.py`**: Implementa la lógica de escaneo. Decide qué pares pasan el triaje y cuáles llegan a la fase de ejecución.
- **`bot_telemetry.py`**: Recolector de métricas. Calcula el Win Rate, PnL diario y salud del sistema.
- **`execution_service.py`**: Capa de abstracción para Binance. Maneja el envío de órdenes, validación de balances y errores de API.
- **`execution_adapters.py`**: Permite cambiar entre modo `REAL` (dinero real) y `SHADOW` (simulación exacta con latencia y rechazos simulados).
- **`risk_engine.py`**: Calcula el tamaño de la posición (`Sizing`) basándose en el riesgo por trade y el ATR actual.

### `core/config/` (La Consola de Control)
- **`strategy.py`**: Configuración de la estrategia (Multiplicadores de ATR, niveles de confianza de la IA, gestión de TP/SL).
- **`operational.py`**: Parámetros de infraestructura (Timeouts de API, límites de escaneo, configuración del Watchdog).
- **`manager.py`**: Umbrales unificados para diferenciar el comportamiento entre modo Shadow y modo Real.

### `strategy/` (Lógica de Análisis)
- **`agents/`**: Contiene los agentes especializados (Breakout, Trend, etc.) que votan la dirección del mercado.

---

## 📈 3. Estrategia de Trading: El Método Trinity v119

La estrategia se basa en la **confluencia**. No entra si un solo indicador lo dice, sino cuando hay consenso.

### Componentes Clave:
1. **Consenso Trinity:** Se requiere que la tendencia (MT), la estructura (SR) y la IA (G) coincidan en la dirección.
2. **Sello RAG (Retrieval Augmented Generation):** El bot busca en su base de datos `sniper_brain.db` trades pasados con condiciones similares. Si el historial dice que ese patrón falló el 80% de las veces, el bot veta la entrada.
3. **Filtro SHOCK:** Mide la distancia al siguiente nivel de soporte/resistencia. Si el "salto" es demasiado corto, no hay espacio para ganar $\rightarrow$ Veto.
4. **Salida Dinámica (The ATR Way):**
   - **No hay TPs fijos:** El bot no cierra la posición en un % exacto.
   - **Trailing ATR:** A medida que el precio sube, el Stop Loss lo sigue a una distancia de $X \times ATR$. Esto permite "surfear" tendencias masivas.
   - **Degraded Confidence:** Si la IA detecta que la probabilidad de éxito ha caído por debajo de un umbral, cierra el trade inmediatamente aunque no haya tocado el SL.

---

## 🛠️ 4. Guía de Configuración y Dependencias

### Requisitos del Sistema
- **OS:** Linux (Recomendado: Ubuntu 22.04+ o Debian) para soporte completo de `systemd`.
- **Python:** 3.10 o superior.
- **Hardware Mínimo:** 2GB RAM, 1 vCPU (Suficiente para modo Shadow/Real).

### Dependencias Críticas
El bot utiliza:
- `pandas` y `numpy`: Para el análisis matemático de velas.
- `python-binance`: Para la comunicación con el exchange.
- `sqlite3`: Base de datos local para memoria a largo plazo y telemetría.
- `scikit-learn` / `xgboost`: Para los modelos de predicción de la IA.

---

## 🚀 5. Instalación en VPS / Nueva PC (Paso a Paso)

### 1. Preparación del Entorno
```bash
# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependencias de sistema
sudo apt install python3-pip python3-venv git -y
```

### 2. Clonación y Entorno Virtual
```bash
git clone https://github.com/Rukawua26/Pbot-V5ARCH-DEV.git
cd Pbot-V5ARCH-DEV
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuración de Secretos
Crea un archivo `.env` en la raíz con:
- `BINANCE_API_KEY`: Tu clave de API.
- `BINANCE_API_SECRET`: Tu secreto de API.
- `TELEGRAM_TOKEN`: Token del bot de Telegram.
- `TELEGRAM_CHAT_ID`: Tu ID de chat para recibir alertas.
- `EXECUTION_BACKEND`: `real` o `shadow_live`.

### 4. Despliegue como Servicio (VPS)
Para que el bot nunca se apague y reinicie solo tras un crash:
```bash
sudo cp sniper-ai.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sniper-ai.service
sudo systemctl start sniper-ai.service
```

---

## 📱 6. Operación y Mantenimiento

### Comandos Maestros (Telegram)
- `/status`: Verifica que el bot esté vivo y escaneando.
- `/targets`: Mira qué monedas están en el radar de la IA.
- `/audit_report`: Analiza los últimos 100 trades para detectar fallos.
- `/rebase_capital`: Sincroniza el balance local con el de Binance.

### Mantenimiento Preventivo
- **Logs:** Revisa `logs/sniper.log` para errores generales.
- **Eventos:** Consulta `logs/execution_events.jsonl` para auditoría de órdenes.
- **DB:** La base de datos `sniper_brain.db` debe respaldarse periódicamente.
