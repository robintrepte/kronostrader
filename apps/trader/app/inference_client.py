from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings
from app.strategies.base import Candle, ForecastPoint

logger = logging.getLogger(__name__)


async def request_forecast(
    settings: Settings,
    symbol: str,
    candles: list[Candle],
    sample_count: int = 2,
) -> tuple[list[ForecastPoint], dict[str, Any]]:
    bars = [
        {
            "timestamp": c.timestamp.isoformat(),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles[- settings.lookback_bars :]
    ]
    # Cap at 512
    bars = bars[-512:]

    payload = {
        "symbol": symbol,
        "bars": bars,
        "pred_len": settings.pred_len,
        "sample_count": sample_count,
        "T": 1.0,
        "top_p": 0.9,
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{settings.inference_url.rstrip('/')}/predict", json=payload)
        resp.raise_for_status()
        data = resp.json()

    points: list[ForecastPoint] = []
    for p in data.get("forecast", []):
        points.append(
            ForecastPoint(
                timestamp=_parse_ts(p["timestamp"]),
                open=float(p["open"]),
                high=float(p["high"]),
                low=float(p["low"]),
                close=float(p["close"]),
                volume=float(p.get("volume") or 0),
                close_low=float(p["close_low"]) if p.get("close_low") is not None else None,
                close_high=float(p["close_high"]) if p.get("close_high") is not None else None,
            )
        )
    return points, data


def _parse_ts(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00"))
