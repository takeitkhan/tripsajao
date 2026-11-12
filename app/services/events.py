"""Tiny pub/sub used by the live dashboard (SSE). Best-effort: failures never break a request."""
import json
import logging
from uuid import UUID

from app.core.redis import get_redis

log = logging.getLogger(__name__)


def channel(tenant_id: UUID | str) -> str:
    return f"events:{tenant_id}"


async def publish(tenant_id: UUID | str, event: str, data: dict, redis=None) -> None:
    try:
        await (redis or get_redis()).publish(channel(tenant_id), json.dumps({"event": event, **data}, default=str))
    except Exception:  # noqa: BLE001
        log.warning("event publish failed", exc_info=True)
