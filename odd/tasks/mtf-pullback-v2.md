# MTF Pullback v2 — estrategia 1H/15M/5M/1M, pre-registrada, solo SHADOW

Rama `research/edge-20usd`. Sucede a `odd/tasks/edge-20usd.md` (TTF descartado: H0/H1 fallan el gate).
Fase A' offline (solo `tools/` + modulo nuevo `core/strategy/mtf_pullback/` + tests). Sin tocar runtime.

## Specs

- S1 — "replanteala con una estrategia que funcione": estrategia nueva disenada con el diagnostico de
  edge-20usd (TP 2.5R casi inalcanzable: 7% de trades; stop 0.38% => coste 0.27R). Se prueba de forma
  honesta; no se garantiza que funcione.
- S2 — "quiero que las temporalidades sean 1minuto 5minutos y 15 minutos teniendo encuenta el de 1 hora":
  1H contexto, 15M setup + stop estructural, 5M confirmacion, 1M momento de entrada.
- S3 — "si no sirve con 20 dolares las pruebas vamos aprobar con 100 dolares": el mismo backtest se evalua
  con perfiles de cuenta $20 y $100 (la estrategia es la misma; cambia universo operable y rechazos).
- S4 — "si solo usar shadow ya que no tenemos para real": si pasa el gate, Fase B solo en SHADOW.
- S5 — "quiero que cuando tengamos las pruebas bien entonces si podemos hacer la rama": integracion de la
  rama solo despues de gate PASS y campana SHADOW; push/PR/merge son decision del humano.
- S6 — Errores encontrados se corrigen y se documentan en `.opencode/context/known-bugs.md`.

## Pre-registro (fijado 2026-11-02 antes de ejecutar; no se modifica tras ver resultados)

Reglas (todas sobre velas CERRADAS, agregadas desde 1M):

1. Contexto 1H: EMA50(1H) y EMA200(1H). LONG solo si close1H > EMA200 y EMA50 > EMA200 y pendiente EMA50
   (vs 3 velas atras) > 0. SHORT simetrico. Si no, sin operacion.
2. Setup 15M: tendencia 15M alineada (EMA20 > EMA50 en LONG; < en SHORT). Retroceso: en las ultimas 4 velas
   15M, algun low <= EMA20(15M) (LONG; high >= EMA20 en SHORT) y ningun close < EMA50(15M) (LONG; > en
   SHORT). Swing del retroceso = min low (LONG) / max high (SHORT) de esas 4 velas.
3. Confirmacion 5M: la ultima vela 5M cerrada cierra por encima del high de la vela 5M anterior (LONG; por
   debajo del low en SHORT) y por encima de EMA20(5M) (LONG; por debajo en SHORT).
4. Entrada 1M: tras la confirmacion, primera vela 1M cerrada (dentro de 15 min) con close > EMA9(1M) (LONG;
   < en SHORT). Entrada a la apertura de la vela 1M siguiente + slippage.
5. Stop: swing del retroceso -/+ 0.1 x ATR14(15M). Riesgo valido si 0.5% <= stop <= 2.5% del precio;
   fuera de ese rango no hay operacion (stop demasiado ajustado = coste alto; demasiado amplio = sizing).
6. Salida: TP fijo 1.5R; SL; cierre por tiempo a las 8 horas (480 velas 1M). Sin trailing ni breakeven.
7. Un setup 15M (identificado por el cierre de la vela de swing) solo puede usarse una vez. Una posicion por
   simbolo. Filtro de sesion 07-22 UTC (igual que el runtime).
8. Costes: taker 0.05% por lado, slippage 0.05% por lado, stop con gap a la apertura, TP al precio exacto.

Universo y perfiles (sizing y filtros de `tools/ttf_backtest.py`):
- Simbolos: SOL, XRP, DOGE, BNB, ADA, ETH, LINK, BTC. El perfil decide cuales son operables
  ($20: max notional $10 → SOL/XRP/DOGE/BNB/ADA; $100: max notional $50 → + ETH, LINK; BTC solo si cabe).
- Perfil $20 y $100: leverage 10, margen 5%, riesgo 1.2%, MAX_RISK_USD 2.0, MAX_OPEN_TRADES 3.

Periodos:
- Desarrollo 2025-09 → 2026-08 (incluye el holdout anterior, ya visto). Solo una corrida y un control de
  descarte: si la E BRUTA en desarrollo <= 0, STOP sin gastar el holdout.
- Holdout nuevo: 2026-09-01 → ultimo dia disponible de 2026-10. Una sola corrida.

Gate (se evalua por perfil, sobre los trades operables de ese perfil):
- PASS si: E neta > 0 R, >= 200 trades, PF >= 1.1, retorno USD del perfil > 0.
- Menos de 200 trades = MUESTRA_INSUFICIENTE (no pasa; se informa y se decide con el humano si se
  acumula muestra en SHADOW, nunca relajando el gate).
- Si ningun perfil pasa: STOP. No hay variantes.

## Tasks

| ID | Specs | Ruta | Estado | Commit |
|---|---|---|---|---|
| T1 | S1, S2 | inline: evaluador puro `core/strategy/mtf_pullback/` + tests RED/GREEN | pending | |
| T2 | S2, S3 | inline: backtest `tools/mtf_backtest.py` reutilizando simulacion y perfil de cuenta | pending | |
| T3 | S1 | ejecucion desarrollo + control de descarte | pending | |
| T4 | S3 | holdout una vez, perfiles $20 y $100, veredicto | pending | |
| T5 | S6 | documentar errores; cierre | pending | |

## Log

- L1 (usuario): "1 replanteala con una estrategia que funcione / 2 si solo usar shadow ya que no tenemos
  para real / 3 no se si dejarla asi pero quiero que cuando tengamos las pruebas bien entonces si podemos
  hacer la rama / si no sirve con 20 dolares las pruebas vamos aprobar con 100 dolares a ver como funciona
  pero quiero que las temporalidades sean 1minuto 5minutos y 15 minutos teniendo encuenta el de 1 hora men
  entiendes la idea a ver si asi nos va mejor"
- L2 (usuario): aprobo el plan "Si, implementalo asi" (stop en estructura 15M, TP 1.5R, holdout sep-oct 2026,
  perfiles $20 y $100, Fase B solo SHADOW si pasa).
