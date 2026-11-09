"""Lee comandos desde archivo IPC y los rutea al command_router del bot."""

import json
import os
import re
import stat
import secrets

CMD_FILE = "/dev/shm/sniper_cmd/command.json"
ALLOWED_DASHBOARD_COMMANDS = frozenset(
    {
        "/pause",
        "/resume",
        "/panic",
        "/recover_halt",
        "/rebase_capital",
        "/sync_wallet",
        "/scan",
        "/force_shadow",
        "/reset",
    }
)


def _is_safe_command(action: str) -> bool:
    action = action.strip()
    if action in ALLOWED_DASHBOARD_COMMANDS:
        return True
    parts = action.split(maxsplit=1)
    if len(parts) == 2:
        cmd, sym = parts[0], parts[1].strip().upper()
        if cmd in ("/close", "/close_trade", "/breakeven", "/be"):
            if re.match(r"^[A-Z0-9/_-]{2,20}$", sym):
                return True
    return False


def _check_ipc_file_safe(path: str) -> bool:
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            return False
        if st.st_mode & 0o077:
            return False
        return True
    except (OSError, FileNotFoundError):
        return False


def consume_command_file(bot):
    """Claim a snapshot of the queue; later publications wait for the next poll.

    Legacy command.json is drained first. Claims are never replayed automatically:
    after a crash their execution outcome is unknown, so retrying could duplicate
    a non-idempotent command.
    """
    directory = os.path.dirname(CMD_FILE)
    try:
        directory_stat = os.lstat(directory)
        if (
            stat.S_ISLNK(directory_stat.st_mode)
            or not stat.S_ISDIR(directory_stat.st_mode)
            or directory_stat.st_uid != os.getuid()
            or directory_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            bot.log(f"⚠️ CMD directory unsafe (owner/mode/type): {directory}")
            return
        names = os.listdir(directory)
    except FileNotFoundError:
        bot.log(f"CMD directory not available: {directory}")
        return
    except OSError as error:
        bot.log(f"⚠️ CMD listing error: {error}")
        return
    pending = sorted(n for n in names if n.startswith("cmd-") and n.endswith(".json"))
    legacy = os.path.basename(CMD_FILE)
    if legacy in names:
        pending.insert(0, legacy)
    for name in pending:
        path = os.path.join(directory, name)
        claimed = f"{path}.{secrets.token_hex(16)}.claimed"
        try:
            os.rename(path, claimed)
        except OSError as error:
            bot.log(f"⚠️ CMD claim skipped {name}: {error}")
            continue
        try:
            if not _check_ipc_file_safe(claimed):
                bot.log(f"⚠️ CMD file unsafe (owner/mode/type), removing: {name}")
                continue
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(claimed, flags)
            with os.fdopen(fd, encoding="utf-8") as handle:
                data = json.load(handle)
            commands = data.get("commands") if isinstance(data, dict) else None
            if not isinstance(commands, list):
                bot.log("⚠️ CMD consume ignored invalid command list")
                continue
            for cmd in commands:
                action = cmd.get("action") if isinstance(cmd, dict) else None
                if not isinstance(action, str) or not _is_safe_command(action):
                    bot.log(f"⚠️ Dashboard command rejected: {str(action)[:64]}")
                    continue
                action = action.strip()
                bot.log(f"📨 Dashboard command: {action}")
                try:
                    bot.handle_command(action)
                except Exception as error:
                    bot.log(f"⚠️ CMD handler error for {action}: {error}")
        except Exception as error:
            bot.log(f"⚠️ CMD consume error for {name}: {error}")
        finally:
            try:
                os.remove(claimed)
            except OSError as cleanup_error:
                bot.log(f"⚠️ CMD cleanup error: {cleanup_error}")
