import express from 'express';
import cors from 'cors';
import cookieParser from 'cookie-parser';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;
const HOST = '0.0.0.0';

app.use(cors());
app.use(express.json());
app.use(cookieParser());

// Static files directory
const staticDir = path.join(__dirname, 'dashboard', 'static');
app.use(express.static(staticDir));

// In-Memory Simulation State
const botState = {
  mode: 'SHADOW',
  balance: 10452.80,
  initial_balance: 10000.00,
  daily_pnl_pct: 2.34,
  is_paused: false,
  halt_system_active: false,
  circuit_breaker_active: false,
  ws_reconciliation_in_progress: false,
  active_trades_count: 2,
  shadow_trades_count: 4,
  scanner_pairs: 28,
  sentiment: 'BULLISH',
  sentiment_color: 'green',
  telemetry: {
    shadow_win_rate: 68.9,
    real_win_rate: 71.4,
    api_weight_used: 120,
    api_weight_max: 1200,
    cpu_pct: 12.4,
    ram_mb: 248.5
  },
  active_trades: [
    { symbol: 'BTCUSDT', side: 'BUY', entry_price: 64230.50, current_price: 64890.00, size: 500.0, pnl_pct: 1.03, confidence: 88, is_shadow: 0, reason: 'Trend Continuation' },
    { symbol: 'ETHUSDT', side: 'BUY', entry_price: 3450.20, current_price: 3498.40, size: 350.0, pnl_pct: 1.40, confidence: 82, is_shadow: 0, reason: 'Breakout S/R' }
  ],
  shadow_trades: [
    { symbol: 'SOLUSDT', side: 'BUY', entry_price: 154.20, current_price: 158.10, size: 250.0, pnl_pct: 2.53, confidence: 91, is_shadow: 1, reason: 'Volume Impulse' },
    { symbol: 'AVAXUSDT', side: 'SELL', entry_price: 28.90, current_price: 28.25, size: 200.0, pnl_pct: 2.25, confidence: 79, is_shadow: 1, reason: 'Mean Reversion' },
    { symbol: 'NEARUSDT', side: 'BUY', entry_price: 4.85, current_price: 4.92, size: 180.0, pnl_pct: 1.44, confidence: 75, is_shadow: 1, reason: 'MTF Confluence' },
    { symbol: 'LINKUSDT', side: 'BUY', entry_price: 12.40, current_price: 12.55, size: 220.0, pnl_pct: 1.21, confidence: 84, is_shadow: 1, reason: 'Ghost Model Pick' }
  ],
  radar: [
    { symbol: 'BTCUSDT', signal: 'BUY', prob: 0.88, result: 'Ejecutable', btc_regime: 'TRENDING_BULL', rsi: 58.4, trend: 'UP', volume_rel: 85, volatility_atr: 62, adx: 34.5 },
    { symbol: 'ETHUSDT', signal: 'BUY', prob: 0.82, result: 'Ejecutable', btc_regime: 'TRENDING_BULL', rsi: 61.2, trend: 'UP', volume_rel: 78, volatility_atr: 58, adx: 29.8 },
    { symbol: 'SOLUSDT', signal: 'BUY', prob: 0.91, result: 'Ejecutable', btc_regime: 'TRENDING_BULL', rsi: 64.0, trend: 'UP', volume_rel: 92, volatility_atr: 75, adx: 38.2 },
    { symbol: 'BNBUSDT', signal: 'WAIT', prob: 0.54, result: 'ADX 18.2 < 22.0', btc_regime: 'TRENDING_BULL', rsi: 49.5, trend: 'NEUTRAL', volume_rel: 44, volatility_atr: 35, adx: 18.2 },
    { symbol: 'XRPUSDT', signal: 'WAIT', prob: 0.49, result: 'volumen 0.42 < 1.00', btc_regime: 'TRENDING_BULL', rsi: 45.1, trend: 'DOWN', volume_rel: 42, volatility_atr: 48, adx: 21.0 },
    { symbol: 'ADAUSDT', signal: 'WAIT', prob: 0.45, result: 'solo 1/4 agentes', btc_regime: 'TRENDING_BULL', rsi: 43.8, trend: 'DOWN', volume_rel: 38, volatility_atr: 52, adx: 19.4 },
    { symbol: 'DOGEUSDT', signal: 'WAIT', prob: 0.38, result: 'RIESGO EXCESIVO (4.2% > 3.0%)', btc_regime: 'TRENDING_BULL', rsi: 52.3, trend: 'UP', volume_rel: 65, volatility_atr: 88, adx: 24.1 },
    { symbol: 'DOTUSDT', signal: 'WAIT', prob: 0.51, result: 'ADX 19.5 < 22.0', btc_regime: 'TRENDING_BULL', rsi: 47.9, trend: 'NEUTRAL', volume_rel: 46, volatility_atr: 40, adx: 19.5 },
    { symbol: 'MATICUSDT', signal: 'WAIT', prob: 0.40, result: 'volumen 0.55 < 1.00', btc_regime: 'TRENDING_BULL', rsi: 42.0, trend: 'DOWN', volume_rel: 55, volatility_atr: 49, adx: 17.8 },
    { symbol: 'AVAXUSDT', signal: 'SELL', prob: 0.79, result: 'Ejecutable', btc_regime: 'TRENDING_BULL', rsi: 38.6, trend: 'DOWN', volume_rel: 81, volatility_atr: 68, adx: 31.4 },
    { symbol: 'NEARUSDT', signal: 'BUY', prob: 0.75, result: 'Ejecutable', btc_regime: 'TRENDING_BULL', rsi: 57.1, trend: 'UP', volume_rel: 76, volatility_atr: 70, adx: 28.6 },
    { symbol: 'LINKUSDT', signal: 'BUY', prob: 0.84, result: 'Ejecutable', btc_regime: 'TRENDING_BULL', rsi: 59.8, trend: 'UP', volume_rel: 84, volatility_atr: 56, adx: 32.0 }
  ]
};

