from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.assets import normalize_symbol

ALLOWED_TIMEFRAMES = {"1Min", "5Min", "15Min", "1Hour", "1Day"}
ALLOWED_STRATEGIES = {"forecast_momentum", "strict_forecast"}


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
    sampleCount: int | None = Field(default=None, ge=1, le=8)
    minConfidence: float | None = Field(default=None, ge=0, le=1)
    maxBandWidthPct: float | None = Field(default=None, ge=0.05, le=20)
    maxForecastDrawdownPct: float | None = Field(default=None, ge=0.05, le=20)
    minHitRate: float | None = Field(default=None, ge=0, le=1)
    maxMape: float | None = Field(default=None, ge=0.001, le=1)
    requireMetricsTradeable: bool | None = None
    takeProfitFraction: float | None = Field(default=None, ge=0.1, le=2)
    topKEntries: int | None = Field(default=None, ge=1, le=10)
    regimeMaxVolPct: float | None = Field(default=None, ge=0.1, le=20)
    regimeMinTrendPct: float | None = Field(default=None, ge=0, le=5)
    risk: RiskPatch | None = None

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [normalize_symbol(s) for s in value if s and s.strip()]
        cleaned = [s for s in cleaned if s]
        if not cleaned:
            raise ValueError("symbols must contain at least one ticker")
        if len(cleaned) > 30:
            raise ValueError("symbols limited to 30 tickers")
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
        "mockMarketData": False,
        "sampleCount": settings.sample_count,
        "minConfidence": settings.min_confidence,
        "maxBandWidthPct": settings.max_band_width_pct,
        "maxForecastDrawdownPct": settings.max_forecast_drawdown_pct,
        "minHitRate": settings.min_hit_rate,
        "maxMape": settings.max_mape,
        "requireMetricsTradeable": settings.require_metrics_tradeable,
        "takeProfitFraction": settings.take_profit_fraction,
        "topKEntries": settings.top_k_entries,
        "regimeMaxVolPct": settings.regime_max_vol_pct,
        "regimeMinTrendPct": settings.regime_min_trend_pct,
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

    def _set(attr: str, value: Any, label: str) -> None:
        if value is not None and getattr(s, attr) != value:
            setattr(s, attr, value)
            changed.append(label)

    if patch.symbols is not None:
        s.trade_symbols = ",".join(patch.symbols)
        state.sync_symbols(patch.symbols)
        changed.append("symbols")

    _set("dry_run", patch.dryRun, "dryRun")
    _set("strategy", patch.strategy, "strategy")
    _set("signal_threshold_pct", patch.signalThresholdPct, "signalThresholdPct")
    _set("trade_interval_seconds", patch.tradeIntervalSeconds, "tradeIntervalSeconds")
    _set("bar_timeframe", patch.barTimeframe, "barTimeframe")
    _set("lookback_bars", patch.lookbackBars, "lookbackBars")
    _set("pred_len", patch.predLen, "predLen")
    _set("sample_count", patch.sampleCount, "sampleCount")
    _set("min_confidence", patch.minConfidence, "minConfidence")
    _set("max_band_width_pct", patch.maxBandWidthPct, "maxBandWidthPct")
    _set("max_forecast_drawdown_pct", patch.maxForecastDrawdownPct, "maxForecastDrawdownPct")
    _set("min_hit_rate", patch.minHitRate, "minHitRate")
    _set("max_mape", patch.maxMape, "maxMape")
    _set("require_metrics_tradeable", patch.requireMetricsTradeable, "requireMetricsTradeable")
    _set("take_profit_fraction", patch.takeProfitFraction, "takeProfitFraction")
    _set("top_k_entries", patch.topKEntries, "topKEntries")
    _set("regime_max_vol_pct", patch.regimeMaxVolPct, "regimeMaxVolPct")
    _set("regime_min_trend_pct", patch.regimeMinTrendPct, "regimeMinTrendPct")

    if patch.mockMarketData is True:
        raise ValueError(
            "mockMarketData cannot be enabled — synthetic candles are disabled. Use real Alpaca data only."
        )
    if patch.mockMarketData is False and s.mock_market_data:
        s.mock_market_data = False
        changed.append("mockMarketData")

    if patch.risk is not None:
        r = patch.risk
        _set("max_position_size", r.maxPositionSize, "maxPositionSize")
        _set("max_portfolio_exposure", r.maxPortfolioExposure, "maxPortfolioExposure")
        _set("stop_loss_pct", r.stopLossPct, "stopLossPct")

    return {"changed": changed, "settings": settings_public(s)}
