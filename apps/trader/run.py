"""Start trader API + loop — loads root .env automatically."""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.ssl_util import configure_ssl  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    configure_ssl(verify=settings.ssl_verify)
    uvicorn.run(
        "app.main:app",
        host=settings.trader_api_host,
        port=settings.trader_api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
