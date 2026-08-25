"""CLI para crear o configurar el tablero GitHub Projects v2 del bot."""

from __future__ import annotations

import argparse
import json

try:
    from tools.github_projects_kanban import (
        DEFAULT_PROJECT_TITLE,
        configurar_tablero_kanban,
        crear_tablero_kanban,
    )
except ModuleNotFoundError:
    from github_projects_kanban import (  # type: ignore
        DEFAULT_PROJECT_TITLE,
        configurar_tablero_kanban,
        crear_tablero_kanban,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap de GitHub Projects Kanban")
    parser.add_argument("--title", default=DEFAULT_PROJECT_TITLE, help="Titulo del proyecto")
    parser.add_argument("--owner", help="Owner del project, por ejemplo Rukawua26")
    parser.add_argument("--repo", help="Repo a enlazar, formato owner/repo")
    parser.add_argument("--project-id", help="Configura un proyecto existente por node ID")
    parser.add_argument(
        "--public",
        action="store_true",
        help="Hace publico el project al configurarlo",
    )
    parser.add_argument(
        "--configure-only",
        action="store_true",
        help="No crea un project nuevo; solo configura el existente",
    )
    args = parser.parse_args()

    if args.configure_only:
        result = configurar_tablero_kanban(
            project_id=args.project_id,
            title=args.title,
            public=True if args.public else None,
        )
    else:
        result = crear_tablero_kanban(
            title=args.title,
            owner_login=args.owner,
            repo_full_name=args.repo,
            public=args.public,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
