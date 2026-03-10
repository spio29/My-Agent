import asyncio
import json
import os
import re
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from redis.exceptions import RedisError, TimeoutError as RedisTimeoutError

from app.core.auth import (
    ROLE_ADMIN,
    extract_auth_token,
    load_auth_config,
    resolve_required_role,
    role_memenuhi,
)
from app.core.audit import (
    AUDIT_EVENT_TYPE,
    build_audit_payload,
    event_to_audit_row,
    is_mutating_method,
)
from app.core.connector_accounts import (
    delete_telegram_account,
    get_telegram_account,
    list_telegram_accounts,
    upsert_telegram_account,
)
from app.core.prospects import (
    create_prospect,
    find_open_prospect_by_contact,
    get_prospect,
    list_prospects,
    mark_prospect_lost,
    mark_prospect_won,
    normalize_prospect_channel,
    update_prospect,
)
from app.core.influencers import (
    get_influencer,
    list_influencers,
    upsert_influencer,
)
from app.core.influencer_templates import (
    ensure_default_templates as ensure_default_influencer_templates,
    get_template as get_influencer_template,
    list_templates as list_influencer_templates,
    upsert_template as upsert_influencer_template,
)
from app.core.agent_memory import (
    build_agent_memory_context,
    delete_agent_memory as hapus_agent_memory,
    list_agent_memories,
)
from app.core.approval_queue import (
    decide_approval_request,
    get_approval_request,
    list_approval_requests,
)
from app.core.integration_configs import (
    delete_integration_account,
    delete_mcp_server,
    get_integration_account,
    get_mcp_server,
    list_integration_accounts,
    list_mcp_servers,
    upsert_integration_account,
    upsert_mcp_server,
)
from app.core.integration_catalog import (
    get_mcp_server_template,
    get_provider_template,
    list_mcp_server_templates,
    list_provider_templates,
)
from app.core.experiments import (
    delete_experiment as hapus_experiment,
    get_experiment,
    list_experiments,
    set_experiment_enabled,
    upsert_experiment,
)
from app.core.models import (
    JobSpec,
    QueueEvent,
    RetryPolicy,
    Run,
    RunStatus,
    Schedule,
    Trigger,
    TriggerPayload,
)
from app.core.skills import (
    delete_skill as hapus_skill,
    get_skill,
    list_skills as list_skill_specs,
    upsert_skill,
)
from app.core.triggers import (
    delete_trigger as hapus_trigger,
    fire_trigger,
    get_trigger,
    list_triggers,
    upsert_trigger,
)
from app.core.observability import expose_metrics, logger
from app.core.queue import (
    add_run_to_job_history,
    append_event,
    enable_job,
    disable_job,
    enqueue_job,
    get_events,
    get_job_run_ids,
    get_job_spec,
    get_job_cooldown_remaining,
    get_job_failure_state,
    get_queue_metrics,
    get_run,
    init_queue,
    is_job_enabled,
    list_enabled_job_ids,
    list_job_specs,
    list_job_spec_versions,
    list_runs,
    rollback_job_spec_to_version,
    save_job_spec,
    save_run,
    set_mode_fallback_redis,
)
from app.core.scheduler import Scheduler
from app.core.redis_client import close_redis, redis_client
from app.core.tools.command import PREFIX_PERINTAH_BAWAAN, normalisasi_daftar_prefix_perintah
from app.services.api.planner import PlannerRequest, PlannerResponse, build_plan_from_prompt
from app.services.api.planner_ai import PlannerAiRequest, build_plan_with_ai_dari_dashboard
from app.services.api.planner_execute import PlannerExecuteRequest, PlannerExecuteResponse, execute_prompt_plan
from app.services.worker.main import worker_main


def _load_cors_allowed_origins() -> List[str]:
    default_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5178",
        "http://127.0.0.1:5178",
    ]

    raw = str(os.getenv("CORS_ALLOW_ORIGINS") or "").strip()
    if not raw:
        return default_origins
    if raw == "*":
        return ["*"]

    origins: List[str] = []
    sudah = set()
    for item in raw.split(","):
        origin = str(item or "").strip().rstrip("/")
        if not origin:
            continue
        key = origin.lower()
        if key in sudah:
            continue
        sudah.add(key)
        origins.append(origin)

    return origins or default_origins


