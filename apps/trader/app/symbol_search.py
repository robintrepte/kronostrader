from __future__ import annotations

import logging
import time
from typing import Any

from app.assets import asset_class_of, normalize_symbol
from app.config import Settings

logger = logging.getLogger(__name__)

# Instant suggestions when the query is empty / very short.
POPULAR_EQUITY = [
    ("SPY", "SPDR S&P 500 ETF"),
    ("QQQ", "Invesco QQQ Trust"),
    ("IWM", "iShares Russell 2000 ETF"),
    ("SMH", "VanEck Semiconductor ETF"),
    ("XLF", "Financial Select Sector SPDR"),
    ("NVDA", "NVIDIA Corporation"),
    ("TSLA", "Tesla Inc."),
    ("AAPL", "Apple Inc."),
    ("MSFT", "Microsoft Corporation"),
    ("AMZN", "Amazon.com Inc."),
    ("META", "Meta Platforms Inc."),
    ("GOOGL", "Alphabet Inc. Class A"),
    ("AMD", "Advanced Micro Devices"),
    ("AVGO", "Broadcom Inc."),
    ("NFLX", "Netflix Inc."),
    ("PLTR", "Palantir Technologies"),
    ("COIN", "Coinbase Global"),
    ("MU", "Micron Technology"),
    ("JPM", "JPMorgan Chase & Co."),
    ("BAC", "Bank of America"),
    ("ORCL", "Oracle Corporation"),
]

POPULAR_CRYPTO = [
    ("BTC/USD", "Bitcoin"),
    ("ETH/USD", "Ethereum"),
    ("SOL/USD", "Solana"),
    ("DOGE/USD", "Dogecoin"),
    ("LINK/USD", "Chainlink"),
    ("AVAX/USD", "Avalanche"),
    ("LTC/USD", "Litecoin"),
    ("UNI/USD", "Uniswap"),
    ("AAVE/USD", "Aave"),
    ("DOT/USD", "Polkadot"),
]

# Crypto first in empty-query suggestions so 24/7 pairs are easy to find.
POPULAR = POPULAR_CRYPTO + POPULAR_EQUITY

_cache: list[dict[str, str]] | None = None
_cache_at = 0.0
_CACHE_TTL = 60 * 60  # 1 hour


def _row(symbol: str, name: str) -> dict[str, str]:
    return {
        "symbol": symbol,
        "name": name,
        "assetClass": asset_class_of(symbol),
    }


def _load_alpaca_assets(settings: Settings) -> list[dict[str, str]]:
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        return [_row(s, n) for s, n in POPULAR]

    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import AssetClass, AssetStatus
    from alpaca.trading.requests import GetAssetsRequest

    client = TradingClient(
        settings.alpaca_api_key.strip().strip('"'),
        settings.alpaca_secret_key.strip().strip('"'),
        paper=settings.use_paper,
    )
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    for asset_class, kind in (
        (AssetClass.CRYPTO, "crypto"),
        (AssetClass.US_EQUITY, "us_equity"),
    ):
        req = GetAssetsRequest(
            status=AssetStatus.ACTIVE,
            asset_class=asset_class,
        )
        assets = client.get_all_assets(req)
        for a in assets:
            if getattr(a, "tradable", True) is False:
                continue
            if getattr(a, "status", None) and str(a.status).lower().endswith("inactive"):
                continue
            symbol = normalize_symbol(str(getattr(a, "symbol", "") or ""))
            name = str(getattr(a, "name", "") or "").strip()
            if not symbol or symbol in seen:
                continue
            if kind == "us_equity":
                if len(symbol) > 10:
                    continue
                if any(ch in symbol for ch in ("*", " ", "/")):
                    continue
            else:
                if "/" not in symbol:
                    continue
                if len(symbol) > 16:
                    continue
            seen.add(symbol)
            out.append(_row(symbol, name or symbol))

    out.sort(key=lambda x: (0 if x["assetClass"] == "crypto" else 1, x["symbol"]))
    logger.info(
        "Cached %s Alpaca symbols for search (%s crypto)",
        len(out),
        sum(1 for r in out if r["assetClass"] == "crypto"),
    )
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
            _cache = [_row(s, n) for s, n in POPULAR]
            _cache_at = now
    return _cache


def search_symbols(
    settings: Settings,
    query: str,
    *,
    limit: int = 12,
    exclude: set[str] | None = None,
) -> list[dict[str, Any]]:
    q = normalize_symbol(query) if query.strip() else ""
    # Also match without forcing slash so "BTC" finds BTC/USD
    q_raw = query.strip().upper()
    exclude = {normalize_symbol(x) for x in (exclude or set())}
    catalog = get_symbol_catalog(settings)
    popular_rank = {s: i for i, (s, _) in enumerate(POPULAR)}

    if not q_raw:
        base = [_row(s, n) for s, n in POPULAR if s not in exclude]
        return base[:limit]

    scored: list[tuple[tuple[int, int, int, str], dict[str, str]]] = []
    for row in catalog:
        sym = row["symbol"]
        if sym in exclude:
            continue
        name = row.get("name", "")
        name_u = name.upper()
        base = sym.split("/")[0] if "/" in sym else sym
        if sym == q or sym == q_raw:
            tier = 0
        elif base == q_raw or sym.startswith(q_raw) or sym.startswith(q):
            tier = 1
        elif q_raw in sym or (q and q in sym):
            tier = 2
        elif name_u.startswith(q_raw) or f" {q_raw}" in name_u:
            tier = 3
        elif q_raw in name_u:
            tier = 4
        else:
            continue
        pop = popular_rank.get(sym, 999)
        scored.append(((tier, pop, len(sym), sym), row))

    scored.sort(key=lambda t: t[0])
    return [
        {
            "symbol": r["symbol"],
            "name": r.get("name", r["symbol"]),
            "assetClass": r.get("assetClass", asset_class_of(r["symbol"])),
        }
        for _, r in scored[:limit]
    ]
