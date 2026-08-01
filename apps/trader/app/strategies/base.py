from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

Side = Literal["buy", "sell", "hold"]


@dataclass
class Candle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class ForecastPoint:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    close_low: float | None = None
    close_high: float | None = None


@dataclass
class Signal:
    id: str
    symbol: str
    side: Side
    strength: float
    reason: str
    strategy: str
    timestamp: datetime
    forecast_horizon_close: float | None = None
    last_close: float | None = None


class Strategy(ABC):
    name: str

    @abstractmethod
    def evaluate(
        self,
        candles: list[Candle],
        forecast: list[ForecastPoint],
        **kwargs,
    ) -> Signal:
        ...


class ForecastMomentumStrategy(Strategy):
    """Buy if forecast horizon close > last close by threshold; sell if below; else hold."""

    name = "forecast_momentum"

    def __init__(self, threshold_pct: float = 0.5) -> None:
        self.threshold_pct = threshold_pct

    def evaluate(
        self,
        candles: list[Candle],
        forecast: list[ForecastPoint],
        **kwargs,
    ) -> Signal:
        if not candles or not forecast:
            return Signal(
                id=str(uuid4()),
                symbol=candles[-1].symbol if candles else "?",
                side="hold",
                strength=0.0,
                reason="insufficient data",
                strategy=self.name,
                timestamp=datetime.now(timezone.utc),
            )

        last = candles[-1]
        horizon = forecast[-1]
        change_pct = ((horizon.close - last.close) / last.close) * 100.0
        strength = abs(change_pct)

        if change_pct >= self.threshold_pct:
            side: Side = "buy"
            reason = f"forecast +{change_pct:.2f}% >= {self.threshold_pct}%"
        elif change_pct <= -self.threshold_pct:
            side = "sell"
            reason = f"forecast {change_pct:.2f}% <= -{self.threshold_pct}%"
        else:
            side = "hold"
            reason = f"forecast {change_pct:.2f}% within ±{self.threshold_pct}%"

        return Signal(
            id=str(uuid4()),
            symbol=last.symbol,
            side=side,
            strength=strength,
            reason=reason,
            strategy=self.name,
            timestamp=datetime.now(timezone.utc),
            forecast_horizon_close=horizon.close,
            last_close=last.close,
        )


def get_strategy(name: str, threshold_pct: float = 0.5, settings=None) -> Strategy:
    if name == "strict_forecast":
        from app.strategies.strict import StrictForecastStrategy

        s = settings
        return StrictForecastStrategy(
            threshold_pct=float(getattr(s, "signal_threshold_pct", threshold_pct) if s else threshold_pct),
            max_band_width_pct=float(getattr(s, "max_band_width_pct", 2.0) if s else 2.0),
            max_forecast_drawdown_pct=float(
                getattr(s, "max_forecast_drawdown_pct", 0.4) if s else 0.4
            ),
            min_confidence=float(getattr(s, "min_confidence", 0.35) if s else 0.35),
            require_metrics_tradeable=bool(
                getattr(s, "require_metrics_tradeable", True) if s else True
            ),
        )
    if name == ForecastMomentumStrategy.name:
        return ForecastMomentumStrategy(threshold_pct)
    raise ValueError(
        f"Unknown strategy: {name}. Available: {[ForecastMomentumStrategy.name, 'strict_forecast']}"
    )
