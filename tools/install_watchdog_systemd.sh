#!/usr/bin/env bash
set -euo pipefail

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${BOT_DIR}/.venv/bin/python"
LOCK_FILE="${BOT_DIR}/.sniperai.lock"
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT_FILE="${UNIT_DIR}/sniper-ai.service"
ENV_FILE="${SNIPER_ENV_FILE:-${BOT_DIR}/.env}"
MEMORY_MAX="${SNIPER_SYSTEMD_MEMORY_MAX:-2G}"
TOP_TRIAGE_COUNT_OVERRIDE="${SNIPER_TOP_TRIAGE_COUNT:-12}"
TRIAGE_MAX_WORKERS_OVERRIDE="${SNIPER_TRIAGE_MAX_WORKERS:-6}"
TRIAGE_POOL_MULTIPLIER_OVERRIDE="${SNIPER_TRIAGE_CANDIDATE_POOL_MULTIPLIER:-2}"
TRIAGE_MAX_POOL_OVERRIDE="${SNIPER_TRIAGE_MAX_CANDIDATE_POOL:-50}"
BEAR_TREND_MAX_PAIRS_OVERRIDE="${SNIPER_BEAR_TREND_MAX_PAIRS:-8}"
SHOCK_LOOKBACK_BARS_OVERRIDE="${SNIPER_SHOCK_LOOKBACK_BARS:-160}"

mkdir -p "${UNIT_DIR}"

if ! flock -n "${LOCK_FILE}" true; then
    owner="$(cat "${LOCK_FILE}" 2>/dev/null || true)"
    echo "Another Sniper AI instance is already running (lock owner: ${owner:-unknown})."
    echo "Stop the existing process before installing/restarting the systemd service."
    echo "To inspect: ps -fp ${owner:-<pid>}"
    exit 75
fi

cat > "${UNIT_FILE}" <<EOF
[Unit]
Description=Sniper AI Bot Watchdog Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${BOT_DIR}
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-${ENV_FILE}
Environment=TOP_TRIAGE_COUNT=${TOP_TRIAGE_COUNT_OVERRIDE}
Environment=TRIAGE_MAX_WORKERS=${TRIAGE_MAX_WORKERS_OVERRIDE}
Environment=TRIAGE_CANDIDATE_POOL_MULTIPLIER=${TRIAGE_POOL_MULTIPLIER_OVERRIDE}
Environment=TRIAGE_MAX_CANDIDATE_POOL=${TRIAGE_MAX_POOL_OVERRIDE}
Environment=BEAR_TREND_MAX_PAIRS=${BEAR_TREND_MAX_PAIRS_OVERRIDE}
Environment=SHOCK_LOOKBACK_BARS=${SHOCK_LOOKBACK_BARS_OVERRIDE}
ExecStartPre=/usr/bin/env bash -lc 'flock -n "${LOCK_FILE}" true || exit 75'
ExecStart=${PYTHON_BIN} main.py
ExecStop=/usr/bin/env bash -lc 'kill -INT "\${MAINPID}" 2>/dev/null || true'
Restart=on-failure
RestartPreventExitStatus=75
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=95
NoNewPrivileges=true
LimitNOFILE=65535
MemoryMax=${MEMORY_MAX}
OOMPolicy=stop
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=${BOT_DIR} /dev/shm

[Install]
WantedBy=default.target
EOF

echo "Service file created: ${UNIT_FILE}"

systemctl --user daemon-reload
systemctl --user enable --now sniper-ai.service
systemctl --user restart sniper-ai.service
sleep 2
systemctl --user --no-pager --full status sniper-ai.service || true

echo "Done. Watchdog active with automatic restart."
