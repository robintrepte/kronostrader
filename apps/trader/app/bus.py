from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._local_subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    async def connect(self) -> None:
        settings = get_settings()
        try:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Connected to Redis at %s", settings.redis_url)
        except Exception:
            logger.warning("Redis unavailable — using in-process fanout only", exc_info=True)
            self._redis = None

    def subscribe_local(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._local_subscribers.append(q)
        return q

    def unsubscribe_local(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        if q in self._local_subscribers:
            self._local_subscribers.remove(q)

    async def publish(self, event: dict[str, Any]) -> None:
        settings = get_settings()
        payload = json.dumps(event, default=str)
        for q in list(self._local_subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                q.put_nowait(event)
        if self._redis is not None:
            try:
                await self._redis.publish(settings.redis_channel, payload)
            except Exception:
                logger.exception("Redis publish failed")

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()


bus = EventBus()
