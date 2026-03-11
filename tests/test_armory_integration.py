import uuid

import pytest

import app.core.armory as armory_mod
import app.core.queue as queue_mod
import app.core.redis_client as redis_client_mod
from app.core.armory import add_account, get_account
from app.core.models import AccountStatus
from app.services.worker.main import _proses_satu_job
from tests.fake_async_redis import FakeAsyncRedis


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def _reset_redis_client_per_test():
    fresh_client = FakeAsyncRedis()

    old_shared = redis_client_mod.redis_client
    old_queue = queue_mod.redis_client
    old_armory = armory_mod.redis_client

    redis_client_mod.redis_client = fresh_client
    queue_mod.redis_client = fresh_client
    armory_mod.redis_client = fresh_client

    try:
        yield
    finally:
        try:
            await fresh_client.aclose()
        except Exception:
            pass
        redis_client_mod.redis_client = old_shared
        queue_mod.redis_client = old_queue
        armory_mod.redis_client = old_armory


@pytest.mark.anyio
async def test_armory_stealth_onboarding_flow(anyio_backend):
    if anyio_backend != "asyncio":
        return

    username = f"warrior_{uuid.uuid4().hex[:4]}"
    acc = await add_account(
        platform="instagram",
        username=username,
        password="secret_password_123",
        proxy="1.2.3.4:8080",
    )

    account_id = acc["account_id"]
    assert acc["status"] == AccountStatus.PENDING

    fetched = await get_account(account_id)
    assert fetched["username"] == username

    event = {
        "type": "armory.account_added",
        "data": {"account_id": account_id},
    }

    await _proses_satu_job("worker_test", event)

    final_acc = await get_account(account_id)
    assert final_acc["status"] == AccountStatus.READY
    assert final_acc["last_active"] is not None
