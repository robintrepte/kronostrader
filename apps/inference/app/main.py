from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.engine import ModelNotReadyError, engine
from app.hardware import collect_hardware
from app.logging_setup import setup_logging
from app.schemas import HealthResponse, PredictRequest, PredictResponse

logger = logging.getLogger(__name__)
STARTED_AT = time.time()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)
    try:
        engine.load(
            model_id=settings.model_id,
            tokenizer_id=settings.tokenizer_id,
            device=settings.device,
            max_context=settings.max_context,
        )
    except Exception:
        logger.exception("Failed to load Kronos model at startup")
        # Stay up so /health can report unloaded; predict will 503
    yield


app = FastAPI(title="Kronos Inference", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    device = engine.device or settings.device
    return HealthResponse(
        status="ok" if engine.loaded else "degraded",
        model=engine.model_id or settings.model_id,
        tokenizer=engine.tokenizer_id or settings.tokenizer_id,
        device=device,
        loaded=engine.loaded,
        uptime_seconds=round(time.time() - STARTED_AT, 2),
        max_context=engine.max_context or settings.max_context,
        hardware=collect_hardware(device),
    )


@app.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest, request: Request) -> PredictResponse:
    settings = get_settings()
    request_id = getattr(request.state, "request_id", "-")
    logger.info(
        "predict_request",
        extra={
            "request_id": request_id,
            "symbol": req.symbol,
            "bars": len(req.bars),
            "pred_len": req.pred_len,
            "sample_count": req.sample_count,
        },
    )
    try:
        bars = [b.model_dump() for b in req.bars]
        pred_ts = req.pred_timestamps
        forecast = engine.predict(
            bars=bars,
            pred_len=req.pred_len,
            pred_timestamps=pred_ts,
            temperature=req.temperature,
            top_p=req.top_p,
            sample_count=req.sample_count,
        )
    except ModelNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("predict_failed", extra={"request_id": request_id})
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PredictResponse(
        symbol=req.symbol,
        model=engine.model_id or settings.model_id,
        device=str(engine.device),
        sample_count=req.sample_count,
        forecast=forecast,
    )


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.exception("unhandled", extra={"path": request.url.path})
    return JSONResponse(status_code=500, content={"detail": str(exc)})
