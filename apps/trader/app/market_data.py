from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.strategies.base import Candle

logger = logging.getLogger(__name__)


def _timeframe_to_delta(tf: str) -> timedelta:
    mapping = {
        "1Min": timedelta(minutes=1),
        "5Min": timedelta(minutes=5),
        "15Min": timedelta(minutes=15),
        "1Hour": timedelta(hours=1),
        "1Day": timedelta(days=1),
    }
    return mapping.get(tf, timedelta(minutes=5))


def mock_candles(symbol: str, lookback: int, timeframe: str) -> list[Candle]:
    delta = _timeframe_to_delta(timeframe)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    # Deterministic-ish walk from symbol hash
    seed = sum(ord(c) for c in symbol) % 50
    price = 100.0 + seed
    out: list[Candle] = []
    for i in range(lookback):
        ts = now - delta * (lookback - i)
        drift = math.sin((i + seed) / 9.0) * 0.4
        o = price
        c = max(1.0, price + drift)
        h = max(o, c) + 0.15
        l = min(o, c) - 0.15
        out.append(
            Candle(
                symbol=symbol,
                timestamp=ts,
                open=round(o, 4),
                high=round(h, 4),
                low=round(l, 4),
                close=round(c, 4),
                volume=1000 + i * 3,
            )
        )
        price = c
    return out


def fetch_candles(settings: Settings, symbol: str) -> list[Candle]:
    if settings.mock_market_data or not settings.alpaca_api_key:
        logger.info("Using mock market data for %s", symbol)
        return mock_candles(symbol, settings.lookback_bars, settings.bar_timeframe)

    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    tf_map = {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
        "1Day": TimeFrame(1, TimeFrameUnit.Day),
    }
    timeframe = tf_map.get(settings.bar_timeframe, TimeFrame(5, TimeFrameUnit.Minute))
    client = StockHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_secret_key)
    end = datetime.now(timezone.utc)
    # Over-fetch then trim
    start = end - _timeframe_to_delta(settings.bar_timeframe) * (settings.lookback_bars + 5)
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        limit=settings.lookback_bars,
    )
    bars = client.get_stock_bars(req)
    raw = bars.data.get(symbol, [])
    candles: list[Candle] = []
    for b in raw:
        candles.append(
            Candle(
                symbol=symbol,
                timestamp=b.timestamp if b.timestamp.tzinfo else b.timestamp.replace(tzinfo=timezone.utc),
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume or 0),
            )
        )
    return candles[-settings.lookback_bars :]