// Config state populated from .env.example definitions
const envConfigMap = {
  // FILTERS
  'EMA_ALIGNMENT_FILTER_ENABLED': { value: 'true', active: true, category: 'FILTERS', type: 'boolean', desc: 'Filtro de alineación de medias exponenciales para confirmar estructura de tendencia limpia' },
  'OI_FILTER_ENABLED': { value: 'true', active: true, category: 'FILTERS', type: 'boolean', desc: 'Filtro de Open Interest para descartar trampas de liquidez institucional' },
  'CVD_FILTER_ENABLED': { value: 'true', active: true, category: 'FILTERS', type: 'boolean', desc: 'Filtro de Cumulative Volume Delta para verificar absorción y presión compradora/vendedora' },
  'MTF_FILTER_ENABLED': { value: 'true', active: true, category: 'FILTERS', type: 'boolean', desc: 'Filtro Multi-Timeframe con confluencia obligatoria en 1h, 15m y 5m' },
  'GLOBAL_FEAR_GREED_FILTER_ENABLED': { value: 'true', active: true, category: 'FILTERS', type: 'boolean', desc: 'Veto preventivo cuando el índice de miedo y codicia cae en pánico extremo' },
  'GLOBAL_BTC_DOM_FILTER_ENABLED': { value: 'true', active: true, category: 'FILTERS', type: 'boolean', desc: 'Filtro de dominancia de BTC para proteger entradas en Altcoins' },
  'CORRELATION_RISK_ENABLED': { value: 'true', active: true, category: 'FILTERS', type: 'boolean', desc: 'Control de correlación cruzada para evitar sobreexposición en pares del mismo clúster' },
  'FVG_TRACKER_ENABLED': { value: 'true', active: true, category: 'FILTERS', type: 'boolean', desc: 'Rastreador y alerta de Fair Value Gaps activos' },
  'BULL_TREND_ALIGNED_REAL_ENABLED': { value: 'true', active: true, category: 'FILTERS', type: 'boolean', desc: 'Solo permite operaciones reales cuando el régimen macro es alcista' },
  'REGIME_TUNING_ENABLED': { value: 'true', active: true, category: 'FILTERS', type: 'boolean', desc: 'Calibración dinámica de parámetros de riesgo según el régimen detectado por HMM' },
  'EMA_SLOPE_FILTER_ENABLED': { value: 'true', active: true, category: 'FILTERS', type: 'boolean', desc: 'Verificación de pendiente positiva de las EMAs antes de entrar en Long' },
  'SIGNAL_AGENT_OVERRIDE_ENABLED': { value: 'false', active: false, category: 'FILTERS', type: 'boolean', desc: 'Permite a agentes de alta confianza sobreescribir vetos menores' },
  
  // RISK
  'MAX_RISK_USD': { value: '50.00', active: true, category: 'RISK', type: 'number', desc: 'Límite monetario estricto de riesgo máximo en USD por posición' },
  'RISK_PER_TRADE_PERCENT': { value: '1.5', active: true, category: 'RISK', type: 'number', desc: 'Porcentaje máximo de la cuenta en riesgo por cada operación' },
  'MAX_ENTRY_SL_PCT': { value: '3.0', active: true, category: 'RISK', type: 'number', desc: 'Stop Loss máximo permitido al momento del cálculo de entrada' },
  'MAX_OPEN_TRADES': { value: '4', active: true, category: 'RISK', type: 'number', desc: 'Número máximo de posiciones abiertas simultáneamente en la cuenta' },
  'MAX_MARGIN_PERCENT': { value: '35.0', active: true, category: 'RISK', type: 'number', desc: 'Porcentaje máximo de margen de la cuenta utilizado en posiciones' },
  'STOP_LOSS_ATR_MODIFIER': { value: '1.8', active: true, category: 'RISK', type: 'number', desc: 'Multiplicador del indicador ATR para calcular la distancia del Hard SL' },
  'HARD_SL_ATTACH_MAX_RETRIES': { value: '3', active: true, category: 'RISK', type: 'number', desc: 'Reintentos máximos para anclar el Stop Loss de emergencia en el exchange' },
  'GLOBAL_FEAR_VETO_THRESHOLD': { value: '25.0', active: true, category: 'RISK', type: 'number', desc: 'Umbral de Fear & Greed por debajo del cual se bloquean nuevas entradas' },
  'SHOCK_MIN_DIST_PCT': { value: '0.15', active: true, category: 'RISK', type: 'number', desc: 'Distancia mínima en porcentaje para protección contra shock de volatilidad' },
  'MIN_NOTIONAL_VALUE': { value: '20.0', active: true, category: 'RISK', type: 'number', desc: 'Tamaño notional mínimo exigido por Binance Futures por orden' },

  // EXECUTION
  'ALLOW_REAL_TRADING': { value: 'false', active: false, category: 'EXECUTION', type: 'boolean', desc: 'Interruptor maestro para habilitar ejecución con saldo real en exchange' },
  'PAPER_MODE': { value: 'false', active: false, category: 'EXECUTION', type: 'boolean', desc: 'Modo puramente simulado en memoria sin llamadas a endpoints de orden' },
  'SHADOW_VALIDATION_ENABLED': { value: 'true', active: true, category: 'EXECUTION', type: 'boolean', desc: 'Modo Shadow Live que simula fills contra el orderbook real en milisegundos' },
  'EXECUTION_BACKEND': { value: 'binance_futures', active: true, category: 'EXECUTION', type: 'string', desc: 'Adaptador de ejecución conectado a Binance USD-M Futures' },
  'SMART_EXIT_THRESHOLD_REAL': { value: '0.72', active: true, category: 'EXECUTION', type: 'number', desc: 'Umbral de convicción para salidas dinámicas inteligentes en modo Real' },
  'SMART_EXIT_THRESHOLD_SHADOW': { value: '0.65', active: true, category: 'EXECUTION', type: 'number', desc: 'Umbral de convicción para salidas dinámicas en modo Shadow' },
  'USE_TESTNET': { value: 'false', active: false, category: 'EXECUTION', type: 'boolean', desc: 'Conectar a Binance Futures Testnet en vez de producción' },

  // SYSTEM
  'WATCHDOG_HEARTBEAT_PATH': { value: '/tmp/sniper_heartbeat.json', active: true, category: 'SYSTEM', type: 'string', desc: 'Ruta del archivo de latido inspeccionado por el supervisor systemd' },
  'SNIPER_DB_PATH': { value: 'data/sniper.db', active: true, category: 'SYSTEM', type: 'string', desc: 'Ruta del archivo SQLite donde persisten órdenes, estados y métricas' },
  'AUTO_MOBILE_REPORTS_ENABLED': { value: 'true', active: true, category: 'SYSTEM', type: 'boolean', desc: 'Emisión automática de reportes ejecutivos al canal de Telegram' },
  'TOP_TRIAGE_COUNT': { value: '5', active: true, category: 'SYSTEM', type: 'number', desc: 'Cantidad de pares con mejor scoring seleccionados por ciclo' },
  'GLOBAL_MARKET_PROVIDER_ENABLED': { value: 'true', active: true, category: 'SYSTEM', type: 'boolean', desc: 'Proveedor global de datos macroeconómicos y métricas de mercado' }
};

