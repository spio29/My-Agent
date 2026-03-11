import asyncio
from datetime import datetime, timedelta, timezone

from redis.exceptions import RedisError, ResponseError, TimeoutError as RedisTimeoutError

from app.core import queue
from app.core.models import Run, RunStatus


class _MustNotCallRedis:
    def __getattr__(self, name):
        async def _raise(*args, **kwargs):
            raise AssertionError(f"Redis method should not be called in fallback mode: {name}")

        return _raise


class _FailingRedisOnXadd:
    def __init__(self):
        self.xadd_calls = 0

    async def xadd(self, *args, **kwargs):
        self.xadd_calls += 1
        raise RedisError("redis unavailable")


class _LegacyRedisNoStreams:
    def __init__(self):
        self._items = []

    async def xgroup_create(self, *args, **kwargs):
        raise ResponseError("unknown command 'XGROUP'")

    async def rpush(self, key, payload):
        self._items.append(payload)
        return len(self._items)

    async def blpop(self, key, timeout=0):
        if not self._items:
            return None
        return (key, self._items.pop(0))

    async def llen(self, key):
        return len(self._items)

    async def zcard(self, key):
        return 0


class _LegacyRedisTimeoutOnBlpop:
    async def blpop(self, key, timeout=0):
        raise RedisTimeoutError("socket timeout")


class _RedisTimeoutOnXreadgroup:
    async def xreadgroup(self, *args, **kwargs):
        raise RedisTimeoutError("socket timeout")


class _RecoveringRedis:
    def __init__(self):
        self.ping_calls = 0
        self.xgroup_create_calls = 0

    async def ping(self):
        self.ping_calls += 1
        return True

    async def xgroup_create(self, *args, **kwargs):
        self.xgroup_create_calls += 1
        return True


def _reset_queue_fallback_state():
    queue.set_mode_fallback_redis(False)
    queue.set_mode_legacy_redis_queue(False)
    queue._last_redis_recovery_attempt_monotonic = 0.0
    queue._fallback_stream.clear()
    queue._fallback_delayed.clear()
    queue._fallback_job_specs.clear()
    queue._fallback_job_all.clear()
    queue._fallback_job_enabled.clear()
    queue._fallback_job_spec_versions.clear()
    queue._fallback_runs.clear()
    queue._fallback_run_scores.clear()
    queue._fallback_job_runs.clear()
    queue._fallback_active_runs.clear()
    queue._fallback_active_flow_runs.clear()
    queue._fallback_failure_state.clear()
    queue._fallback_events.clear()


def test_queue_fallback_mode_short_circuits_redis(monkeypatch):
    _reset_queue_fallback_state()
    monkeypatch.setattr(queue, "redis_client", _MustNotCallRedis())
    queue.set_mode_fallback_redis(True)

    message_id = asyncio.run(
        queue.enqueue_job(
            {
                "run_id": "run_1",
                "job_id": "job_1",
                "type": "monitor.channel",
                "inputs": {},
                "attempt": 0,
            }
        )
    )
    assert message_id

    dequeued = asyncio.run(queue.dequeue_job("worker_1"))
    assert dequeued is not None
    assert dequeued["data"]["job_id"] == "job_1"

    asyncio.run(queue.save_job_spec("job_1", {"job_id": "job_1", "type": "monitor.channel"}))
    spec = asyncio.run(queue.get_job_spec("job_1"))
    assert spec is not None
    assert spec["job_id"] == "job_1"

    asyncio.run(queue.enable_job("job_1"))
    assert asyncio.run(queue.is_job_enabled("job_1")) is True
    assert asyncio.run(queue.list_enabled_job_ids()) == ["job_1"]

    run = Run(
        run_id="run_1",
        job_id="job_1",
        status=RunStatus.QUEUED,
        attempt=0,
        scheduled_at=datetime.now(timezone.utc),
        inputs={},
    )
    asyncio.run(queue.save_run(run))
    loaded = asyncio.run(queue.get_run("run_1"))
    assert loaded is not None
    assert loaded.run_id == "run_1"

    asyncio.run(queue.append_event("test.event", {"ok": True}))
    events = asyncio.run(queue.get_events(limit=10))
    assert len(events) == 1
    assert events[0]["type"] == "test.event"


