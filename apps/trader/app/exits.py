from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.strategies.base import ForecastPoint


ExitReason = Literal[
    "time_stop",
    "take_profit",
    "stop_loss",
    "forecast_flip",
    "none",
]


@dataclass
class ExitDecision:
    should_exit: bool
    reason: ExitReason
    detail: str


def default_position_meta(
    *,
    entry_price: float,
    qty: float,
    pred_len: int,
    forecast_return_pct: float,
    take_profit_fraction: float,
    stop_loss_pct: float,
    bars_held: int = 0,
) -> dict[str, Any]:
    direction = 1 if forecast_return_pct >= 0 else -1
    target_pct = abs(forecast_return_pct) * take_profit_fraction
    return {
        "entryPrice": entry_price,
        "qty": qty,
        "openedAt": datetime.now(timezone.utc).isoformat(),
        "horizonBars": pred_len,
        "barsHeld": bars_held,
        "direction": direction,
        "targetPct": target_pct,
        "stopLossPct": abs(stop_loss_pct),
        "forecastReturnPct": forecast_return_pct,
    }


def evaluate_exit(
    *,
    meta: dict[str, Any],
    current_price: float,
    forecast: list[ForecastPoint] | None,
    stop_loss_pct: float,
) -> ExitDecision:
    entry = float(meta.get("entryPrice") or 0)
    if entry <= 0 or current_price <= 0:
        return ExitDecision(False, "none", "no entry")

    pnl_pct = ((current_price - entry) / entry) * 100.0
    stop = float(meta.get("stopLossPct") or stop_loss_pct)
    if pnl_pct <= -abs(stop):
        return ExitDecision(True, "stop_loss", f"pnl {pnl_pct:.2f}% <= -{stop}%")

    target = float(meta.get("targetPct") or 0)
    if target > 0 and pnl_pct >= target:
        return ExitDecision(True, "take_profit", f"pnl {pnl_pct:.2f}% >= target {target:.2f}%")

    bars_held = int(meta.get("barsHeld") or 0)
    horizon = int(meta.get("horizonBars") or 0)
    if horizon > 0 and bars_held >= horizon:
        return ExitDecision(True, "time_stop", f"held {bars_held} >= horizon {horizon}")

    direction = int(meta.get("direction") or 1)
    if forecast and len(forecast) >= 1:
        horizon_close = float(forecast[-1].close)
        pred_ret = (horizon_close - current_price) / current_price
        # Long-only book: flip if forecast now expects decline
        if direction >= 0 and pred_ret < -0.001:
            return ExitDecision(
                True,
                "forecast_flip",
                f"forecast now {pred_ret * 100:.2f}% against long",
            )

    return ExitDecision(False, "none", "hold")


def bump_bars_held(meta: dict[str, Any]) -> dict[str, Any]:
    out = dict(meta)
    out["barsHeld"] = int(out.get("barsHeld") or 0) + 1
    return out
