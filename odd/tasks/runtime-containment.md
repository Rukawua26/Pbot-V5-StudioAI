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
  vez, en orden; la API distingue "encolado" de "ejecutado".
- S3 — "La config acepta `nan` o `inf` en límites de riesgo": valores no finitos se rechazan centralmente
  (warning + default), y un `inf` en enteros no debe tumbar la carga de config.
- S4 — "si arranca y realiza las correciones como recominedas": corregir con test RED/GREEN y documentar
  en `.opencode/context/known-bugs.md`.

## Tasks

| ID | Specs | Ruta | Estado | Commit |
|---|---|---|---|---|
| T1 | S3, S4 | inline: `core/config/env_helpers.py` + tests | pending | |
| T2 | S1, S2, S4 | worker: dashboard auth + IPC por archivos unicos + tests | pending | |
| T3 | S4 | known-bugs, CI completo, cierre | pending | |

## Log

- L1 (usuario): "si arranca y realiza las correciones como recominedas" (respuesta a: contencion = #1
  dashboard + nan/inf ahora; bloque REAL #2-#10 antes de dinero real).
- L2: #9 (perdida de `/panic`) se incluye en la contencion porque afecta todos los modos y comparte archivo
  con #1.
