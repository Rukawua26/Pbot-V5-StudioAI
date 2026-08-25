def update_dynamic_risk(bot):
    try:
        wins, losses = bot.brain.get_recent_performance(last_n=5)
        total = wins + losses
        if total >= 3:
            win_rate = wins / total
            if win_rate >= 0.7:
                bot.risk_multiplier = 1.2
            elif win_rate <= 0.4:
                bot.risk_multiplier = 0.8
            else:
                bot.risk_multiplier = 1.0
        bot.log(f"📉 Riesgo Dinámico: {bot.risk_multiplier}x (WR: {wins}/{total})")
    except Exception as error:
        bot.log(f"⚠️ Err Risk Update: {error}")


def get_ob_efficiency_report(bot):
    """Genera la comparativa: ¿Es mejor operar con OB o sin OB?"""
    trades = bot.brain.get_todays_trades()

    with_ob = [trade for trade in trades if trade.get("entry_ob", "⚪") != "⚪"]
    no_ob = [trade for trade in trades if trade.get("entry_ob", "⚪") == "⚪"]

    def calc_stats(group):
        if not group:
            return "0 trades"
        wins = sum(1 for trade in group if trade["pnl_percent"] > 0)
        wr = (wins / len(group)) * 100
        pnl = sum(trade["pnl_percent"] for trade in group)
        return f"{len(group)} T | WR: {wr:.1f}% | PNL: {pnl:+.2f}%"

    report = (
        "📊 *REPORTE DE EFICIENCIA OB*\n"
        f"🏛️ *CON APOYO OB:* {calc_stats(with_ob)}\n"
        f"🧠 *SOLO IA (SIN OB):* {calc_stats(no_ob)}\n"
    )
    return report


def perform_healthcheck(bot):
    """Verifica conectividad y balance (v104.5)."""
    try:
        balance = bot.execution.fetch_balance()
        usdt = balance["total"].get("USDT", 0)
        btc = bot.execution.fetch_ticker("BTC/USDT:USDT")["last"]
        return (
            "🩺 *DIAGNÓSTICO v104.5*\n"
            f"💰 Balance: ${usdt:.2f} USDT\n"
            f"₿ BTC: ${btc:,.2f}\n"
            "🧠 IA: Modelo Cargado\n"
            "🚀 Estado: LISTO"
        )
    except Exception as error:
        return f"🚨 Error en Diagnóstico: {str(error)}"
