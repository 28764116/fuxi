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
    worldline_id: str | None = None,
    latest_event: dict | None = None,
) -> None:
    """Publish task progress to Redis channel.

    Payload fields:
      task_id, status, progress, message, error,
      worldline_id (当前推演中的世界线 ID，可选),
      latest_event  (最新事件摘要，可选)
    """
    payload = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "message": message,
        "error": error,
        "worldline_id": worldline_id,
        "latest_event": latest_event,
    }
    channel = f"sim:progress:{task_id}"
    try:
        _get_redis().publish(channel, json.dumps(payload, ensure_ascii=False))
    except Exception:
        logger.exception("Failed to publish progress for task %s", task_id)