// Seed historical trades
const mockTrades = [];
const symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'AVAXUSDT', 'NEARUSDT', 'LINKUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT'];
const reasons = ['Trailing Stop', 'Hard SL Attached', 'Take Profit Dynamic', 'Time Limit Exit', 'Smart Exit Momentum', 'Breakeven Pullback'];
const now = Date.now();

for (let i = 0; i < 80; i++) {
  const tradeTime = new Date(now - (i * 3.5 * 3600 * 1000));
  const isWin = Math.random() > 0.31;
  const pnlPct = isWin ? +(Math.random() * 4.5 + 0.5).toFixed(2) : -(+(Math.random() * 2.2 + 0.3).toFixed(2));
  const pnlUsd = +(pnlPct * 5.0).toFixed(2);
  const sym = symbols[i % symbols.length];
  const isShadow = i === 3 || i === 12 ? 0 : 1;
  const reason = isWin 
    ? (pnlPct > 3 ? 'Trailing Stop' : 'Take Profit Dynamic') 
    : (pnlPct < -1.8 ? 'Hard SL Attached' : 'Smart Exit Momentum');

  mockTrades.push({
    id: 1000 + i,
    timestamp: tradeTime.toISOString().replace('T', ' ').slice(0, 19),
    symbol: sym,
    side: Math.random() > 0.4 ? 'BUY' : 'SELL',
    entry_price: +(Math.random() * 100 + 20).toFixed(4),
    exit_price: +(Math.random() * 100 + 20).toFixed(4),
    pnl: pnlUsd,
    pnl_percent: pnlPct,
    reason: reason,
    exit_reason: reason,
    is_shadow: isShadow,
    confidence: Math.floor(Math.random() * 25 + 75),
    mfe_percent: +(Math.max(pnlPct, 0) + Math.random() * 1.5).toFixed(2),
    mae_percent: -(+(Math.abs(Math.min(pnlPct, 0)) + Math.random() * 0.8).toFixed(2))
  });
}

// Seed blocked events
const blockedEvents = [
  { ts: new Date(now - 120000).toISOString(), symbol: 'DOGEUSDT', side: 'BUY', reason: 'MAX_RISK_EXCEEDED (4.2% > 3.0%)', prob_final: 0.62, btc_regime: 'TRENDING_BULL', event_type: 'FILTER' },
  { ts: new Date(now - 450000).toISOString(), symbol: 'BNBUSDT', side: 'BUY', reason: 'ADX_BELOW_THRESHOLD (18.2 < 22.0)', prob_final: 0.54, btc_regime: 'TRENDING_BULL', event_type: 'FILTER' },
  { ts: new Date(now - 900000).toISOString(), symbol: 'XRPUSDT', side: 'SELL', reason: 'VOLUME_INSUFFICIENT (0.42x vol)', prob_final: 0.49, btc_regime: 'TRENDING_BULL', event_type: 'FILTER' },
  { ts: new Date(now - 1400000).toISOString(), symbol: 'ADAUSDT', side: 'BUY', reason: 'RANGE_VETO', prob_final: 0.45, btc_regime: 'RANGE_BOUND', event_type: 'RANGE_VETO' },
  { ts: new Date(now - 1900000).toISOString(), symbol: 'DOTUSDT', side: 'BUY', reason: 'MTF_VETO_1H_AGAINST', prob_final: 0.51, btc_regime: 'TRENDING_BULL', event_type: 'MTF_VETO' },
  { ts: new Date(now - 2500000).toISOString(), symbol: 'MATICUSDT', side: 'SELL', reason: 'MARKOV_BEAR_CONFIRMATION_FAIL', prob_final: 0.40, btc_regime: 'TRENDING_BULL', event_type: 'MARKOV_VETO' }
];

