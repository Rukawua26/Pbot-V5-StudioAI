"""Pure TTF evaluation on already-closed candles; reservation belongs to acceptance."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

from core.strategy.triple_tf.closed_candles import last_close_ms


@dataclass(frozen=True)
class TTFSignalParams:
    adaptive_rvol_enabled: bool = True
    min_rvol: float = 0.8
    min_1h_vol_usd: float = 3_000_000.0
    max_setup_minutes: int = 15
    min_fvg_gap_pct: float = 0.30
    trigger_timeframe: str = "1m"

    @classmethod
    def from_config(cls, config):
        return cls(
            adaptive_rvol_enabled=bool(
                getattr(config, "TRIAGE_ADAPTIVE_RVOL_ENABLED", True)
            ),
            min_rvol=float(getattr(config, "TRIAGE_MIN_RVOL", 0.8)),
            min_1h_vol_usd=float(getattr(config, "TRIAGE_MIN_1H_VOL_USD", 3_000_000.0)),
            max_setup_minutes=int(getattr(config, "TTF_MAX_PULLBACK_AGE_MINUTES", 15)),
            min_fvg_gap_pct=float(getattr(config, "TTF_MIN_FVG_GAP_PCT", 0.30)),
        )


@dataclass
class TTFDecision:
    side: str = "WAIT"
    confidence: float = 0.0
    reason: str = ""
    suggested_sl: float = 0.0
    entry_price: float = 0.0
    setup_key: tuple | None = None
    signal_close_time: int | None = None
    bias: Any = None
    structure: Any = None
    fvg: Any = None
    trigger: Any = None
    telemetry: dict = field(default_factory=dict)


def reserve_setup(owner, setup_key) -> bool:
    """Reserve in insertion order, once. Shared by runtime and offline acceptance."""
    consumed = getattr(owner, "_ttf_consumed_setups", None)
    if consumed is None:
        consumed = {}
        owner._ttf_consumed_setups = consumed
    if setup_key in consumed:
        return False
    consumed[setup_key] = None
    if len(consumed) > 200:
        for key in list(consumed)[: len(consumed) - 100]:
            del consumed[key]
    return True


def evaluate_ttf_signal(
    df_1h, df_5m, df_1m, *, spread=0.0, params=None, consumed_setups=(), symbol="Asset"
) -> TTFDecision:
    """No input/state mutation or I/O. Missing frames produce staged WAIT decisions."""
    from core.strategy.triple_tf.bias_1h import evaluate_bias_1h
    from core.strategy.triple_tf.structure_5m import evaluate_structure_5m
    from core.strategy.triple_tf.fvg_5m import detect_fvg_5m
    from core.strategy.triple_tf.trigger_1m import evaluate_trigger_1m

    p = params or TTFSignalParams()
    d = TTFDecision()
    d.bias = evaluate_bias_1h(df_1h)
    b = d.bias
    rvol_status = "DISABLED"
    rvol = vol = None
    dormant = False
    if p.adaptive_rvol_enabled and df_1h is not None and len(df_1h) >= 2:
        try:
            close = float(df_1h.iloc[-1]["close"])
            volume = float(df_1h.iloc[-1]["volume"])
            vol = close * volume if math.isfinite(close * volume) else 0.0
            recent = df_1h.tail(24)
            avg = (
                float((recent["volume"] * recent["close"]).dropna().mean())
                if len(recent) >= 6
                else 0.0
            )
            avg = avg if math.isfinite(avg) and avg > 0 else 1.0
            rvol = vol / avg
            dormant = rvol < p.min_rvol and vol < p.min_1h_vol_usd
            rvol_status = "VOL_DORMIDO" if dormant else "ACTIVE"
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            rvol_status = f"RVOL_ERROR:{type(exc).__name__}"
    d.reason = f"1H:{b.reason}"
    if dormant:
        d.side = "NEUTRAL"
        d.reason = f"VOL_DORMIDO: RVol={rvol:.2f}x < {p.min_rvol}x y vol_1h=${vol:,.0f} < ${p.min_1h_vol_usd:,.0f}"
    elif b.bias in {"BUY", "SELL"}:
        d.structure = evaluate_structure_5m(
            df_5m=df_5m, bias_1h=b.bias, max_setup_minutes=p.max_setup_minutes
        )
        s = d.structure
        d.suggested_sl = float(s.suggested_sl or 0.0)
        d.reason += f" | 5M:{s.reason}"
        d.confidence = 40.0
        if s.valid_setup:
            d.fvg = detect_fvg_5m(
                df_5m=df_5m, bias_1h=b.bias, min_gap_pct=p.min_fvg_gap_pct
            )
            d.suggested_sl = float(
                d.fvg.suggested_sl if d.fvg is not None else s.suggested_sl or 0.0
            )
            d.trigger = evaluate_trigger_1m(
                df_1m=df_1m,
                bias_1h=b.bias,
                setup_5m_valid=True,
                spread=spread,
                fvg_zone=d.fvg,
            )
            t = d.trigger
            d.confidence = 50.0
            d.signal_close_time = last_close_ms(df_1m, p.trigger_timeframe)
            d.entry_price = float(t.entry_price or 0.0)
            if d.entry_price <= 0 and df_1m is not None and len(df_1m):
                d.entry_price = float(df_1m["close"].iloc[-1])
            trigger_reason = t.reason
            if t.triggered and t.side in {"BUY", "SELL"}:
                d.setup_key = (symbol, s.mss_time, s.pullback_time)
                if (
                    s.mss_time
                    and s.pullback_time
                    and t.trigger_time
                    and not s.mss_time < s.pullback_time <= t.trigger_time
                ):
                    trigger_reason = "TTF_CAUSALITY_VIOLATION"
                elif d.setup_key in consumed_setups:
                    trigger_reason = "TTF_SETUP_ALREADY_CONSUMED"
                else:
                    d.side, d.confidence = t.side, 85.0
            d.reason += f" | 1M:{trigger_reason}"
            if d.side in {"BUY", "SELL"}:
                d.reason = f"TTF_ENTRY_CONFIRMED: 1H={b.bias}, 5M=MSS+Pullback, 1M={trigger_reason}"
    valid = d.structure is not None and d.structure.valid_setup
    directional = b.bias in {"BUY", "SELL"} and not dormant
    votos = {
        "TTF_1H": (100.0 if b.bias == "BUY" else 0.0) if directional else 50.0,
        "TTF_5M": 100.0 if valid else 50.0,
    }
    if dormant:
        votos["RVOL"] = 0.0
    metrics = {"bias_1h": b.__dict__}
    if d.structure is not None:
        metrics["structure_5m"] = d.structure.__dict__
    if d.trigger is not None:
        metrics.update(
            fvg_5m=d.fvg.__dict__ if d.fvg else None,
            trigger_1m=d.trigger.__dict__,
            setup_key=d.setup_key,
        )
    trend = "UP" if b.bias == "BUY" else "DOWN"
    d.telemetry = {
        "regime": "VOL_DORMIDO" if dormant else f"TTF_{b.bias}",
        "reason": d.reason,
        "bias_1h": b.bias,
        "setup_5m_valid": valid,
        "trigger_1m_ready": bool(d.trigger and d.trigger.triggered),
        "stop_loss": d.suggested_sl,
        "votos": votos,
        "ttf_metrics": metrics,
        "atr_pct": 0.01,
        "adx": 0.0 if dormant else (25.0 if directional else 20.0),
        "rsi": {"val": 50.0},
        "trend": trend if directional else "RANGE",
        "base_trend": trend,
        "agent_direction_score": (50.0 if d.side == "BUY" else -50.0)
        if d.side in {"BUY", "SELL"}
        else (25.0 if b.bias == "BUY" else -25.0)
        if directional and not valid
        else 0.0,
        "agent_signal_override": False,
        "agent_signal_resolved": d.side if directional else "WAIT",
        "rvol_status": rvol_status,
    }
    if rvol is not None:
        d.telemetry.update(rvol_1h=rvol, vol_1h_usd=vol)
    if d.trigger is not None:
        d.telemetry.update(signal_close_time=d.signal_close_time, setup_key=d.setup_key)
    return d
