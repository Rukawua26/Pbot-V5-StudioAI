# Wallet sync hardening (auditoria 2026-11)

Rama `research/edge-20usd`. Origen: revision general del proyecto (hallazgos 1-4).
Runtime critico (`core/bot_wallet_sync.py`). Sin commits salvo peticion explicita (AGENTS.md).

## Specs

- S1 — Hallazgo 1 (confirmado): `core/trade_entry.py:1657` guarda `partial_fill_started_at` con
  `utc_now_iso()` (aware) y `core/bot_wallet_sync.py:449-450` lo resta de `datetime.now()` (naive):
  `TypeError`, el timeout de fill parcial nunca cancela y el wallet sync termina en HALT. Debe aceptar
  timestamps aware y naive legacy (hora local) y calcular la edad en UTC.
- S2 — Hallazgo 2 (confirmado): `_ensure_hard_sl_attached` cancela el SL insuficiente antes de colocar
  el reemplazo; si la colocacion falla la posicion REAL queda sin HARD SL. Debe colocar y validar el
  nuevo SL antes de cancelar el viejo (como `core/bot_guardian.py`); si el reemplazo falla, el SL viejo
  sigue en el libro.
- S3 — Hallazgo 3 (confirmado): `sync_wallet` solo sincroniza `amount`/`size_usd` cuando cambia el
  precio de entrada. El exchange manda: la cantidad debe sincronizarse siempre que difiera.
- S4 — Hallazgo 4: 3 tests fallan segun el `.env` local (`load_runtime_env` usa `override=True`).
  Los tests deben fijar la configuracion de la que dependen.
- S5 — "empieza y tienes mi autorizacion para corregir": corregir con test RED/GREEN, documentar en
  `docs/engineering/memoria-tecnica.md` y `.opencode/context/known-bugs.md`.

- S6 — Plan aprobado (L8): ID de reparacion estable mientras la reparacion esta pendiente (el contador solo
  avanza cuando la reparacion termina), para que un ACK ambiguo se adopte en el ciclo siguiente sin otra colocacion;
  restaurar juntos ID de exchange y clientOrderId del SL viejo; tests propuestos por el verificador + multiciclo.
- S7 — CI: `anyio` 4.13.0 -> 4.14.2 (CVE-2026-63374, CVE-2026-64847) y mypy en verde con `ignore_missing_imports`
  solo para pandas/tensorflow.
- S8 — `create_precision_order` no reintenta sin clientOrderId; la migracion de `tools/learning.py:345` registra el
  error en log.
- S9 — Medir lint de `tools/` y corregir `.opencode/context/repo-summary.md` (learning.py raiz inexistente).

## Tasks

| ID | Specs | Ruta | Estado | Commit |
|---|---|---|---|---|
| T1 | S1, S5 | inline: `core/bot_wallet_sync.py` + test | done | 3ed8363 |
| T2 | S2, S5 | inline: `core/bot_wallet_sync.py` + test | done | 3ed8363 |
| T3 | S3, S5 | inline: `core/bot_wallet_sync.py` + test | done | 3ed8363 |
| T4 | S4 | inline: 3 tests | done | 3ed8363 |
| T5 | S5 | suite, verify independiente, memoria tecnica, known-bugs | done | 3ed8363 |
| T6 | S6 | worker (context backstop): `core/bot_wallet_sync.py` + tests | done | b611f91 |
| T7 | S7 | inline: locks + mypy.ini | done | a7de9bb |
| T8 | S8 | inline: `core/execution_service.py`, `tools/learning.py` + tests | done | (fase 3) |
| T9 | S9 | inline: medicion + doc | done | (fase 4) |
| T10 | S6 | humano: test de integracion testnet (claves de testnet) | blocked | - |

Ruta inline: cada unidad < 100 lineas y dependiente del mismo archivo; sin trigger de writer.

## Log

- L1: "realiza una revision del proyecto y dime si esta correecto encuanto a estructura forma de funcionar y codigo"
- L2: "empieza y tienes mi autorizacion para corregir"
- L3 (evidencia): RED observado en 5 tests nuevos de S1-S3; GREEN 21/21 en wallet sync. Suite completa
  1496 OK (2 skipped); ruff check/format, compileall, silent-pass, contratos, chaos matrix 8/8 y recovery drill OK.
  Verificador independiente no admitido por el runtime; revision adversarial inline realizada.
- L4: "y las opciones anteriores que me recomendabas la A y la C ya la realizastes?" -> A hecha (hallazgos 2 y 3
  confirmados y corregidos). C: CI de GitHub falla en "Dependency vulnerability audit" antes de mypy; mypy local 2.1.0
  igual al lock, sin pandas-stubs/types-tensorflow: los 66 errores no son solo del entorno local.
- L5 (verify): gentle-ai-verify UNVERIFIED (0 tests: harness bloqueo su copia aislada). Hallazgo estatico: lookup
  intermedio fallido se trataba como ausencia del SL viejo, y el clientOrderId de reparacion colisionaba (leg truncado
  a 6). Corregido con RED/GREEN: lookup fallido conserva SL viejo + HALT; contador dentro de la semilla hasheada.
  Suite 1498 OK (2 skipped); ruff, compileall, silent-pass, contratos, chaos 8/8, recovery drill OK.
- L6: CI main falla en pip-audit: anyio 4.13.0 (CVE-2026-63374, CVE-2026-64847), fix 4.14.2, via starlette.
  Pendiente de autorizacion (dependencias/CI = riesgo item 5).
- L7: "nuestrame el mejor plan a seguir para las todas las correciones que necesitamos" / "este es el mejor plan o hay uno mejor?"
- L8: "si apruebo el plan" (fases 0-4; commits por fase autorizados; push no).
- L9 (T6): RED 4 fallos (doble colocacion con IDs distintos tras ACK ambiguo; clientOrderId viejo pisado). GREEN 28/28;
  suite completa 1503 OK (2 skipped); ruff y silent-pass OK.
- L10 (T7): pip-audit local encontro mas CVEs que el CI de septiembre; actualizados en ambos locks anyio 4.14.2,
  urllib3 2.8.0, multidict 6.9.1, setuptools 84.1.0, filelock 4.2.1 (solo dev, via cachecontrol), msgpack 1.2.3,
  aiohttp 3.14.4, certifi 2026.10.18, yarl 1.25.1 (requerido por aiohttp). pip check, pip-audit --strict y
  `pip install --dry-run` de ambos locks OK. mypy.ini ignora imports solo de paquetes sin stubs; 0 errores reales.
  CI local completo OK; suite 1503 OK (2 skipped).
- L11 (T8): RED: entrada sin clientOrderId enviada 3 veces; fallo inesperado de migracion sin log. GREEN.
- L12 (T9): `ruff check tools/` solo 4 errores (corregidos) -> agregado al CI; `ruff format tools/` daria 55
  archivos reformateados: descartado. Suite 1506 OK (2 skipped). Revision nativa (risk, resilience,
  reliability) aprobada y reconocida; sugerencia R3-001 informativa sobre tests/test_learning_storage.py.
- L13: "si autorizp" (3 ejecuciones de modelo de la revision nativa).