// Seed consensus rounds
const consensusRounds = [
  {
    round_id: 4201,
    timestamp: new Date(now - 60000).toISOString(),
    selected_pair: 'SOLUSDT',
    consensus_probability: 0.91,
    action: 'EXECUTED_SHADOW',
    agents: { breakout: 0.94, mean_reversion: 0.88, shock: 0.85, ghost_nn: 0.92 },
    regime: 'TRENDING_BULL'
  },
  {
    round_id: 4200,
    timestamp: new Date(now - 360000).toISOString(),
    selected_pair: 'ETHUSDT',
    consensus_probability: 0.82,
    action: 'EXECUTED_REAL',
    agents: { breakout: 0.86, mean_reversion: 0.78, shock: 0.80, ghost_nn: 0.84 },
    regime: 'TRENDING_BULL'
  },
  {
    round_id: 4199,
    timestamp: new Date(now - 720000).toISOString(),
    selected_pair: 'DOGEUSDT',
    consensus_probability: 0.62,
    action: 'VETOED_RISK',
    agents: { breakout: 0.65, mean_reversion: 0.58, shock: 0.60, ghost_nn: 0.63 },
    regime: 'TRENDING_BULL'
  }
];

// Seed equity points
const equityPoints = [];
let runningBal = 10000;
for (let d = 30; d >= 0; d--) {
  const pDate = new Date(now - d * 24 * 3600 * 1000);
  runningBal += (Math.random() * 45 - 12);
  equityPoints.push({
    ts: pDate.toISOString().slice(0, 10),
    balance: +runningBal.toFixed(2)
  });
}

// Routes
app.get('/', (req, res) => {
  res.sendFile(path.join(staticDir, 'index.html'));
});

app.get('/api/v1/health', (req, res) => {
  res.json({
    status: 'healthy',
    reason: 'OK',
    state_age_s: 0.8,
    ws_reconciliation_in_progress: botState.ws_reconciliation_in_progress,
    halt_system_active: botState.halt_system_active,
    circuit_breaker_active: botState.circuit_breaker_active,
    is_paused: botState.is_paused,
    timestamp: Date.now() / 1000
  });
});

app.get('/api/v1/state', (req, res) => {
  res.json({
    ...botState,
    state_age_s: 0.5
  });
});

app.get('/api/v1/consensus', (req, res) => {
  res.json({
    latest: consensusRounds[0],
    rounds: consensusRounds,
    total: consensusRounds.length,
    risk_summary: {
      halt_active: botState.halt_system_active,
      integrity_lock: false,
      circuit_breaker: botState.circuit_breaker_active,
      paused: botState.is_paused,
      ws_reconciliation_in_progress: botState.ws_reconciliation_in_progress
    },
    state_age_s: 0.5
  });
});

app.get('/api/v1/logs', (req, res) => {
  const linesCount = parseInt(req.query.lines) || 50;
  const logEntries = [
    `[INFO] ${new Date().toISOString().slice(0, 19)} - Radar scanner evaluated 28 candidate pairs`,
    `[INFO] ${new Date(now - 15000).toISOString().slice(0, 19)} - Consensus NN calculated probability matrix (SOLUSDT: 0.91, ETHUSDT: 0.82)`,
    `[INFO] ${new Date(now - 30000).toISOString().slice(0, 19)} - Shadow wallet balance updated: $${botState.balance.toFixed(2)} (+${botState.daily_pnl_pct}%)`,
    `[INFO] ${new Date(now - 45000).toISOString().slice(0, 19)} - Hard SL verified and active across all live positions`,
    `[INFO] ${new Date(now - 60000).toISOString().slice(0, 19)} - Heartbeat OK: Watchdog cycle 4201 completed in 42ms`,
    `[INFO] ${new Date(now - 75000).toISOString().slice(0, 19)} - MTF confluence: 1h Bullish, 15m Trend, 5m Trigger aligned`,
    `[INFO] ${new Date(now - 90000).toISOString().slice(0, 19)} - CVD delta positive: aggressive market buyers dominating orderbook`,
    `[INFO] ${new Date(now - 120000).toISOString().slice(0, 19)} - Risk Engine audit: Max Drawdown 1.8%, Sharpe 2.45, Margin ratio safe`
  ];
  res.json({ lines: logEntries.slice(0, linesCount) });
});

app.post('/api/v1/command', (req, res) => {
  const { action } = req.body;
  if (action === '/pause') {
    botState.is_paused = true;
  } else if (action === '/resume') {
    botState.is_paused = false;
  } else if (action === '/panic') {
    botState.halt_system_active = true;
    botState.is_paused = true;
  } else if (action === '/recover_halt') {
    botState.halt_system_active = false;
    botState.is_paused = false;
  }
  res.json({ ok: true, action });
});

app.get('/api/v1/trades', (req, res) => {
  const limit = parseInt(req.query.limit) || 100;
  const type = req.query.type || 'all';
  const date = req.query.date || '';

  let filtered = [...mockTrades];
  if (type === 'real') {
    filtered = filtered.filter(t => t.is_shadow === 0);
  } else if (type === 'shadow') {
    filtered = filtered.filter(t => t.is_shadow === 1);
  }

  if (date) {
    filtered = filtered.filter(t => t.timestamp.startsWith(date));
  }

  res.json({
    trades: filtered.slice(0, limit),
    total: filtered.length
  });
});

