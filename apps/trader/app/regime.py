from __future__ import annotations

from dataclasses import dataclass

from app.assets import is_crypto_symbol
from app.strategies.base import Candle


@dataclass
class RegimeDecision:
    ok: bool
    reason: str
    vol_pct: float
    trend_pct: float


def _atr_pct(candles: list[Candle], lookback: int = 20) -> float:
    window = candles[-lookback:] if len(candles) >= lookback else candles
    if len(window) < 2:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(window)):
        prev = window[i - 1].close
        c = window[i]
        tr = max(c.high - c.low, abs(c.high - prev), abs(c.low - prev))
        trs.append(tr / prev if prev else 0.0)
    return (sum(trs) / len(trs)) * 100.0 if trs else 0.0


def _ema(values: list[float], span: int) -> float:
    if not values:
        return 0.0
    alpha = 2 / (span + 1)
    ema = values[0]
    for v in values[1:]:
        ema = alpha * v + (1 - alpha) * ema
    return ema


def evaluate_regime(
    candles: list[Candle],
    symbol: str,
    *,
    equity_session_open: bool,
    max_vol_pct: float = 2.5,
    min_trend_pct: float = 0.05,
) -> RegimeDecision:
    """Strict regime: skip chop / extreme vol; equities need cash session open."""
    if not is_crypto_symbol(symbol) and not equity_session_open:
        return RegimeDecision(False, "equity session closed", 0.0, 0.0)

    if len(candles) < 30:
        return RegimeDecision(False, "insufficient bars for regime", 0.0, 0.0)

    vol = _atr_pct(candles, 20)
    closes = [c.close for c in candles[-40:]]
    ema_fast = _ema(closes, 8)
    ema_slow = _ema(closes, 21)
    mid = closes[-1] or 1.0
    trend = abs(ema_fast - ema_slow) / mid * 100.0

    if vol > max_vol_pct:
        return RegimeDecision(False, f"vol too high ({vol:.2f}% > {max_vol_pct}%)", vol, trend)

    if trend < min_trend_pct:
        return RegimeDecision(
            False, f"chop / weak trend ({trend:.3f}% < {min_trend_pct}%)", vol, trend
        )

    return RegimeDecision(True, "regime ok", vol, trend)
