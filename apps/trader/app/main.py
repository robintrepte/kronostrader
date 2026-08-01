from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.bus import bus
from app.config import get_settings
from app.db.session import init_db
from app.logging_setup import setup_logging
from app.loop import trading_loop
from app.settings_api import SettingsPatch, apply_settings_patch, settings_public
from app.state import get_state
from app.symbol_search import search_symbols
from app.system_status import build_system_status

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)
    await init_db()
    await bus.connect()
    get_state()  # init
    from app.forecast_history import load_forecast_history

    await load_forecast_history()
    task = asyncio.create_task(trading_loop(settings), name="trading-loop")
    logger.info(
        "Trader API up on %s:%s (symbols=%s)",
        settings.trader_api_host,
        settings.trader_api_port,
        settings.symbols,
    )
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await bus.close()


app = FastAPI(title="Kronos Trader", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    settings = get_state().settings
    return {
        "status": "ok",
        "paper": settings.use_paper,
        "dryRun": settings.dry_run,
        "live": settings.live_trading_enabled,
        "symbols": settings.symbols,
    }


@app.get("/api/snapshot")
async def snapshot():
    return get_state().snapshot()


@app.get("/api/status")
async def system_status():
    return await build_system_status()


@app.get("/api/metrics/forecasts")
async def forecast_metrics():
    from app.forecast_metrics import refresh_all_metrics

    state = get_state()
    s = state.settings
    state.forecast_metrics = refresh_all_metrics(
        state.forecast_history,
        state.candles,
        list(s.symbols),
        min_hit_rate=s.min_hit_rate,
        max_mape=s.max_mape,
    )
    return {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "minHitRate": s.min_hit_rate,
        "maxMape": s.max_mape,
        "bySymbol": state.forecast_metrics,
    }


@app.get("/api/backtest/last")
async def backtest_last():
    from app.backtest.engine import load_backtest_result

    state = get_state()
    data = state.last_backtest or load_backtest_result()
    if not data:
        return {"ok": False, "message": "No backtest result yet. Run scripts/run_backtest.py"}
    return data


@app.post("/api/backtest/run")
async def backtest_run(
    symbols: str = Query("BTC/USD,SPY"),
    max_steps: int = Query(16, ge=4, le=80),
    use_inference: bool = Query(True),
):
    """Run a short cost-aware backtest (can take a while with inference)."""
    from app.backtest.engine import BacktestConfig, run_backtest

    state = get_state()
    settings = state.settings
    cfg = BacktestConfig(
        symbols=[s.strip() for s in symbols.split(",") if s.strip()],
        max_steps=max_steps,
        use_inference=use_inference,
        sample_count=min(2, settings.sample_count),
    )
    result = await run_backtest(settings, cfg)
    payload = {
        "ok": result.ok,
        "generatedAt": result.generatedAt,
        "startingCash": result.startingCash,
        "endingEquity": result.endingEquity,
        "netPnl": result.netPnl,
        "netPnlPct": result.netPnlPct,
        "maxDrawdownPct": result.maxDrawdownPct,
        "sharpeLike": result.sharpeLike,
        "winRate": result.winRate,
        "tradeCount": result.tradeCount,
        "avgEdgeBps": result.avgEdgeBps,
        "perSymbol": result.perSymbol,
        "config": result.config,
        "notes": result.notes,
    }
    state.last_backtest = payload
    return payload


@app.get("/api/symbols/search")
async def symbols_search(
    q: str = Query("", max_length=32),
    limit: int = Query(12, ge=1, le=30),
    exclude: str = Query("", description="Comma-separated tickers to hide"),
):
    from app.assets import normalize_symbol

    settings = get_state().settings
    excluded = {normalize_symbol(s) for s in exclude.split(",") if s.strip()}
    results = await asyncio.to_thread(
        search_symbols, settings, q, limit=limit, exclude=excluded
    )
    return {"query": normalize_symbol(q) if q.strip() else "", "results": results}


@app.get("/api/settings")
async def get_trader_settings():
    return settings_public(get_state().settings)


@app.patch("/api/settings")
async def patch_trader_settings(patch: SettingsPatch):
    state = get_state()
    try:
        result = apply_settings_patch(state, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result["changed"]:
        entry = state.add_activity(
            "system",
            f"Settings updated: {', '.join(result['changed'])}",
        )
        await bus.publish(
            {"type": "activity", "timestamp": entry["timestamp"], "payload": entry}
        )
        snap = state.snapshot()
        await bus.publish(
            {
                "type": "snapshot",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": snap,
            }
        )
    return result


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    q = bus.subscribe_local()
    try:
        # Send initial snapshot
        snap = get_state().snapshot()
        await websocket.send_text(
            json.dumps(
                {"type": "snapshot", "timestamp": snap["equity"][-1]["timestamp"] if snap["equity"] else "", "payload": snap},
                default=str,
            )
        )
        while True:
            event = await q.get()
            await websocket.send_text(json.dumps(event, default=str))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        bus.unsubscribe_local(q)
