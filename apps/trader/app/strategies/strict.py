from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.strategies.base import Candle, ForecastPoint, Side, Signal, Strategy


class StrictForecastStrategy(Strategy):
    """Path + band + metrics gated entries — defaults to HOLD most of the time."""

    name = "strict_forecast"

    def __init__(
        self,
        *,
        threshold_pct: float = 0.8,
        max_band_width_pct: float = 1.2,
        max_forecast_drawdown_pct: float = 0.6,
        min_confidence: float = 0.55,
        require_metrics_tradeable: bool = True,
    ) -> None:
        self.threshold_pct = threshold_pct
        self.max_band_width_pct = max_band_width_pct
        self.max_forecast_drawdown_pct = max_forecast_drawdown_pct
        self.min_confidence = min_confidence
        self.require_metrics_tradeable = require_metrics_tradeable

    def evaluate(
        self,
        candles: list[Candle],
        forecast: list[ForecastPoint],
        *,
        metrics: dict | None = None,
    ) -> Signal:
        last = candles[-1] if candles else None
        if not last or not forecast:
            return self._hold("?", "insufficient data")

        metrics = metrics or {}
        if self.require_metrics_tradeable and metrics.get("n", 0) >= 3:
            if not metrics.get("tradeable", False):
                return self._hold(
                    last.symbol,
                    f"metrics gate (hit={metrics.get('hitRate')}, mape={metrics.get('mape')})",
                    last_close=last.close,
                )

        closes = [float(p.close) for p in forecast]
        horizon = closes[-1]
        change_pct = ((horizon - last.close) / last.close) * 100.0

        # Path adverse excursion vs entry (long path)
        if change_pct >= 0:
            min_c = min(closes)
            dd = ((min_c - last.close) / last.close) * 100.0  # negative if dips
            adverse = abs(min(0.0, dd))
        else:
            max_c = max(closes)
            uu = ((max_c - last.close) / last.close) * 100.0
            adverse = abs(max(0.0, uu))

        if adverse > self.max_forecast_drawdown_pct:
            return self._hold(
                last.symbol,
                f"forecast path drawdown {adverse:.2f}% > {self.max_forecast_drawdown_pct}%",
                last_close=last.close,
                horizon=horizon,
            )

        # Band agreement / tightness from last point
        lo = forecast[-1].close_low
        hi = forecast[-1].close_high
        confidence = 0.5
        if lo is not None and hi is not None and last.close > 0:
            mid = (float(lo) + float(hi)) / 2.0
            width_pct = ((float(hi) - float(lo)) / mid) * 100.0 if mid else 999.0
            if width_pct > self.max_band_width_pct:
                return self._hold(
                    last.symbol,
                    f"band too wide {width_pct:.2f}% > {self.max_band_width_pct}%",
                    last_close=last.close,
                    horizon=horizon,
                )
            # Agreement: band entirely on same side of last close as mean forecast
            if change_pct > 0 and float(lo) < last.close:
                return self._hold(
                    last.symbol,
                    "band crosses below spot (weak long)",
                    last_close=last.close,
                    horizon=horizon,
                )
            if change_pct < 0 and float(hi) > last.close:
                return self._hold(
                    last.symbol,
                    "band crosses above spot (weak short)",
                    last_close=last.close,
                    horizon=horizon,
                )
            # Tighter band → higher confidence
            confidence = max(0.0, min(1.0, 1.0 - (width_pct / max(self.max_band_width_pct, 1e-6))))
        else:
            confidence = 0.45  # no band → weaker

        if confidence < self.min_confidence:
            return self._hold(
                last.symbol,
                f"confidence {confidence:.2f} < {self.min_confidence}",
                last_close=last.close,
                horizon=horizon,
            )

        strength = abs(change_pct) * confidence
        if change_pct >= self.threshold_pct:
            return Signal(
                id=str(uuid4()),
                symbol=last.symbol,
                side="buy",
                strength=strength,
                reason=(
                    f"strict +{change_pct:.2f}% path_ok adverse={adverse:.2f}% "
                    f"conf={confidence:.2f}"
                ),
                strategy=self.name,
                timestamp=datetime.now(timezone.utc),
                forecast_horizon_close=horizon,
                last_close=last.close,
            )
        if change_pct <= -self.threshold_pct:
            # Long-only: emit sell only as a signal for exit layer / flatten
            return Signal(
                id=str(uuid4()),
                symbol=last.symbol,
                side="sell",
                strength=strength,
                reason=(
                    f"strict {change_pct:.2f}% path_ok adverse={adverse:.2f}% "
                    f"conf={confidence:.2f}"
                ),
                strategy=self.name,
                timestamp=datetime.now(timezone.utc),
                forecast_horizon_close=horizon,
                last_close=last.close,
            )

        return self._hold(
            last.symbol,
            f"strict {change_pct:.2f}% within ±{self.threshold_pct}%",
            last_close=last.close,
            horizon=horizon,
        )

    def _hold(
        self,
        symbol: str,
        reason: str,
        *,
        last_close: float | None = None,
        horizon: float | None = None,
    ) -> Signal:
        return Signal(
            id=str(uuid4()),
            symbol=symbol,
            side="hold",
            strength=0.0,
            reason=reason,
            strategy=self.name,
            timestamp=datetime.now(timezone.utc),
            forecast_horizon_close=horizon,
            last_close=last_close,
        )
