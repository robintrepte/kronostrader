from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

ALLOWED_TIMEFRAMES = {"1Min", "5Min", "15Min", "1Hour", "1Day"}
ALLOWED_STRATEGIES = {"forecast_momentum"}


class RiskPatch(BaseModel):
    maxPositionSize: float | None = Field(default=None, gt=0)
    maxPortfolioExposure: float | None = Field(default=None, gt=0)
    stopLossPct: float | None = Field(default=None, gt=0, le=100)


class SettingsPatch(BaseModel):
    symbols: list[str] | None = None
    dryRun: bool | None = None
    strategy: str | None = None
    signalThresholdPct: float | None = Field(default=None, ge=0, le=50)
    tradeIntervalSeconds: int | None = Field(default=None, ge=5, le=3600)
    barTimeframe: str | None = None
    lookbackBars: int | None = Field(default=None, ge=32, le=2048)
    predLen: int | None = Field(default=None, ge=1, le=256)
    mockMarketData: bool | None = None
    risk: RiskPatch | None = None

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [s.strip().upper() for s in value if s and s.strip()]
        if not cleaned:
            raise ValueError("symbols must contain at least one ticker")
        if len(cleaned) > 25:
            raise ValueError("symbols limited to 25 tickers")
        # de-dupe preserving order
        seen: set[str] = set()
        out: list[str] = []
        for s in cleaned:
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in ALLOWED_STRATEGIES:
            raise ValueError(f"Unknown strategy. Allowed: {sorted(ALLOWED_STRATEGIES)}")
        return value

    @field_validator("barTimeframe")
    @classmethod
    def validate_timeframe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in ALLOWED_TIMEFRAMES:
            raise ValueError(f"Unknown timeframe. Allowed: {sorted(ALLOWED_TIMEFRAMES)}")
        return value


def settings_public(settings) -> dict[str, Any]:
    return {
        "symbols": settings.symbols,
        "dryRun": settings.dry_run,
        "paper": settings.use_paper,
        "live": settings.live_trading_enabled,
        "strategy": settings.strategy,
        "signalThresholdPct": settings.signal_threshold_pct,
        "tradeIntervalSeconds": settings.trade_interval_seconds,
        "barTimeframe": settings.bar_timeframe,
        "lookbackBars": settings.lookback_bars,
        "predLen": settings.pred_len,
        "mockMarketData": settings.mock_market_data,
        "risk": {
            "maxPositionSize": settings.max_position_size,
            "maxPortfolioExposure": settings.max_portfolio_exposure,
            "stopLossPct": settings.stop_loss_pct,
        },
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def apply_settings_patch(state, patch: SettingsPatch) -> dict[str, Any]:
    """Mutate runtime settings in-place. Does not allow enabling live trading."""
    s = state.settings
    changed: list[str] = []

    if patch.symbols is not None:
        s.trade_symbols = ",".join(patch.symbols)
        state.sync_symbols(patch.symbols)
        changed.append("symbols")

    if patch.dryRun is not None and patch.dryRun != s.dry_run:
        s.dry_run = patch.dryRun
        changed.append("dryRun")

    if patch.strategy is not None and patch.strategy != s.strategy:
        s.strategy = patch.strategy
        changed.append("strategy")

    if patch.signalThresholdPct is not None and patch.signalThresholdPct != s.signal_threshold_pct:
        s.signal_threshold_pct = patch.signalThresholdPct
        changed.append("signalThresholdPct")

    if patch.tradeIntervalSeconds is not None and patch.tradeIntervalSeconds != s.trade_interval_seconds:
        s.trade_interval_seconds = patch.tradeIntervalSeconds
        changed.append("tradeIntervalSeconds")

    if patch.barTimeframe is not None and patch.barTimeframe != s.bar_timeframe:
        s.bar_timeframe = patch.barTimeframe
        changed.append("barTimeframe")

    if patch.lookbackBars is not None and patch.lookbackBars != s.lookback_bars:
        s.lookback_bars = patch.lookbackBars
        changed.append("lookbackBars")

    if patch.predLen is not None and patch.predLen != s.pred_len:
        s.pred_len = patch.predLen
        changed.append("predLen")

    if patch.mockMarketData is not None and patch.mockMarketData != s.mock_market_data:
        s.mock_market_data = patch.mockMarketData
        changed.append("mockMarketData")

    if patch.risk is not None:
        r = patch.risk
        if r.maxPositionSize is not None and r.maxPositionSize != s.max_position_size:
            s.max_position_size = r.maxPositionSize
            changed.append("maxPositionSize")
        if r.maxPortfolioExposure is not None and r.maxPortfolioExposure != s.max_portfolio_exposure:
            s.max_portfolio_exposure = r.maxPortfolioExposure
            changed.append("maxPortfolioExposure")
        if r.stopLossPct is not None and r.stopLossPct != s.stop_loss_pct:
            s.stop_loss_pct = r.stopLossPct
            changed.append("stopLossPct")

    return {"changed": changed, "settings": settings_public(s)}
