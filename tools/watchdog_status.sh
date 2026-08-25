#!/usr/bin/env bash
set -euo pipefail

echo "=== Process ==="
pgrep -af "python3 main.py" || true

echo "=== Service ==="
systemctl --user --no-pager --full status sniper-ai.service || true

echo "=== Recent Logs ==="
journalctl --user -u sniper-ai.service -n 60 --no-pager || true