app.get('/api/v1/trades/daily-summary', (req, res) => {
  const date = req.query.date || new Date().toISOString().slice(0, 10);
  const type = req.query.type || 'all';
  
  let list = mockTrades.filter(t => t.timestamp.startsWith(date));
  if (type === 'real') list = list.filter(t => t.is_shadow === 0);
  if (type === 'shadow') list = list.filter(t => t.is_shadow === 1);

  if (list.length === 0) {
    list = mockTrades.slice(0, 12);
  }

  const total = list.length;
  const wins = list.filter(t => t.pnl_percent > 0).length;
  const losses = total - wins;
  const pnl_total = +list.reduce((acc, t) => acc + (t.pnl || 0), 0).toFixed(2);
  const avg_pnl = total > 0 ? +(list.reduce((acc, t) => acc + t.pnl_percent, 0) / total).toFixed(4) : 0;
  const winList = list.filter(t => t.pnl_percent > 0);
  const lossList = list.filter(t => t.pnl_percent <= 0);
  const avg_win = winList.length > 0 ? +(winList.reduce((acc, t) => acc + t.pnl_percent, 0) / winList.length).toFixed(4) : 0;
  const avg_loss = lossList.length > 0 ? +(lossList.reduce((acc, t) => acc + t.pnl_percent, 0) / lossList.length).toFixed(4) : 0;

  const reasonsMap = {};
  list.forEach(t => {
    const r = t.reason || 'OTHER';
    if (!reasonsMap[r]) reasonsMap[r] = { count: 0, wins: 0 };
    reasonsMap[r].count++;
    if (t.pnl_percent > 0) reasonsMap[r].wins++;
  });

  const reasons = Object.entries(reasonsMap).map(([k, v]) => ({
    reason: k,
    count: v.count,
    wins: v.wins
  }));

  const symbolsMap = {};
  list.forEach(t => {
    if (!symbolsMap[t.symbol]) symbolsMap[t.symbol] = { count: 0, sum_pnl: 0 };
    symbolsMap[t.symbol].count++;
    symbolsMap[t.symbol].sum_pnl += t.pnl_percent;
  });

  const symList = Object.entries(symbolsMap).map(([k, v]) => ({
    symbol: k,
    count: v.count,
    avg_pnl: +(v.sum_pnl / v.count).toFixed(4)
  }));

  res.json({
    date,
    total,
    wins,
    losses,
    win_rate: total > 0 ? +((wins / total) * 100).toFixed(1) : 0,
    avg_pnl,
    avg_win,
    avg_loss,
    pnl_total,
    hard_sl: list.filter(t => t.reason.includes('Hard SL')).length,
    trailing: list.filter(t => t.reason.includes('Trailing')).length,
    time_limit: list.filter(t => t.reason.includes('Time Limit')).length,
    avg_mfe: 2.85,
    avg_mae: -0.92,
    shadow_count: list.filter(t => t.is_shadow === 1).length,
    real_count: list.filter(t => t.is_shadow === 0).length,
    reasons,
    symbols: symList
  });
});

app.get('/api/v1/trades/calendar', (req, res) => {
  const year = parseInt(req.query.year) || new Date().getFullYear();
  const month = parseInt(req.query.month) || new Date().getMonth() + 1;
  const daysInMonth = new Date(year, month, 0).getDate();
  const days = [];

  for (let d = 1; d <= daysInMonth; d++) {
    const dayStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const dayTrades = mockTrades.filter(t => t.timestamp.startsWith(dayStr));
    const cnt = dayTrades.length || Math.floor(Math.random() * 4);
    const wins = Math.round(cnt * 0.7);
    const losses = cnt - wins;
    const pnl_total = +(cnt * (Math.random() * 30 + 5)).toFixed(2);
    const avg_pnl = cnt > 0 ? +(pnl_total / (cnt * 10)).toFixed(2) : 0;
    days.push({
      date: dayStr,
      count: cnt,
      wins,
      losses,
      pnl_total,
      avg_pnl,
      hard_sl: losses > 1 ? 1 : 0,
      win_rate: cnt > 0 ? +((wins / cnt) * 100).toFixed(1) : 0
    });
  }

  res.json({ year, month, days });
});

app.get('/api/v1/blocked', (req, res) => {
  const limit = parseInt(req.query.limit) || 100;
  const reason_counts = [
    { reason: 'MAX_RISK_EXCEEDED', count: 18 },
    { reason: 'ADX_BELOW_THRESHOLD', count: 15 },
    { reason: 'VOLUME_INSUFFICIENT', count: 11 },
    { reason: 'RANGE_VETO', count: 9 },
    { reason: 'MTF_VETO_1H_AGAINST', count: 7 },
    { reason: 'MARKOV_REGIME_CONFLICT', count: 5 }
  ];
  res.json({
    blocked: blockedEvents.slice(0, limit),
    total: blockedEvents.length,
    reason_counts
  });
});

app.get('/api/v1/trade-stats', (req, res) => {
  const total = mockTrades.length + 393;
  const wins = Math.round(total * 0.689);
  const losses = total - wins;
  res.json({
    total,
    wins,
    losses,
    win_rate: 68.9,
    avg_win_pct: '2.64',
    avg_loss_pct: '-1.12',
    profit_factor: 2.18,
    shadow: 471,
    real: 2,
    exit_reasons: [
      { reason: 'Trailing Stop', count: 215, wins: 202, losses: 13, avg_pnl_pct: 3.12 },
      { reason: 'Take Profit Dynamic', count: 134, wins: 124, losses: 10, avg_pnl_pct: 2.45 },
      { reason: 'Smart Exit Momentum', count: 68, wins: 0, losses: 68, avg_pnl_pct: -0.85 },
      { reason: 'Hard SL Attached', count: 38, wins: 0, losses: 38, avg_pnl_pct: -2.10 },
      { reason: 'Time Limit Exit', count: 18, wins: 0, losses: 18, avg_pnl_pct: -0.40 }
    ]
  });
});

