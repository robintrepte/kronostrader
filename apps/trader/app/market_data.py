from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

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


def fetch_candles(settings: Settings, symbol: str) -> list[Candle]:
    if settings.mock_market_data:
        raise MarketDataError(
            "MOCK_MARKET_DATA is enabled. Disable it — synthetic candles are not allowed."
        )
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        raise MarketDataError(
            "Alpaca API keys missing. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env."
        )
    return _fetch_alpaca_candles(settings, symbol)


def _fetch_alpaca_candles(settings: Settings, symbol: str) -> list[Candle]:
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    feed_name = (settings.alpaca_data_feed or "iex").strip().lower()
    feed = DataFeed.SIP if feed_name == "sip" else DataFeed.IEX

    tf_map = {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
        "1Day": TimeFrame(1, TimeFrameUnit.Day),
    }
    timeframe = tf_map.get(settings.bar_timeframe, TimeFrame(5, TimeFrameUnit.Minute))
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
        raise MarketDataError(f"Alpaca bars failed for {symbol}: {exc}") from exc

    raw = bars.data.get(symbol, [])
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
    if not candles:
        raise MarketDataError(
            f"Alpaca returned 0 bars for {symbol} "
            f"(feed={feed.value}, timeframe={settings.bar_timeframe}, "
            f"window={start.isoformat()}→{end.isoformat()}). "
            "Market may be closed or the symbol/subscription may be invalid."
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
