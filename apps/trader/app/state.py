from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import Settings

# Keep enough history to judge model accuracy across a few hours of 5m bars
FORECAST_HISTORY_LIMIT = 48


class RuntimeState:
    def __init__(self, settings: Settings) -> None:
        # Never allow mock data at runtime
        if settings.mock_market_data:
            settings.mock_market_data = False

        self.settings = settings
        self.candles: dict[str, list[dict[str, Any]]] = {s: [] for s in settings.symbols}
        self.forecasts: dict[str, dict[str, Any] | None] = {s: None for s in settings.symbols}
        self.forecast_history: dict[str, list[dict[str, Any]]] = {s: [] for s in settings.symbols}
        self.positions: list[dict[str, Any]] = []
        self.orders: list[dict[str, Any]] = []
        self.equity: list[dict[str, Any]] = []
        self.activity: list[dict[str, Any]] = []
        self.selected_symbol: str = settings.symbols[0] if settings.symbols else "AAPL"
        self.lock = asyncio.Lock()
        # Local paper book when dry-run
        self._local_positions: dict[str, float] = {}
        self._local_avg: dict[str, float] = {}

        # Health / diagnostics (no silent mock fallbacks)
        self.market_errors: dict[str, str] = {}
        self.market_last_ok: dict[str, str] = {}
        self.inference_errors: dict[str, str] = {}
        self.inference_last_ok: dict[str, str] = {}
        self.last_loop_error: str | None = None

    def sync_symbols(self, symbols: list[str]) -> None:
        for s in symbols:
            self.candles.setdefault(s, [])
            self.forecasts.setdefault(s, None)
            self.forecast_history.setdefault(s, [])
        remove = [k for k in self.candles if k not in symbols]
        for k in remove:
            self.candles.pop(k, None)
            self.forecasts.pop(k, None)
            self.forecast_history.pop(k, None)
            self.market_errors.pop(k, None)
            self.market_last_ok.pop(k, None)
            self.inference_errors.pop(k, None)
            self.inference_last_ok.pop(k, None)
        if self.selected_symbol not in symbols:
            self.selected_symbol = symbols[0] if symbols else "AAPL"

    def record_forecast(self, forecast: dict[str, Any]) -> dict[str, Any]:
        """Store as current forecast and append to history (deduped by generatedAt)."""
        symbol = forecast["symbol"]
        entry = {
            "id": forecast.get("id") or str(uuid4()),
            "symbol": symbol,
            "generatedAt": forecast["generatedAt"],
            "model": forecast.get("model", "kronos"),
            "sampleCount": forecast.get("sampleCount", 1),
            "points": forecast["points"],
            "anchorTimestamp": forecast.get("anchorTimestamp"),
            "anchorClose": forecast.get("anchorClose"),
        }
        self.forecasts[symbol] = {
            "symbol": symbol,
            "generatedAt": entry["generatedAt"],
            "model": entry["model"],
            "sampleCount": entry["sampleCount"],
            "points": entry["points"],
            "anchorTimestamp": entry["anchorTimestamp"],
            "anchorClose": entry["anchorClose"],
        }
        hist = self.forecast_history.setdefault(symbol, [])
        if not any(h.get("generatedAt") == entry["generatedAt"] for h in hist):
            hist.append(entry)
            self.forecast_history[symbol] = hist[-FORECAST_HISTORY_LIMIT:]
        return entry

    def note_market_ok(self, symbol: str) -> None:
        self.market_errors.pop(symbol, None)
        self.market_last_ok[symbol] = datetime.now(timezone.utc).isoformat()
        self.last_loop_error = None

    def note_market_error(self, symbol: str, message: str) -> None:
        self.market_errors[symbol] = message
        self.last_loop_error = message

    def note_inference_ok(self, symbol: str) -> None:
        self.inference_errors.pop(symbol, None)
        self.inference_last_ok[symbol] = datetime.now(timezone.utc).isoformat()

    def note_inference_error(self, symbol: str, message: str) -> None:
        self.inference_errors[symbol] = message
        self.last_loop_error = message

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
        s = self.settings
        return {
            "symbols": s.symbols,
            "selectedSymbol": self.selected_symbol,
            "candles": self.candles,
            "forecasts": self.forecasts,
            "forecastHistory": self.forecast_history,
            "positions": self.positions,
            "orders": self.orders[:50],
            "equity": self.equity[-200:],
            "activity": self.activity[:100],
            "risk": {
                "maxPositionSize": s.max_position_size,
                "maxPortfolioExposure": s.max_portfolio_exposure,
                "stopLossPct": s.stop_loss_pct,
            },
            "paper": s.use_paper,
            "dryRun": s.dry_run,
            "live": s.live_trading_enabled,
            "strategy": s.strategy,
            "signalThresholdPct": s.signal_threshold_pct,
            "tradeIntervalSeconds": s.trade_interval_seconds,
            "barTimeframe": s.bar_timeframe,
            "lookbackBars": s.lookback_bars,
            "predLen": s.pred_len,
            "mockMarketData": False,
            "marketDataFeed": (s.alpaca_data_feed or "iex").lower(),
            "marketErrors": dict(self.market_errors),
            "inferenceErrors": dict(self.inference_errors),
        }


state: RuntimeState | None = None


def get_state() -> RuntimeState:
    global state
    if state is None:
        from app.config import get_settings

        state = RuntimeState(get_settings())
    return state