app.get('/api/v1/equity', (req, res) => {
  res.json({
    points: equityPoints
  });
});

app.get('/api/v1/exec-events', (req, res) => {
  const limit = parseInt(req.query.event_limit) || 200;
  res.json({
    events: blockedEvents.slice(0, limit),
    total: blockedEvents.length
  });
});

// INTELLIGENCE & CORRELATION MATRIX
app.get('/api/v1/intelligence/correlation', (req, res) => {
  const activePairSymbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'AVAXUSDT', 'NEARUSDT', 'LINKUSDT'];
  const allSymbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'AVAXUSDT', 'NEARUSDT', 'LINKUSDT', 'BNBUSDT', 'XRPUSDT', 'DOGEUSDT'];
  
  // Realistically modeled correlation matrix
  const matrixData = {
    'BTCUSDT': { 'BTCUSDT': 1.00, 'ETHUSDT': 0.89, 'SOLUSDT': 0.82, 'AVAXUSDT': 0.78, 'NEARUSDT': 0.74, 'LINKUSDT': 0.81, 'BNBUSDT': 0.69, 'XRPUSDT': 0.48, 'DOGEUSDT': 0.58 },
    'ETHUSDT': { 'BTCUSDT': 0.89, 'ETHUSDT': 1.00, 'SOLUSDT': 0.84, 'AVAXUSDT': 0.81, 'NEARUSDT': 0.77, 'LINKUSDT': 0.85, 'BNBUSDT': 0.71, 'XRPUSDT': 0.51, 'DOGEUSDT': 0.61 },
    'SOLUSDT': { 'BTCUSDT': 0.82, 'ETHUSDT': 0.84, 'SOLUSDT': 1.00, 'AVAXUSDT': 0.86, 'NEARUSDT': 0.83, 'LINKUSDT': 0.79, 'BNBUSDT': 0.65, 'XRPUSDT': 0.46, 'DOGEUSDT': 0.67 },
    'AVAXUSDT': { 'BTCUSDT': 0.78, 'ETHUSDT': 0.81, 'SOLUSDT': 0.86, 'AVAXUSDT': 1.00, 'NEARUSDT': 0.88, 'LINKUSDT': 0.76, 'BNBUSDT': 0.62, 'XRPUSDT': 0.44, 'DOGEUSDT': 0.63 },
    'NEARUSDT': { 'BTCUSDT': 0.74, 'ETHUSDT': 0.77, 'SOLUSDT': 0.83, 'AVAXUSDT': 0.88, 'NEARUSDT': 1.00, 'LINKUSDT': 0.75, 'BNBUSDT': 0.59, 'XRPUSDT': 0.42, 'DOGEUSDT': 0.65 },
    'LINKUSDT': { 'BTCUSDT': 0.81, 'ETHUSDT': 0.85, 'SOLUSDT': 0.79, 'AVAXUSDT': 0.76, 'NEARUSDT': 0.75, 'LINKUSDT': 1.00, 'BNBUSDT': 0.68, 'XRPUSDT': 0.49, 'DOGEUSDT': 0.55 },
    'BNBUSDT': { 'BTCUSDT': 0.69, 'ETHUSDT': 0.71, 'SOLUSDT': 0.65, 'AVAXUSDT': 0.62, 'NEARUSDT': 0.59, 'LINKUSDT': 0.68, 'BNBUSDT': 1.00, 'XRPUSDT': 0.41, 'DOGEUSDT': 0.49 },
    'XRPUSDT': { 'BTCUSDT': 0.48, 'ETHUSDT': 0.51, 'SOLUSDT': 0.46, 'AVAXUSDT': 0.44, 'NEARUSDT': 0.42, 'LINKUSDT': 0.49, 'BNBUSDT': 0.41, 'XRPUSDT': 1.00, 'DOGEUSDT': 0.53 },
    'DOGEUSDT': { 'BTCUSDT': 0.58, 'ETHUSDT': 0.61, 'SOLUSDT': 0.67, 'AVAXUSDT': 0.63, 'NEARUSDT': 0.65, 'LINKUSDT': 0.55, 'BNBUSDT': 0.49, 'XRPUSDT': 0.53, 'DOGEUSDT': 1.00 }
  };

  // Detected extreme correlations (> 0.80)
  const extremeAlerts = [
    {
      pairA: 'BTCUSDT',
      pairB: 'ETHUSDT',
      corr: 0.89,
      risk_level: 'CRITICAL',
      status: 'HIGH_CO_RISK',
      description: 'Correlación extrema (+0.89). Ambas posiciones en LONG generan doble exposición direccional de beta.',
      action: 'CORRELATION_RISK_GUARD: Limitar sizing de la 2ª posición a un 50% de notional.'
    },
    {
      pairA: 'AVAXUSDT',
      pairB: 'NEARUSDT',
      corr: 0.88,
      risk_level: 'HIGH',
      status: 'EXTREME_CLUSTER',
      description: 'Correlación (+0.88) en clúster L1. Si AVAX está en SHORT y NEAR en LONG actúa como hedge parcial pero con fricción de fees.',
      action: 'REDUCTION_RECOMMENDED: Monitorear divergencia de momentum.'
    },
    {
      pairA: 'SOLUSDT',
      pairB: 'AVAXUSDT',
      corr: 0.86,
      risk_level: 'HIGH',
      status: 'HIGH_CO_RISK',
      description: 'Alta correlación L1 (+0.86). Alta sensibilidad a movimientos de liquidación rápida.',
      action: 'MONITORING: Hard Stop Losses activos a 1.8 ATR requeridos.'
    },
    {
      pairA: 'ETHUSDT',
      pairB: 'LINKUSDT',
      corr: 0.85,
      risk_level: 'HIGH',
      status: 'SECTOR_OVERLAP',
      description: 'Correlación (+0.85) en ecosistema Ethereum / DeFi.',
      action: 'SECTOR_GUARD: Sizing ponderado por volatilidad aplicado.'
    }
  ];

  res.json({
    active_pairs: activePairSymbols,
    all_pairs: allSymbols,
    matrix: matrixData,
    extreme_alerts: extremeAlerts,
    portfolio_metrics: {
      diversification_score: 64,
      avg_portfolio_corr: 0.81,
      peak_pair_corr: 0.89,
      total_active_exposure_usd: 1500.0,
      risk_engine_status: 'GUARD_ACTIVE',
      overexposure_detected: true
    }
  });
});

