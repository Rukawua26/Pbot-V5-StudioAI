def load_ai_restrictions(bot):
    """Carga las listas negras generadas por el AI Coach desde la BD."""
    try:
        bot.restricted_hours = bot.brain.get_hourly_blacklist()
        bot.restricted_sectors = bot.brain.get_sector_blacklist()
        if bot.restricted_hours or bot.restricted_sectors:
            bot.log("🧠 Restricciones del AI Coach cargadas.")
            if bot.restricted_hours:
                bot.log(f"   - 🚫 Horas vetadas: {bot.restricted_hours}")
            if bot.restricted_sectors:
                bot.log(f"   - 🚫 Sectores vetados: {bot.restricted_sectors}")
    except Exception as error:
        bot.log(f"⚠️ Error cargando restricciones del AI Coach: {error}")


def self_adjust_exigency(bot):
    """La IA analiza su éxito reciente y ajusta su propia dificultad (v105.6)."""
    with bot.db_lock:
        stats = bot.brain.get_stats()
    # Obtenemos el Win Rate de los últimos 50 trades shadow
    recent_swr = stats.get("shadow_win_rate", 50.0)

    # Lógica v105.6: Si el éxito cae del 45%, subimos la vara +0.05
    if recent_swr < 45.0:
        bot.dynamic_offset = 0.05  # +5% de exigencia
        status_suffix = f" (🔒 EXIGENCIA +5% | WR: {recent_swr:.1f}%)"
    else:
        bot.dynamic_offset = 0.0
        status_suffix = ""

    return status_suffix


def get_vol_24h(symbol, tickers):
    """Obtiene el volumen 24h de los tickers de forma robusta."""
    if not tickers:
        return 0.0

    clean_symbol = symbol.split(":")[0]

    if clean_symbol in tickers:
        return float(tickers[clean_symbol].get("quoteVolume", 0) or 0)

    for key, val in tickers.items():
        if key == clean_symbol or key.split("/")[0] == clean_symbol.split("/")[0]:
            return float(val.get("quoteVolume", 0) or 0)

    return 0.0


def handle_command(bot, text, handle_basic_command_fn, export_dataset_fn, notify_fn):
    """Centraliza la lógica de comandos para Telegram y Dashboard."""
    text = text.strip()

    if handle_basic_command_fn(bot, text):
        return

    if text == "/export_data":
        if export_dataset_fn:
            export_dataset_fn()
            notify_fn("✅ Dataset Maestro exportado correctamente.")
        else:
            notify_fn("❌ Script de exportación no encontrado.")
