"""Task progress publishing via Redis Pub/Sub.

Workers call publish_progress() to push updates.
WebSocket endpoint subscribes and forwards to clients.
"""

import json
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.redis_url)
    return _redis_client


def publish_progress(
    task_id: str,
    status: str,
    progress: int,
    message: str = "",
    error: str | None = None,
) -> None:
    """Publish task progress to Redis channel."""
    payload = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "message": message,
        "error": error,
    }
    channel = f"sim:progress:{task_id}"
    try:
        _get_redis().publish(channel, json.dumps(payload, ensure_ascii=False))
    except Exception:
        logger.exception("Failed to publish progress for task %s", task_id)
