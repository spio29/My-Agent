import asyncio
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from .approval_queue import create_approval_request
from .models import RunStatus, Run, RunResult
from .queue import add_run_to_job_history, append_event, get_run, record_job_outcome, save_run
from .redis_client import redis_client


class JobContext:
    def __init__(
        self,
        job_id: str,
        run_id: str,
        trace_id: str,
        redis_client,
        tools,
        logger,
        metrics,
        span,
        timeout_ms: int,
        inputs: Optional[Dict[str, Any]] = None,
    ):
        self.job_id = job_id
        self.run_id = run_id
        self.trace_id = trace_id
        self.redis = redis_client
        self.tools = tools
        self.logger = logger
        self.metrics = metrics
        self.span = span
        self.timeout_ms = timeout_ms
        self.inputs = inputs or {}

        branch_id = str(self.inputs.get("branch_id") or self.inputs.get("target_branch_id") or "").strip()
        if not branch_id:
            flow_group = str(self.inputs.get("flow_group") or "").strip()
            if flow_group.lower().startswith("br_"):
                branch_id = flow_group
        self.branch_id = branch_id


async def execute_job_handler(handler: Callable, ctx: JobContext, inputs: Dict) -> RunResult:
    """Execute a job handler with timeout and error handling"""
    waktu_mulai = time.time()

    try:
        hasil_handler = await asyncio.wait_for(handler(ctx, inputs), timeout=ctx.timeout_ms / 1000.0)
        durasi_ms = int((time.time() - waktu_mulai) * 1000)

        # Convention: handlers may return {"success": false, "error": "..."} to signal logical failure.
        # Treat this as a failed run so status, retries, and observability stay consistent.
        if isinstance(hasil_handler, dict) and hasil_handler.get("success") is False:
            pesan_error = str(hasil_handler.get("error") or "Handler returned success=false")
            ctx.logger.warning(
                "Handler returned logical failure",
                extra={"job_id": ctx.job_id, "run_id": ctx.run_id, "error": pesan_error},
            )
            return RunResult(success=False, output=hasil_handler, error=pesan_error, duration_ms=durasi_ms)

        return RunResult(success=True, output=hasil_handler, duration_ms=durasi_ms)

    except asyncio.TimeoutError:
        pesan_error = f"Job timed out after {ctx.timeout_ms}ms"
        ctx.logger.error(pesan_error, extra={"job_id": ctx.job_id, "run_id": ctx.run_id})
        return RunResult(success=False, error=pesan_error, duration_ms=int((time.time() - waktu_mulai) * 1000))

    except Exception as e:
        pesan_error = f"Job failed with exception: {str(e)}\n{traceback.format_exc()}"
        ctx.logger.error(pesan_error, extra={"job_id": ctx.job_id, "run_id": ctx.run_id})
        return RunResult(success=False, error=pesan_error, duration_ms=int((time.time() - waktu_mulai) * 1000))


async def _coba_simpan_approval_dari_output(
    *,
    run_id: str,
    job_id: str,
    job_type: str,
    inputs: Dict[str, Any],
    hasil_run: RunResult,
    logger,
) -> None:
    output = hasil_run.output
    if not isinstance(output, dict):
        return
    if not bool(output.get("requires_approval")):
        return

    daftar_request = output.get("approval_requests", [])
    if not isinstance(daftar_request, list) or len(daftar_request) == 0:
        return

    prompt = str(output.get("prompt") or inputs.get("prompt") or "").strip()
    summary = str(output.get("summary") or output.get("error") or "Agen meminta approval tambahan.").strip()

    try:
        approval, baru_dibuat = await create_approval_request(
            run_id=run_id,
            job_id=job_id,
            job_type=job_type,
            prompt=prompt,
            summary=summary,
            approval_requests=daftar_request,
            available_providers=output.get("available_providers"),
            available_mcp_servers=output.get("available_mcp_servers"),
            source=str(output.get("source") or "agent.workflow"),
        )
    except Exception as exc:
        logger.warning(
            "Gagal menyimpan approval request",
            extra={"job_id": job_id, "run_id": run_id, "error": str(exc)},
        )
        return

    if not baru_dibuat:
        return

    await append_event(
        "approval.request_created",
        {
            "approval_id": approval.get("approval_id"),
            "run_id": run_id,
            "job_id": job_id,
            "job_type": job_type,
            "request_count": len(daftar_request),
        },
    )


