import uuid

import pytest
import redis.asyncio as redis_async

import app.core.queue as queue_mod
import app.core.redis_client as redis_client_mod
import app.core.triggers as triggers_mod
from app.core.config import settings
from app.core.queue import enable_job, save_job_spec
from app.core.triggers import delete_trigger, fire_trigger, get_trigger, list_triggers, upsert_trigger


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def _reset_redis_client_per_test():
    fresh_client = redis_async.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
        encoding="utf-8",
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
        retry_on_timeout=False,
    )

    old_shared = redis_client_mod.redis_client
    old_queue = queue_mod.redis_client
    old_triggers = triggers_mod.redis_client

    redis_client_mod.redis_client = fresh_client
    queue_mod.redis_client = fresh_client
    triggers_mod.redis_client = fresh_client

    try:
        yield
    finally:
        try:
            await fresh_client.aclose()
        except Exception:
            pass
        redis_client_mod.redis_client = old_shared
        queue_mod.redis_client = old_queue
        triggers_mod.redis_client = old_triggers


@pytest.mark.anyio
async def test_trigger_lifecycle(anyio_backend):
    if anyio_backend != "asyncio":
        return

    # Setup job target
    job_id = f"test-job-{uuid.uuid4().hex[:6]}"
    await save_job_spec(
        job_id,
        {
            "job_id": job_id,
            "type": "monitor.channel",
            "inputs": {"test": True},
        },
    )
    await enable_job(job_id)

    trigger_id = f"test-trigger-{uuid.uuid4().hex[:6]}"

    # 1. Upsert
    payload = {
        "name": "Test Trigger",
        "job_id": job_id,
        "channel": "webhook",
        "description": "A test trigger",
        "enabled": True,
        "default_payload": {"foo": "bar"},
    }
    row = await upsert_trigger(trigger_id, payload)
    assert row["trigger_id"] == trigger_id
    assert row["name"] == "Test Trigger"
    assert row["channel"] == "webhook"

    # 2. Get
    fetched = await get_trigger(trigger_id)
    assert fetched is not None
    assert fetched["name"] == "Test Trigger"

    # 3. List
    all_triggers = await list_triggers()
    assert any(t["trigger_id"] == trigger_id for t in all_triggers)

    # 4. Fire
    result = await fire_trigger(trigger_id, payload={"extra": 123}, source="test.suite")
    assert "run_id" in result
    assert result["job_id"] == job_id
    assert result["channel"] == "webhook"

    # 5. Delete
    deleted = await delete_trigger(trigger_id)
    assert deleted is True
    assert await get_trigger(trigger_id) is None
