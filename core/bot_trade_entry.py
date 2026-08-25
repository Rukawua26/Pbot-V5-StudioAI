from core.trade_manager import execute_order as tm_execute_order


def execute_order(
    bot,
    symbol,
    side,
    price,
    atr,
    is_shadow=False,
    vol=0.0,
    context=None,
    ob_status="⚪",
    override_usd_size=0.0,
):
    return tm_execute_order(
        bot,
        symbol=symbol,
        side=side,
        price=price,
        atr=atr,
        is_shadow=is_shadow,
        vol=vol,
        context=context,
        ob_status=ob_status,
        override_usd_size=override_usd_size,
    )
