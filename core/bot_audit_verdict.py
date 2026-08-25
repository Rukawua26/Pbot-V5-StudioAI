from config import Config


def get_audit_verdict(
    bot,
    symbol,
    prob_ia,
    signal,
    ob_status,
    pnl_hoy,
    meta_actual,
    mode="NONE",
    ctx=None,
):
    """Analiza filtros y devuelve la razón exacta del estado actual."""
    if signal not in ["BUY", "SELL"]:
        return "⏳ ESPERANDO TÉCNICA"

    # Filtros de entrada y concesiones informativas.
    if ctx:
        filter_veto = ctx.get("filter_veto")
        if filter_veto:
            return f"⛔ VETO: {filter_veto}"

        # Las concesiones son informativas, no vetos duros. Una probabilidad alta
        # significa que el consenso superó los warnings individuales.
        strategy_warnings = ctx.get("veto_reason")
        if strategy_warnings and prob_ia * 100 < 75:
            # Bajo 75%: reportar el riesgo y dejar que el umbral decida
            return f"⚠️ RIESGO: {strategy_warnings}"
        # Si prob >= 75, ignorar los warnings porque el consenso los superó.

    ia_percent = prob_ia * 100

    # --- VETO DE SEGURIDAD (PRIORIDAD MÁXIMA) ---
    # 1. DISPARO REAL: Confianza alta (basado en Config.REAL_CONFIDENCE_MIN)
    real_min = Config.REAL_CONFIDENCE_MIN * 100
    shadow_min = float(getattr(Config, "SHADOW_MODE_MIN", Config.SHADOW_PROB_MIN * 100))

    # VETO DE SEGURIDAD: Si ya llegamos a la meta, todo es SHADOW
    if pnl_hoy >= meta_actual:
        return f"🧪 SHADOW (META {pnl_hoy:.2f}%)"

    if ia_percent >= real_min:
        # Si la estrategia dice que es modo SHADOW (por técnica), respetamos
        if mode == "SHADOW":
            return "🧪 SHADOW (TÉCNICA LIMITADA)"

        # VETO REAL: Solo si BTC cae y es compra
        if bot.current_sentiment[0] == "🔴 TENDENCIA BAJISTA" and signal == "BUY":
            return "⛔ VETO: TENDENCIA BTC (PROTECCIÓN REAL)"
        return f"🚀 OK: REAL ({ia_percent:.1f}% | OB:{ob_status})"

    # 2. MODO SHADOW: EXPLORADOR
    if ia_percent >= shadow_min:
        return f"👻 SHADOW (IA {ia_percent:.1f}% | {shadow_min}-{real_min - 1}%)"

    return f"❌ VETO: BAJA PROB IA ({ia_percent:.1f}%)"
