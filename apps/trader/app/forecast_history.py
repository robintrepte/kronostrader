from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.db.models import ForecastRow
from app.db.session import session_scope
from app.state import FORECAST_HISTORY_LIMIT, get_state

logger = logging.getLogger(__name__)


def _row_to_entry(row: ForecastRow) -> dict[str, Any]:
    raw_points = row.points or {}
    points = raw_points.get("points", raw_points) if isinstance(raw_points, dict) else []
    if not isinstance(points, list):
        points = []
    generated = row.generated_at
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    return {
        "id": f"db-{row.id}",
        "symbol": row.symbol,
        "generatedAt": generated.isoformat(),
        "model": row.model,
        "sampleCount": row.sample_count,
        "points": points,
        "anchorTimestamp": raw_points.get("anchorTimestamp") if isinstance(raw_points, dict) else None,
        "anchorClose": raw_points.get("anchorClose") if isinstance(raw_points, dict) else None,
    }


async def load_forecast_history() -> None:
    """Hydrate in-memory forecast history from Postgres so restarts keep accuracy overlays."""
    state = get_state()
    try:
        async with session_scope() as session:
            for symbol in state.settings.symbols:
                result = await session.execute(
                    select(ForecastRow)
                    .where(ForecastRow.symbol == symbol)
                    .order_by(ForecastRow.generated_at.desc())
                    .limit(FORECAST_HISTORY_LIMIT)
                )
                rows = list(reversed(result.scalars().all()))
                entries = [_row_to_entry(r) for r in rows if r.points]
                state.forecast_history[symbol] = entries
                if entries:
                    latest = entries[-1]
                    state.forecasts[symbol] = {
                        "symbol": latest["symbol"],
                        "generatedAt": latest["generatedAt"],
                        "model": latest["model"],
                        "sampleCount": latest["sampleCount"],
                        "points": latest["points"],
                        "anchorTimestamp": latest.get("anchorTimestamp"),
                        "anchorClose": latest.get("anchorClose"),
                    }
        total = sum(len(v) for v in state.forecast_history.values())
        logger.info("Loaded %s historical forecasts from DB", total)
    except Exception:
        logger.exception("Failed to load forecast history from DB")


def enrich_forecast_payload(
    symbol: str,
    points: list[dict[str, Any]],
    model: str,
    sample_count: int,
    anchor_timestamp: str | None,
    anchor_close: float | None,
) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "symbol": symbol,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "sampleCount": sample_count,
        "points": points,
        "anchorTimestamp": anchor_timestamp,
        "anchorClose": anchor_close,
    }
