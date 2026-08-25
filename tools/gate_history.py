#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_gate_result(
    path: Path,
    *,
    gate: str,
    passed: bool,
    failures: list[str],
    metadata: dict[str, Any] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "gate": gate,
        "passed": bool(passed),
        "failures": list(failures or []),
        "metadata": metadata or {},
    }
    with path.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(record, sort_keys=True) + "\n")
