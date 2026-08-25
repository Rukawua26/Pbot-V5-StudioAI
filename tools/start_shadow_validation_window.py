#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    root = Path(".").resolve()
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    marker_path = logs / "shadow_validation_start.json"
    payload = {"ts": datetime.now(timezone.utc).isoformat()}
    marker_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"SHADOW validation window started: {marker_path}")
    print(payload["ts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
