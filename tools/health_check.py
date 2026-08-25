#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["PYTHONUNBUFFERED"] = "1"

from dotenv import load_dotenv
load_dotenv()

SERVICE_NAME = "sniper-ai.service"
PAPER_MODE = str(os.getenv("PAPER_MODE", "true")).strip().lower() in {"1", "true"}


def service_active() -> bool:
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_NAME],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() == "active"
    except Exception:
        return False


def send_alert():
    mode = "PAPER" if PAPER_MODE else "REAL"
    msg = (
        f"🚨 *SNIPER AI HEALTH ALERT*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 Service: `{SERVICE_NAME}`\n"
        f"🔹 Mode: {mode}\n"
        f"🔹 Status: *DOWN* ❌\n"
        f"🔹 Time: {subprocess.run(['date', '+%Y-%m-%d %H:%M:%S'], capture_output=True, text=True).stdout.strip()}\n"
        f"⚠️ *INTERVENCIÓN MANUAL REQUERIDA*"
    )
    try:
        from tools.notifier import send_telegram_msg
        send_telegram_msg(msg)
    except Exception as e:
        print(f"Failed to send alert: {e}", file=sys.stderr)


def main() -> int:
    if service_active():
        return 0
    send_alert()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
