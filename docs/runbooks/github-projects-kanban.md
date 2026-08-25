# GitHub Projects Kanban

Este modulo permite usar GitHub Projects v2 como un tablero estilo Trello para el ciclo de vida de operaciones del bot.

## Archivos

- `tools/github_projects_kanban.py`: cliente reutilizable y funciones listas para invocar desde el bot.
- `tools/bootstrap_github_project_kanban.py`: CLI para crear o configurar el tablero.
- `tests/test_github_projects_kanban.py`: pruebas unitarias sin red.

## Variables de entorno

Define una de estas opciones de proyecto:

```env
GITHUB_TOKEN=ghp_xxx_o_github_pat_xxx

# Opcion A: usar el node ID directo del proyecto
GITHUB_PROJECT_ID=PVT_kwHOA...

# Opcion B: resolver por owner + numero
GITHUB_PROJECT_OWNER=Rukawua26
GITHUB_PROJECT_NUMBER=1

# Opcional: enlazar el project al repo
GITHUB_REPOSITORY=Rukawua26/Pbot-V5ARCH-DEV
```

## Columnas requeridas en GitHub Projects

En el campo `Status` del proyecto deben existir exactamente estas opciones:

- `Estrategias Activas`
- `Órdenes Pendientes`
- `Posiciones Abiertas`
- `Historial de Cierre`

## Uso desde el bot

```python
from tools.github_projects_kanban import (
    actualizar_pnl_tarjeta,
    crear_tarjeta_operacion,
    mover_tarjeta,
)

creada = crear_tarjeta_operacion("BTC/USDT", "Breakout 1H", 25)

if creada["ok"]:
    item_id = creada["item_id"]
    mover_tarjeta(item_id, "Órdenes Pendientes")
    mover_tarjeta(item_id, "Posiciones Abiertas")
    actualizar_pnl_tarjeta(item_id, pnl_actual=12.4, precio_actual=103450.8)
    mover_tarjeta(item_id, "Historial de Cierre")
```

## Crear el tablero automáticamente

```bash
./.venv/bin/python tools/bootstrap_github_project_kanban.py \
  --owner Rukawua26 \
  --repo Rukawua26/Pbot-V5ARCH-DEV
```

Si ya tienes un `PROJECT_ID`, puedes reconfigurar solo las columnas y el README del proyecto:

```bash
./.venv/bin/python tools/bootstrap_github_project_kanban.py \
  --configure-only \
  --project-id PVT_kwHOA... \
  --title "Trading Operations Kanban"
```

El comando devuelve el `url` exacto del tablero cuando la creación/configuración termina bien.

## Como obtener las credenciales en GitHub

1. Crea un token en GitHub desde `Settings > Developer settings > Personal access tokens`.
2. Si usas token classic, habilita `project` y acceso al repo si corresponde.
3. Si usas fine-grained token, da permisos sobre `Projects` y alcance al owner donde vive el proyecto.
4. Abre tu GitHub Project v2.
5. Si prefieres `GITHUB_PROJECT_NUMBER`, copia el numero visible del proyecto y el login del owner.
6. Si prefieres `GITHUB_PROJECT_ID`, consulta el node ID con GraphQL o desde una llamada previa del modulo resolviendo por owner + numero.

## Dónde ver el tablero

- URL exacta del tablero operativo: `https://github.com/users/Rukawua26/projects/1/views/1`
- URL general de proyectos del usuario: `https://github.com/users/Rukawua26/projects`
- Si enlazas el project al repo, también lo verás desde la pestaña `Projects` del repositorio.
- Tras ejecutar el bootstrap, usa el `url` devuelto por el script para abrir el tablero exacto.

## Comportamiento ante errores

Las funciones publicas devuelven un `dict` con `ok=False` y `error=...` cuando GitHub falla o faltan variables, para no interrumpir el runtime principal del bot.