app.get('/api/v1/intelligence/regimes', (req, res) => {
  // Generate 24h hourly historical regime probabilities for stacked area chart
  const now = Date.now();
  const history_24h = [];
  const hours = 24;
  for (let i = hours; i >= 0; i--) {
    const t = new Date(now - i * 3600 * 1000);
    const hourLabel = t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    // Smooth probabilistic transition simulation representing HMM state distribution
    const progress = (hours - i) / hours;
    let bull = 0.55 + 0.22 * Math.sin(progress * Math.PI * 1.5) + (Math.random() * 0.05 - 0.025);
    let bear = 0.20 - 0.10 * Math.sin(progress * Math.PI * 1.2) + (Math.random() * 0.04 - 0.02);
    let side = 0.25 - 0.12 * Math.sin(progress * Math.PI * 1.8) + (Math.random() * 0.04 - 0.02);
    bull = Math.max(0.05, bull);
    bear = Math.max(0.05, bear);
    side = Math.max(0.05, side);
    const sum = bull + bear + side;
    bull = +(bull / sum).toFixed(3);
    bear = +(bear / sum).toFixed(3);
    side = +(1 - bull - bear).toFixed(3);

    history_24h.push({
      timestamp: t.toISOString(),
      label: hourLabel,
      bullish_pct: Math.round(bull * 100),
      bearish_pct: Math.round(bear * 100),
      sideways_pct: Math.round(side * 100)
    });
  }

  res.json({
    current_regime: 'BULLISH',
    model: 'GaussianHMM (3-State Markov Model)',
    confidence: 84.5,
    last_update: new Date().toISOString(),
    history_24h,
    regimes: [
      {
        id: 'BULLISH',
        name: 'Tendencia Alcista (Bullish)',
        state: 'ACTIVE',
        status_color: 'green',
        prob: 0.74,
        confidence_pct: 74,
        volatility_level: 'MODERADA',
        adx_benchmark: '28.4 > 22.0 (Fuerte)',
        btc_position: 'Por encima de EMA 200 (4H / 1D)',
        cvd_delta: '+$42.8M (Presión compradora neta)',
        active_strategies: ['Breakout Momentum', 'Trend Continuation Long', 'Pullback Support Bounce'],
        risk_stance: 'EXPANSIVA: Sizing estándar permitido con Hard SL anclado a 1.8 ATR.',
        agents_aligned: 3,
        total_agents: 4
      },
      {
        id: 'BEARISH',
        name: 'Tendencia Bajista (Bearish)',
        state: 'INACTIVE',
        status_color: 'red',
        prob: 0.11,
        confidence_pct: 11,
        volatility_level: 'ELEVADA',
        adx_benchmark: 'No activado',
        btc_position: 'Lejos de zona de ruptura bajista',
        cvd_delta: 'Neutral / Sin absorción de venta institucional',
        active_strategies: ['Short Mean Reversion', 'Breakdown Breakdown'],
        risk_stance: 'RESTRICTIVA: Solo entradas en Short con veto estricto de MTF.',
        agents_aligned: 0,
        total_agents: 4
      },
      {
        id: 'SIDEWAYS',
        name: 'Rango Lateral (Sideways / Consolidation)',
        state: 'MONITORING',
        status_color: 'amber',
        prob: 0.15,
        confidence_pct: 15,
        volatility_level: 'COMPRESIÓN',
        adx_benchmark: 'ADX en zonas de consolidación',
        btc_position: 'Bandas Bollinger comprimiéndose en 15m',
        cvd_delta: 'Delta plano sin desequilibrio direccional',
        active_strategies: ['Mean Reversion Bollinger', 'Range Boundary Fade'],
        risk_stance: 'DEFENSIVA: Reducción de sizing a 0.5x, targets ajustados a 1.2R.',
        agents_aligned: 1,
        total_agents: 4
      }
    ],
    transition_probabilities: {
      from_bullish: { to_bullish: 0.85, to_sideways: 0.12, to_bearish: 0.03 },
      from_sideways: { to_bullish: 0.35, to_sideways: 0.50, to_bearish: 0.15 },
      from_bearish: { to_bullish: 0.08, to_sideways: 0.22, to_bearish: 0.70 }
    }
  });
});

