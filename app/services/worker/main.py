import asyncio
import time
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.core.handlers_registry import get_handler
from app.core.observability import logger, metrics_collector
from app.core.queue import (
    append_event,
    dequeue_job,
    get_job_spec,
    get_run,
    init_queue,
    is_mode_fallback_redis,
    is_mode_legacy_redis_queue,
    save_run,
)
from app.core.redis_client import redis_client
from app.core.registry import policy_manager, tool_registry
from app.core.runner import handle_retry, process_job_event
from app.core.tools.command import CommandTool
from app.core.tools.files import FilesTool
from app.core.tools.http import HTTPTool
from app.core.tools.kv import KVTool
from app.core.tools.messaging import MessagingTool
from app.core.tools.metrics import MetricsTool
from app.core.tools.multimedia import MultimediaTool
from app.core.tools.revenue import RevenueTool
from app.core.models import RunResult, RunStatus

AGENT_HEARTBEAT_TTL = 30

# Initialize tools
tool_registry.register_tool("http", "1.0.0", HTTPTool().run)
tool_registry.register_tool("kv", "1.0.0", KVTool().run)
tool_registry.register_tool("messaging", "1.0.0", MessagingTool().run)
tool_registry.register_tool("files", "1.0.0", FilesTool().run)
tool_registry.register_tool("metrics", "1.0.0", MetricsTool().run)
tool_registry.register_tool("command", "1.0.0", CommandTool().run)
tool_registry.register_tool("multimedia", "1.0.0", MultimediaTool().run)
tool_registry.register_tool("revenue", "1.0.0", RevenueTool().run)

# Set default policies
policy_manager.set_allowlist("monitor.channel", ["metrics", "messaging"])
policy_manager.set_allowlist("report.daily", ["metrics", "messaging"])
policy_manager.set_allowlist("backup.export", ["files", "kv"])
policy_manager.set_allowlist("agent.workflow", ["http", "kv", "messaging", "files", "metrics", "command", "multimedia", "revenue"])
policy_manager.set_allowlist("simulation.heavy", ["metrics"])


async def update_heartbeat(worker_id: str):
    if is_mode_fallback_redis():
        return

    try:
        import json
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool": _get_agent_pool(),
            "concurrency": _normalisasi_konkruensi()
        }
        await redis_client.setex(
            f"hb:agent:worker:{worker_id}",
            AGENT_HEARTBEAT_TTL,
            json.dumps(payload),
        )
    except Exception:
        # In local fallback mode Redis may be unavailable; keep worker running.
        return


def _normalisasi_konkruensi() -> int:
    try:
        value = int(settings.WORKER_CONCURRENCY)
    except Exception:
        value = 1
    return max(1, min(value, 64))

def _get_agent_pool() -> str:
    import os
    return str(os.getenv("AGENT_POOL", "default")).strip().lower()

