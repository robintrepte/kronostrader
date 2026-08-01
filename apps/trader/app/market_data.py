from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.assets import is_crypto_symbol
from app.config import Settings
from app.strategies.base import Candle

logger = logging.getLogger(__name__)


class MarketDataError(RuntimeError):
    """Raised when real market data cannot be fetched. Never falls back to mock."""


def _timeframe_to_delta(tf: str) -> timedelta:
    mapping = {
        "1Min": timedelta(minutes=1),
        "5Min": timedelta(minutes=5),
        "15Min": timedelta(minutes=15),
        "1Hour": timedelta(hours=1),
        "1Day": timedelta(days=1),
    }
    return mapping.get(tf, timedelta(minutes=5))


def _timeframe(settings: Settings):
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    tf_map = {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
        "1Day": TimeFrame(1, TimeFrameUnit.Day),
    }
    return tf_map.get(settings.bar_timeframe, TimeFrame(5, TimeFrameUnit.Minute))


def _bars_to_candles(symbol: str, raw) -> list[Candle]:
    candles: list[Candle] = []
    for b in raw:
        candles.append(
            Candle(
                symbol=symbol,
                timestamp=b.timestamp
                if b.timestamp.tzinfo
                else b.timestamp.replace(tzinfo=timezone.utc),
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume or 0),
            )
        )
    return candles


def fetch_candles(settings: Settings, symbol: str) -> list[Candle]:
    if settings.mock_market_data:
        raise MarketDataError(
            "MOCK_MARKET_DATA is enabled. Disable it — synthetic candles are not allowed."
        )
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        raise MarketDataError(
            "Alpaca API keys missing. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env."
        )
    if is_crypto_symbol(symbol):
        return _fetch_crypto_candles(settings, symbol)
    return _fetch_stock_candles(settings, symbol)


def _fetch_stock_candles(settings: Settings, symbol: str) -> list[Candle]:
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest

    feed_name = (settings.alpaca_data_feed or "iex").strip().lower()
    feed = DataFeed.SIP if feed_name == "sip" else DataFeed.IEX
    timeframe = _timeframe(settings)
    client = StockHistoricalDataClient(
        settings.alpaca_api_key.strip().strip('"'),
        settings.alpaca_secret_key.strip().strip('"'),
    )

    # Free/basic plans disallow "recent SIP"; keep a small buffer even for IEX.
    end = datetime.now(timezone.utc) - timedelta(minutes=settings.alpaca_data_delay_minutes)
    start = end - _timeframe_to_delta(settings.bar_timeframe) * (settings.lookback_bars + 5)
    try:
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            limit=settings.lookback_bars,
            feed=feed,
        )
        bars = client.get_stock_bars(req)
    except Exception as exc:
        raise MarketDataError(f"Alpaca stock bars failed for {symbol}: {exc}") from exc

    candles = _bars_to_candles(symbol, bars.data.get(symbol, []))
    if not candles:
        raise MarketDataError(
            f"Alpaca returned 0 stock bars for {symbol} "
            f"(feed={feed.value}, timeframe={settings.bar_timeframe}, "
            f"window={start.isoformat()}→{end.isoformat()}). "
            "US equity session may be closed or the symbol/subscription may be invalid."
        )
    logger.info(
        "Fetched %s real Alpaca/%s bars for %s (last close=%.4f @ %s)",
        len(candles),
        feed.value,
        symbol,
        candles[-1].close,
        candles[-1].timestamp.isoformat(),
    )
    return candles[-settings.lookback_bars :]


def _fetch_crypto_candles(settings: Settings, symbol: str) -> list[Candle]:
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest

    timeframe = _timeframe(settings)
    client = CryptoHistoricalDataClient(
        settings.alpaca_api_key.strip().strip('"'),
        settings.alpaca_secret_key.strip().strip('"'),
    )

    # Crypto is 24/7; no IEX-style delay buffer needed.
    end = datetime.now(timezone.utc)
    start = end - _timeframe_to_delta(settings.bar_timeframe) * (settings.lookback_bars + 5)
    try:
        req = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            limit=settings.lookback_bars,
        )
        bars = client.get_crypto_bars(req)
    except Exception as exc:
        raise MarketDataError(f"Alpaca crypto bars failed for {symbol}: {exc}") from exc

    raw = bars.data.get(symbol, [])
    if not raw:
        # Some SDK versions key without slash; try both.
        alt = symbol.replace("/", "")
        raw = bars.data.get(alt, [])
    candles = _bars_to_candles(symbol, raw)
    if not candles:
        raise MarketDataError(
            f"Alpaca returned 0 crypto bars for {symbol} "
            f"(timeframe={settings.bar_timeframe}, "
            f"window={start.isoformat()}→{end.isoformat()}). "
            "Check that the pair is tradable on Alpaca (e.g. BTC/USD)."
        )
    logger.info(
        "Fetched %s real Alpaca/crypto bars for %s (last close=%.6f @ %s)",
        len(candles),
        symbol,
        candles[-1].close,
        candles[-1].timestamp.isoformat(),
    )
    return candles[-settings.lookback_bars :]