app.get('/api/v1/intelligence/daily', (req, res) => {
  res.json({
    generated_at: new Date().toISOString(),
    summary: {
      trade_count: 18,
      shadow_trade_count: 14,
      real_trade_count: 4
    },
    summary_text: 'High regime alignment observed across top liquid perpetuals. Win rate maintaining above 68.9% with strictly controlled drawdown and zero unattached hard stop loss events.',
    state: {
      mode: botState.mode,
      regime: 'TRENDING_BULL',
      halt_system_active: botState.halt_system_active,
      sentiment: botState.sentiment
    },
    blocked_reason_counts: [
      { reason: 'MAX_RISK_EXCEEDED', count: 18 },
      { reason: 'ADX_BELOW_THRESHOLD', count: 15 },
      { reason: 'VOLUME_INSUFFICIENT', count: 11 }
    ]
  });
});

app.get('/api/v1/intelligence/weekly', (req, res) => {
  res.json({
    focus: {
      shadow_vs_real: {
        shadow: { closed: 84 },
        real: { closed: 12 },
        delta_win_rate_pct: 2.8,
        delta_avg_pnl_pct: 0.42
      },
      top_clusters: [
        { label: 'Breakout Trend Continuation', count: 32 },
        { label: 'Support Bounce Momentum', count: 24 },
        { label: 'Ghost NN High Conviction', count: 19 }
      ]
    }
  });
});

app.get('/api/v1/intelligence/advisories', (req, res) => {
  res.json({
    advisories: [
      {
        advisory_type: 'REGIME_ALIGNMENT',
        created_at: new Date(now - 3600000).toISOString(),
        summary: 'Market breadth fear index is neutral (52). Bull trend filter enabled with strong BTC dominance.'
      },
      {
        advisory_type: 'CORRELATION_GUARD',
        created_at: new Date(now - 5400000).toISOString(),
        summary: 'Matriz de correlación detectó sobreexposición BTC/ETH (+0.89). Filtro CORRELATION_RISK_ENABLED activo regulando sizing.'
      },
      {
        advisory_type: 'RISK_ENGINE',
        created_at: new Date(now - 7200000).toISOString(),
        summary: 'Hard stop losses active across all 6 current positions. Wallet reconciliation 100% in sync.'
      }
    ],
    total: 3
  });
});

app.get('/api/v1/intelligence/annotations', (req, res) => {
  res.json({
    annotations: [
      {
        symbol: 'BTCUSDT',
        mode: 'REAL',
        context_label: 'TREND_CONTINUATION',
        risk_label: 'LOW_RISK',
        narrative: 'Clean breakout above $64,200 with 4h MTF confirmation and positive CVD delta volume.'
      },
      {
        symbol: 'SOLUSDT',
        mode: 'SHADOW',
        context_label: 'IMPULSE_BREAKOUT',
        risk_label: 'MEDIUM_RISK',
        narrative: 'Strong momentum candle on 15m timeframe. Ghost model consensus probability scored at 91%.'
      }
    ],
    total: 2
  });
});

app.get('/api/v1/intelligence/postmortem/:trade_id', (req, res) => {
  const tradeId = parseInt(req.params.trade_id);
  const found = mockTrades.find(t => t.id === tradeId) || mockTrades[0];
  res.json({
    trade_id: tradeId,
    symbol: found.symbol,
    mode: found.is_shadow ? 'SHADOW' : 'REAL',
    severity: found.pnl_percent < -2 ? 'HIGH' : 'LOW',
    entry_price: found.entry_price,
    exit_price: found.exit_price,
    pnl_percent: found.pnl_percent,
    pnl_usd: found.pnl,
    exit_reason: found.reason,
    mfe_percent: found.mfe_percent,
    mae_percent: found.mae_percent,
    regime_at_entry: 'TRENDING_BULL',
    agents_breakdown: { breakout: 0.88, mean_reversion: 0.72, ghost_nn: 0.91 }
  });
});

app.post('/api/v1/intelligence/generate', (req, res) => {
  res.json({
    ok: true,
    daily_path: 'reports/daily_report.json',
    weekly_path: 'reports/weekly_report.json',
    advisories: 3
  });
});

// CONFIGURATION & ENVIRONMENT PANEL
app.get('/api/v1/config/env', (req, res) => {
  const items = Object.entries(envConfigMap).map(([key, item]) => ({
    key,
    value: item.value,
    active: item.active,
    category: item.category,
    type: item.type,
    desc: item.desc
  }));

  const categoriesCount = {
    TOTAL: items.length,
    FILTERS: items.filter(i => i.category === 'FILTERS').length,
    FILTERS_ACTIVE: items.filter(i => i.category === 'FILTERS' && i.active).length,
    RISK: items.filter(i => i.category === 'RISK').length,
    EXECUTION: items.filter(i => i.category === 'EXECUTION').length,
    SYSTEM: items.filter(i => i.category === 'SYSTEM').length
  };

  res.json({
    config: items,
    counts: categoriesCount,
    runtime_mode: botState.mode,
    active_filters_count: items.filter(i => i.category === 'FILTERS' && i.active).length,
    total_filters_count: items.filter(i => i.category === 'FILTERS').length
  });
});

app.post('/api/v1/config/env/toggle', (req, res) => {
  const { key } = req.body;
  if (envConfigMap[key]) {
    envConfigMap[key].active = !envConfigMap[key].active;
    if (envConfigMap[key].type === 'boolean') {
      envConfigMap[key].value = envConfigMap[key].active ? 'true' : 'false';
    }
    return res.json({ ok: true, key, active: envConfigMap[key].active, value: envConfigMap[key].value });
  }
  res.status(404).json({ ok: false, error: 'Key not found' });
});

app.listen(PORT, HOST, () => {
  console.log(`Sniper AI Master Monitor listening on http://${HOST}:${PORT}`);
});
