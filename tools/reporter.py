"""
SNIPER AI - ELITE INSIGHTS REPORTER v5.1
========================================
Generador de reportes de inteligencia operativa.
"""
from tools.learning import Brain
from config import Config

def generate_mobile_report(balance=0.0, limit=None):
    """Genera el Dashboard de Comando Elite Insights."""
    brain = Brain()
    data = brain.get_elite_insights_stats()
    
    # Estimación de Capital Protegido (Vetos * Riesgo por Trade)
    # Si el balance es 0 (no pasado), usamos un valor base de referencia o mostramos 0
    risk_usd = (balance * Config.RISK_PER_TRADE / 100) if balance > 0 else 0
    saved_usd = data['veto_count'] * risk_usd

    report = (
        f"🚀 *ELITE INSIGHTS v5.1*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"1️⃣ *SALUD EJECUTIVA*\n"
        f"🌍 *Estado:* {data['market_state']}\n"
        f"🧠 *Nivel IA:* {data['level']}/10 (Analista)\n"
        f"🧪 *Micro-Simulaciones:* {data['sim_count']} hoy\n"
        f"📊 *Efectividad I+D:* {data['sim_wr']:.1f}%\n\n"
        
        f"2️⃣ *INVENTARIO ESTRATÉGICO*\n"
        f"🐂 *Bullish:* {data['inventory'].get('UP', 0)} patrones\n"
        f"🐻 *Bearish:* {data['inventory'].get('DOWN', 0)} patrones\n"
        f"🦀 *Lateral:* {data['inventory'].get('RANGO', 0)} patrones\n\n"
        
        f"3️⃣ *ESCUDO DE SEGURIDAD*\n"
        f"🛡️ *Trades Bloqueados:* {data['veto_count']}\n"
        f"💰 *Capital Protegido:* ~${saved_usd:.2f}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    return report

def generate_audit_report(trades):
    """Genera un reporte compacto de los últimos trades para auditoría."""
    if not trades:
        return "📭 No hay trades registrados para auditoría."

    wins = sum(1 for t in trades if t['pnl_percent'] > 0)
    total = len(trades)
    wr = (wins / total * 100) if total > 0 else 0
    total_pnl = sum(t['pnl'] for t in trades)

    header = (
        f"📋 *REPORTE DE AUDITORÍA ({total} TRADES)*\n"
        f"📊 *Win Rate:* {wr:.1f}% ({wins}W / {total - wins}L)\n"
        f"💰 *PnL Total:* ${total_pnl:+.2f}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    rows = []
    for t in trades[:30]:  # Limitar a 30 trades para no exceder límites de Telegram
        emoji = "✅" if t['pnl_percent'] > 0 else "❌"
        mode = "🧪" if t['is_shadow'] else "🔥"
        side = "L" if t['side'] == 'BUY' else "S"
        row = f"{emoji}{mode} {t['symbol'][:6]} {side} {t['pnl_percent']:+.1f}%"
        rows.append(row)

    footer = f"\n━━━━━━━━━━━━━━━━━━━━\n_Mostrando últimos {min(total, 30)} trades._"
    
    return header + "\n".join(rows) + footer

def generate_terminal_audit_table(trades):
    """Genera una tabla de Rich para visualizar auditoría en la terminal."""
    from rich.table import Table
    from rich import box
    
    if not trades:
        return "📭 No hay trades registrados."

    # Calcular totales y estadísticas por par
    relevant_trades = trades[:100]
    total_pnl_pct = sum(t.get('pnl_percent', 0) for t in relevant_trades)
    total_pnl_usd = sum(t.get('pnl', 0) for t in relevant_trades)
    
    # Estadísticas por par (Win/Loss en los últimos 100)
    pair_stats = {}
    for t in relevant_trades:
        sym = t.get('symbol', '').split(':')[0]
        if sym not in pair_stats:
            pair_stats[sym] = {'W': 0, 'L': 0}
        if t.get('pnl_percent', 0) > 0:
            pair_stats[sym]['W'] += 1
        else:
            pair_stats[sym]['L'] += 1

    pnl_pct_color = "bold green" if total_pnl_pct >= 0 else "bold red"
    pnl_usd_color = "bold green" if total_pnl_usd >= 0 else "bold red"

    table = Table(
        title=f"📊 REPORTE DE AUDITORÍA (Últimos {len(relevant_trades)})",
        box=box.DOUBLE_EDGE,
        header_style="bold cyan",
        show_footer=True,
        expand=True
    )
    
    table.add_column("ID", justify="right", style="dim")
    table.add_column("FECHA", justify="center")
    table.add_column("PAR", style="bold white", footer="TOTALES")
    table.add_column("W/L (100)", justify="center", style="dim")
    table.add_column("LADO", justify="center")
    table.add_column("ENTRY", justify="right")
    table.add_column("EXIT", justify="right")
    table.add_column("PNL%", justify="right", footer=f"[{pnl_pct_color}]{total_pnl_pct:+.2f}%[/]")
    table.add_column("USD", justify="right", footer=f"[{pnl_usd_color}]${total_pnl_usd:+.2f}[/]")
    table.add_column("MODE", justify="center")
    
    for i, t in enumerate(relevant_trades):
        pnl_pct = t.get('pnl_percent', 0)
        pnl_usd = t.get('pnl', 0)
        color = "green" if pnl_pct > 0 else "red"
        
        sym = t.get('symbol', '').split(':')[0]
        stats = pair_stats.get(sym, {'W': 0, 'L': 0})
        wl_str = f"[green]{stats['W']}W[/] [red]{stats['L']}L[/]"

        mode = "🧪" if t.get('is_shadow') else "🔥"
        side = "LONG" if t.get('side') == 'BUY' else "SHORT"
        side_color = "green" if t.get('side') == 'BUY' else "red"
        
        table.add_row(
            str(len(relevant_trades) - i),
            t.get('timestamp', '')[5:16].replace('T', ' '),
            sym,
            wl_str,
            f"[{side_color}]{side}[/]",
            f"{t.get('entry_price', 0):.4f}",
            f"{t.get('exit_price', 0):.4f}",
            f"[{color}]{pnl_pct:+.2f}%[/]",
            f"[{color}]${pnl_usd:+.2f}[/]",
            mode
        )
        
    return table