from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.assets import partition_symbols
from app.broker import Broker
from app.bus import bus
from app.config import Settings
from app.db.models import ActivityRow, CandleRow, EquityRow, ForecastRow, OrderRow, PositionRow, SignalRow
from app.db.session import session_scope
from app.exits import bump_bars_held, default_position_meta, evaluate_exit
from app.forecast_metrics import refresh_all_metrics
from app.inference_client import request_forecast
from app.market_data import fetch_candles
from app.market_hours import fetch_market_clock, seconds_until
from app.portfolio import EntryCandidate, select_entries
from app.regime import evaluate_regime
from app.risk import RiskLimits, evaluate_risk
from app.state import get_state
from app.strategies import get_strategy
from app.strategies.base import Candle, ForecastPoint, Signal

logger = logging.getLogger(__name__)


@dataclass
class SymbolContext:
    symbol: str
    candles: list[Candle]
    points: list[ForecastPoint]
    forecast_payload: dict[str, Any]
    signal: Signal
    last_close: float
    forecast_return_pct: float
    confidence: float


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


def _signal_payload(signal: Signal) -> dict:
    return {
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


def _confidence_from_signal(signal: Signal) -> float:
    # strict reasons embed conf=; fall back to scaled strength
    reason = signal.reason or ""
    if "conf=" in reason:
        try:
            return float(reason.split("conf=")[1].split()[0])
        except Exception:
            pass
    return min(1.0, max(0.0, signal.strength / 5.0))


async def _persist_forecast_and_signal(
    symbol: str,
    candles: list[Candle],
    forecast_payload: dict,
    raw: dict,
    signal: Signal,
) -> None:
    signal_payload = _signal_payload(signal)
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


async def _submit_order(
    settings: Settings,
    broker: Broker,
    signal: Signal,
    qty: float,
    last_close: float,
    *,
    forecast_return_pct: float = 0.0,
) -> dict[str, Any] | None:
    state = get_state()
    symbol = signal.symbol
    order = broker.submit_market_order(signal, qty)
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
            qty_held = state._local_positions.get(symbol, 0.0)
            if order.side == "buy":
                new_qty = qty_held + order.qty
                if new_qty > 0:
                    prev_cost = state._local_avg.get(symbol, last_close) * qty_held
                    state._local_avg[symbol] = (prev_cost + last_close * order.qty) / new_qty
                state._local_positions[symbol] = new_qty
                state.position_meta[symbol] = default_position_meta(
                    entry_price=last_close,
                    qty=new_qty,
                    pred_len=settings.pred_len,
                    forecast_return_pct=forecast_return_pct,
                    take_profit_fraction=settings.take_profit_fraction,
                    stop_loss_pct=settings.stop_loss_pct,
                )
            else:
                state._local_positions[symbol] = max(0.0, qty_held - order.qty)
                if state._local_positions[symbol] <= 0:
                    state._local_positions.pop(symbol, None)
                    state._local_avg.pop(symbol, None)
                    state.position_meta.pop(symbol, None)
            state.rebuild_local_positions()
        else:
            if order.side == "buy":
                state.position_meta[symbol] = default_position_meta(
                    entry_price=order.filled_avg_price or last_close,
                    qty=order.qty,
                    pred_len=settings.pred_len,
                    forecast_return_pct=forecast_return_pct,
                    take_profit_fraction=settings.take_profit_fraction,
                    stop_loss_pct=settings.stop_loss_pct,
                )
            else:
                state.position_meta.pop(symbol, None)

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

    async with session_scope() as session:
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
    return order_payload


async def refresh_symbol(
    settings: Settings,
    symbol: str,
    *,
    equity_session_open: bool,
) -> SymbolContext | None:
    state = get_state()
    strategy = get_strategy(settings.strategy, settings.signal_threshold_pct, settings=settings)

    try:
        candles = await asyncio.to_thread(fetch_candles, settings, symbol)
    except Exception as exc:
        logger.exception("Market data failed for %s", symbol)
        msg = str(exc)
        state.note_market_error(symbol, msg)
        entry = state.add_activity("error", msg, symbol, meta={"source": "market_data"})
        await bus.publish({"type": "activity", "timestamp": entry["timestamp"], "payload": entry})
        return None

    if len(candles) < 2:
        msg = f"Not enough candles for {symbol} (got {len(candles)})"
        state.note_market_error(symbol, msg)
        return None

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
        points, raw = await request_forecast(
            settings, symbol, candles, sample_count=settings.sample_count
        )
    except Exception as exc:
        logger.exception("Inference failed for %s", symbol)
        msg = f"Inference failed: {exc}"
        state.note_inference_error(symbol, msg)
        entry = state.add_activity("error", msg, symbol)
        await bus.publish({"type": "activity", "timestamp": entry["timestamp"], "payload": entry})
        return None

    state.note_inference_ok(symbol)
    forecast_payload = _forecast_dict(
        symbol,
        points,
        raw.get("model", "kronos"),
        raw.get("sample_count", settings.sample_count),
        anchor_timestamp=last.timestamp.isoformat(),
        anchor_close=float(last.close),
    )
    async with state.lock:
        state.record_forecast(forecast_payload)
        state.forecast_metrics = refresh_all_metrics(
            state.forecast_history,
            state.candles,
            list(settings.symbols),
            min_hit_rate=settings.min_hit_rate,
            max_mape=settings.max_mape,
        )
    await bus.publish(
        {
            "type": "forecast",
            "timestamp": forecast_payload["generatedAt"],
            "payload": forecast_payload,
        }
    )

    metrics = state.forecast_metrics.get(symbol) or {}
    signal = strategy.evaluate(candles, points, metrics=metrics)

    # Regime only blocks new buys (exits still allowed)
    if signal.side == "buy":
        regime = evaluate_regime(
            candles,
            symbol,
            equity_session_open=equity_session_open,
            max_vol_pct=settings.regime_max_vol_pct,
            min_trend_pct=settings.regime_min_trend_pct,
        )
        if not regime.ok:
            signal = Signal(
                id=str(uuid4()),
                symbol=symbol,
                side="hold",
                strength=0.0,
                reason=f"regime: {regime.reason}",
                strategy=signal.strategy,
                timestamp=datetime.now(timezone.utc),
                forecast_horizon_close=signal.forecast_horizon_close,
                last_close=last.close,
            )

    await bus.publish(
        {"type": "signal", "timestamp": signal.timestamp.isoformat(), "payload": _signal_payload(signal)}
    )
    await _persist_forecast_and_signal(symbol, candles, forecast_payload, raw, signal)

    f_ret = 0.0
    if signal.forecast_horizon_close and last.close:
        f_ret = ((signal.forecast_horizon_close - last.close) / last.close) * 100.0

    return SymbolContext(
        symbol=symbol,
        candles=candles,
        points=points,
        forecast_payload=forecast_payload,
        signal=signal,
        last_close=float(last.close),
        forecast_return_pct=f_ret,
        confidence=_confidence_from_signal(signal),
    )


def _current_book(settings: Settings, broker: Broker, fallback_price: float) -> tuple[dict[str, float], float]:
    state = get_state()
    if settings.dry_run:
        positions = dict(state._local_positions)
        exposure = sum(
            abs(qty)
            * (
                state.candles.get(sym, [{}])[-1].get("close", fallback_price)
                if state.candles.get(sym)
                else fallback_price
            )
            for sym, qty in positions.items()
        )
        return positions, exposure
    positions_list = broker.get_positions()
    state.positions = positions_list
    positions = {p["symbol"]: p["qty"] for p in positions_list}
    exposure = sum(abs(p.get("marketValue", 0.0)) for p in positions_list)
    return positions, exposure


async def process_cycle(settings: Settings, broker: Broker, symbols: list[str], *, equity_open: bool) -> None:
    state = get_state()
    contexts: list[SymbolContext] = []
    for symbol in symbols:
        try:
            ctx = await refresh_symbol(
                settings, symbol, equity_session_open=equity_open
            )
        except Exception:
            logger.exception("refresh failed for %s", symbol)
            continue
        if ctx:
            contexts.append(ctx)

    if not contexts:
        return

    # Bump bars held + exits first
    limits = RiskLimits(
        max_position_size=settings.max_position_size,
        max_portfolio_exposure=settings.max_portfolio_exposure,
        stop_loss_pct=settings.stop_loss_pct,
    )
    positions, exposure = _current_book(settings, broker, contexts[0].last_close)

    for ctx in contexts:
        sym = ctx.symbol
        held = positions.get(sym, 0.0)
        if held <= 0:
            continue
        meta = state.position_meta.get(sym)
        if meta:
            meta = bump_bars_held(meta)
            state.position_meta[sym] = meta
        else:
            meta = default_position_meta(
                entry_price=ctx.last_close,
                qty=held,
                pred_len=settings.pred_len,
                forecast_return_pct=ctx.forecast_return_pct,
                take_profit_fraction=settings.take_profit_fraction,
                stop_loss_pct=settings.stop_loss_pct,
            )
            state.position_meta[sym] = meta

        exit_dec = evaluate_exit(
            meta=meta,
            current_price=ctx.last_close,
            forecast=ctx.points,
            stop_loss_pct=settings.stop_loss_pct,
        )
        # Also exit on strict sell signal
        force_sell = ctx.signal.side == "sell"
        if exit_dec.should_exit or force_sell:
            reason = exit_dec.detail if exit_dec.should_exit else ctx.signal.reason
            sell_signal = Signal(
                id=str(uuid4()),
                symbol=sym,
                side="sell",
                strength=ctx.signal.strength or 1.0,
                reason=f"exit: {reason}",
                strategy=settings.strategy,
                timestamp=datetime.now(timezone.utc),
                forecast_horizon_close=ctx.signal.forecast_horizon_close,
                last_close=ctx.last_close,
            )
            decision = evaluate_risk(
                side="sell",
                symbol=sym,
                price=ctx.last_close,
                limits=limits,
                current_positions=positions,
                current_exposure=exposure,
            )
            if decision.allowed:
                entry = state.add_activity(
                    "signal",
                    f"SELL {sym}: {sell_signal.reason}",
                    sym,
                    _signal_payload(sell_signal),
                )
                await bus.publish(
                    {"type": "activity", "timestamp": entry["timestamp"], "payload": entry}
                )
                await _submit_order(
                    settings, broker, sell_signal, decision.qty, ctx.last_close
                )
                positions, exposure = _current_book(settings, broker, ctx.last_close)

    # Collect buy candidates (after exits freed capacity)
    positions, exposure = _current_book(settings, broker, contexts[0].last_close)
    candidates: list[EntryCandidate] = []
    for ctx in contexts:
        if ctx.signal.side != "buy":
            continue
        if positions.get(ctx.symbol, 0.0) > 0:
            continue
        metrics = state.forecast_metrics.get(ctx.symbol) or {}
        hit = float(metrics["hitRate"]) if metrics.get("hitRate") is not None else 0.5
        candidates.append(
            EntryCandidate(
                symbol=ctx.symbol,
                strength=ctx.signal.strength,
                confidence=ctx.confidence,
                hit_rate=hit,
                price=ctx.last_close,
                reason=ctx.signal.reason,
                signal=ctx.signal,
                forecast_return_pct=ctx.forecast_return_pct,
            )
        )

    selected = select_entries(
        candidates,
        top_k=settings.top_k_entries,
        max_position_size=settings.max_position_size,
        max_portfolio_exposure=settings.max_portfolio_exposure,
        current_exposure=exposure,
    )

    # Mark non-selected buys as held (quiet)
    selected_syms = {c.symbol for c, _ in selected}
    for c in candidates:
        if c.symbol not in selected_syms:
            continue  # will log when traded
        pass

    for cand, notional in selected:
        qty = round(notional / cand.price, 6 if "/" in cand.symbol else 4)
        if qty <= 0:
            continue
        decision = evaluate_risk(
            side="buy",
            symbol=cand.symbol,
            price=cand.price,
            limits=limits,
            current_positions=positions,
            current_exposure=exposure,
        )
        if not decision.allowed:
            continue
        # Prefer portfolio notional sizing
        use_qty = min(decision.qty, qty)
        if use_qty <= 0:
            continue
        entry = state.add_activity(
            "signal",
            f"BUY {cand.symbol}: {cand.reason} (ranked)",
            cand.symbol,
            _signal_payload(cand.signal),
        )
        await bus.publish({"type": "activity", "timestamp": entry["timestamp"], "payload": entry})
        await _submit_order(
            settings,
            broker,
            cand.signal,
            use_qty,
            cand.price,
            forecast_return_pct=cand.forecast_return_pct,
        )
        positions, exposure = _current_book(settings, broker, cand.price)


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
    settings = state.settings
    broker = Broker(settings)
    last_dry = settings.dry_run
    market_was_open: bool | None = None
    state.add_activity(
        "system",
        f"Trader started (strategy={settings.strategy}, paper={settings.use_paper}, "
        f"dry_run={settings.dry_run}, live={settings.live_trading_enabled})",
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
                entry = state.add_activity("system", msg, meta={"clock": clock})
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

        try:
            await process_cycle(settings, broker, to_process, equity_open=equity_open)
        except Exception:
            logger.exception("Cycle error")
            state.add_activity("error", "Trading cycle error")

        try:
            await refresh_equity(settings, broker)
        except Exception:
            logger.exception("Equity refresh failed")
        await asyncio.sleep(max(5, settings.trade_interval_seconds))