app = FastAPI(
    title="Multi-Job Platform API",
    description="API for managing and monitoring jobs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_load_cors_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

_AUTH_CONFIG = load_auth_config()


@app.middleware("http")
async def auth_rbac_middleware(request: Request, call_next):
    required_role = resolve_required_role(path=request.url.path, method=request.method)
    if not required_role:
        return await call_next(request)

    if not _AUTH_CONFIG.enabled:
        request.state.auth = {
            "enabled": False,
            "role": ROLE_ADMIN,
            "subject": "auth-disabled",
        }
        try:
            response = await call_next(request)
        except Exception as exc:
            await _catat_audit_api(
                request,
                required_role=required_role,
                status_code=500,
                detail=f"Unhandled exception: {exc}",
            )
            raise

        await _catat_audit_api(
            request,
            required_role=required_role,
            status_code=response.status_code,
            detail="auth disabled",
        )
        return response

    token = extract_auth_token(dict(request.headers), _AUTH_CONFIG.header_name, _AUTH_CONFIG.scheme)
    if not token:
        response = JSONResponse(
            status_code=401,
            content={
                "detail": "Unauthorized: missing auth token.",
                "required_role": required_role,
            },
        )
        await _catat_audit_api(
            request,
            required_role=required_role,
            status_code=401,
            detail="missing auth token",
        )
        return response

    role = _AUTH_CONFIG.token_roles.get(token, "")
    if not role:
        response = JSONResponse(
            status_code=401,
            content={
                "detail": "Unauthorized: invalid auth token.",
                "required_role": required_role,
            },
        )
        await _catat_audit_api(
            request,
            required_role=required_role,
            status_code=401,
            detail="invalid auth token",
        )
        return response

    if not role_memenuhi(required_role, role):
        response = JSONResponse(
            status_code=403,
            content={
                "detail": "Forbidden: role is not allowed for this endpoint.",
                "required_role": required_role,
                "role": role,
            },
        )
        await _catat_audit_api(
            request,
            required_role=required_role,
            status_code=403,
            detail=f"insufficient role: {role}",
        )
        return response

    request.state.auth = {
        "enabled": True,
        "role": role,
        "subject": token[:6] + "***",
    }
    try:
        response = await call_next(request)
    except Exception as exc:
        await _catat_audit_api(
            request,
            required_role=required_role,
            status_code=500,
            detail=f"Unhandled exception: {exc}",
        )
        raise

    await _catat_audit_api(
        request,
        required_role=required_role,
        status_code=response.status_code,
    )
    return response


@app.exception_handler(RedisError)
@app.exception_handler(RedisTimeoutError)
async def redis_exception_handler(request: Request, exc: Exception):
    app.state.redis_ready = False
    set_mode_fallback_redis(True)
    logger.warning("Redis request failed", extra={"path": request.url.path, "error": str(exc)})
    return JSONResponse(
        status_code=503,
        content={"detail": "Redis is unavailable. Service is running in degraded mode."},
    )


def _serialisasi_model(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _sekarang_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _queue_custom_job_run(
    *,
    job_id: str,
    job_type: str,
    inputs: Dict[str, Any],
    timeout_ms: int = 30000,
    agent_pool: Optional[str] = None,
    priority: int = 0,
    source: str = "api.custom",
) -> Dict[str, str]:
    run_id = f"run_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4().hex[:8]}"
    trace_id = f"trace_{uuid.uuid4().hex}"

    data_run = Run(
        run_id=run_id,
        job_id=job_id,
        status=RunStatus.QUEUED,
        attempt=0,
        scheduled_at=datetime.now(timezone.utc),
        inputs=inputs,
        trace_id=trace_id,
        agent_pool=agent_pool,
    )
    await save_run(data_run)
    await add_run_to_job_history(job_id, run_id)

    event_antrean = QueueEvent(
        run_id=run_id,
        job_id=job_id,
        type=job_type,
        inputs=inputs,
        attempt=0,
        scheduled_at=_sekarang_iso(),
        timeout_ms=int(timeout_ms),
        trace_id=trace_id,
        agent_pool=agent_pool,
        priority=int(priority),
    )
    await enqueue_job(event_antrean)
    await append_event(
        "run.queued",
        {"run_id": run_id, "job_id": job_id, "job_type": job_type, "source": source},
    )
    return {"run_id": run_id, "job_id": job_id, "status": "queued"}


def _fallback_payload(endpoint: str, payload: Any) -> Any:
    logger.warning("Serving degraded fallback payload", extra={"endpoint": endpoint})
    return payload


def _merge_config_defaults(existing: Dict[str, Any], defaults: Dict[str, Any], overwrite: bool) -> Dict[str, Any]:
    merged = dict(existing) if isinstance(existing, dict) else {}
    for key, value in defaults.items():
        if overwrite or key not in merged:
            merged[key] = value
    return merged


_SLUG_RE = re.compile(r"[^a-z0-9]+")
_TEMPLATE_TOKEN_RE = re.compile(r"{([a-zA-Z0-9_]+)}")


def _slugify_text(value: str, fallback: str = "influencer") -> str:
    normalized = _SLUG_RE.sub("-", str(value or "").strip().lower()).strip("-")
    return normalized or fallback


def _normalize_clone_channels(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    rows: Dict[str, str] = {}
    for key, value in raw.items():
        channel = str(key or "").strip().lower()
        target = str(value or "").strip()
        if not channel or not target:
            continue
        rows[channel] = target
    return rows


def _render_template_text(text: str, context: Dict[str, Any]) -> str:
    def _replace(match: re.Match[str]) -> str:
        key = str(match.group(1) or "").strip()
        value = context.get(key)
        if value is None:
            return match.group(0)
        return str(value)

    return _TEMPLATE_TOKEN_RE.sub(_replace, str(text))


def _render_template_payload(value: Any, context: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _render_template_text(value, context)
    if isinstance(value, list):
        return [_render_template_payload(item, context) for item in value]
    if isinstance(value, dict):
        rendered: Dict[str, Any] = {}
        for key, item in value.items():
            rendered[str(key)] = _render_template_payload(item, context)
        return rendered
    return value


def _resolve_followup_account_id(job_type: str, inputs: Dict[str, Any]) -> str:
    if str(job_type or "").strip() != "sales.followup":
        return ""
    if not isinstance(inputs, dict):
        return ""
    return str(inputs.get("account_id") or "").strip()


async def _can_enable_cloned_job(job_type: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    account_id = _resolve_followup_account_id(job_type, inputs)
    if not account_id:
        return {"ok": True, "reason": ""}

    account = await get_telegram_account(account_id, include_secret=False)
    if not account:
        return {"ok": False, "reason": f"connector_account_not_found:{account_id}"}

    if not bool(account.get("enabled", False)):
        return {"ok": False, "reason": f"connector_account_disabled:{account_id}"}

    if not bool(account.get("has_bot_token", False)):
        return {"ok": False, "reason": f"connector_bot_token_missing:{account_id}"}

    return {"ok": True, "reason": ""}


async def _is_redis_ready() -> bool:
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=0.5)
        return True
    except Exception:
        return False


def _local_agents_snapshot() -> List[Dict[str, Any]]:
    sekarang = _sekarang_iso()
    rows: List[Dict[str, Any]] = []

    worker_task = getattr(app.state, "local_worker_task", None)
    scheduler_task = getattr(app.state, "local_scheduler_task", None)

    if worker_task:
        rows.append(
            {
                "id": "local-worker",
                "type": "worker",
                "status": "offline" if worker_task.done() else "online",
                "last_heartbeat": sekarang,
                "last_heartbeat_at": sekarang,
                "active_sessions": 1 if not worker_task.done() else 0,
                "version": "local-fallback",
            }
        )

    if scheduler_task:
        rows.append(
            {
                "id": "local-scheduler",
                "type": "scheduler",
                "status": "offline" if scheduler_task.done() else "online",
                "last_heartbeat": sekarang,
                "last_heartbeat_at": sekarang,
                "active_sessions": 1 if not scheduler_task.done() else 0,
                "version": "local-fallback",
            }
        )

    return rows


async def _catat_audit_api(
    request: Request,
    *,
    required_role: str,
    status_code: int,
    detail: str = "",
) -> None:
    if not is_mutating_method(request.method) and int(status_code) not in {401, 403}:
        return

    client_ip = ""
    if request.client and request.client.host:
        client_ip = str(request.client.host)

    payload = build_audit_payload(
        method=request.method,
        path=request.url.path,
        status_code=status_code,
        required_role=required_role,
        auth_ctx=getattr(request.state, "auth", None),
        query=request.url.query or "",
        detail=detail,
        client_ip=client_ip,
    )
    with suppress(Exception):
        await append_event(AUDIT_EVENT_TYPE, payload)


class TelegramConnectorAccountUpsert(BaseModel):
    bot_token: Optional[str] = None
    allowed_chat_ids: List[str] = Field(default_factory=list)
    enabled: bool = True
    use_ai: bool = True
    force_rule_based: bool = False
    run_immediately: bool = True
    wait_seconds: int = Field(default=2, ge=0, le=30)
    timezone: str = "Asia/Jakarta"
    default_channel: str = "telegram"
    default_account_id: str = "default"
    default_branch_id: str = "br_01"
    capture_inbound_text: bool = False
    inbound_auto_followup: bool = True
    inbound_followup_template: str = ""


class TelegramConnectorAccountView(BaseModel):
    account_id: str
    enabled: bool = True
    has_bot_token: bool = False
    bot_token_masked: Optional[str] = None
    allowed_chat_ids: List[str] = Field(default_factory=list)
    use_ai: bool = True
    force_rule_based: bool = False
    run_immediately: bool = True
    wait_seconds: int = 2
    timezone: str = "Asia/Jakarta"
    default_channel: str = "telegram"
    default_account_id: str = "default"
    default_branch_id: str = "br_01"
    capture_inbound_text: bool = False
    inbound_auto_followup: bool = True
    inbound_followup_template: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProspectCreateRequest(BaseModel):
    branch_id: str
    name: str
    channel: str
    contact_id: str
    source: str = ""
    offer: str = ""
    owner: str = ""
    value_estimate: float = 0
    stage: str = "new"
    notes: str = ""
    tags: List[str] = Field(default_factory=list)
    next_followup_at: Optional[str] = None


class ProspectUpdateRequest(BaseModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    contact_id: Optional[str] = None
    source: Optional[str] = None
    offer: Optional[str] = None
    owner: Optional[str] = None
    value_estimate: Optional[float] = None
    stage: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    next_followup_at: Optional[str] = None


class ProspectCloseWonRequest(BaseModel):
    amount: float = Field(gt=0)
    leads_delta: int = Field(default=0, ge=0, le=100000)
    closings_delta: int = Field(default=1, ge=1, le=100000)
    note: str = ""


class ProspectCloseLostRequest(BaseModel):
    reason: str = ""


class SalesFollowupDispatchRequest(BaseModel):
    prospect_id: Optional[str] = None
    branch_id: str = ""
    account_id: str = ""
    template: str = ""
    max_items: int = Field(default=10, ge=1, le=100)
    next_followup_minutes: int = Field(default=1440, ge=10, le=20160)


class SalesFollowupAutomationRequest(BaseModel):
    branch_id: str
    account_id: str = ""
    template: str = ""
    max_items: int = Field(default=10, ge=1, le=100)
    next_followup_minutes: int = Field(default=1440, ge=10, le=20160)
    interval_sec: int = Field(default=600, ge=30, le=86400)


class SalesInboundRequest(BaseModel):
    branch_id: str
    channel: str
    contact_id: str
    name: str = ""
    source: str = ""
    offer: str = ""
    owner: str = ""
    message: str = ""
    value_estimate: float = Field(default=0, ge=0)
    tags: List[str] = Field(default_factory=list)
    stage: str = "new"
    auto_followup: bool = True
    account_id: str = ""
    followup_template: str = ""
    next_followup_minutes: int = Field(default=720, ge=10, le=20160)


class SalesInboundResponse(BaseModel):
    status: str
    action: str
    prospect_id: str
    branch_id: str
    channel: str
    contact_id: str
    followup_queued: bool = False
    run_id: Optional[str] = None


class InfluencerTemplateUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    mode: str = "product"
    description: str = ""
    enabled: bool = True
    default_branch_id: str = "br_01"
    branch_blueprint_id: str = "bp_agency_digital"
    channels_required: List[str] = Field(default_factory=list)
    job_templates: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InfluencerTemplateView(BaseModel):
    template_id: str
    name: str
    mode: str = "product"
    description: str = ""
    enabled: bool = True
    default_branch_id: str = ""
    branch_blueprint_id: str = ""
    channels_required: List[str] = Field(default_factory=list)
    job_templates: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class InfluencerProfileView(BaseModel):
    influencer_id: str
    name: str
    niche: str = ""
    mode: str = "product"
    status: str = "active"
    template_id: str = ""
    branch_id: str = ""
    channels: Dict[str, str] = Field(default_factory=dict)
    offer_name: str = ""
    offer_price: float = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class InfluencerCloneJobView(BaseModel):
    job_id: str
    type: str
    enabled: bool
    status: str


class InfluencerTemplateCloneRequest(BaseModel):
    influencer_id: str = ""
    name: str = Field(min_length=1, max_length=140)
    niche: str = ""
    mode: str = ""
    branch_id: str = ""
    channels: Dict[str, str] = Field(default_factory=dict)
    offer_name: str = ""
    offer_price: float = Field(default=0, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    enable_jobs: bool = True
    overwrite_existing_jobs: bool = True


class InfluencerTemplateCloneResponse(BaseModel):
    template_id: str
    influencer: InfluencerProfileView
    jobs: List[InfluencerCloneJobView] = Field(default_factory=list)
    status: str = "ok"


class InfluencerProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=140)
    niche: Optional[str] = None
    mode: Optional[str] = None
    status: Optional[str] = None
    template_id: Optional[str] = None
    branch_id: Optional[str] = None
    channels: Optional[Dict[str, str]] = None
    offer_name: Optional[str] = None
    offer_price: Optional[float] = Field(default=None, ge=0)
    metadata: Optional[Dict[str, Any]] = None
    apply_template_jobs: bool = False
    enable_jobs: bool = True
    overwrite_existing_jobs: bool = True


class InfluencerProfileUpdateResponse(BaseModel):
    influencer: InfluencerProfileView
    jobs: List[InfluencerCloneJobView] = Field(default_factory=list)
    status: str = "ok"


class McpServerUpsertRequest(BaseModel):
    enabled: bool = True
    transport: str = "stdio"
    description: str = ""
    command: str = ""
    args: List[str] = Field(default_factory=list)
    url: str = ""
    headers: Dict[str, str] = Field(default_factory=dict)
    env: Dict[str, str] = Field(default_factory=dict)
    auth_token: Optional[str] = None
    timeout_sec: int = Field(default=20, ge=1, le=120)


class McpServerView(BaseModel):
    server_id: str
    enabled: bool = True
    transport: str = "stdio"
    description: str = ""
    command: str = ""
    args: List[str] = Field(default_factory=list)
    url: str = ""
    headers: Dict[str, str] = Field(default_factory=dict)
    env: Dict[str, str] = Field(default_factory=dict)
    has_auth_token: bool = False
    auth_token_masked: Optional[str] = None
    timeout_sec: int = 20
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class IntegrationAccountUpsertRequest(BaseModel):
    enabled: bool = True
    secret: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class IntegrationAccountView(BaseModel):
    provider: str
    account_id: str
    enabled: bool = True
    has_secret: bool = False
    secret_masked: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class IntegrationProviderTemplateView(BaseModel):
    provider: str
    label: str
    description: str
    auth_hint: str
    default_account_id: str = "default"
    default_enabled: bool = False
    default_config: Dict[str, Any] = Field(default_factory=dict)


class McpServerTemplateView(BaseModel):
    template_id: str
    server_id: str
    label: str
    description: str
    transport: str
    command: str = ""
    args: List[str] = Field(default_factory=list)
    url: str = ""
    headers: Dict[str, str] = Field(default_factory=dict)
    env: Dict[str, str] = Field(default_factory=dict)
    timeout_sec: int = 20
    default_enabled: bool = False


class IntegrationsCatalogView(BaseModel):
    providers: List[IntegrationProviderTemplateView] = Field(default_factory=list)
    mcp_servers: List[McpServerTemplateView] = Field(default_factory=list)


class IntegrationsBootstrapRequest(BaseModel):
    provider_ids: List[str] = Field(default_factory=list)
    mcp_template_ids: List[str] = Field(default_factory=list)
    account_id: str = "default"
    overwrite: bool = False


class IntegrationsBootstrapResponse(BaseModel):
    account_id: str
    overwrite: bool
    providers_created: List[str] = Field(default_factory=list)
    providers_updated: List[str] = Field(default_factory=list)
    providers_skipped: List[str] = Field(default_factory=list)
    mcp_created: List[str] = Field(default_factory=list)
    mcp_updated: List[str] = Field(default_factory=list)
    mcp_skipped: List[str] = Field(default_factory=list)


class ExperimentUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    job_id: str = ""
    hypothesis: str = ""
    variant_a_name: str = "control"
    variant_b_name: str = "treatment"
    variant_a_prompt: str = ""
    variant_b_prompt: str = ""
    traffic_split_b: int = Field(default=50, ge=0, le=100)
    enabled: bool = False
    tags: List[str] = Field(default_factory=list)
    owner: str = ""
    notes: str = ""


class ExperimentView(BaseModel):
    experiment_id: str
    name: str
    description: str = ""
    job_id: str = ""
    hypothesis: str = ""
    variant_a_name: str = "control"
    variant_b_name: str = "treatment"
    variant_a_prompt: str = ""
    variant_b_prompt: str = ""
    traffic_split_b: int = 50
    enabled: bool = False
    tags: List[str] = Field(default_factory=list)
    owner: str = ""
    notes: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_variant: Optional[str] = None
    last_variant_name: str = ""
    last_variant_bucket: Optional[int] = None
    last_variant_run_at: Optional[str] = None


class ExperimentEnabledRequest(BaseModel):
    enabled: bool


class TriggerUpsertRequest(TriggerPayload):
    name: str = Field(min_length=1, max_length=120)
    job_id: str
    channel: str

class TriggerView(Trigger):
    secret_present: bool = False


class TriggerFireRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    source: str = "api.trigger"


class TriggerFireResponse(BaseModel):
    trigger_id: str
    job_id: str
    message_id: str
    run_id: str
    channel: str
    source: str


class ConnectorWebhookRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)


class ConnectorTelegramRequest(BaseModel):
    chat_id: str
    text: str
    username: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
class ConnectorSlackRequest(BaseModel):
    channel_id: str
    user_id: str
    command: str
    text: str
    response_url: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class ConnectorSmsRequest(BaseModel):
    phone_number: str
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)

class ConnectorEmailRequest(BaseModel):
    sender: str
    subject: str
    body: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ConnectorVoiceRequest(BaseModel):
    caller: str
    transcript: str
    call_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class RateLimitConfig(BaseModel):
    max_runs: int = Field(default=0, ge=0)
    window_sec: int = Field(default=60, ge=1)

class SkillSpecRequest(BaseModel):
    skill_id: str = Field(min_length=1, max_length=64)
    name: str
    job_type: str
    description: str = ""
    version: str = "1.0.0"
    runbook: str = ""
    source: str = ""
    default_inputs: Dict[str, Any] = Field(default_factory=dict)
    command_allow_prefixes: List[str] = Field(default_factory=list)
    allowed_channels: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    tool_allowlist: List[str] = Field(default_factory=list)
    required_secrets: List[str] = Field(default_factory=list)
    rate_limit: Optional[RateLimitConfig] = None
    allow_sensitive_commands: bool = False
    require_approval: bool = False


class SkillView(SkillSpecRequest):
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SkillSyncRequest(BaseModel):
    skills: List[SkillSpecRequest] = Field(default_factory=list)


class AgentWorkflowAutomationRequest(BaseModel):
    job_id: str
    prompt: str
    interval_sec: Optional[int] = Field(default=None, ge=10, le=86400)
    cron: Optional[str] = None
    enabled: bool = True
    timezone: str = "Asia/Jakarta"
    default_channel: str = "telegram"
    default_account_id: str = "default"
    flow_group: str = Field(default="default", min_length=1, max_length=64, pattern="^[a-zA-Z0-9._:-]+$")
    flow_max_active_runs: int = Field(default=10, ge=1, le=1000)
    require_approval_for_missing: bool = True
    allow_overlap: bool = False
    pressure_priority: str = Field(default="normal", pattern="^(critical|normal|low)$")
    dispatch_jitter_sec: int = Field(default=0, ge=0, le=3600)
    failure_threshold: int = Field(default=3, ge=1, le=20)
    failure_cooldown_sec: int = Field(default=120, ge=10, le=86400)
    failure_cooldown_max_sec: int = Field(default=3600, ge=10, le=604800)
    failure_memory_enabled: bool = True
    command_allow_prefixes: List[str] = Field(default_factory=lambda: list(PREFIX_PERINTAH_BAWAAN))
    allow_sensitive_commands: bool = False
    timeout_ms: int = Field(default=90000, ge=5000, le=300000)
    max_retry: int = Field(default=1, ge=0, le=10)
    backoff_sec: List[int] = Field(default_factory=lambda: [2, 5])


class ApprovalRequestView(BaseModel):
    approval_id: str
    status: str
    source: str
    run_id: str
    job_id: str
    job_type: str
    prompt: str
    summary: str
    request_count: int
    approval_requests: List[Dict[str, Any]] = Field(default_factory=list)
    available_providers: Dict[str, Any] = Field(default_factory=dict)
    available_mcp_servers: List[Any] = Field(default_factory=list)
    command_allow_prefixes_requested: List[str] = Field(default_factory=list)
    command_allow_prefixes_rejected: List[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    decided_at: Optional[str] = None
    decision_by: Optional[str] = None
    decision_note: Optional[str] = None


class AuditLogView(BaseModel):
    id: str
    timestamp: str
    method: str
    path: str
    status_code: int
    outcome: str
    required_role: str = ""
    actor_role: str = ""
    actor_subject: str = ""
    auth_enabled: bool = False
    query: str = ""
    detail: str = ""
    client_ip: str = ""


class ApprovalDecisionRequest(BaseModel):
    decision_by: Optional[str] = None
    decision_note: Optional[str] = None


class JobMemoryView(BaseModel):
    job_id: str
    consecutive_failures: int
    cooldown_until: Optional[str] = None
    cooldown_remaining_sec: int
    last_error: Optional[str] = None
    last_failure_at: Optional[str] = None
    last_success_at: Optional[str] = None
    updated_at: str


class JobSpecVersionView(BaseModel):
    version_id: str
    job_id: str
    created_at: str
    source: str = ""
    actor: str = ""
    note: str = ""
    spec: Dict[str, Any] = Field(default_factory=dict)


class JobRollbackResponse(BaseModel):
    job_id: str
    status: str
    rolled_back_to_version_id: str
    enabled: bool
    spec: Dict[str, Any] = Field(default_factory=dict)


class AgentMemoryFailureView(BaseModel):
    at: str
    signature: str
    error: str

class AgentMemoryEpisodicView(BaseModel):
    timestamp: str
    type: str
    description: str
    context: Dict[str, Any] = Field(default_factory=dict)

class AgentMemoryView(BaseModel):
    agent_key: str
    total_runs: int
    success_runs: int
    failed_runs: int
    success_rate: float
    last_error: str
    last_summary: str
    avoid_signatures: List[str] = Field(default_factory=list)
    top_failure_signatures: List[str] = Field(default_factory=list)
    recent_failures: List[AgentMemoryFailureView] = Field(default_factory=list)
    episodic_events: List[AgentMemoryEpisodicView] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    updated_at: str


class AgentMemoryResetView(BaseModel):
    agent_key: str
    deleted: bool
    status: str


async def _start_local_runtime():
    if getattr(app.state, "local_mode", False):
        return

    scheduler = Scheduler()
    app.state.local_scheduler = scheduler
    app.state.local_worker_task = asyncio.create_task(worker_main(), name="local-worker")
    app.state.local_scheduler_task = asyncio.create_task(scheduler.start(), name="local-scheduler")
    app.state.local_mode = True

    await append_event(
        "system.local_mode_enabled",
        {"message": "Redis unavailable; local worker and scheduler enabled"},
    )


async def _stop_local_runtime():
    scheduler = getattr(app.state, "local_scheduler", None)
    if scheduler:
        with suppress(Exception):
            await scheduler.stop()

    for attr in ("local_worker_task", "local_scheduler_task"):
        task = getattr(app.state, attr, None)
        if task and not task.done():
            task.cancel()

    for attr in ("local_worker_task", "local_scheduler_task"):
        task = getattr(app.state, attr, None)
        if task:
            with suppress(asyncio.CancelledError, Exception):
                await task


@app.on_event("startup")
async def on_startup():
    app.state.local_mode = False
    app.state.local_scheduler = None
    app.state.local_worker_task = None
    app.state.local_scheduler_task = None

    redis_ready = await _is_redis_ready()
    app.state.redis_ready = redis_ready
    set_mode_fallback_redis(not redis_ready)

    if redis_ready:
        await init_queue()

    with suppress(Exception):
        await ensure_default_influencer_templates()

    await append_event("system.api_started", {"message": "API service started", "redis_ready": redis_ready})
    if not redis_ready:
        await _start_local_runtime()


@app.on_event("shutdown")
async def on_shutdown():
    await _stop_local_runtime()
    await close_redis()


@app.get("/healthz")
async def healthz():
    return {"status": "healthy"}


@app.head("/healthz")
async def healthz_head():
    return Response(status_code=200)


@app.get("/readyz")
async def readyz():
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=0.5)
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service not ready: {str(e)}")


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(expose_metrics(), media_type="text/plain; version=0.0.4")


@app.get("/auth/me")
async def auth_me(request: Request):
    auth_ctx = getattr(request.state, "auth", None)
    if not isinstance(auth_ctx, dict):
        return {"enabled": False, "role": "unknown", "subject": "n/a"}
    return auth_ctx


@app.post("/planner/plan", response_model=PlannerResponse)
async def planner_plan(request: PlannerRequest):
    rencana = build_plan_from_prompt(request)

    with suppress(Exception):
        await append_event(
            "planner.plan_generated",
            {
                "message": "Prompt converted into job plan",
                "job_count": len(rencana.jobs),
            },
        )

    return rencana


@app.post("/planner/plan-ai", response_model=PlannerResponse)
async def planner_plan_ai(request: PlannerAiRequest):
    rencana = await build_plan_with_ai_dari_dashboard(request)

    with suppress(Exception):
        await append_event(
            "planner.ai_plan_generated",
            {
                "message": "Prompt processed with planner AI mode",
                "job_count": len(rencana.jobs),
                "planner_source": rencana.planner_source,
            },
        )

    return rencana


@app.post("/planner/execute", response_model=PlannerExecuteResponse)
async def planner_execute(request: PlannerExecuteRequest):
    eksekusi = await execute_prompt_plan(request)

    with suppress(Exception):
        await append_event(
            "planner.execute_completed",
            {
                "message": "Prompt planned and executed",
                "planner_source": eksekusi.planner_source,
                "result_count": len(eksekusi.results),
            },
        )

    return eksekusi


@app.post("/jobs")
async def create_job(job_spec: JobSpec):
    spesifikasi = _serialisasi_model(job_spec)
    await save_job_spec(job_spec.job_id, spesifikasi, source="api.jobs.create")
    await enable_job(job_spec.job_id)
    await append_event(
        "job.created",
        {"job_id": job_spec.job_id, "job_type": job_spec.type, "message": "Job created and enabled"},
    )
    logger.info("Job created", extra={"job_id": job_spec.job_id, "type": job_spec.type})
    return {"job_id": job_spec.job_id, "status": "created"}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    spec = await get_job_spec(job_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Job not found")
    spec["enabled"] = await is_job_enabled(job_id)
    return spec


@app.get("/jobs/{job_id}/versions", response_model=List[JobSpecVersionView])
async def get_job_versions(job_id: str, limit: int = Query(default=20, ge=1, le=200)):
    spec = await get_job_spec(job_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Job not found")
    return await list_job_spec_versions(job_id, limit=limit)


@app.post("/jobs/{job_id}/rollback/{version_id}", response_model=JobRollbackResponse)
async def rollback_job(job_id: str, version_id: str, request: Request):
    spec = await get_job_spec(job_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Job not found")

    auth_ctx = getattr(request.state, "auth", {})
    actor = ""
    if isinstance(auth_ctx, dict):
        actor = str(auth_ctx.get("subject") or auth_ctx.get("role") or "").strip()

    restored = await rollback_job_spec_to_version(
        job_id,
        version_id,
        source="api.rollback",
        actor=actor,
        note=f"manual rollback to {version_id}",
    )
    if not restored:
        raise HTTPException(status_code=404, detail="Job version not found")

    enabled = await is_job_enabled(job_id)
    with suppress(Exception):
        await append_event(
            "job.rolled_back",
            {
                "job_id": job_id,
                "version_id": version_id,
                "enabled": enabled,
                "actor": actor,
            },
        )

    restored_payload = dict(restored)
    restored_payload["enabled"] = enabled
    return {
        "job_id": job_id,
        "status": "rolled_back",
        "rolled_back_to_version_id": version_id,
        "enabled": enabled,
        "spec": restored_payload,
    }


@app.get("/jobs/{job_id}/memory", response_model=JobMemoryView)
async def get_job_memory(job_id: str):
    spec = await get_job_spec(job_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Job not found")

    memory = await get_job_failure_state(job_id)
    cooldown_remaining = await get_job_cooldown_remaining(job_id)
    return {
        "job_id": job_id,
        "consecutive_failures": int(memory.get("consecutive_failures") or 0),
        "cooldown_until": memory.get("cooldown_until"),
        "cooldown_remaining_sec": cooldown_remaining,
        "last_error": memory.get("last_error"),
        "last_failure_at": memory.get("last_failure_at"),
        "last_success_at": memory.get("last_success_at"),
        "updated_at": str(memory.get("updated_at") or _sekarang_iso()),
    }


@app.put("/jobs/{job_id}/enable")
async def enable_job_endpoint(job_id: str):
    spec = await get_job_spec(job_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Job not found")
    await enable_job(job_id)
    await append_event("job.enabled", {"job_id": job_id, "message": "Job enabled"})
    return {"job_id": job_id, "status": "enabled"}


@app.put("/jobs/{job_id}/disable")
async def disable_job_endpoint(job_id: str):
    spec = await get_job_spec(job_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Job not found")
    await disable_job(job_id)
    await append_event("job.disabled", {"job_id": job_id, "message": "Job disabled"})
    return {"job_id": job_id, "status": "disabled"}


@app.post("/jobs/{job_id}/run")
async def trigger_job(job_id: str):
    spesifikasi = await get_job_spec(job_id)
    if not spesifikasi:
        raise HTTPException(status_code=404, detail="Job not found")

    run_id = f"run_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4().hex[:8]}"
    trace_id = f"trace_{uuid.uuid4().hex}"

    data_run = Run(
        run_id=run_id,
        job_id=job_id,
        status=RunStatus.QUEUED,
        attempt=0,
        scheduled_at=datetime.now(timezone.utc),
        inputs=spesifikasi.get("inputs", {}),
        trace_id=trace_id,
        agent_pool=spesifikasi.get("agent_pool"),
    )
    await save_run(data_run)
    await add_run_to_job_history(job_id, run_id)

    event_antrean = QueueEvent(
        run_id=run_id,
        job_id=job_id,
        type=spesifikasi["type"],
        inputs=spesifikasi.get("inputs", {}),
        attempt=0,
        scheduled_at=_sekarang_iso(),
        timeout_ms=int(spesifikasi.get("timeout_ms", 30000)),
        trace_id=trace_id,
        agent_pool=spesifikasi.get("agent_pool"),
        priority=int(spesifikasi.get("priority", 0) or 0),
    )
    await enqueue_job(event_antrean)
    await append_event(
        "run.queued",
        {"run_id": run_id, "job_id": job_id, "job_type": spesifikasi["type"], "source": "manual"},
    )

    return {"run_id": run_id, "job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}/runs")
async def get_job_runs(job_id: str, limit: int = 20):
    try:
        run_ids = await get_job_run_ids(job_id, limit)
        runs: List[Dict[str, Any]] = []
        for run_id in run_ids:
            run = await get_run(run_id)
            if run:
                runs.append(_serialisasi_model(run))
        return runs
    except RedisError:
        return _fallback_payload("/jobs/{job_id}/runs", [])


@app.get("/jobs")
async def list_jobs(
    search: Optional[str] = Query(default=None, max_length=120),
    enabled: Optional[bool] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    try:
        specs = await list_job_specs()
        enabled_ids = set(await list_enabled_job_ids())

        jobs: List[Dict[str, Any]] = []
        for spec in specs:
            job = dict(spec)
            job["enabled"] = spec.get("job_id") in enabled_ids
            jobs.append(job)

        jobs.sort(key=lambda job: job.get("job_id", ""))
        query_search = str(search or "").strip().lower()
        if query_search:
            jobs = [
                job
                for job in jobs
                if query_search in str(job.get("job_id") or "").lower()
                or query_search in str(job.get("type") or "").lower()
            ]

        if enabled is not None:
            jobs = [job for job in jobs if bool(job.get("enabled")) == enabled]

        if offset:
            jobs = jobs[offset:]
        if len(jobs) > limit:
            jobs = jobs[:limit]
        return jobs
    except RedisError:
        return _fallback_payload("/jobs", [])


@app.get("/automation/agent-workflows")
async def list_agent_workflow_jobs():
    try:
        specs = await list_job_specs()
        enabled_ids = set(await list_enabled_job_ids())
    except RedisError:
        return _fallback_payload("/automation/agent-workflows", [])

    rows: List[Dict[str, Any]] = []
    for spec in specs:
        if str(spec.get("type") or "") != "agent.workflow":
            continue
        row = dict(spec)
        row["enabled"] = spec.get("job_id") in enabled_ids
        rows.append(row)
    rows.sort(key=lambda row: row.get("job_id", ""))
    return rows


@app.post("/automation/agent-workflow")
async def upsert_agent_workflow_job(request: AgentWorkflowAutomationRequest):
    job_id = request.job_id.strip()
    prompt = request.prompt.strip()

    if not job_id:
        raise HTTPException(status_code=400, detail="job_id wajib diisi.")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt wajib diisi.")

    cron = (request.cron or "").strip() or None
    interval_sec = request.interval_sec

    if cron and interval_sec:
        raise HTTPException(status_code=400, detail="Pilih salah satu jadwal: interval_sec atau cron.")
    if not cron and not interval_sec:
        interval_sec = 900

    jadwal = Schedule(cron=cron, interval_sec=interval_sec)
    retry_policy = RetryPolicy(max_retry=request.max_retry, backoff_sec=list(request.backoff_sec))
    flow_group = request.flow_group.strip() or "default"
    command_allow_prefixes = normalisasi_daftar_prefix_perintah(request.command_allow_prefixes)
    if not command_allow_prefixes:
        command_allow_prefixes = list(PREFIX_PERINTAH_BAWAAN)
    spesifikasi = JobSpec(
        job_id=job_id,
        type="agent.workflow",
        schedule=jadwal,
        timeout_ms=request.timeout_ms,
        retry_policy=retry_policy,
        inputs={
            "prompt": prompt,
            "timezone": request.timezone.strip() or "Asia/Jakarta",
            "default_channel": request.default_channel.strip() or "telegram",
            "default_account_id": request.default_account_id.strip() or "default",
            "flow_group": flow_group,
            "flow_max_active_runs": request.flow_max_active_runs,
            "require_approval_for_missing": request.require_approval_for_missing,
            "allow_overlap": request.allow_overlap,
            "pressure_priority": request.pressure_priority,
            "dispatch_jitter_sec": request.dispatch_jitter_sec,
            "failure_threshold": request.failure_threshold,
            "failure_cooldown_sec": request.failure_cooldown_sec,
            "failure_cooldown_max_sec": request.failure_cooldown_max_sec,
            "failure_memory_enabled": request.failure_memory_enabled,
            "command_allow_prefixes": command_allow_prefixes,
            "allow_sensitive_commands": request.allow_sensitive_commands,
        },
    )

    payload_spesifikasi = _serialisasi_model(spesifikasi)
    sudah_ada = await get_job_spec(job_id) is not None
    await save_job_spec(job_id, payload_spesifikasi, source="api.automation.upsert")
    if request.enabled:
        await enable_job(job_id)
    else:
        await disable_job(job_id)

    await append_event(
        "automation.agent_workflow_saved",
        {
            "job_id": job_id,
            "enabled": request.enabled,
            "schedule": _serialisasi_model(jadwal),
            "status": "updated" if sudah_ada else "created",
        },
    )

    result = dict(payload_spesifikasi)
    result["enabled"] = request.enabled
    result["status"] = "updated" if sudah_ada else "created"
    return result


@app.get("/approvals", response_model=List[ApprovalRequestView])
async def list_approvals(
    status: Optional[str] = Query(default=None, pattern="^(pending|approved|rejected)$"),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return await list_approval_requests(status=status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/approvals/{approval_id}", response_model=ApprovalRequestView)
async def get_approval(approval_id: str):
    row = await get_approval_request(approval_id)
    if not row:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return row


@app.post("/approvals/{approval_id}/approve", response_model=ApprovalRequestView)
async def approve_approval(approval_id: str, request: ApprovalDecisionRequest):
    try:
        row = await decide_approval_request(
            approval_id,
            status="approved",
            decision_by=request.decision_by,
            decision_note=request.decision_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not row:
        raise HTTPException(status_code=404, detail="Approval request not found")

    await append_event(
        "approval.request_approved",
        {
            "approval_id": row.get("approval_id"),
            "run_id": row.get("run_id"),
            "job_id": row.get("job_id"),
            "decision_by": row.get("decision_by"),
        },
    )

    # Auto-provisioning logic for Discovery Proposals (Phase 14 - Holding Structure)
    approval_requests = row.get("approval_requests", [])
    if any(req.get("kind") == "discovery_approval" for req in approval_requests):
        details = row.get("details", {})
        title = details.get("title", "New Unit")
        # Extract blueprint_id from details, default to agency if not specified
        blueprint_id = details.get("blueprint_id", "bp_agency_digital")
        
        from app.core.branches import create_branch, get_blueprint
        from app.core.queue import save_job_spec, enable_job
        import uuid
        
        try:
            # 1. Create the Branch
            branch = await create_branch(name=title, blueprint_id=blueprint_id)
            branch_id = branch["branch_id"]
            blueprint = await get_blueprint(blueprint_id)
            
            squad_ids = {}
            
            # 2. Deploy the Squad (Hunter, Marketer, Closer)
            for job_config in blueprint.get("default_jobs", []):
                role = job_config["role"]
                new_job_id = f"job_{role}_{uuid.uuid4().hex[:6]}"
                
                new_spec = {
                    "job_id": new_job_id,
                    "type": "agent.workflow",
                    "schedule": {"interval_sec": 86400},
                    "inputs": {
                        "prompt": f"Unit: {title} | Role: {role.upper()}. Goal: {job_config['prompt']}",
                        "agent_key": f"{role}:{branch_id}",
                        "flow_group": branch_id, # Isolation by branch_id
                        "branch_id": branch_id,
                        "allow_sensitive_commands": False
                    }
                }
                await save_job_spec(new_job_id, new_spec)
                await enable_job(new_job_id)
                squad_ids[f"{role}_job_id"] = new_job_id
            
            # 3. Update Branch with Squad info
            from app.core.redis_client import redis_client
            branch["squad"] = squad_ids
            await redis_client.set(f"branch:item:{branch_id}", json.dumps(branch))
            
            await append_event(
                "system.branch_opened",
                {"branch_id": branch_id, "name": title, "blueprint": blueprint_id}
            )
        except Exception as e:
            # Log error but don't block
            await append_event("system.error", {"message": f"Auto-provisioning failed: {str(e)}"})

    return row


@app.post("/approvals/{approval_id}/reject", response_model=ApprovalRequestView)
async def reject_approval(approval_id: str, request: ApprovalDecisionRequest):
    try:
        row = await decide_approval_request(
            approval_id,
            status="rejected",
            decision_by=request.decision_by,
            decision_note=request.decision_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not row:
        raise HTTPException(status_code=404, detail="Approval request not found")

    await append_event(
        "approval.request_rejected",
        {
            "approval_id": row.get("approval_id"),
            "run_id": row.get("run_id"),
            "job_id": row.get("job_id"),
            "decision_by": row.get("decision_by"),
        },
    )
    return row


@app.get("/queue")
async def queue_metrics():
    try:
        return await get_queue_metrics()
    except RedisError:
        return _fallback_payload("/queue", {"depth": 0, "delayed": 0})


@app.get("/connector/telegram/accounts", response_model=List[TelegramConnectorAccountView])
async def list_telegram_connector_accounts():
    return await list_telegram_accounts(include_secret=False)


@app.get("/connector/telegram/accounts/{account_id}", response_model=TelegramConnectorAccountView)
async def get_telegram_connector_account(account_id: str):
    row = await get_telegram_account(account_id, include_secret=False)
    if not row:
        raise HTTPException(status_code=404, detail="Telegram account not found")
    return row


@app.put("/connector/telegram/accounts/{account_id}", response_model=TelegramConnectorAccountView)
async def upsert_telegram_connector_account(account_id: str, request: TelegramConnectorAccountUpsert):
    try:
        row = await upsert_telegram_account(account_id, request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await append_event(
        "connector.telegram.account_upserted",
        {
            "account_id": account_id,
            "enabled": row.get("enabled", True),
            "has_bot_token": row.get("has_bot_token", False),
        },
    )

    return row

@app.delete("/connector/telegram/accounts/{account_id}")
async def delete_telegram_connector_account(account_id: str):
    removed = await delete_telegram_account(account_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Telegram account not found")

    await append_event(
        "connector.telegram.account_deleted",
        {"account_id": account_id},
    )

    return {"account_id": account_id, "status": "deleted"}


@app.get("/integrations/mcp/servers", response_model=List[McpServerView])
async def list_mcp_integration_servers():
    return await list_mcp_servers(include_secret=False)


@app.get("/integrations/mcp/servers/{server_id}", response_model=McpServerView)
async def get_mcp_integration_server(server_id: str):
    row = await get_mcp_server(server_id, include_secret=False)
    if not row:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return row


@app.put("/integrations/mcp/servers/{server_id}", response_model=McpServerView)
async def upsert_mcp_integration_server(server_id: str, request: McpServerUpsertRequest):
    try:
        row = await upsert_mcp_server(server_id, request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await append_event(
        "integration.mcp_server_upserted",
        {
            "server_id": server_id,
            "enabled": row.get("enabled", True),
            "transport": row.get("transport", "stdio"),
        },
    )

    return row


@app.delete("/integrations/mcp/servers/{server_id}")
async def delete_mcp_integration_server(server_id: str):
    removed = await delete_mcp_server(server_id)
    if not removed:
        raise HTTPException(status_code=404, detail="MCP server not found")

    await append_event("integration.mcp_server_deleted", {"server_id": server_id})
    return {"server_id": server_id, "status": "deleted"}


@app.get("/integrations/accounts", response_model=List[IntegrationAccountView])
async def list_integration_accounts_endpoint(provider: Optional[str] = None):
    try:
        return await list_integration_accounts(provider=provider, include_secret=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/integrations/accounts/{provider}/{account_id}", response_model=IntegrationAccountView)
async def get_integration_account_endpoint(provider: str, account_id: str):
    try:
        row = await get_integration_account(provider, account_id, include_secret=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not row:
        raise HTTPException(status_code=404, detail="Integration account not found")
    return row


@app.put("/integrations/accounts/{provider}/{account_id}", response_model=IntegrationAccountView)
async def upsert_integration_account_endpoint(
    provider: str,
    account_id: str,
    request: IntegrationAccountUpsertRequest,
):
    try:
        row = await upsert_integration_account(provider, account_id, request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await append_event(
        "integration.account_upserted",
        {"provider": row.get("provider"), "account_id": row.get("account_id"), "enabled": row.get("enabled", True)},
    )
    return row


@app.delete("/integrations/accounts/{provider}/{account_id}")
async def delete_integration_account_endpoint(provider: str, account_id: str):
    try:
        removed = await delete_integration_account(provider, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not removed:
        raise HTTPException(status_code=404, detail="Integration account not found")

    await append_event("integration.account_deleted", {"provider": provider, "account_id": account_id})
    return {"provider": provider, "account_id": account_id, "status": "deleted"}


@app.get("/integrations/catalog", response_model=IntegrationsCatalogView)
async def get_integrations_catalog():
    return {
        "providers": list_provider_templates(),
        "mcp_servers": list_mcp_server_templates(),
    }


@app.post("/integrations/catalog/bootstrap", response_model=IntegrationsBootstrapResponse)
async def bootstrap_integrations_catalog(request: IntegrationsBootstrapRequest):
    account_id = request.account_id.strip() or "default"

    selected_provider_ids = [value.strip().lower() for value in request.provider_ids if value.strip()]
    selected_mcp_template_ids = [value.strip().lower() for value in request.mcp_template_ids if value.strip()]

    if not selected_provider_ids:
        selected_provider_ids = [
            str(row.get("provider", "")).strip().lower()
            for row in list_provider_templates()
            if str(row.get("provider", "")).strip()
        ]
    if not selected_mcp_template_ids:
        selected_mcp_template_ids = [
            str(row.get("template_id", "")).strip().lower()
            for row in list_mcp_server_templates()
            if str(row.get("template_id", "")).strip()
        ]

    providers_created: List[str] = []
    providers_updated: List[str] = []
    providers_skipped: List[str] = []

    mcp_created: List[str] = []
    mcp_updated: List[str] = []
    mcp_skipped: List[str] = []

    for provider_id in selected_provider_ids:
        template = get_provider_template(provider_id)
        if not template:
            raise HTTPException(status_code=400, detail=f"Unknown provider template: {provider_id}")

        provider = str(template.get("provider", "")).strip().lower()
        existing = await get_integration_account(provider, account_id, include_secret=False)

        if existing and not request.overwrite:
            providers_skipped.append(provider)
            continue

        existing_config = existing.get("config", {}) if isinstance(existing, dict) else {}
        template_config = template.get("default_config", {})
        payload = {
            "enabled": (
                bool(template.get("default_enabled", False))
                if request.overwrite or not existing
                else bool(existing.get("enabled", True))
            ),
            "config": _merge_config_defaults(existing_config, template_config, overwrite=request.overwrite),
        }

        await upsert_integration_account(provider, account_id, payload)
        if existing:
            providers_updated.append(provider)
        else:
            providers_created.append(provider)

    for template_id in selected_mcp_template_ids:
        template = get_mcp_server_template(template_id)
        if not template:
            raise HTTPException(status_code=400, detail=f"Unknown MCP template: {template_id}")

        server_id = str(template.get("server_id", "")).strip()
        existing = await get_mcp_server(server_id, include_secret=False)

        if existing and not request.overwrite:
            mcp_skipped.append(server_id)
            continue

        existing_headers = existing.get("headers", {}) if isinstance(existing, dict) else {}
        existing_env = existing.get("env", {}) if isinstance(existing, dict) else {}

        payload = {
            "enabled": (
                bool(template.get("default_enabled", False))
                if request.overwrite or not existing
                else bool(existing.get("enabled", True))
            ),
            "transport": str(template.get("transport", "stdio")),
            "description": str(template.get("description", "")),
            "command": str(template.get("command", "")),
            "args": list(template.get("args", [])),
            "url": str(template.get("url", "")),
            "headers": _merge_config_defaults(existing_headers, template.get("headers", {}), overwrite=request.overwrite),
            "env": _merge_config_defaults(existing_env, template.get("env", {}), overwrite=request.overwrite),
            "timeout_sec": int(template.get("timeout_sec", 20)),
        }

        try:
            await upsert_mcp_server(server_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if existing:
            mcp_updated.append(server_id)
        else:
            mcp_created.append(server_id)

    await append_event(
        "integration.catalog_bootstrap",
        {
            "account_id": account_id,
            "overwrite": request.overwrite,
            "providers_created": len(providers_created),
            "providers_updated": len(providers_updated),
            "providers_skipped": len(providers_skipped),
            "mcp_created": len(mcp_created),
            "mcp_updated": len(mcp_updated),
            "mcp_skipped": len(mcp_skipped),
        },
    )

    return {
        "account_id": account_id,
        "overwrite": request.overwrite,
        "providers_created": providers_created,
        "providers_updated": providers_updated,
        "providers_skipped": providers_skipped,
        "mcp_created": mcp_created,
        "mcp_updated": mcp_updated,
        "mcp_skipped": mcp_skipped,
    }


@app.get("/experiments", response_model=List[ExperimentView])
async def list_experiments_endpoint(
    enabled: Optional[bool] = None,
    search: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=200, ge=1, le=500),
):
    return await list_experiments(enabled=enabled, search=search, limit=limit)


@app.get("/experiments/{experiment_id}", response_model=ExperimentView)
async def get_experiment_endpoint(experiment_id: str):
    try:
        row = await get_experiment(experiment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not row:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return row


@app.put("/experiments/{experiment_id}", response_model=ExperimentView)
async def upsert_experiment_endpoint(experiment_id: str, request: ExperimentUpsertRequest):
    try:
        row = await upsert_experiment(experiment_id, request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await append_event(
        "experiment.saved",
        {
            "experiment_id": row.get("experiment_id"),
            "name": row.get("name"),
            "job_id": row.get("job_id"),
            "enabled": row.get("enabled", False),
        },
    )
    return row


@app.post("/experiments/{experiment_id}/enabled", response_model=ExperimentView)
async def set_experiment_enabled_endpoint(experiment_id: str, request: ExperimentEnabledRequest):
    try:
        row = await set_experiment_enabled(experiment_id, enabled=request.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not row:
        raise HTTPException(status_code=404, detail="Experiment not found")

    await append_event(
        "experiment.enabled_changed",
        {
            "experiment_id": row.get("experiment_id"),
            "enabled": row.get("enabled", False),
        },
    )
    return row


@app.delete("/experiments/{experiment_id}")
async def delete_experiment_endpoint(experiment_id: str):
    try:
        removed = await hapus_experiment(experiment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not removed:
        raise HTTPException(status_code=404, detail="Experiment not found")

    await append_event("experiment.deleted", {"experiment_id": str(experiment_id or "").strip().lower()})
    return {"experiment_id": str(experiment_id or "").strip().lower(), "status": "deleted"}


@app.get("/triggers", response_model=List[TriggerView])
async def list_triggers_endpoint():
    return await list_triggers()


@app.get("/triggers/{trigger_id}", response_model=TriggerView)
async def get_trigger_endpoint(trigger_id: str):
    row = await get_trigger(trigger_id)
    if not row:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return row


@app.put("/triggers/{trigger_id}", response_model=TriggerView)
async def upsert_trigger_endpoint(trigger_id: str, request: TriggerUpsertRequest):
    try:
        row = await upsert_trigger(trigger_id, request.model_dump(mode="json", exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return row


def _resolve_trigger_auth(request: Request) -> Optional[str]:
    token = request.headers.get("x-trigger-auth") or request.headers.get("authorization")
    if not token:
        return None
    token = token.strip()
    if token.lower().startswith("bearer "):
        return token[7:].strip()
    return token


@app.post("/triggers/{trigger_id}/fire", response_model=TriggerFireResponse)
async def fire_trigger_endpoint(trigger_id: str, request: TriggerFireRequest, http_request: Request):
    auth_token = _resolve_trigger_auth(http_request)
    try:
        result = await fire_trigger(
            trigger_id,
            payload=request.payload,
            source=request.source,
            auth_token=auth_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "trigger_id": trigger_id,
        "job_id": result["job_id"],
        "message_id": result["message_id"],
        "run_id": result["run_id"],
        "channel": result["channel"],
        "source": request.source,
    }


@app.post("/connectors/webhook/{trigger_id}", response_model=TriggerFireResponse)
async def connector_webhook(trigger_id: str, request_body: ConnectorWebhookRequest, http_request: Request):
    trigger = await get_trigger(trigger_id)
    if not trigger or trigger.get("channel") != "webhook":
        raise HTTPException(status_code=404, detail="Webhook trigger not found")
    auth_token = _resolve_trigger_auth(http_request)
    try:
        result = await fire_trigger(
            trigger_id,
            payload=request_body.payload,
            source="connector.webhook",
            auth_token=auth_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "trigger_id": trigger_id,
        "job_id": result["job_id"],
        "message_id": result["message_id"],
        "run_id": result["run_id"],
        "channel": trigger["channel"],
        "source": "connector.webhook",
    }


@app.post("/connectors/telegram/{trigger_id}", response_model=TriggerFireResponse)
async def connector_telegram(trigger_id: str, request_body: ConnectorTelegramRequest, http_request: Request):
    trigger = await get_trigger(trigger_id)
    if not trigger or trigger.get("channel") != "telegram":
        raise HTTPException(status_code=404, detail="Telegram trigger not found")
    auth_token = _resolve_trigger_auth(http_request)
    payload = {
        **request_body.payload,
        "chat_id": request_body.chat_id,
        "text": request_body.text,
    }
    if request_body.username:
        payload["username"] = request_body.username
    try:
        result = await fire_trigger(
            trigger_id,
            payload=payload,
            source="connector.telegram",
            auth_token=auth_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "trigger_id": trigger_id,
        "job_id": result["job_id"],
        "message_id": result["message_id"],
        "run_id": result["run_id"],
        "channel": trigger["channel"],
        "source": "connector.telegram",
    }


@app.post("/connectors/email/{trigger_id}", response_model=TriggerFireResponse)
async def connector_email(trigger_id: str, request_body: ConnectorEmailRequest, http_request: Request):
    trigger = await get_trigger(trigger_id)
    if not trigger or trigger.get("channel") != "email":
        raise HTTPException(status_code=404, detail="Email trigger not found")
    auth_token = _resolve_trigger_auth(http_request)
    payload = {
        **request_body.payload,
        "sender": request_body.sender,
        "subject": request_body.subject,
        "body": request_body.body,
    }
    try:
        result = await fire_trigger(
            trigger_id,
            payload=payload,
            source="connector.email",
            auth_token=auth_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "trigger_id": trigger_id,
        "job_id": result["job_id"],
        "message_id": result["message_id"],
        "run_id": result["run_id"],
        "channel": trigger["channel"],
        "source": "connector.email",
    }


@app.post("/connectors/voice/{trigger_id}", response_model=TriggerFireResponse)
async def connector_voice(trigger_id: str, request_body: ConnectorVoiceRequest, http_request: Request):
    trigger = await get_trigger(trigger_id)
    if not trigger or trigger.get("channel") != "voice":
        raise HTTPException(status_code=404, detail="Voice trigger not found")
    auth_token = _resolve_trigger_auth(http_request)
    payload = {
        **request_body.payload,
        "caller": request_body.caller,
        "transcript": request_body.transcript,
    }
    if request_body.call_id:
        payload["call_id"] = request_body.call_id
    try:
        result = await fire_trigger(
            trigger_id,
            payload=payload,
            source="connector.voice",
            auth_token=auth_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "trigger_id": trigger_id,
        "job_id": result["job_id"],
        "message_id": result["message_id"],
        "run_id": result["run_id"],
        "channel": trigger["channel"],
        "source": "connector.voice",
    }


@app.post("/connectors/slack/{trigger_id}", response_model=TriggerFireResponse)
async def connector_slack(trigger_id: str, request_body: ConnectorSlackRequest, http_request: Request):
    trigger = await get_trigger(trigger_id)
    if not trigger or trigger.get("channel") != "slack":
        raise HTTPException(status_code=404, detail="Slack trigger not found")
    auth_token = _resolve_trigger_auth(http_request)
    payload = {
        **request_body.payload,
        "channel_id": request_body.channel_id,
        "user_id": request_body.user_id,
        "command": request_body.command,
        "text": request_body.text,
    }
    if request_body.response_url:
        payload["response_url"] = request_body.response_url
    try:
        result = await fire_trigger(
            trigger_id,
            payload=payload,
            source="connector.slack",
            auth_token=auth_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "trigger_id": trigger_id,
        "job_id": result["job_id"],
        "message_id": result["message_id"],
        "run_id": result["run_id"],
        "channel": trigger["channel"],
        "source": "connector.slack",
    }


@app.post("/connectors/sms/{trigger_id}", response_model=TriggerFireResponse)
async def connector_sms(trigger_id: str, request_body: ConnectorSmsRequest, http_request: Request):
    trigger = await get_trigger(trigger_id)
    if not trigger or trigger.get("channel") != "sms":
        raise HTTPException(status_code=404, detail="SMS trigger not found")
    auth_token = _resolve_trigger_auth(http_request)
    payload = {
        **request_body.payload,
        "phone_number": request_body.phone_number,
        "message": request_body.message,
    }
    try:
        result = await fire_trigger(
            trigger_id,
            payload=payload,
            source="connector.sms",
            auth_token=auth_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "trigger_id": trigger_id,
        "job_id": result["job_id"],
        "message_id": result["message_id"],
        "run_id": result["run_id"],
        "channel": trigger["channel"],
        "source": "connector.sms",
    }


@app.delete("/triggers/{trigger_id}")
async def delete_trigger_endpoint(trigger_id: str):
    removed = await hapus_trigger(trigger_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Trigger not found")
    await append_event("trigger.deleted", {"trigger_id": trigger_id})
    return {"trigger_id": trigger_id, "status": "deleted"}


def _parse_skill_tags(tags: Optional[str]) -> Optional[List[str]]:
    if not tags:
        return None
    tokens = [token.strip() for token in tags.split(",")]
    return [token for token in tokens if token]


@app.get("/skills", response_model=List[SkillView])
async def list_skills_endpoint(tags: Optional[str] = Query(None, description="Filter berdasarkan comma-separated tags")):
    tag_list = _parse_skill_tags(tags)
    return await list_skill_specs(tags=tag_list)


@app.get("/skills/{skill_id}", response_model=SkillView)
async def get_skill_endpoint(skill_id: str):
    row = await get_skill(skill_id)
    if not row:
        raise HTTPException(status_code=404, detail="Skill not found")
    return row


@app.put("/skills/{skill_id}", response_model=SkillView)
async def upsert_skill_endpoint(skill_id: str, request: SkillSpecRequest):
    try:
        row = await upsert_skill(skill_id, request.model_dump(exclude={"skill_id"}))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return row


@app.post("/skills/sync", response_model=List[SkillView])
async def sync_skills_endpoint(request: SkillSyncRequest):
    hasil: List[Dict[str, Any]] = []
    for spec in request.skills:
        try:
            row = await upsert_skill(spec.skill_id, spec.model_dump(exclude={"skill_id"}))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{spec.skill_id}: {exc}")
        hasil.append(row)
    return hasil


@app.delete("/skills/{skill_id}")
async def delete_skill_endpoint(skill_id: str):
    removed = await hapus_skill(skill_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Skill not found")
    await append_event("skill.deleted", {"skill_id": skill_id})
    return {"skill_id": skill_id, "status": "deleted"}


@app.get("/connectors")
async def connectors():
    if not getattr(app.state, "redis_ready", True):
        return _fallback_payload("/connectors", [])

    try:
        rows: List[Dict[str, Any]] = []
        keys = sorted(await redis_client.keys("hb:connector:*"))

        for key in keys:
            parts = key.split(":")
            if len(parts) < 4:
                continue
            channel, account_id = parts[2], parts[3]
            status_raw = (await redis_client.get(key)) or "offline"
            ttl = await redis_client.ttl(key)
            status = "online" if status_raw in {"online", "connected"} and ttl > 0 else "offline"
            rows.append(
                {
                    "channel": channel,
                    "account_id": account_id,
                    "status": status,
                    "last_heartbeat_at": _sekarang_iso(),
                    "reconnect_count": 0,
                    "last_error": None,
                }
            )
        return rows
    except RedisError:
        return _fallback_payload("/connectors", [])


@app.get("/agents")
async def agents():
    if not getattr(app.state, "redis_ready", True):
        return _fallback_payload("/agents", _local_agents_snapshot())

    try:
        rows: List[Dict[str, Any]] = []
        keys = sorted(await redis_client.keys("hb:agent:*:*"))

        for key in keys:
            parts = key.split(":")
            if len(parts) < 4:
                continue

            agent_type, agent_id = parts[2], parts[3]
            heartbeat_raw = await redis_client.get(key)
            ttl = await redis_client.ttl(key)
            status = "online" if ttl > 0 else "offline"

            timestamp = _sekarang_iso()
            pool = "default"
            concurrency = 1
            if heartbeat_raw:
                try:
                    import json
                    data = json.loads(heartbeat_raw)
                    if isinstance(data, dict):
                        timestamp = data.get("timestamp", timestamp)
                        pool = data.get("pool", pool)
                        concurrency = data.get("concurrency", concurrency)
                except Exception:
                    timestamp = heartbeat_raw

            rows.append(
                {
                    "id": agent_id,
                    "type": agent_type,
                    "status": status,
                    "last_heartbeat": timestamp,
                    "last_heartbeat_at": timestamp,
                    "active_sessions": concurrency if status == "online" else 0,
                    "pool": pool,
                    "version": "0.1.0",
                }
            )

        return rows
    except RedisError:
        return _fallback_payload("/agents", _local_agents_snapshot())


@app.get("/agents/memory", response_model=List[AgentMemoryView])
async def agents_memory(limit: int = Query(default=100, ge=1, le=500)):
    try:
        rows = await list_agent_memories(limit=limit)
        return [build_agent_memory_context(row) for row in rows]
    except RedisError:
        return _fallback_payload("/agents/memory", [])


@app.delete("/agents/memory/{agent_key}", response_model=AgentMemoryResetView)
async def reset_agent_memory(agent_key: str):
    normalized = str(agent_key or "").strip().lower()[:128]
    if not normalized:
        raise HTTPException(status_code=400, detail="agent_key is required")

    deleted = await hapus_agent_memory(normalized)
    status = "cleared" if deleted else "not_found"

    with suppress(Exception):
        await append_event(
            "agent.memory_reset",
            {"agent_key": normalized, "deleted": deleted},
        )

    return {
        "agent_key": normalized,
        "deleted": deleted,
        "status": status,
    }


@app.get("/runs")
async def runs(
    job_id: Optional[str] = None,
    status: Optional[str] = Query(default=None, pattern="^(queued|running|success|failed)$"),
    search: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    try:
        rows = await list_runs(limit=limit, job_id=job_id, status=status, offset=offset, search=search)
        return [_serialisasi_model(run) for run in rows]
    except RedisError:
        return _fallback_payload("/runs", [])


@app.get("/runs/{run_id}")
async def run_detail(run_id: str):
    run = await get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _serialisasi_model(run)


@app.get("/audit/logs", response_model=List[AuditLogView])
async def audit_logs(
    since: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    method: Optional[str] = Query(default=None, pattern="^(GET|POST|PUT|DELETE|PATCH)$"),
    outcome: Optional[str] = Query(default=None, pattern="^(success|error|denied)$"),
    actor_role: Optional[str] = Query(default=None, pattern="^(viewer|operator|admin|unknown)$"),
    path_contains: Optional[str] = None,
):
    scan_limit = min(max(limit * 8, 300), 5000)

    try:
        rows = await get_events(limit=scan_limit, since=since)
    except RedisError:
        return _fallback_payload("/audit/logs", [])

    method_filter = method.upper() if method else ""
    outcome_filter = outcome.lower() if outcome else ""
    role_filter = actor_role.lower() if actor_role else ""
    path_filter = str(path_contains or "").strip().lower()

    hasil: List[Dict[str, Any]] = []
    for event in rows:
        row = event_to_audit_row(event)
        if not row:
            continue
        if method_filter and row.get("method") != method_filter:
            continue
        if outcome_filter and row.get("outcome") != outcome_filter:
            continue
        if role_filter and row.get("actor_role") != role_filter:
            continue
        if path_filter and path_filter not in str(row.get("path") or "").lower():
            continue
        hasil.append(row)

    if len(hasil) > limit:
        return hasil[-limit:]
    return hasil


@app.get("/events")
async def events(
    request: Request,
    since: Optional[str] = None,
    event_type: Optional[str] = Query(default=None, max_length=120),
    search: Optional[str] = Query(default=None, max_length=160),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    type_filter = str(event_type or "").strip()
    search_filter = str(search or "").strip().lower()

    def cocok_filter_event(row: Dict[str, Any]) -> bool:
        if type_filter and str(row.get("type") or "") != type_filter:
            return False
        if search_filter:
            token_type = str(row.get("type") or "").lower()
            token_id = str(row.get("id") or "").lower()
            token_data = json.dumps(row.get("data") or {}, ensure_ascii=False).lower()
            if search_filter not in token_type and search_filter not in token_id and search_filter not in token_data:
                return False
        return True

    accept = request.headers.get("accept", "")

    if "text/event-stream" in accept:
        async def stream():
            seen_ids = set()
            while True:
                try:
                    rows = await get_events(limit=limit, since=since)
                except RedisError:
                    await asyncio.sleep(1)
                    continue
                for row in rows:
                    if not cocok_filter_event(row):
                        continue
                    event_id = row.get("id")
                    if event_id in seen_ids:
                        continue
                    seen_ids.add(event_id)
                    yield f"data: {json.dumps(row)}\n\n"

                # Keep memory bounded
                if len(seen_ids) > 2000:
                    seen_ids.clear()

                await asyncio.sleep(1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    try:
        if type_filter or search_filter:
            scan_limit = min(max((offset + limit) * 6, limit), 5000)
            rows = await get_events(limit=scan_limit, since=since, offset=0)
            rows = [row for row in rows if cocok_filter_event(row)]
            if offset:
                rows = rows[offset:]
            if len(rows) > limit:
                rows = rows[:limit]
            return rows

        rows = await get_events(limit=limit, since=since, offset=offset)
        return rows
    except RedisError:
        return _fallback_payload("/events", [])


# Sales Closing Engine Endpoints
@app.post("/sales/prospects")
async def api_create_prospect(request: ProspectCreateRequest):
    from app.core.branches import get_branch

    branch_id = str(request.branch_id or "").strip().lower()
    branch = await get_branch(branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    try:
        row = await create_prospect(
            {
                "branch_id": branch_id,
                "name": request.name,
                "channel": request.channel,
                "contact_id": request.contact_id,
                "source": request.source,
                "offer": request.offer,
                "owner": request.owner,
                "value_estimate": request.value_estimate,
                "stage": request.stage,
                "notes": request.notes,
                "tags": request.tags,
                "next_followup_at": request.next_followup_at,
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await append_event(
        "sales.prospect_created",
        {
            "prospect_id": row.get("prospect_id"),
            "branch_id": row.get("branch_id"),
            "channel": row.get("channel"),
            "source": row.get("source"),
        },
    )
    return row


@app.post("/sales/inbound", response_model=SalesInboundResponse)
async def api_sales_inbound(request: SalesInboundRequest):
    from app.core.branches import get_branch

    branch_id = str(request.branch_id or "").strip().lower()
    if not branch_id:
        raise HTTPException(status_code=400, detail="branch_id is required")
    branch = await get_branch(branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    channel = normalize_prospect_channel(request.channel)
    contact_id = str(request.contact_id or "").strip()
    if not channel:
        raise HTTPException(status_code=400, detail="channel is required")
    if not contact_id:
        raise HTTPException(status_code=400, detail="contact_id is required")

    now_iso = datetime.now(timezone.utc).isoformat()
    inbound_message = str(request.message or "").strip()
    inbound_note = ""
    if inbound_message:
        inbound_note = f"[inbound:{channel}] {now_iso} {inbound_message}"

    normalized_tags = [str(tag or "").strip().lower() for tag in (request.tags or [])]
    normalized_tags = [tag for tag in normalized_tags if tag]
    if "inbound" not in normalized_tags:
        normalized_tags.append("inbound")
    if channel not in normalized_tags:
        normalized_tags.append(channel)

    existing = await find_open_prospect_by_contact(
        branch_id=branch_id,
        channel=channel,
        contact_id=contact_id,
    )

    action = "created"
    if existing:
        existing_notes = str(existing.get("notes") or "").strip()
        merged_notes = existing_notes
        if inbound_note:
            merged_notes = f"{existing_notes}\n{inbound_note}".strip() if existing_notes else inbound_note

        existing_tags = [str(tag or "").strip().lower() for tag in (existing.get("tags") or [])]
        merged_tags: List[str] = []
        seen_tags = set()
        for tag in existing_tags + normalized_tags:
            if not tag or tag in seen_tags:
                continue
            seen_tags.add(tag)
            merged_tags.append(tag)

        update_payload: Dict[str, Any] = {
            "name": str(request.name or existing.get("name") or "").strip() or str(existing.get("name") or ""),
            "source": str(request.source or existing.get("source") or "").strip(),
            "offer": str(request.offer or existing.get("offer") or "").strip(),
            "owner": str(request.owner or existing.get("owner") or "").strip(),
            "notes": merged_notes,
            "tags": merged_tags,
        }
        if request.value_estimate > 0:
            update_payload["value_estimate"] = float(request.value_estimate)
        prospect = await update_prospect(str(existing.get("prospect_id") or "").strip(), update_payload)
        if not prospect:
            raise HTTPException(status_code=500, detail="Failed to update inbound prospect")
        action = "updated"
    else:
        try:
            prospect = await create_prospect(
                {
                    "branch_id": branch_id,
                    "name": str(request.name or contact_id).strip(),
                    "channel": channel,
                    "contact_id": contact_id,
                    "source": str(request.source or f"inbound.{channel}").strip(),
                    "offer": str(request.offer or "").strip(),
                    "owner": str(request.owner or "").strip(),
                    "value_estimate": float(request.value_estimate or 0),
                    "stage": str(request.stage or "new").strip() or "new",
                    "notes": inbound_note,
                    "tags": normalized_tags,
                    "next_followup_at": (
                        datetime.now(timezone.utc) + timedelta(minutes=int(request.next_followup_minutes))
                    ).isoformat(),
                }
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    prospect_id = str(prospect.get("prospect_id") or "").strip()
    followup_queued = False
    queued_run_id: Optional[str] = None
    if bool(request.auto_followup):
        payload_inputs = {
            "prospect_id": prospect_id,
            "branch_id": branch_id,
            "account_id": str(request.account_id or "").strip(),
            "template": str(request.followup_template or "").strip(),
            "max_items": 1,
            "next_followup_minutes": int(request.next_followup_minutes),
        }
        payload_inputs = {k: v for k, v in payload_inputs.items() if v not in {"", None}}
        queued = await _queue_custom_job_run(
            job_id=f"sales-followup-dispatch-{branch_id}",
            job_type="sales.followup",
            inputs=payload_inputs,
            timeout_ms=45000,
            source="api.sales_inbound",
        )
        followup_queued = True
        queued_run_id = str(queued.get("run_id") or "").strip() or None

    await append_event(
        "sales.inbound_received",
        {
            "prospect_id": prospect_id,
            "branch_id": branch_id,
            "channel": channel,
            "contact_id": contact_id,
            "action": action,
            "followup_queued": followup_queued,
            "run_id": queued_run_id,
        },
    )

    return SalesInboundResponse(
        status="ok",
        action=action,
        prospect_id=prospect_id,
        branch_id=branch_id,
        channel=channel,
        contact_id=contact_id,
        followup_queued=followup_queued,
        run_id=queued_run_id,
    )


@app.get("/sales/prospects")
async def api_list_prospects(
    branch_id: str = "",
    stage: str = "",
    due_only: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
):
    rows = await list_prospects(
        branch_id=str(branch_id or "").strip().lower(),
        stage=str(stage or "").strip().lower(),
        due_only=bool(due_only),
        limit=limit,
    )
    return rows


@app.get("/sales/prospects/{prospect_id}")
async def api_get_prospect(prospect_id: str):
    row = await get_prospect(str(prospect_id or "").strip())
    if not row:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return row


@app.patch("/sales/prospects/{prospect_id}")
async def api_update_prospect(prospect_id: str, request: ProspectUpdateRequest):
    payload = request.model_dump(mode="json", exclude_unset=True)
    row = await update_prospect(str(prospect_id or "").strip(), payload)
    if not row:
        raise HTTPException(status_code=404, detail="Prospect not found")

    await append_event(
        "sales.prospect_updated",
        {
            "prospect_id": row.get("prospect_id"),
            "branch_id": row.get("branch_id"),
            "stage": row.get("stage"),
        },
    )
    return row


@app.post("/sales/prospects/{prospect_id}/close-won")
async def api_close_prospect_won(prospect_id: str, request: ProspectCloseWonRequest):
    from app.core.branches import update_branch_metrics

    pid = str(prospect_id or "").strip()
    if not await get_prospect(pid):
        raise HTTPException(status_code=404, detail="Prospect not found")

    row = await mark_prospect_won(prospect_id=pid, amount=request.amount, note=request.note)
    if not row:
        raise HTTPException(status_code=404, detail="Prospect not found")

    await update_branch_metrics(
        str(row.get("branch_id") or "").strip().lower(),
        {
            "revenue": float(request.amount),
            "closings": int(request.closings_delta),
            "leads": int(request.leads_delta),
        },
    )
    await append_event(
        "sales.prospect_closed_won",
        {
            "prospect_id": pid,
            "branch_id": row.get("branch_id"),
            "revenue": float(request.amount),
            "closings_delta": int(request.closings_delta),
            "leads_delta": int(request.leads_delta),
        },
    )
    return row


@app.post("/sales/prospects/{prospect_id}/close-lost")
async def api_close_prospect_lost(prospect_id: str, request: ProspectCloseLostRequest):
    pid = str(prospect_id or "").strip()
    row = await mark_prospect_lost(prospect_id=pid, reason=request.reason)
    if not row:
        raise HTTPException(status_code=404, detail="Prospect not found")

    await append_event(
        "sales.prospect_closed_lost",
        {
            "prospect_id": pid,
            "branch_id": row.get("branch_id"),
            "reason": request.reason,
        },
    )
    return row


@app.post("/sales/followup/run")
async def api_dispatch_followup_run(request: SalesFollowupDispatchRequest):
    branch_id = str(request.branch_id or "").strip().lower()
    pid = str(request.prospect_id or "").strip()
    if not pid and not branch_id:
        raise HTTPException(status_code=400, detail="branch_id or prospect_id is required")

    if pid:
        prospect = await get_prospect(pid)
        if not prospect:
            raise HTTPException(status_code=404, detail="Prospect not found")
        if not branch_id:
            branch_id = str(prospect.get("branch_id") or "").strip().lower()

    payload_inputs = {
        "prospect_id": pid or None,
        "branch_id": branch_id,
        "account_id": str(request.account_id or "").strip(),
        "template": str(request.template or "").strip(),
        "max_items": int(request.max_items),
        "next_followup_minutes": int(request.next_followup_minutes),
    }
    payload_inputs = {k: v for k, v in payload_inputs.items() if v not in {"", None}}

    job_id = f"sales-followup-dispatch-{branch_id or 'manual'}"
    queued = await _queue_custom_job_run(
        job_id=job_id,
        job_type="sales.followup",
        inputs=payload_inputs,
        timeout_ms=45000,
        source="api.sales_followup_dispatch",
    )
    return queued


@app.post("/sales/followup/automation")
async def api_upsert_followup_automation(request: SalesFollowupAutomationRequest):
    from app.core.branches import get_branch

    branch_id = str(request.branch_id or "").strip().lower()
    branch = await get_branch(branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    job_id = f"sales-followup-{branch_id}"
    spec = JobSpec(
        job_id=job_id,
        type="sales.followup",
        schedule=Schedule(interval_sec=int(request.interval_sec)),
        timeout_ms=45000,
        retry_policy=RetryPolicy(max_retry=3, backoff_sec=[5, 15, 30]),
        inputs={
            "branch_id": branch_id,
            "account_id": str(request.account_id or "").strip(),
            "template": str(request.template or "").strip(),
            "max_items": int(request.max_items),
            "next_followup_minutes": int(request.next_followup_minutes),
            "source": "sales.followup.automation",
        },
    )
    await save_job_spec(job_id, _serialisasi_model(spec))
    await enable_job(job_id)

    await append_event(
        "sales.followup_automation_upserted",
        {
            "job_id": job_id,
            "branch_id": branch_id,
            "interval_sec": int(request.interval_sec),
        },
    )
    return {"job_id": job_id, "status": "enabled", "branch_id": branch_id}


@app.get("/influencer/templates", response_model=List[InfluencerTemplateView])
async def api_list_influencer_template(limit: int = Query(default=200, ge=1, le=1000)):
    return await list_influencer_templates(limit=limit)


@app.get("/influencer/templates/{template_id}", response_model=InfluencerTemplateView)
async def api_get_influencer_template_by_id(template_id: str):
    row = await get_influencer_template(str(template_id or "").strip().lower())
    if not row:
        raise HTTPException(status_code=404, detail="Influencer template not found")
    return row


@app.put("/influencer/templates/{template_id}", response_model=InfluencerTemplateView)
async def api_upsert_influencer_template_by_id(template_id: str, request: InfluencerTemplateUpsertRequest):
    clean_template_id = str(template_id or "").strip().lower()
    if not clean_template_id:
        raise HTTPException(status_code=400, detail="template_id is required")

    row = await upsert_influencer_template(clean_template_id, request.model_dump(mode="json"))
    await append_event(
        "influencer.template_upserted",
        {
            "template_id": clean_template_id,
            "mode": row.get("mode"),
            "enabled": bool(row.get("enabled", True)),
        },
    )
    return row


@app.get("/influencer/profiles", response_model=List[InfluencerProfileView])
async def api_list_influencer_profiles(limit: int = Query(default=200, ge=1, le=1000)):
    return await list_influencers(limit=limit)


@app.get("/influencer/profiles/{influencer_id}", response_model=InfluencerProfileView)
async def api_get_influencer_profile(influencer_id: str):
    row = await get_influencer(str(influencer_id or "").strip().lower())
    if not row:
        raise HTTPException(status_code=404, detail="Influencer profile not found")
    return row


def _normalize_influencer_mode(value: Any, fallback: str = "product") -> str:
    mode = str(value or fallback).strip().lower()
    if mode not in {"endorse", "product", "hybrid"}:
        return str(fallback or "product").strip().lower() or "product"
    return mode


def _build_influencer_render_context(template_id: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    offer_price = float(profile.get("offer_price") or 0)
    return {
        "template_id": str(template_id or "").strip().lower(),
        "influencer_id": str(profile.get("influencer_id") or "").strip().lower(),
        "influencer_name": str(profile.get("name") or "").strip(),
        "niche": str(profile.get("niche") or "").strip(),
        "mode": _normalize_influencer_mode(profile.get("mode"), fallback="product"),
        "branch_id": str(profile.get("branch_id") or "").strip().lower(),
        "offer_name": str(profile.get("offer_name") or "").strip() or "offer",
        "offer_price": int(offer_price) if offer_price.is_integer() else offer_price,
    }


async def _apply_template_jobs_for_influencer(
    *,
    template_id: str,
    template: Dict[str, Any],
    profile: Dict[str, Any],
    enable_jobs: bool,
    overwrite_existing_jobs: bool,
    source: str,
) -> List[InfluencerCloneJobView]:
    from app.core.branches import get_branch

    clean_template_id = str(template_id or "").strip().lower()
    influencer_id = str(profile.get("influencer_id") or "").strip().lower()
    branch_id = str(profile.get("branch_id") or "").strip().lower()
    if not influencer_id:
        raise HTTPException(status_code=400, detail="Influencer profile missing influencer_id")
    if not branch_id:
        raise HTTPException(status_code=400, detail="Influencer profile missing branch_id")

    branch = await get_branch(branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail=f"Branch '{branch_id}' not found")

    render_context = _build_influencer_render_context(clean_template_id, profile)
    jobs_payload: List[InfluencerCloneJobView] = []
    raw_job_templates = template.get("job_templates", [])
    if not isinstance(raw_job_templates, list):
        raw_job_templates = []

    for index, row in enumerate(raw_job_templates, start=1):
        if not isinstance(row, dict):
            continue

        job_id_pattern = str(row.get("job_id_pattern") or f"inf-{influencer_id}-job-{index}").strip()
        job_id = _slugify_text(
            _render_template_text(job_id_pattern, render_context),
            fallback=f"inf-{influencer_id}-job-{index}",
        )
        job_type = str(row.get("type") or "agent.workflow").strip()

        schedule_payload = row.get("schedule", {})
        schedule_cron = ""
        schedule_interval = None
        if isinstance(schedule_payload, dict):
            schedule_cron = str(schedule_payload.get("cron") or "").strip()
            interval_value = schedule_payload.get("interval_sec")
            if isinstance(interval_value, int):
                schedule_interval = max(10, interval_value)
        if not schedule_cron and schedule_interval is None:
            schedule_interval = 1800

        retry_payload = row.get("retry_policy", {})
        max_retry = 2
        backoff_sec = [5, 15, 30]
        if isinstance(retry_payload, dict):
            raw_retry = retry_payload.get("max_retry")
            raw_backoff = retry_payload.get("backoff_sec")
            if isinstance(raw_retry, int):
                max_retry = max(0, min(10, raw_retry))
            if isinstance(raw_backoff, list):
                candidate = [int(item) for item in raw_backoff if isinstance(item, (int, float))]
                if candidate:
                    backoff_sec = candidate[:10]

        inputs_raw = row.get("inputs", {})
        inputs_rendered = _render_template_payload(inputs_raw, render_context) if isinstance(inputs_raw, dict) else {}

        job_spec = JobSpec(
            job_id=job_id,
            type=job_type,
            schedule=Schedule(
                cron=schedule_cron or None,
                interval_sec=schedule_interval,
            ),
            timeout_ms=max(5000, int(row.get("timeout_ms") or 45000)),
            retry_policy=RetryPolicy(max_retry=max_retry, backoff_sec=backoff_sec),
            inputs=inputs_rendered,
        )

        existing_job = await get_job_spec(job_id)
        if existing_job and not bool(overwrite_existing_jobs):
            is_enabled = await is_job_enabled(job_id)
            jobs_payload.append(
                InfluencerCloneJobView(
                    job_id=job_id,
                    type=job_type,
                    enabled=bool(is_enabled),
                    status="skipped_existing",
                )
            )
            continue

        job_status = "updated" if existing_job else "created"
        await save_job_spec(
            job_id,
            _serialisasi_model(job_spec),
            source=source,
            note=f"template_sync:{clean_template_id}:{influencer_id}",
        )

        requested_enable = bool(enable_jobs and bool(row.get("enabled", True)))
        should_enable = requested_enable
        block_reason = ""
        if requested_enable:
            readiness = await _can_enable_cloned_job(job_type, inputs_rendered)
            should_enable = bool(readiness.get("ok"))
            block_reason = str(readiness.get("reason") or "").strip()

        if should_enable:
            await enable_job(job_id)
        else:
            await disable_job(job_id)

        status_label = job_status
        if requested_enable and not should_enable and block_reason:
            status_label = f"{job_status}:blocked:{block_reason}"

        jobs_payload.append(
            InfluencerCloneJobView(
                job_id=job_id,
                type=job_type,
                enabled=should_enable,
                status=status_label,
            )
        )

    return jobs_payload


@app.patch("/influencer/profiles/{influencer_id}", response_model=InfluencerProfileUpdateResponse)
async def api_patch_influencer_profile(influencer_id: str, request: InfluencerProfileUpdateRequest):
    clean_id = str(influencer_id or "").strip().lower()
    if not clean_id:
        raise HTTPException(status_code=400, detail="influencer_id is required")

    existing = await get_influencer(clean_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Influencer profile not found")

    payload = request.model_dump(mode="json", exclude_unset=True)
    apply_template_jobs = bool(payload.pop("apply_template_jobs", False))
    enable_jobs = bool(payload.pop("enable_jobs", True))
    overwrite_existing_jobs = bool(payload.pop("overwrite_existing_jobs", True))

    if "mode" in payload:
        payload["mode"] = _normalize_influencer_mode(payload.get("mode"), fallback=str(existing.get("mode") or "product"))
    if "template_id" in payload:
        payload["template_id"] = str(payload.get("template_id") or "").strip().lower()
    if "branch_id" in payload:
        payload["branch_id"] = str(payload.get("branch_id") or "").strip().lower()
    if "status" in payload:
        status = str(payload.get("status") or "").strip().lower()
        payload["status"] = status or str(existing.get("status") or "active").strip().lower() or "active"

    updated_profile = await upsert_influencer(clean_id, payload)
    jobs_payload: List[InfluencerCloneJobView] = []
    if apply_template_jobs:
        clean_template_id = str(updated_profile.get("template_id") or "").strip().lower()
        if not clean_template_id:
            raise HTTPException(status_code=400, detail="template_id is required to apply template jobs")
        template = await get_influencer_template(clean_template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Influencer template not found")

        jobs_payload = await _apply_template_jobs_for_influencer(
            template_id=clean_template_id,
            template=template,
            profile=updated_profile,
            enable_jobs=enable_jobs,
            overwrite_existing_jobs=overwrite_existing_jobs,
            source="api.influencer.profile_update",
        )

    await append_event(
        "influencer.profile_updated",
        {
            "influencer_id": clean_id,
            "template_id": updated_profile.get("template_id"),
            "branch_id": updated_profile.get("branch_id"),
            "apply_template_jobs": apply_template_jobs,
            "job_count": len(jobs_payload),
        },
    )

    return InfluencerProfileUpdateResponse(
        influencer=InfluencerProfileView(**updated_profile),
        jobs=jobs_payload,
        status="ok",
    )


@app.post("/influencer/templates/{template_id}/clone", response_model=InfluencerTemplateCloneResponse)
async def api_clone_influencer_template(template_id: str, request: InfluencerTemplateCloneRequest):
    from app.core.branches import get_branch

    clean_template_id = str(template_id or "").strip().lower()
    template = await get_influencer_template(clean_template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Influencer template not found")

    requested_id = str(request.influencer_id or "").strip().lower()
    generated_from_name = _slugify_text(request.name, fallback="influencer")
    influencer_id = _slugify_text(requested_id or generated_from_name, fallback="influencer")
    mode = str(request.mode or template.get("mode") or "product").strip().lower()
    if mode not in {"endorse", "product", "hybrid"}:
        mode = "product"

    branch_id = (
        str(request.branch_id or "").strip().lower()
        or str(template.get("default_branch_id") or "").strip().lower()
        or "br_01"
    )
    branch = await get_branch(branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail=f"Branch '{branch_id}' not found")

    normalized_channels = _normalize_clone_channels(request.channels)
    offer_name = str(request.offer_name or "").strip()
    offer_price = float(request.offer_price or 0)

    influencer_profile = await upsert_influencer(
        influencer_id,
        {
            "name": request.name,
            "niche": request.niche,
            "mode": mode,
            "template_id": clean_template_id,
            "branch_id": branch_id,
            "channels": normalized_channels,
            "offer_name": offer_name,
            "offer_price": offer_price,
            "metadata": request.metadata,
        },
    )

    jobs_payload = await _apply_template_jobs_for_influencer(
        template_id=clean_template_id,
        template=template,
        profile=influencer_profile,
        enable_jobs=bool(request.enable_jobs),
        overwrite_existing_jobs=bool(request.overwrite_existing_jobs),
        source="api.influencer.clone",
    )

    await append_event(
        "influencer.template_cloned",
        {
            "template_id": clean_template_id,
            "influencer_id": influencer_id,
            "branch_id": branch_id,
            "job_count": len(jobs_payload),
        },
    )

    return InfluencerTemplateCloneResponse(
        template_id=clean_template_id,
        influencer=InfluencerProfileView(**influencer_profile),
        jobs=jobs_payload,
        status="ok",
    )


# Branch Endpoints (Phase 15 - Holding Suite)
@app.get("/branches")
async def api_list_branches():
    from app.core.branches import list_branches
    from app.core.armory import count_ready_accounts_for_branch
    try:
        branches = await list_branches()
        # Enrich with operational readiness data
        for b in branches:
            b["operational_ready"] = await count_ready_accounts_for_branch(b["branch_id"])
        return branches
    except Exception:
        return []

@app.get("/branches/{branch_id}")
async def api_get_branch(branch_id: str):
    from app.core.branches import get_branch
    row = await get_branch(branch_id)
    if not row:
        raise HTTPException(status_code=404, detail="Branch not found")
    return row

# Armory Endpoints (Phase 18)
class AccountAddRequest(BaseModel):
    platform: str
    username: str
    password: str
    proxy: Optional[str] = None
    two_factor: Optional[str] = None

@app.get("/armory/accounts")
async def api_list_accounts(platform: Optional[str] = None):
    from app.core.armory import list_all_accounts
    return await list_all_accounts(platform=platform)

@app.post("/armory/accounts")
async def api_add_account(request: AccountAddRequest):
    from app.core.armory import add_account
    try:
        return await add_account(
            platform=request.platform,
            username=request.username,
            password=request.password,
            proxy=request.proxy,
            two_factor=request.two_factor
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/armory/accounts/{account_id}/deploy")
async def api_deploy_account(account_id: str, branch_id: str):
    from app.core.armory import deploy_account_to_branch
    await deploy_account_to_branch(account_id, branch_id)
    return {"status": "deployed"}

# Boardroom Endpoints (Phase 15 - Executive Chat)
class ChatMessageRequest(BaseModel):
    text: str

@app.get("/boardroom/history")
async def api_get_chat_history(limit: int = 30):
    from app.core.boardroom import get_chat_history
    return await get_chat_history(limit=limit)

@app.post("/boardroom/chat")
async def api_chat_with_ceo(request: ChatMessageRequest):
    from app.core.boardroom import process_chairman_mandate
    return await process_chairman_mandate(request.text)

@app.get("/system/infrastructure")
async def api_system_infrastructure():
    from app.core.redis_client import redis_client
    import time
    
    # 1. Check Redis
    redis_ok = False
    redis_info = {}
    try:
        redis_info = await redis_client.info()
        redis_ok = True
    except: pass
    
    # 2. Check AI Node (VPS 2)
    ai_node_ok = False
    from app.core.config import settings
    if settings.AI_NODE_URL:
        # Simple ping simulation
        ai_node_ok = True 

    return {
        "api": {"status": "ok", "uptime": "active"},
        "redis": {
            "status": "ok" if redis_ok else "error",
            "memory_used": redis_info.get("used_memory_human", "0B")
        },
        "ai_factory": {
            "status": "ready" if ai_node_ok else "not_configured",
            "endpoint": settings.AI_NODE_URL or "none"
        },
        "timestamp": time.time()
    }
class MemoryEntry(BaseModel):
    key: str
    value: str

@app.get("/memory")
async def api_list_memory():
    from app.core.redis_client import redis_client
    keys = await redis_client.keys("memory:context:*")
    results = []
    for k in keys:
        v = await redis_client.get(k)
        results.append({"key": k.replace("memory:context:", ""), "value": v})
    return results

@app.post("/memory")
async def api_save_memory(mem: MemoryEntry):
    from app.core.redis_client import redis_client
    await redis_client.set(f"memory:context:{mem.key}", mem.value)
    return {"status": "saved"}
