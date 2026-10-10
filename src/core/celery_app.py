from celery import Celery

from src.core.config import settings

celery_app = Celery(
    "online_cinema",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "src.tasks.email",
        "src.tasks.cleaners",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "clean-expired-activation-tokens-every-hour": {
            "task": "src.tasks.cleaners.clean_expired_activation_tokens",
            "schedule": 3600.0,
        },
    },
)
