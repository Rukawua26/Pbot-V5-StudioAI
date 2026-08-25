#!/usr/bin/env python3
"""Fail CI if disallowed `pass` statements exist in core modules."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"

# Archivos donde `pass` es intencional (interfaces abstractas o no críticas)
ALLOWLIST = {
    (CORE / "strategy" / "base_agent.py").resolve(),
    (CORE / "strategy" / "agents" / "visual_agent.py").resolve(),
}


def main() -> int:
    failures: list[str] = []

    for path in CORE.rglob("*.py"):
        full = path.resolve()
        if full in ALLOWLIST:
            continue

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception as error:
            failures.append(f"{path}: parse error: {error}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Pass):
                failures.append(f"{path}:{getattr(node, 'lineno', '?')}: disallowed pass")

    if failures:
        print("[FAIL] Se encontraron pass silenciosos no permitidos en core/")
        for item in failures:
            print(f" - {item}")
        return 1

    print("[OK] No hay pass silenciosos no permitidos en core/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