def test_queue_auto_switches_to_fallback_after_redis_error(monkeypatch):
    _reset_queue_fallback_state()
    redis_fail = _FailingRedisOnXadd()
    monkeypatch.setattr(queue, "redis_client", redis_fail)

    assert queue.is_mode_fallback_redis() is False

    first_id = asyncio.run(
        queue.enqueue_job(
            {
                "run_id": "run_a",
                "job_id": "job_a",
                "type": "monitor.channel",
                "inputs": {},
                "attempt": 0,
            }
        )
    )
    assert first_id
    assert redis_fail.xadd_calls == 1
    assert queue.is_mode_fallback_redis() is True

    second_id = asyncio.run(
        queue.enqueue_job(
            {
                "run_id": "run_b",
                "job_id": "job_b",
                "type": "monitor.channel",
                "inputs": {},
                "attempt": 0,
            }
        )
    )
    assert second_id
    assert redis_fail.xadd_calls == 1


def test_queue_switches_to_legacy_mode_when_stream_not_supported(monkeypatch):
    _reset_queue_fallback_state()
    legacy_redis = _LegacyRedisNoStreams()
    monkeypatch.setattr(queue, "redis_client", legacy_redis)

    asyncio.run(queue.init_queue())
    assert queue.is_mode_fallback_redis() is False
    assert queue.is_mode_legacy_redis_queue() is True

    message_id = asyncio.run(
        queue.enqueue_job(
            {
                "run_id": "run_legacy_1",
                "job_id": "job_legacy_1",
                "type": "monitor.channel",
                "inputs": {},
                "attempt": 0,
            }
        )
    )
    assert message_id

    dequeued = asyncio.run(queue.dequeue_job("worker_legacy"))
    assert dequeued is not None
    assert dequeued["data"]["job_id"] == "job_legacy_1"

    metrics = asyncio.run(queue.get_queue_metrics())
    assert metrics == {"depth": 0, "delayed": 0}


def test_legacy_dequeue_timeout_does_not_trigger_fallback(monkeypatch):
    _reset_queue_fallback_state()
    queue.set_mode_legacy_redis_queue(True)
    monkeypatch.setattr(queue, "redis_client", _LegacyRedisTimeoutOnBlpop())

    row = asyncio.run(queue.dequeue_job("worker_legacy_timeout"))
    assert row is None
    assert queue.is_mode_fallback_redis() is False
    assert queue.is_mode_legacy_redis_queue() is True


def test_stream_dequeue_timeout_does_not_trigger_fallback(monkeypatch):
    _reset_queue_fallback_state()
    monkeypatch.setattr(queue, "redis_client", _RedisTimeoutOnXreadgroup())

    row = asyncio.run(queue.dequeue_job("worker_stream_timeout"))
    assert row is None
    assert queue.is_mode_fallback_redis() is False
    assert queue.is_mode_legacy_redis_queue() is False


def test_try_recover_redis_leaves_fallback_mode_when_redis_returns(monkeypatch):
    _reset_queue_fallback_state()
    redis_recover = _RecoveringRedis()
    monkeypatch.setattr(queue, "redis_client", redis_recover)
    queue.set_mode_fallback_redis(True)

    recovered = asyncio.run(queue.try_recover_redis(force=True))

    assert recovered is True
    assert queue.is_mode_fallback_redis() is False
    assert queue.is_mode_legacy_redis_queue() is False
    assert redis_recover.ping_calls == 1
    assert redis_recover.xgroup_create_calls == 1


def test_active_runs_index_updates_in_fallback_mode(monkeypatch):
    _reset_queue_fallback_state()
    monkeypatch.setattr(queue, "redis_client", _MustNotCallRedis())
    queue.set_mode_fallback_redis(True)

    run = Run(
        run_id="run_active_1",
        job_id="job_active_1",
        status=RunStatus.QUEUED,
        attempt=0,
        scheduled_at=datetime.now(timezone.utc),
        inputs={},
    )
    asyncio.run(queue.save_run(run))
    assert asyncio.run(queue.has_active_runs("job_active_1")) is True

    run.status = RunStatus.SUCCESS
    asyncio.run(queue.save_run(run))
    assert asyncio.run(queue.has_active_runs("job_active_1")) is False


