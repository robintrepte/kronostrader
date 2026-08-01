from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.assets import is_crypto_symbol

# Correlated crypto majors — at most one new entry per cycle from this bucket.
CRYPTO_MAJOR_BUCKET = {"BTC/USD", "ETH/USD", "SOL/USD", "BTCUSD", "ETHUSD", "SOLUSD"}


@dataclass
class EntryCandidate:
    symbol: str
    strength: float
    confidence: float
    hit_rate: float
    price: float
    reason: str
    signal: Any  # Strategy Signal
    forecast_return_pct: float


def score_candidate(c: EntryCandidate) -> float:
    hr = c.hit_rate if c.hit_rate > 0 else 0.5
    return max(0.0, c.strength) * max(0.0, c.confidence) * hr


def select_entries(
    candidates: list[EntryCandidate],
    *,
    top_k: int,
    max_position_size: float,
    max_portfolio_exposure: float,
    current_exposure: float,
) -> list[tuple[EntryCandidate, float]]:
    """Return (candidate, notional) for top-K after crypto-bucket dampening."""
    if not candidates or top_k <= 0:
        return []

    ranked = sorted(candidates, key=score_candidate, reverse=True)
    picked: list[EntryCandidate] = []
    crypto_bucket_used = False

    for c in ranked:
        if len(picked) >= top_k:
            break
        sym = c.symbol
        in_bucket = sym in CRYPTO_MAJOR_BUCKET or (
            is_crypto_symbol(sym) and sym.split("/")[0] in {"BTC", "ETH", "SOL"}
        )
        if in_bucket:
            if crypto_bucket_used:
                continue
            crypto_bucket_used = True
        picked.append(c)

    if not picked:
        return []

    room = max(0.0, max_portfolio_exposure - current_exposure)
    if room < 10:
        return []

    scores = [score_candidate(c) for c in picked]
    total = sum(scores) or 1.0
    out: list[tuple[EntryCandidate, float]] = []
    remaining = room
    for c, sc in zip(picked, scores):
        weight = sc / total
        notional = min(max_position_size, remaining * weight, remaining)
        if notional < 10:
            continue
        out.append((c, notional))
        remaining -= notional
    return out
