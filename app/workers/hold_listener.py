"""Redis keyspace-notification listener.  Run:  python -m app.workers.hold_listener

Subscribes to `__keyevent@*__:expired`. When `hold:{tenant}:{booking}` expires it enqueues the idempotent
`release_hold` Celery task. Needs `notify-keyspace-events Ex` (the docker-compose file sets it; managed Redis
services usually require enabling it in their console - the listener also tries CONFIG SET).
Events are best-effort; `sweep_expired_holds` (beat, every 60s) is the correctness backstop."""
import asyncio
import logging

from redis.exceptions import ConnectionError as RedisConnectionError, ResponseError

from app.core.redis import new_redis
from app.services.holds import parse_hold_key
from app.workers.tasks import release_hold

log = logging.getLogger("hold_listener")


async def run_forever() -> None:
    backoff = 1
    while True:
        redis = new_redis()
        try:
            try:
                await redis.config_set("notify-keyspace-events", "Ex")
            except ResponseError:
                log.warning("CONFIG SET not permitted; make sure notify-keyspace-events includes 'Ex'")
            pubsub = redis.pubsub()
            await pubsub.psubscribe("__keyevent@*__:expired")
            backoff = 1
            log.info("listening for expired hold keys")
            async for msg in pubsub.listen():
                if msg["type"] != "pmessage":
                    continue
                parsed = parse_hold_key(msg["data"])
                if parsed:
                    tenant_id, booking_id = parsed
                    release_hold.delay(str(tenant_id), str(booking_id))
        except (RedisConnectionError, OSError):
            log.warning("redis connection lost; retrying in %ss", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
        finally:
            await redis.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
