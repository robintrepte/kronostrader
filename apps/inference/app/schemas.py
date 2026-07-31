from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OhlcvBar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    amount: Optional[float] = None


class PredictRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    bars: list[OhlcvBar] = Field(..., min_length=2, max_length=512)
    pred_len: int = Field(24, ge=1, le=512)
    pred_timestamps: Optional[list[datetime]] = None
    temperature: float = Field(1.0, alias="T", ge=0.0)
    top_p: float = Field(0.9, ge=0.0, le=1.0)
    sample_count: int = Field(1, ge=1, le=8)

    model_config = {"populate_by_name": True}


class ForecastPointOut(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    amount: float = 0.0
    close_low: Optional[float] = None
    close_high: Optional[float] = None


class PredictResponse(BaseModel):
    symbol: str
    model: str
    device: str
    sample_count: int
    forecast: list[ForecastPointOut]


class HealthResponse(BaseModel):
    status: str
    model: str
    tokenizer: str
    device: str
    loaded: bool
    uptime_seconds: float
    max_context: int