async def _proses_satu_job(worker_id: str, data_event: dict):
    tipe_event = data_event.get("type")
    
    # Handle Armory Events (Internal System Tasks)
    if tipe_event == "armory.account_added":
        from app.core.armory import verify_account_stealth
        account_id = data_event.get("data", {}).get("account_id")
        if account_id:
            logger.info(f"Starting stealth onboarding for account: {account_id}")
            await verify_account_stealth(account_id)
        return

    # Handle standard job processing...
    tipe_job = tipe_event
    
    # Check pool assignment
    job_pool = str(data_event.get("agent_pool") or "default").strip().lower()
    worker_pool = _get_agent_pool()

    # NOTE:
    # Current implementation uses a single shared Redis Stream across pools.
    # Skipping here can strand runs in "queued" because messages are already ACK-ed
    # at dequeue time. To preserve reliability we process the job even on mismatch.
    # Strict per-pool routing should only be enabled once multi-stream routing is in place.
    if job_pool != worker_pool and worker_pool != "global":
        logger.warning(
            "Pool mismatch detected on shared stream; processing job to avoid stranded queued run",
            extra={"job_pool": job_pool, "worker_pool": worker_pool, "run_id": data_event.get("run_id")},
        )

    metrics_collector.increment("worker_job_dequeued", tags={"pool": worker_pool, "type": tipe_job})
    
    handler = get_handler(tipe_job)
    
    # Let dynamic skills pass through to process_job_event for resolution
    if not handler and not tipe_job.startswith("skill:"):
        logger.error(
            f"No handler found for job type: {tipe_job}",
            extra={"run_id": data_event.get("run_id"), "job_id": data_event.get("job_id")},
        )
        run_id = str(data_event.get("run_id") or "").strip()
        if run_id:
            data_run = await get_run(run_id)
            if data_run:
                data_run.status = RunStatus.FAILED
                data_run.finished_at = datetime.now(timezone.utc)
                data_run.result = RunResult(success=False, error=f"No handler for {tipe_job}")
                await save_run(data_run)
        await append_event(
            "run.failed",
            {
                "run_id": data_event.get("run_id"),
                "job_id": data_event.get("job_id"),
                "job_type": tipe_job,
                "error": f"No handler for {tipe_job}",
            },
        )
        return

    # Pass the entire registry, process_job_event will resolve 'skill:*' dynamically
    handler_map = {tipe_job: handler} if handler else {}
    from app.core.handlers_registry import peta_handler_job
    
    berhasil = await process_job_event(
        data_event,
        worker_id,
        peta_handler_job, # Pass the full registry so resolved skills can find their base handler
        tool_registry.tools,
        logger,
        metrics_collector,
    )
    if berhasil:
        return

    # If failed, schedule retry when possible.
    job_id = data_event.get("job_id")
    run_id = data_event.get("run_id")
    attempt = int(data_event.get("attempt", 0))
    spesifikasi = await get_job_spec(job_id) if job_id else None
    if not spesifikasi:
        return

    kebijakan_retry = spesifikasi.get("retry_policy", {"max_retry": 0, "backoff_sec": [1, 2, 5]})
    await handle_retry(
        job_id=job_id,
        run_id=run_id,
        attempt=attempt,
        retry_policy=kebijakan_retry,
        scheduled_at=datetime.now(timezone.utc),
    )


async def _worker_slot_loop(worker_id: str, consumer_id: str):
    while True:
        try:
            data_job = await dequeue_job(consumer_id)
            if not data_job:
                await asyncio.sleep(0.1)
                continue

            await _proses_satu_job(worker_id, data_job["data"])

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                f"Worker slot error: {e}",
                extra={"worker_id": worker_id, "consumer_id": consumer_id},
            )
            await asyncio.sleep(0.5)


async def _heartbeat_loop(worker_id: str):
    while True:
        try:
            await update_heartbeat(worker_id)
            await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(1)


async def worker_main():
    """Main worker loop."""
    await init_queue()

    worker_id = f"worker_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    concurrency = _normalisasi_konkruensi()
    logger.info(
        "Worker started",
        extra={
            "worker_id": worker_id,
            "concurrency": concurrency,
            "fallback_mode": is_mode_fallback_redis(),
            "legacy_queue_mode": is_mode_legacy_redis_queue(),
        },
    )
    try:
        await asyncio.wait_for(
            append_event(
                "system.worker_started",
                {"worker_id": worker_id, "concurrency": concurrency},
            ),
            timeout=1.0,
        )
    except Exception:
        # Startup event should not block worker execution in degraded Redis conditions.
        pass

    tasks = [asyncio.create_task(_heartbeat_loop(worker_id), name=f"{worker_id}:heartbeat")]
    for index in range(concurrency):
        consumer_id = f"{worker_id}_c{index + 1}"
        tasks.append(asyncio.create_task(_worker_slot_loop(worker_id, consumer_id), name=f"{worker_id}:{consumer_id}"))

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Worker cancelled", extra={"worker_id": worker_id})
        raise
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(worker_main())