async def process_job_event(
    event_data: dict,
    worker_id: str,
    handler_registry: dict,
    tools: dict,
    logger,
    metrics,
) -> bool:
    """Process a single job event from the queue"""
    try:
        # Parse event data
        run_id = event_data["run_id"]
        job_id = event_data["job_id"]
        job_type = event_data["type"]
        inputs = event_data.get("inputs", {})
        attempt = event_data.get("attempt", 0)
        scheduled_at_str = event_data.get("scheduled_at")
        timeout_ms = int(event_data.get("timeout_ms", 30000))

        # Skill resolution
        resolved_job_type = job_type
        skill_payload = None
        if job_type.startswith("skill:"):
            from .skills import get_skill
            skill_id = job_type[6:]
            skill_payload = await get_skill(skill_id)
            if skill_payload:
                resolved_job_type = skill_payload.get("job_type", job_type)
                # Merge default inputs from skill
                default_inputs = skill_payload.get("default_inputs", {})
                if isinstance(default_inputs, dict):
                    merged_inputs = dict(default_inputs)
                    merged_inputs.update(inputs)
                    inputs = merged_inputs

        # Get current run status
        data_run = await get_run(run_id)
        if not data_run:
            data_run = Run(
                run_id=run_id,
                job_id=job_id,
                status=RunStatus.QUEUED,
                attempt=attempt,
                scheduled_at=datetime.fromisoformat(scheduled_at_str) if scheduled_at_str else datetime.now(timezone.utc),
                inputs=inputs,
                trace_id=event_data.get("trace_id"),
                agent_pool=event_data.get("agent_pool"),
            )
        elif not getattr(data_run, "inputs", None):
            data_run.inputs = inputs

        data_run.status = RunStatus.RUNNING
        data_run.started_at = datetime.now(timezone.utc)
        await save_run(data_run)
        await append_event(
            "run.started",
            {"run_id": run_id, "job_id": job_id, "job_type": job_type, "worker_id": worker_id, "attempt": attempt},
        )

        # Get handler for this job type
        handler = handler_registry.get(resolved_job_type)
        if not handler:
            pesan_error = f"No handler registered for job type: {resolved_job_type} (resolved from {job_type})"
            logger.error(pesan_error, extra={"job_id": job_id, "run_id": run_id})
            data_run.status = RunStatus.FAILED
            data_run.result = RunResult(success=False, error=pesan_error)
            data_run.finished_at = datetime.now(timezone.utc)
            await save_run(data_run)
            await _record_failure_memory(
                job_id=job_id,
                inputs=inputs,
                success=False,
                error=pesan_error,
            )
            await append_event(
                "run.failed",
                {"run_id": run_id, "job_id": job_id, "job_type": job_type, "error": pesan_error, "attempt": attempt},
            )
            return False

        # Apply Policy Manager
        from .registry import policy_manager
        allowed_tools = {}
        skill_tool_allowlist = set(skill_payload.get("tool_allowlist", [])) if skill_payload else set()
        
        for tool_name, tool_instance in tools.items():
            # 1. Check global policy
            if not policy_manager.is_tool_allowed(resolved_job_type, tool_name):
                continue
            # 2. Check skill-specific policy if defined
            if skill_tool_allowlist and tool_name not in skill_tool_allowlist:
                continue
            allowed_tools[tool_name] = tool_instance

        # Approval Gate Verification (if skill requires approval)
        if skill_payload and skill_payload.get("require_approval", False):
            # Typically approval would be handled at enqueue time, but we can do a runtime check here.
            # Assuming 'approved_run' is injected or we just ensure it's logged
            pass

        # Create context
        ctx = JobContext(
            job_id=job_id,
            run_id=run_id,
            trace_id=event_data.get("trace_id", ""),
            redis_client=redis_client,
            tools=allowed_tools,
            logger=logger,
            metrics=metrics,
            span=None,
            timeout_ms=timeout_ms,
            inputs=inputs,
        )

        # Execute handler
        hasil_run = await execute_job_handler(handler, ctx, inputs)

        # Update run status
        data_run.status = RunStatus.SUCCESS if hasil_run.success else RunStatus.FAILED
        data_run.finished_at = datetime.now(timezone.utc)
        data_run.result = hasil_run

        await save_run(data_run)
        await add_run_to_job_history(job_id, run_id)
        await _coba_simpan_approval_dari_output(
            run_id=run_id,
            job_id=job_id,
            job_type=job_type,
            inputs=inputs,
            hasil_run=hasil_run,
            logger=logger,
        )
        await _record_failure_memory(
            job_id=job_id,
            inputs=inputs,
            success=hasil_run.success,
            error=hasil_run.error,
        )

        await append_event(
            "run.completed" if hasil_run.success else "run.failed",
            {
                "run_id": run_id,
                "job_id": job_id,
                "job_type": job_type,
                "attempt": attempt,
                "duration_ms": hasil_run.duration_ms,
                "error": hasil_run.error,
            },
        )

        # Emit metrics
        if metrics:
            status_label = data_run.status.value if hasattr(data_run.status, "value") else str(data_run.status)
            metrics.increment("job_runs_total", tags={"type": job_type, "status": status_label})
            if hasil_run.duration_ms:
                metrics.observe("job_duration_ms", hasil_run.duration_ms, tags={"type": job_type})

        return hasil_run.success

    except Exception as e:
        logger.error(
            f"Error processing job event: {e}",
            extra={"job_id": event_data.get("job_id"), "run_id": event_data.get("run_id"), "error": str(e)},
        )
        return False


