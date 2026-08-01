from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.assets import partition_symbols
from app.broker import Broker
from app.bus import bus
from app.config import Settings
from app.db.models import ActivityRow, CandleRow, EquityRow, ForecastRow, OrderRow, PositionRow, SignalRow
from app.db.session import session_scope
from app.market_hours import fetch_market_clock, seconds_until
from app.inference_client import request_forecast
from app.market_data import fetch_candles
from app.risk import RiskLimits, evaluate_risk
from app.state import get_state
from app.strategies import get_strategy

logger = logging.getLogger(__name__)


def _candle_dict(c) -> dict:
    return {
        "symbol": c.symbol,
        "timestamp": c.timestamp.isoformat(),
        "open": c.open,
        "high": c.high,
        "low": c.low,
        "close": c.close,
        "volume": c.volume,
    }


def _forecast_dict(
    symbol: str,
    points,
    model: str,
    sample_count: int,
    *,
    anchor_timestamp: str | None = None,
    anchor_close: float | None = None,
) -> dict:
    from uuid import uuid4

    return {
        "id": str(uuid4()),
        "symbol": symbol,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "sampleCount": sample_count,
        "anchorTimestamp": anchor_timestamp,
        "anchorClose": anchor_close,
        "points": [
            {
                "timestamp": p.timestamp.isoformat(),
                "open": p.open,
                "high": p.high,
                "low": p.low,
                "close": p.close,
                "volume": p.volume,
                "closeLow": p.close_low,
                "closeHigh": p.close_high,
            }
            for p in points
        ],
    }


