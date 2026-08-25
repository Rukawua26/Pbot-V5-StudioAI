def normalize_position_symbol(
    pos_symbol: str,
    default_quote: str | None = None,
    strict: bool = False,
) -> str:
    """Normalize exchange position symbols to the internal SYMBOL/USDT format."""
    clean = str(pos_symbol or "").split(":")[0].strip().upper().replace(" ", "")
    if not clean:
        return ""

    if "/" in clean:
        base = clean.split("/", 1)[0]
        if len(base) < 2:
            return "" if strict else clean
        quote = default_quote or clean.split("/", 1)[1] or "USDT"
        return f"{base}/{quote}"

    for suffix in ("USDT", "BUSD", "USDC", "USD"):
        if clean.endswith(suffix):
            base = clean[: -len(suffix)]
            if len(base) > 1:
                quote = default_quote or suffix
                return f"{base}/{quote}"

    if default_quote and len(clean) > 1 and clean.isalnum():
        return f"{clean}/{default_quote}"

    return "" if strict else clean
