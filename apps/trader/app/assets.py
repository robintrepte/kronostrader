from __future__ import annotations

# Quote currencies Alpaca crypto pairs use — used to normalize BTCUSD → BTC/USD.
_CRYPTO_QUOTES = ("USDT", "USDC", "USD", "BTC", "ETH")


def normalize_symbol(raw: str) -> str:
    """Canonical ticker: uppercased; crypto pairs keep or gain a slash (BTC/USD)."""
    s = raw.strip().upper().replace(" ", "")
    if not s:
        return s
    if "/" in s:
        parts = [p for p in s.split("/") if p]
        if len(parts) == 2:
            return f"{parts[0]}/{parts[1]}"
        return s
    for quote in _CRYPTO_QUOTES:
        if s.endswith(quote) and len(s) > len(quote) + 1:
            base = s[: -len(quote)]
            if base.isalpha() and 2 <= len(base) <= 6:
                return f"{base}/{quote}"
    return s


def is_crypto_symbol(symbol: str) -> bool:
    """Alpaca crypto trading pairs always contain '/' (e.g. BTC/USD)."""
    return "/" in (symbol or "")


def asset_class_of(symbol: str) -> str:
    return "crypto" if is_crypto_symbol(symbol) else "us_equity"


def partition_symbols(symbols: list[str]) -> tuple[list[str], list[str]]:
    """Return (equity_symbols, crypto_symbols) preserving order."""
    equity: list[str] = []
    crypto: list[str] = []
    for s in symbols:
        if is_crypto_symbol(s):
            crypto.append(s)
        else:
            equity.append(s)
    return equity, crypto