async def process_symbol(settings: Settings, broker: Broker, symbol: str) -> None:
    state = get_state()
    strategy = get_strategy(settings.strategy, settings.signal_threshold_pct)
    limits = RiskLimits(
        max_position_size=settings.max_position_size,
        max_portfolio_exposure=settings.max_portfolio_exposure,
        stop_loss_pct=settings.stop_loss_pct,
    )

    try:
        candles = await asyncio.to_thread(fetch_candles, settings, symbol)
    except Exception as exc:
        logger.exception("Market data failed for %s", symbol)
        msg = str(exc)
        state.note_market_error(symbol, msg)
        entry = state.add_activity("error", msg, symbol, meta={"source": "market_data"})
        await bus.publish({"type": "activity", "timestamp": entry["timestamp"], "payload": entry})
        return

    if len(candles) < 2:
        msg = f"Not enough candles for {symbol} (got {len(candles)})"
        state.note_market_error(symbol, msg)
        entry = state.add_activity("error", msg, symbol)
        await bus.publish({"type": "activity", "timestamp": entry["timestamp"], "payload": entry})
        return

    state.note_market_ok(symbol)
    async with state.lock:
        state.candles[symbol] = [_candle_dict(c) for c in candles]
        if settings.dry_run and state._local_positions:
            marked = state.rebuild_local_positions()
        else:
            marked = None
    last = candles[-1]
    await bus.publish(
        {"type": "candle", "timestamp": datetime.now(timezone.utc).isoformat(), "payload": _candle_dict(last)}
    )
    if marked is not None:
        await bus.publish(
            {
                "type": "position",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": marked,
            }
        )

    try:
        points, raw = await request_forecast(settings, symbol, candles, sample_count=2)
    except Exception as exc:
        logger.exception("Inference failed for %s", symbol)
        msg = f"Inference failed: {exc}"
        state.note_inference_error(symbol, msg)
        entry = state.add_activity("error", msg, symbol)
        await bus.publish({"type": "activity", "timestamp": entry["timestamp"], "payload": entry})
        return

    state.note_inference_ok(symbol)
    forecast_payload = _forecast_dict(
        symbol,
        points,
        raw.get("model", "kronos"),
        raw.get("sample_count", 1),
        anchor_timestamp=last.timestamp.isoformat(),
        anchor_close=float(last.close),
    )
    async with state.lock:
        state.record_forecast(forecast_payload)
    await bus.publish(
        {
            "type": "forecast",
            "timestamp": forecast_payload["generatedAt"],
            "payload": forecast_payload,
        }
    )

    signal = strategy.evaluate(candles, points)
    signal_payload = {
        "id": signal.id,
        "symbol": signal.symbol,
        "side": signal.side,
        "strength": signal.strength,
        "reason": signal.reason,
        "strategy": signal.strategy,
        "timestamp": signal.timestamp.isoformat(),
        "forecastHorizonClose": signal.forecast_horizon_close,
        "lastClose": signal.last_close,
    }
    await bus.publish(
        {"type": "signal", "timestamp": signal_payload["timestamp"], "payload": signal_payload}
    )

    # Positions / exposure from local dry-run book or broker
    if settings.dry_run:
        current_positions = dict(state._local_positions)
        current_exposure = sum(
            abs(qty) * (state.candles.get(sym, [{}])[-1].get("close", last.close) if state.candles.get(sym) else last.close)
            for sym, qty in current_positions.items()
        )
        unrealized = None
        if symbol in state._local_avg and state._local_positions.get(symbol, 0) > 0:
            avg = state._local_avg[symbol]
            unrealized = ((last.close - avg) / avg) * 100.0
    else:
        positions = broker.get_positions()
        current_positions = {p["symbol"]: p["qty"] for p in positions}
        current_exposure = sum(abs(p.get("marketValue", 0.0)) for p in positions)
        match = next((p for p in positions if p["symbol"] == symbol), None)
        unrealized = match["unrealizedPnlPct"] if match else None
        async with state.lock:
            state.positions = positions

    decision = evaluate_risk(
        side=signal.side,
        symbol=symbol,
        price=last.close,
        limits=limits,
        current_positions=current_positions,
        current_exposure=current_exposure,
        unrealized_pnl_pct=unrealized,
    )

    # Only surface signals that can actually trade (avoids buy+reject spam at caps)
    if decision.allowed:
        entry = state.add_activity(
            "signal",
            f"{signal.side.upper()} {symbol}: {signal.reason}",
            symbol,
            signal_payload,
        )
        await bus.publish({"type": "activity", "timestamp": entry["timestamp"], "payload": entry})

    async with session_scope() as session:
        for c in candles[-50:]:
            session.add(
                CandleRow(
                    symbol=c.symbol,
                    timestamp=c.timestamp,
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    volume=c.volume,
                )
            )
        session.add(
            ForecastRow(
                symbol=symbol,
                generated_at=datetime.now(timezone.utc),
                model=raw.get("model", "kronos"),
                sample_count=int(raw.get("sample_count", 1)),
                points={
                    "points": forecast_payload["points"],
                    "anchorTimestamp": forecast_payload.get("anchorTimestamp"),
                    "anchorClose": forecast_payload.get("anchorClose"),
                    "id": forecast_payload.get("id"),
                },
            )
        )
        session.add(
            SignalRow(
                id=signal.id,
                symbol=symbol,
                side=signal.side,
                strength=signal.strength,
                reason=signal.reason,
                strategy=signal.strategy,
                timestamp=signal.timestamp,
                meta=signal_payload,
            )
        )

        if not decision.allowed:
            # Capacity / flat / hold gates fire every cycle — keep them out of the desk feed
            quiet_reasons = {
                "hold signal — no order",
                "no long position to sell",
                "max position size or portfolio exposure reached",
                "computed qty is zero",
            }
            if decision.reason not in quiet_reasons:
                reject = state.add_activity(
                    "risk_reject",
                    f"Risk blocked {signal.side} {symbol}: {decision.reason}",
                    symbol,
                )
                await bus.publish(
                    {
                        "type": "activity",
                        "timestamp": reject["timestamp"],
                        "payload": reject,
                    }
                )
                session.add(
                    ActivityRow(
                        id=reject["id"],
                        kind="risk_reject",
                        message=reject["message"],
                        symbol=symbol,
                        timestamp=datetime.now(timezone.utc),
                        meta={"reason": decision.reason},
                    )
                )
            return

        order = broker.submit_market_order(signal, decision.qty)
        order_payload = {
            "id": order.id,
            "clientOrderId": order.client_order_id,
            "symbol": order.symbol,
            "side": order.side,
            "qty": order.qty,
            "type": order.type,
            "status": order.status,
            "filledAvgPrice": order.filled_avg_price,
            "submittedAt": order.submitted_at.isoformat(),
            "filledAt": order.filled_at.isoformat() if order.filled_at else None,
            "dryRun": order.dry_run,
        }
        async with state.lock:
            state.orders.insert(0, order_payload)
            state.orders = state.orders[:100]
            if settings.dry_run:
                qty = state._local_positions.get(symbol, 0.0)
                if order.side == "buy":
                    new_qty = qty + order.qty
                    if new_qty > 0:
                        prev_cost = state._local_avg.get(symbol, last.close) * qty
                        state._local_avg[symbol] = (prev_cost + last.close * order.qty) / new_qty
                    state._local_positions[symbol] = new_qty
                else:
                    state._local_positions[symbol] = max(0.0, qty - order.qty)
                    if state._local_positions[symbol] <= 0:
                        state._local_positions.pop(symbol, None)
                        state._local_avg.pop(symbol, None)
                state.rebuild_local_positions()

        await bus.publish(
            {"type": "order", "timestamp": order_payload["submittedAt"], "payload": order_payload}
        )
        await bus.publish(
            {
                "type": "position",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": state.positions,
            }
        )
        fill_entry = state.add_activity(
            "order",
            f"{'DRY ' if order.dry_run else ''}{order.side.upper()} {order.qty} {order.symbol}",
            symbol,
            order_payload,
        )
        await bus.publish({"type": "activity", "timestamp": fill_entry["timestamp"], "payload": fill_entry})

        session.add(
            OrderRow(
                id=order.id,
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                side=order.side,
                qty=order.qty,
                type=order.type,
                status=order.status,
                filled_avg_price=order.filled_avg_price,
                submitted_at=order.submitted_at,
                filled_at=order.filled_at,
                dry_run=order.dry_run,
            )
        )
        session.add(
            ActivityRow(
                id=fill_entry["id"],
                kind="order",
                message=fill_entry["message"],
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                meta=order_payload,
            )
        )


