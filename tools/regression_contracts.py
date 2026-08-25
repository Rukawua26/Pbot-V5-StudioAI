#!/usr/bin/env python3
"""Checks lightweight architectural contracts after modular refactor."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_ast(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def class_method_names(tree: ast.AST, class_name: str) -> set[str]:
    for node in tree.body:  # type: ignore[attr-defined]
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
    return set()


def assert_main_entrypoint() -> None:
    main_file = ROOT / "main.py"
    source = main_file.read_text(encoding="utf-8")
    required = [
        "from core.bot_app import run_entrypoint",
        'if __name__ == "__main__":',
        "run_entrypoint()",
    ]
    for token in required:
        if token not in source:
            raise AssertionError(f"main.py no contiene contrato requerido: {token}")


def assert_bot_app_contract() -> None:
    tree = load_ast(ROOT / "core" / "bot_app.py")
    methods = class_method_names(tree, "Bot")
    required = {
        "__init__",
        "connect",
        "sync_wallet",
        "monitor_open_trades",
        "handle_command",
        "run",
        "execute_order",
        "close_trade",
        "update_radar",
        "get_audit_verdict",
    }
    missing = sorted(required - methods)
    if missing:
        raise AssertionError(f"Bot contract incompleto, faltan métodos: {missing}")


def assert_bot_facade_contract() -> None:
    source = (ROOT / "core" / "bot_facade.py").read_text(encoding="utf-8")
    if "Bot as BotFacade" not in source:
        raise AssertionError("bot_facade.py debe re-exportar Bot como BotFacade")


def assert_execution_safety_invariants() -> None:
    sources: dict[str, str] = {}
    for mod in ("trade_manager.py", "trade_entry.py", "trade_exit.py", "trade_helpers.py"):
        path = ROOT / "core" / mod
        if path.exists():
            sources[mod] = path.read_text(encoding="utf-8")
    execution_service_source = (ROOT / "core" / "execution_service.py").read_text(
        encoding="utf-8"
    )
    execution_port_source = (ROOT / "core" / "execution_port.py").read_text(
        encoding="utf-8"
    )
    risk_engine_source = (ROOT / "core" / "risk_engine.py").read_text(encoding="utf-8")

    required_tokens: dict[str, list[str]] = {
        "trade_entry.py": [
            "ENTRY_ABORTED_NO_HARD_SL",
            "FAIL_SAFE_CLOSE_FAILED_HALT",
        ],
        "trade_helpers.py": [
            "_fail_safe_close_when_sl_missing",
        ],
    }
    for source_name, tokens in required_tokens.items():
        source = sources.get(source_name, "")
        for token in tokens:
            if token not in source:
                raise AssertionError(
                    f"{source_name} no contiene invariante de seguridad requerido: {token}"
                )

    if "def fetch_book_ticker(self, symbol: str)" not in execution_port_source:
        raise AssertionError(
            "execution_port.py no define fetch_book_ticker(symbol), contrato de spread incompleto"
        )

    if "def _call_exchange(" not in execution_service_source:
        raise AssertionError(
            "execution_service.py no define _call_exchange, resiliencia exchange incompleta"
        )

    if "if margin_fraction > 1.0:" not in risk_engine_source:
        raise AssertionError(
            "risk_engine.py no normaliza MAX_MARGIN_PERCENT (porcentaje/fracción)"
        )


def main() -> int:
    assert_main_entrypoint()
    assert_bot_app_contract()
    assert_bot_facade_contract()
    assert_execution_safety_invariants()
    print("[OK] Contratos arquitectónicos validados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
