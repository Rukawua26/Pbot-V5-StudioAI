# Contencion runtime (antes de la campana SHADOW de $20)

Rama `research/edge-20usd`. Origen: auditoria 2026-11-01 (hallazgos #1, #9 y config nan/inf).
Bloque REAL (#2-#8, #10) queda fuera: se hace antes de usar dinero real.

## Specs

- S1 — Hallazgo #1: "Dashboard grants control credentials without authentication": `GET /` de
  `tools/dashboard_api_server.py` emite la cookie de CONTROL sin autenticar; cualquiera que alcance el
  dashboard puede enviar `/panic`, `/recover_halt` o cerrar posiciones. El indice solo puede emitir la
  sesion de LECTURA; la sesion de control exige presentar la clave de control.
- S2 — Hallazgo #9: "Dashboard IPC silently loses acknowledged trading commands": `command.json` unico se
  sobrescribe y el consumidor puede borrar un comando nuevo. Cada comando debe sobrevivir y ejecutarse una
  vez, en orden; la API distingue "encolado" de "ejecutado". Garantia: a lo sumo una vez. Un comando
  reclamado cuando el bot se cae no se reintenta (reintentar `/panic` o `/close` podria duplicar la accion;
  AGENTS.md prohibe reintentos no idempotentes). Queda como `.claimed` para revision manual.
- S3 — "La config acepta `nan` o `inf` en límites de riesgo": valores no finitos se rechazan centralmente
  (warning + default), y un `inf` en enteros no debe tumbar la carga de config.
- S4 — "si arranca y realiza las correciones como recominedas": corregir con test RED/GREEN y documentar
  en `.opencode/context/known-bugs.md`.

## Tasks

| ID | Specs | Ruta | Estado | Commit |
|---|---|---|---|---|
| T1 | S3, S4 | inline: `core/config/env_helpers.py` + tests | done | db36f67 |
| T2 | S1, S2, S4 | worker: dashboard auth + IPC por archivos unicos + tests | done | (commit de cierre) |
| T3 | S4 | known-bugs, CI completo, cierre | done | (commit de cierre) |

## Log

- L1 (usuario): "si arranca y realiza las correciones como recominedas" (respuesta a: contencion = #1
  dashboard + nan/inf ahora; bloque REAL #2-#10 antes de dinero real).
- L3: Verificador independiente sobre T2: C1, C3, C8 confirmados. Defectos: (a) causado por el cambio: la UI
  no permite cargar la clave de control y los botones fallan con 401 en silencio; (b) preexistente:
  `POST /api/v1/intelligence/generate` usa `verify_key` (lectura), disparable con la cookie anonima;
  (c) preexistente: el consumidor no valida el directorio de la cola (`/dev/shm` es escribible por todos);
  (d) advertencias preexistentes sin cambio: `CONTROL_API_KEY` cae a `API_KEY` si no se define (decision
  del operador) y la cookie no lleva `secure` (correcto para el bind 127.0.0.1 por defecto).
- L4: Hallazgos del verificador corregidos con RED/GREEN: (a) UI: helper `controlRequest` comun a todos los
  pedidos de control; ante 401 pide la clave una vez, la guarda y reintenta una vez; errores visibles
  (toast). Se quito el reenvio automatico de close/breakeven tras un fallo ambiguo (podia duplicar el
  comando). (b) `intelligence/generate` exige control. (c) El consumidor rechaza un directorio de cola
  symlink, ajeno o escribible por grupo/otros. 40 tests focales OK. La UI solo se verifico estaticamente
  (sin navegador). `toggleEnvKey` llama a `/api/v1/config/env/toggle`, que no existe en el servidor
  (preexistente): ahora muestra el error en vez de fallar en silencio.
- L5: CI completo: 1456 tests OK (2 skipped), cobertura 80%, ruff OK, mypy 65 (igual a la base), chaos 8/8,
  recovery drill OK, contratos OK, sin pass silenciosos.
- L2: #9 (perdida de `/panic`) se incluye en la contencion porque afecta todos los modos y comparte archivo
  con #1.