async def refresh_equity(settings: Settings, broker: Broker) -> None:
    state = get_state()
    acct = broker.get_account_equity()
    if settings.dry_run:
        positions_value = sum(p.get("marketValue", 0) for p in state.positions)
        cash = 100_000.0 - sum(
            p.get("avgEntryPrice", 0) * p.get("qty", 0) for p in state.positions
        )
        acct = {"equity": cash + positions_value, "cash": cash, "buying_power": cash}

    point = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "equity": acct["equity"],
        "cash": acct["cash"],
        "buyingPower": acct.get("buying_power"),
    }
    async with state.lock:
        state.equity.append(point)
        state.equity = state.equity[-500:]
    await bus.publish({"type": "equity", "timestamp": point["timestamp"], "payload": point})

    async with session_scope() as session:
        session.add(
            EquityRow(
                timestamp=datetime.now(timezone.utc),
                equity=point["equity"],
                cash=point["cash"],
                buying_power=point.get("buyingPower"),
            )
        )
        # Upsert positions snapshot
        for p in state.positions:
            existing = await session.get(PositionRow, p["symbol"])
            if existing:
                existing.qty = p["qty"]
                existing.side = p["side"]
                existing.avg_entry_price = p["avgEntryPrice"]
                existing.current_price = p["currentPrice"]
                existing.market_value = p["marketValue"]
                existing.unrealized_pnl = p["unrealizedPnl"]
                existing.unrealized_pnl_pct = p["unrealizedPnlPct"]
                existing.updated_at = datetime.now(timezone.utc)
            else:
                session.add(
                    PositionRow(
                        symbol=p["symbol"],
                        qty=p["qty"],
                        side=p["side"],
                        avg_entry_price=p["avgEntryPrice"],
                        current_price=p["currentPrice"],
                        market_value=p["marketValue"],
                        unrealized_pnl=p["unrealizedPnl"],
                        unrealized_pnl_pct=p["unrealizedPnlPct"],
                        updated_at=datetime.now(timezone.utc),
                    )
                )


async def trading_loop(settings: Settings) -> None:
    state = get_state()
    # Prefer the shared runtime settings object so PATCH /api/settings takes effect.
    settings = state.settings
    broker = Broker(settings)
    last_dry = settings.dry_run
    market_was_open: bool | None = None
    state.add_activity(
        "system",
        f"Trader started (paper={settings.use_paper}, dry_run={settings.dry_run}, live={settings.live_trading_enabled})",
    )
    while True:
        settings = state.settings
        if settings.dry_run != last_dry:
            broker = Broker(settings)
            last_dry = settings.dry_run
            entry = state.add_activity(
                "system",
                f"Broker reinitialized (dry_run={settings.dry_run})",
            )
            await bus.publish(
                {"type": "activity", "timestamp": entry["timestamp"], "payload": entry}
            )

        clock = await asyncio.to_thread(fetch_market_clock, settings)
        equity_open = bool(clock.get("isOpen"))
        equity_syms, crypto_syms = partition_symbols(list(settings.symbols))

        if equity_syms and not equity_open:
            if market_was_open is not False:
                nxt = clock.get("nextOpen") or "next session"
                msg = (
                    f"US equity market closed — stocks/ETFs paused until {nxt}"
                    + ("; crypto still trading 24/7" if crypto_syms else "")
                )
                entry = state.add_activity(
                    "system",
                    msg,
                    meta={"clock": clock},
                )
                await bus.publish(
                    {"type": "activity", "timestamp": entry["timestamp"], "payload": entry}
                )
            market_was_open = False
            if not crypto_syms:
                wait = seconds_until(clock.get("nextOpen"))
                sleep_for = 60.0 if wait is None else min(max(30.0, wait), 300.0)
                await asyncio.sleep(sleep_for)
                continue
        elif equity_syms and market_was_open is False:
            entry = state.add_activity(
                "system",
                "US equity market open — resuming stocks/ETFs",
                meta={"clock": clock},
            )
            await bus.publish(
                {"type": "activity", "timestamp": entry["timestamp"], "payload": entry}
            )
            market_was_open = True
        elif equity_open:
            market_was_open = True

        to_process = list(crypto_syms)
        if equity_open:
            to_process.extend(equity_syms)

        for symbol in to_process:
            try:
                await process_symbol(settings, broker, symbol)
            except Exception:
                logger.exception("Loop error for %s", symbol)
                msg = f"Loop error for {symbol}"
                state.note_market_error(symbol, msg)
                entry = state.add_activity("error", msg, symbol)
                await bus.publish({"type": "activity", "timestamp": entry["timestamp"], "payload": entry})
        try:
            await refresh_equity(settings, broker)
        except Exception:
            logger.exception("Equity refresh failed")
        await asyncio.sleep(max(5, settings.trade_interval_seconds))
