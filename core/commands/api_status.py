from tools.notifier import send_telegram_msg


def _handle_api_status_commands(bot, text: str) -> bool:
    if text in ("/api_status", "/api", "/weight"):
        wt = getattr(bot, "weight_tracker", None)
        if wt is None:
            send_telegram_msg("⚠️ *API Status*\nWeight tracker no disponible.")
            return True

        report = wt.get_formatted_report()
        send_telegram_msg(f"📡 *API Status*\n```\n{report}\n```")
        return True

    return False