def test_failure_memory_sets_and_clears_cooldown_in_fallback(monkeypatch):
    _reset_queue_fallback_state()
    monkeypatch.setattr(queue, "redis_client", _MustNotCallRedis())
    queue.set_mode_fallback_redis(True)

    # Fail 3x to trigger cooldown.
    for _ in range(3):
        asyncio.run(
            queue.record_job_outcome(
                "job_fail_1",
                success=False,
                error="simulated error",
                failure_threshold=3,
                failure_cooldown_sec=60,
                failure_cooldown_max_sec=300,
            )
        )

    state = asyncio.run(queue.get_job_failure_state("job_fail_1"))
    assert state["consecutive_failures"] == 3
    assert state["cooldown_until"] is not None
    assert asyncio.run(queue.get_job_cooldown_remaining("job_fail_1")) > 0

    asyncio.run(queue.record_job_outcome("job_fail_1", success=True))
    state_after = asyncio.run(queue.get_job_failure_state("job_fail_1"))
    assert state_after["consecutive_failures"] == 0
    assert state_after["cooldown_until"] is None


def test_flow_active_runs_index_updates_in_fallback_mode(monkeypatch):
    _reset_queue_fallback_state()
    monkeypatch.setattr(queue, "redis_client", _MustNotCallRedis())
    queue.set_mode_fallback_redis(True)

    run = Run(
        run_id="run_flow_1",
        job_id="job_flow_1",
        status=RunStatus.RUNNING,
        attempt=0,
        scheduled_at=datetime.now(timezone.utc),
        inputs={"flow_group": "tim_konten"},
    )
    asyncio.run(queue.save_run(run))
    assert asyncio.run(queue.count_active_runs_for_flow_group("tim_konten")) == 1

    run.status = RunStatus.SUCCESS
    asyncio.run(queue.save_run(run))
    assert asyncio.run(queue.count_active_runs_for_flow_group("tim_konten")) == 0


def test_list_runs_supports_offset_and_search_in_fallback_mode(monkeypatch):
    _reset_queue_fallback_state()
    monkeypatch.setattr(queue, "redis_client", _MustNotCallRedis())
    queue.set_mode_fallback_redis(True)

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        ("run_1", "job_a", RunStatus.QUEUED),
        ("run_2", "job_b", RunStatus.SUCCESS),
        ("run_3", "job_a", RunStatus.FAILED),
        ("run_4", "job_b", RunStatus.SUCCESS),
        ("run_5", "job_a", RunStatus.RUNNING),
    ]
    for idx, (run_id, job_id, status) in enumerate(rows):
        asyncio.run(
            queue.save_run(
                Run(
                    run_id=run_id,
                    job_id=job_id,
                    status=status,
                    attempt=0,
                    scheduled_at=base + timedelta(minutes=idx),
                    inputs={},
                )
            )
        )

    page = asyncio.run(queue.list_runs(limit=2, offset=1))
    assert [run.run_id for run in page] == ["run_4", "run_3"]

    success_rows = asyncio.run(queue.list_runs(limit=10, status="success"))
    assert [run.run_id for run in success_rows] == ["run_4", "run_2"]

    search_rows = asyncio.run(queue.list_runs(limit=10, search="job_b"))
    assert [run.run_id for run in search_rows] == ["run_4", "run_2"]


def test_get_events_supports_offset_and_since_in_fallback_mode(monkeypatch):
    _reset_queue_fallback_state()
    monkeypatch.setattr(queue, "redis_client", _MustNotCallRedis())
    queue.set_mode_fallback_redis(True)

    queue._fallback_events[:] = [
        {"id": "evt_5", "type": "run.failed", "timestamp": "2026-01-05T00:00:00+00:00", "data": {"run_id": "run_5"}},
        {"id": "evt_4", "type": "run.success", "timestamp": "2026-01-04T00:00:00+00:00", "data": {"run_id": "run_4"}},
        {"id": "evt_3", "type": "run.started", "timestamp": "2026-01-03T00:00:00+00:00", "data": {"run_id": "run_3"}},
        {"id": "evt_2", "type": "run.queued", "timestamp": "2026-01-02T00:00:00+00:00", "data": {"run_id": "run_2"}},
        {"id": "evt_1", "type": "system.ready", "timestamp": "2026-01-01T00:00:00+00:00", "data": {"ok": True}},
    ]

    page = asyncio.run(queue.get_events(limit=2, offset=1))
    assert [row["id"] for row in page] == ["evt_3", "evt_4"]

    since_rows = asyncio.run(queue.get_events(limit=10, since="2026-01-02T12:00:00+00:00"))
    assert [row["id"] for row in since_rows] == ["evt_3", "evt_4", "evt_5"]

    second_page = asyncio.run(queue.get_events(limit=1, offset=1, since="2026-01-01T00:00:00+00:00"))
    assert [row["id"] for row in second_page] == ["evt_4"]
