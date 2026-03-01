import uuid

import pytest
import redis.asyncio as redis_async

import app.core.armory as armory_mod
import app.core.branches as branches_mod
import app.core.redis_client as redis_client_mod
import app.core.boardroom as boardroom_mod
from app.core.armory import add_account, update_account_status
from app.core.branches import create_branch, get_branch, upsert_blueprint
from app.core.config import settings
from app.core.models import AccountStatus


class _Ctx:
    def __init__(self, tools, branch_id, run_id="run_money_test"):
        self.tools = tools
        self.branch_id = branch_id
        self.run_id = run_id


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
    old_branches = branches_mod.redis_client
    old_armory = armory_mod.redis_client

    redis_client_mod.redis_client = fresh_client
    branches_mod.redis_client = fresh_client
    armory_mod.redis_client = fresh_client

    try:
        yield
    finally:
        try:
            await fresh_client.aclose()
        except Exception:
            pass
        redis_client_mod.redis_client = old_shared
        branches_mod.redis_client = old_branches
        armory_mod.redis_client = old_armory


@pytest.mark.anyio
async def test_full_money_making_flow(anyio_backend, monkeypatch):
    if anyio_backend != "asyncio":
        return


    async def _noop_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(boardroom_mod, "notify_chairman", _noop_notify)

    # 1. Setup Blueprint & Branch
    bp_id = f"bp_test_money_{uuid.uuid4().hex[:6]}"
    await upsert_blueprint(
        {
            "blueprint_id": bp_id,
            "name": "Money Test Unit",
            "description": "Testing the flow",
            "base_strategy": "test",
            "default_jobs": [],
        }
    )
    branch = await create_branch("Test Branch", bp_id)
    branch_id = branch["branch_id"]

    # 2. Setup Account in Armory
    acc = await add_account("instagram", "test_seller", "pass", "1.2.3.4")
    await update_account_status(acc["account_id"], AccountStatus.READY)
    from app.core.armory import deploy_account_to_branch

    await deploy_account_to_branch(acc["account_id"], branch_id)

    # 3. Setup Tools
    from app.core.tools.messaging import MessagingTool
    from app.core.tools.revenue import RevenueTool

    tools = {
        "messaging": MessagingTool().run,
        "revenue": RevenueTool().run,
    }
    ctx = _Ctx(tools, branch_id)

    # 4. Simulate a SUCCESSFUL SALE (Closing)
    result = await tools["revenue"]({"amount": 1000000, "customer": "Chairman Test"}, ctx)
    assert result["success"] is True

    # 5. Verify Branch Metrics are updated
    updated_branch = await get_branch(branch_id)
    assert updated_branch["current_metrics"]["revenue"] == 1000000
    assert updated_branch["current_metrics"]["closings"] == 1
