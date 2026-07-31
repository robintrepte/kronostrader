from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.config import Settings
from app.strategies.base import Signal

logger = logging.getLogger(__name__)


class OrderResult:
    def __init__(
        self,
        id: str,
        symbol: str,
        side: str,
        qty: float,
        status: str,
        dry_run: bool,
        filled_avg_price: float | None = None,
        client_order_id: str | None = None,
        submitted_at: datetime | None = None,
        filled_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.symbol = symbol
        self.side = side
        self.qty = qty
        self.status = status
        self.dry_run = dry_run
        self.filled_avg_price = filled_avg_price
        self.client_order_id = client_order_id
        self.submitted_at = submitted_at or datetime.now(timezone.utc)
        self.filled_at = filled_at
        self.type = "market"


class Broker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        if not settings.dry_run and settings.alpaca_api_key:
            self._init_client()

    def _init_client(self) -> None:
        from alpaca.trading.client import TradingClient

        if self.settings.live_trading_enabled:
            logger.warning("LIVE TRADING ENABLED — real capital at risk")
            paper = False
        else:
            paper = True
            logger.info("Using Alpaca PAPER trading endpoint")

        self._client = TradingClient(
            self.settings.alpaca_api_key,
            self.settings.alpaca_secret_key,
            paper=paper,
        )

    def submit_market_order(self, signal: Signal, qty: float) -> OrderResult:
        side = signal.side
        assert side in ("buy", "sell")

        if self.settings.dry_run or self._client is None:
            oid = f"dry-{uuid4()}"
            logger.info(
                "DRY_RUN order %s %s qty=%s reason=%s",
                side,
                signal.symbol,
                qty,
                signal.reason,
            )
            return OrderResult(
                id=oid,
                symbol=signal.symbol,
                side=side,
                qty=qty,
                status="dry_run",
                dry_run=True,
                filled_avg_price=signal.last_close,
                filled_at=datetime.now(timezone.utc),
            )

        # Guardrail: refuse live unless both flags correct
        if self.settings.alpaca_live and self.settings.alpaca_paper:
            raise RuntimeError(
                "Refusing to trade: ALPACA_LIVE=true but ALPACA_PAPER=true. "
                "Set ALPACA_PAPER=false only when intentionally going live."
            )

        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        req = MarketOrderRequest(
            symbol=signal.symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        order = self._client.submit_order(req)
        return OrderResult(
            id=str(order.id),
            symbol=signal.symbol,
            side=side,
            qty=float(order.qty or qty),
            status=str(order.status.value if hasattr(order.status, "value") else order.status),
            dry_run=False,
            filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
            client_order_id=order.client_order_id,
            submitted_at=order.submitted_at or datetime.now(timezone.utc),
            filled_at=order.filled_at,
        )

    def get_positions(self) -> list[dict]:
        if self.settings.dry_run or self._client is None:
            return []
        positions = self._client.get_all_positions()
        out = []
        for p in positions:
            qty = float(p.qty)
            out.append(
                {
                    "symbol": p.symbol,
                    "qty": abs(qty),
                    "side": "long" if qty >= 0 else "short",
                    "avg_entry_price": float(p.avg_entry_price),
                    "current_price": float(p.current_price),
                    "market_value": float(p.market_value),
                    "unrealized_pnl": float(p.unrealized_pl),
                    "unrealized_pnl_pct": float(p.unrealized_plpc) * 100.0,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return out

    def get_account_equity(self) -> dict:
        if self.settings.dry_run or self._client is None:
            return {
                "equity": 100_000.0,
                "cash": 100_000.0,
                "buying_power": 100_000.0,
            }
        acct = self._client.get_account()
        return {
            "equity": float(acct.equity),
            "cash": float(acct.cash),
            "buying_power": float(acct.buying_power),
        }
