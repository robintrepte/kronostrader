from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TRADER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRADER_ROOT))

from app.config import get_settings
from app.market_data import fetch_candles
from app.ssl_util import configure_ssl


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    configure_ssl(verify=settings.ssl_verify)
    candles = fetch_candles(settings, "AAPL")
    print(f"count={len(candles)}")
    if candles:
        print(f"first={candles[0].timestamp.isoformat()} close={candles[0].close}")
        print(f"last={candles[-1].timestamp.isoformat()} close={candles[-1].close}")


if __name__ == "__main__":
    main()
