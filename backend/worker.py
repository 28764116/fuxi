from celery import Celery

from app.config import settings

celery_app = Celery(
    "fuxi",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["memory", "simulation"])
