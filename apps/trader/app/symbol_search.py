from __future__ import annotations

import logging
import time
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)

# Instant suggestions when the query is empty / very short
POPULAR = [
    ("AAPL", "Apple Inc."),
    ("MSFT", "Microsoft Corporation"),
    ("NVDA", "NVIDIA Corporation"),
    ("AMZN", "Amazon.com Inc."),
    ("GOOGL", "Alphabet Inc. Class A"),
    ("META", "Meta Platforms Inc."),
    ("TSLA", "Tesla Inc."),
    ("AMD", "Advanced Micro Devices"),
    ("NFLX", "Netflix Inc."),
    ("SPY", "SPDR S&P 500 ETF"),
    ("QQQ", "Invesco QQQ Trust"),
    ("IWM", "iShares Russell 2000 ETF"),
    ("JPM", "JPMorgan Chase & Co."),
    ("V", "Visa Inc."),
    ("MA", "Mastercard Inc."),
    ("COST", "Costco Wholesale"),
    ("AVGO", "Broadcom Inc."),
    ("BRK.B", "Berkshire Hathaway Class B"),
]

_cache: list[dict[str, str]] | None = None
_cache_at = 0.0
_CACHE_TTL = 60 * 60  # 1 hour


def _normalize(s: str) -> str:
    return s.strip().upper()


def _load_alpaca_assets(settings: Settings) -> list[dict[str, str]]:
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        return [{"symbol": s, "name": n} for s, n in POPULAR]

    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import AssetClass, AssetStatus
    from alpaca.trading.requests import GetAssetsRequest

    client = TradingClient(
        settings.alpaca_api_key.strip().strip('"'),
        settings.alpaca_secret_key.strip().strip('"'),
        paper=settings.use_paper,
    )
    req = GetAssetsRequest(
        status=AssetStatus.ACTIVE,
        asset_class=AssetClass.US_EQUITY,
    )
    assets = client.get_all_assets(req)
    out: list[dict[str, str]] = []
    for a in assets:
        # Prefer plain tradable equities / ETFs
        if getattr(a, "tradable", True) is False:
            continue
        if getattr(a, "status", None) and str(a.status).lower().endswith("inactive"):
            continue
        symbol = str(getattr(a, "symbol", "") or "").upper()
        name = str(getattr(a, "name", "") or "").strip()
        if not symbol or len(symbol) > 10:
            continue
        # Skip odd warrants / units noise when possible
        if any(ch in symbol for ch in ("*", "/", " ")):
            continue
        out.append({"symbol": symbol, "name": name or symbol})
    out.sort(key=lambda x: x["symbol"])
    logger.info("Cached %s Alpaca US equity symbols for search", len(out))
    return out


def get_symbol_catalog(settings: Settings, *, force: bool = False) -> list[dict[str, str]]:
    global _cache, _cache_at
    now = time.time()
    if not force and _cache is not None and now - _cache_at < _CACHE_TTL:
        return _cache
    try:
        _cache = _load_alpaca_assets(settings)
        _cache_at = now
    except Exception:
        logger.exception("Alpaca asset catalog load failed — using popular fallback")
        if _cache is None:
            _cache = [{"symbol": s, "name": n} for s, n in POPULAR]
            _cache_at = now
    return _cache


def search_symbols(
    settings: Settings,
    query: str,
    *,
    limit: int = 12,
    exclude: set[str] | None = None,
) -> list[dict[str, Any]]:
    q = _normalize(query)
    exclude = {_normalize(x) for x in (exclude or set())}
    catalog = get_symbol_catalog(settings)
    popular_rank = {s: i for i, (s, _) in enumerate(POPULAR)}

    if not q:
        base = [{"symbol": s, "name": n} for s, n in POPULAR if s not in exclude]
        return base[:limit]

    # Sort key: (match tier, popular boost, symbol length, alpha)
    scored: list[tuple[tuple[int, int, int, str], dict[str, str]]] = []
    for row in catalog:
        sym = row["symbol"]
        if sym in exclude:
            continue
        name = row.get("name", "")
        name_u = name.upper()
        if sym == q:
            tier = 0
        elif sym.startswith(q):
            tier = 1
        elif q in sym:
            tier = 2
        elif name_u.startswith(q) or f" {q}" in name_u:
            tier = 3
        elif q in name_u:
            tier = 4
        else:
            continue
        pop = popular_rank.get(sym, 999)
        scored.append(((tier, pop, len(sym), sym), row))

    scored.sort(key=lambda t: t[0])
    return [
        {"symbol": r["symbol"], "name": r.get("name", r["symbol"])}
        for _, r in scored[:limit]
    ]
