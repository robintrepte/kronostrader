from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskLimits:
    max_position_size: float
    max_portfolio_exposure: float
    stop_loss_pct: float


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    qty: float = 0.0


def evaluate_risk(
    *,
    side: str,
    symbol: str,
    price: float,
    limits: RiskLimits,
    current_positions: dict[str, float],
    current_exposure: float,
    unrealized_pnl_pct: float | None = None,
) -> RiskDecision:
    """Hard gates — no trade without passing these checks."""
    if side == "hold":
        return RiskDecision(False, "hold signal — no order", 0.0)

    if price <= 0:
        return RiskDecision(False, "invalid price", 0.0)

    if limits.max_position_size <= 0 or limits.max_portfolio_exposure <= 0:
        return RiskDecision(False, "risk limits not configured", 0.0)

    if unrealized_pnl_pct is not None and unrealized_pnl_pct <= -abs(limits.stop_loss_pct):
        if side == "buy":
            return RiskDecision(
                False,
                f"stop-loss active ({unrealized_pnl_pct:.2f}% <= -{limits.stop_loss_pct}%)",
                0.0,
            )

    existing_notional = abs(current_positions.get(symbol, 0.0)) * price
    room_symbol = max(0.0, limits.max_position_size - existing_notional)
    room_portfolio = max(0.0, limits.max_portfolio_exposure - current_exposure)

    notional = min(room_symbol, room_portfolio, limits.max_position_size)
    if notional <= 0:
        return RiskDecision(False, "max position size or portfolio exposure reached", 0.0)

    qty = round(notional / price, 4)
    if qty <= 0:
        return RiskDecision(False, "computed qty is zero", 0.0)

    if side == "sell":
        held = current_positions.get(symbol, 0.0)
        if held <= 0:
            return RiskDecision(False, "no long position to sell", 0.0)
        qty = min(qty, held)

    return RiskDecision(True, "passed risk checks", qty)
