from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.bus import bus
from app.config import get_settings
from app.db.session import init_db
from app.logging_setup import setup_logging
from app.loop import trading_loop
from app.settings_api import SettingsPatch, apply_settings_patch, settings_public
from app.state import get_state

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)
    await init_db()
    await bus.connect()
    get_state()  # init
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
