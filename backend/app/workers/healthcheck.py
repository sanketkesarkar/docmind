"""Check this pod's RQ heartbeat, allowing dependency outages to recover."""
import os
import sys
from datetime import datetime, timezone

import redis
from redis.exceptions import RedisError
from rq import Worker
from app.config import settings


def healthy():
    connection = redis.from_url(settings.REDIS_URL, socket_connect_timeout=3, socket_timeout=3)
    try:
        worker = Worker.find_by_key("rq:worker:" + os.environ.get("HOSTNAME", "docmind-worker"), connection=connection)
        if worker is None or worker.last_heartbeat is None:
            return False
        heartbeat = worker.last_heartbeat
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - heartbeat).total_seconds() < 120
    except RedisError:
        # Redis outage is not evidence of a dead worker; its main loop reconnects.
        return True


if __name__ == "__main__":
    sys.exit(0 if healthy() else 1)
