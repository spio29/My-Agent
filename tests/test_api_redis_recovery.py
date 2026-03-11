import asyncio

from app.core import queue
from app.services.api import main


class _RecoveringRedis:
    async def keys(self, pattern: str):
        assert pattern == "hb:agent:*:*"
        return ["hb:agent:worker:worker_real"]

    async def get(self, key: str):
        assert key == "hb:agent:worker:worker_real"
        return '{"timestamp":"2026-03-11T07:15:11+00:00","pool":"default","concurrency":5}'

    async def ttl(self, key: str):
        assert key == "hb:agent:worker:worker_real"
        return 15


class _RunningTask:
    def done(self):
        return False


def test_agents_refreshes_runtime_state_after_redis_recovers(monkeypatch):
    queue.set_mode_fallback_redis(True)
    queue.set_mode_legacy_redis_queue(False)

    async def _healthy():
        return True

    calls = {"init_queue": 0, "stop_local_runtime": 0}

    async def _fake_init_queue():
        calls["init_queue"] += 1

    async def _fake_stop_local_runtime():
        calls["stop_local_runtime"] += 1
        main.app.state.local_mode = False
        main.app.state.local_worker_task = None
        main.app.state.local_scheduler_task = None

    monkeypatch.setattr(main, "_is_redis_ready", _healthy)
    monkeypatch.setattr(main, "init_queue", _fake_init_queue)
    monkeypatch.setattr(main, "_stop_local_runtime", _fake_stop_local_runtime)
    monkeypatch.setattr(main, "redis_client", _RecoveringRedis())

    main.app.state.redis_ready = False
    main.app.state.local_mode = True
    main.app.state.local_worker_task = _RunningTask()
    main.app.state.local_scheduler_task = _RunningTask()

    rows = asyncio.run(main.agents())

    assert calls["init_queue"] == 1
    assert calls["stop_local_runtime"] == 1
    assert main.app.state.redis_ready is True
    assert queue.is_mode_fallback_redis() is False
    assert rows == [
        {
            "id": "worker_real",
            "type": "worker",
            "status": "online",
            "last_heartbeat": "2026-03-11T07:15:11+00:00",
            "last_heartbeat_at": "2026-03-11T07:15:11+00:00",
            "active_sessions": 5,
            "pool": "default",
            "version": "0.1.0",
        }
    ]
