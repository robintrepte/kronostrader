from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import Settings


class RuntimeState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.candles: dict[str, list[dict[str, Any]]] = {s: [] for s in settings.symbols}
        self.forecasts: dict[str, dict[str, Any] | None] = {s: None for s in settings.symbols}
        self.positions: list[dict[str, Any]] = []
        self.orders: list[dict[str, Any]] = []
        self.equity: list[dict[str, Any]] = []
        self.activity: list[dict[str, Any]] = []
        self.selected_symbol: str = settings.symbols[0] if settings.symbols else "AAPL"
        self.lock = asyncio.Lock()
        # Local paper book when dry-run
        self._local_positions: dict[str, float] = {}
        self._local_avg: dict[str, float] = {}

    def add_activity(self, kind: str, message: str, symbol: str | None = None, meta: dict | None = None) -> dict:
        entry = {
            "id": str(uuid4()),
            "kind": kind,
            "message": message,
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "meta": meta or {},
        }
        self.activity.insert(0, entry)
        self.activity = self.activity[:200]
        return entry

    def snapshot(self) -> dict[str, Any]:
        return {
            "symbols": self.settings.symbols,
            "selectedSymbol": self.selected_symbol,
            "candles": self.candles,
            "forecasts": self.forecasts,
            "positions": self.positions,
            "orders": self.orders[:50],
            "equity": self.equity[-200:],
            "activity": self.activity[:100],
            "risk": {
                "maxPositionSize": self.settings.max_position_size,
                "maxPortfolioExposure": self.settings.max_portfolio_exposure,
                "stopLossPct": self.settings.stop_loss_pct,
            },
            "paper": self.settings.use_paper,
            "dryRun": self.settings.dry_run,
            "live": self.settings.live_trading_enabled,
        }


state: RuntimeState | None = None


def get_state() -> RuntimeState:
    global state
    if state is None:
        from app.config import get_settings

        state = RuntimeState(get_settings())
    return state
