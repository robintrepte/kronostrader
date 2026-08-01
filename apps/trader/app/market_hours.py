from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.config import Settings

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


def crypto_session_clock() -> dict[str, Any]:
    """Alpaca crypto spot trades 24/7 (aside from rare maintenance)."""
    now = datetime.now(timezone.utc)
    return {
        "isOpen": True,
        "nextOpen": None,
        "nextClose": None,
        "timestamp": now.isoformat(),
        "source": "crypto_24_7",
    }


def _fallback_rth_clock(now: datetime | None = None) -> dict[str, Any]:
    """US cash equity RTH approx when Alpaca clock is unavailable (weekdays 9:30–16:00 ET)."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(_ET)
    open_t = time(9, 30)
    close_t = time(16, 0)
    weekday = local.weekday() < 5
    is_open = weekday and open_t <= local.time() < close_t

    def _next_open(from_local: datetime) -> datetime:
        d = from_local.date()
        candidate = datetime.combine(d, open_t, tzinfo=_ET)
        if from_local.time() >= open_t or not (from_local.weekday() < 5):
            d = d + timedelta(days=1)
            candidate = datetime.combine(d, open_t, tzinfo=_ET)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)

    def _next_close(from_local: datetime) -> datetime:
        d = from_local.date()
        candidate = datetime.combine(d, close_t, tzinfo=_ET)
        if from_local.time() >= close_t or not (from_local.weekday() < 5):
            return _next_open(from_local) + timedelta(hours=6, minutes=30)
        return candidate.astimezone(timezone.utc)

    return {
        "isOpen": is_open,
        "nextOpen": _next_open(local).isoformat(),
        "nextClose": _next_close(local).isoformat(),
        "timestamp": now.isoformat(),
        "source": "fallback_rth_et",
    }


def fetch_market_clock(settings: Settings) -> dict[str, Any]:
    """Return Alpaca market clock when keys exist; else weekday RTH fallback."""
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        return _fallback_rth_clock()

    try:
        from alpaca.trading.client import TradingClient

        client = TradingClient(
            settings.alpaca_api_key.strip().strip('"'),
            settings.alpaca_secret_key.strip().strip('"'),
            paper=settings.use_paper,
        )
        clock = client.get_clock()
        next_open = clock.next_open
        next_close = clock.next_close
        if getattr(next_open, "tzinfo", None) is None:
            next_open = next_open.replace(tzinfo=timezone.utc)
        if getattr(next_close, "tzinfo", None) is None:
            next_close = next_close.replace(tzinfo=timezone.utc)
        return {
            "isOpen": bool(clock.is_open),
            "nextOpen": next_open.astimezone(timezone.utc).isoformat(),
            "nextClose": next_close.astimezone(timezone.utc).isoformat(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "alpaca",
        }
    except Exception:
        logger.exception("Alpaca market clock failed — using RTH fallback")
        return _fallback_rth_clock()


def seconds_until(iso_ts: str | None) -> float | None:
    if not iso_ts:
        return None
    try:
        when = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None