def _ambil_int_dari_inputs(inputs: Dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    raw = inputs.get(key, default)
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


async def _record_failure_memory(
    *,
    job_id: str,
    inputs: Dict[str, Any],
    success: bool,
    error: Optional[str] = None,
) -> None:
    enabled = bool(inputs.get("failure_memory_enabled", True))
    if not enabled:
        return

    threshold = _ambil_int_dari_inputs(inputs, "failure_threshold", default=3, minimum=1, maximum=20)
    cooldown_sec = _ambil_int_dari_inputs(inputs, "failure_cooldown_sec", default=120, minimum=10, maximum=86400)
    cooldown_max_sec = _ambil_int_dari_inputs(
        inputs,
        "failure_cooldown_max_sec",
        default=max(600, cooldown_sec * 4),
        minimum=cooldown_sec,
        maximum=604800,
    )

    try:
        await record_job_outcome(
            job_id,
            success=success,
            error=error,
            failure_threshold=threshold,
            failure_cooldown_sec=cooldown_sec,
            failure_cooldown_max_sec=cooldown_max_sec,
        )
    except Exception:
        return


async def handle_retry(job_id: str, run_id: str, attempt: int, retry_policy: dict, scheduled_at: datetime):
    """Handle job retry logic"""
    batas_retry = int(retry_policy.get("max_retry", 0))
    if attempt >= batas_retry:
        return False  # No more retries

    # Calculate backoff delay
    daftar_backoff_detik = retry_policy.get("backoff_sec", [1, 2, 5])
    jeda_detik = daftar_backoff_detik[min(attempt, len(daftar_backoff_detik) - 1)]

    # Schedule retry
    from .queue import schedule_delayed_job
    from .models import QueueEvent

    # Get current job spec
    from .queue import get_job_spec
    spesifikasi = await get_job_spec(job_id)
    if not spesifikasi:
        return False

    # Create new event for retry
    event_retry = QueueEvent(
        run_id=run_id,
        job_id=job_id,
        type=spesifikasi["type"],
        inputs=spesifikasi.get("inputs", {}),
        attempt=attempt + 1,
        scheduled_at=scheduled_at.isoformat(),
        timeout_ms=int(spesifikasi.get("timeout_ms", 30000)),
        agent_pool=spesifikasi.get("agent_pool"),
        priority=spesifikasi.get("priority", 0),
    )

    await schedule_delayed_job(event_retry, jeda_detik)
    await append_event(
        "run.retry_scheduled",
        {"run_id": run_id, "job_id": job_id, "attempt": attempt + 1, "delay_sec": jeda_detik},
    )
    return True
