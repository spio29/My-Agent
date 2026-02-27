import json
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from redis.exceptions import RedisError, ResponseError, TimeoutError as RedisTimeoutError

from .models import QueueEvent, Run
from .redis_client import redis_client

# Redis stream key for jobs
STREAM_JOBS = "stream:jobs"
# Redis list key for compatibility mode on older Redis without Streams support.
LIST_JOBS = "list:jobs"
# Consumer group for workers
CG_WORKERS = "cg:workers"
# ZSET for delayed jobs (score = unix timestamp)
ZSET_DELAYED = "zset:delayed"
# Job registry keys
JOB_SPEC_PREFIX = "job:spec:"
JOB_ENABLED_SET = "job:enabled"
JOB_ALL_SET = "job:all"
JOB_SPEC_VERSIONS_PREFIX = "job:spec:versions:"
RUN_PREFIX = "run:"
ZSET_RUNS = "zset:runs"
JOB_RUNS_PREFIX = "job:runs:"
JOB_ACTIVE_RUNS_PREFIX = "job:active:runs:"
FLOW_ACTIVE_RUNS_PREFIX = "flow:active:runs:"
JOB_FAILURE_STATE_PREFIX = "job:failure:state:"
EVENTS_LOG = "events:log"
EVENTS_MAX = 500
JOB_SPEC_VERSIONS_MAX = 100


# In-memory fallback store used when Redis is unavailable.
_fallback_stream: List[Dict[str, Any]] = []
_fallback_stream_seq = 0
_fallback_delayed: List[Dict[str, Any]] = []
_fallback_job_specs: Dict[str, Dict[str, Any]] = {}
_fallback_job_all: set = set()
_fallback_job_enabled: set = set()
_fallback_job_spec_versions: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
_fallback_runs: Dict[str, Dict[str, Any]] = {}
_fallback_run_scores: Dict[str, float] = {}
_fallback_job_runs: Dict[str, List[str]] = defaultdict(list)
_fallback_active_runs: Dict[str, set] = defaultdict(set)
_fallback_active_flow_runs: Dict[str, set] = defaultdict(set)
_fallback_failure_state: Dict[str, Dict[str, Any]] = {}
_fallback_events: List[Dict[str, Any]] = []
_mode_fallback_redis = False
_mode_legacy_redis_queue = False


def set_mode_fallback_redis(enabled: bool) -> None:
    global _mode_fallback_redis
    _mode_fallback_redis = bool(enabled)


def set_mode_legacy_redis_queue(enabled: bool) -> None:
    global _mode_legacy_redis_queue
    _mode_legacy_redis_queue = bool(enabled)


def _sedang_mode_fallback_redis() -> bool:
    return _mode_fallback_redis


def is_mode_fallback_redis() -> bool:
    return _mode_fallback_redis


def is_mode_legacy_redis_queue() -> bool:
    return _mode_legacy_redis_queue


def _aktifkan_mode_fallback() -> None:
    set_mode_fallback_redis(True)


def _aktifkan_mode_legacy_redis_queue() -> None:
    set_mode_legacy_redis_queue(True)


def _error_stream_tidak_didukung(exc: Exception) -> bool:
    msg = str(exc or "").upper()
    if "UNKNOWN COMMAND" not in msg:
        return False
    return any(cmd in msg for cmd in ("XGROUP", "XADD", "XREADGROUP", "XLEN"))


def _sekarang_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _salin_nilai(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _serialisasi_model(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _ke_dict_event(event: Union[QueueEvent, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(event, QueueEvent):
        return _serialisasi_model(event)
    return dict(event)


def _ke_timestamp(value: Any) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            return time.time()
    return time.time()


def _status_run_aktif(value: Any) -> bool:
    status = str(value or "").strip().lower()
    return status in {"queued", "running"}


def _kunci_active_runs(job_id: str) -> str:
    return f"{JOB_ACTIVE_RUNS_PREFIX}{job_id}"


def _kunci_active_flow_runs(flow_group: str) -> str:
    return f"{FLOW_ACTIVE_RUNS_PREFIX}{flow_group}"


def _kunci_failure_state(job_id: str) -> str:
    return f"{JOB_FAILURE_STATE_PREFIX}{job_id}"


def _kunci_job_spec_versions(job_id: str) -> str:
    return f"{JOB_SPEC_VERSIONS_PREFIX}{job_id}"


def _ke_datetime_utc(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _parse_iso_datetime(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _normalisasi_flow_group(raw: Any) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    return value[:64]


def _ambil_flow_group_dari_run_data(data: Optional[Dict[str, Any]]) -> str:
    if not isinstance(data, dict):
        return ""
    inputs = data.get("inputs")
    if not isinstance(inputs, dict):
        return ""
    return _normalisasi_flow_group(inputs.get("flow_group"))


def _refresh_index_active_runs_fallback(previous_data: Optional[Dict[str, Any]], current_data: Dict[str, Any], run_id: str) -> None:
    if isinstance(previous_data, dict):
        prev_job_id = str(previous_data.get("job_id") or "").strip()
        prev_status = previous_data.get("status")
        if prev_job_id and _status_run_aktif(prev_status):
            _fallback_active_runs[prev_job_id].discard(run_id)
        prev_flow_group = _ambil_flow_group_dari_run_data(previous_data)
        if prev_flow_group and _status_run_aktif(prev_status):
            _fallback_active_flow_runs[prev_flow_group].discard(run_id)

    job_id = str(current_data.get("job_id") or "").strip()
    flow_group = _ambil_flow_group_dari_run_data(current_data)
    status_aktif = _status_run_aktif(current_data.get("status"))

    if job_id:
        if status_aktif:
            _fallback_active_runs[job_id].add(run_id)
        else:
            _fallback_active_runs[job_id].discard(run_id)

    if flow_group and status_aktif:
        _fallback_active_flow_runs[flow_group].add(run_id)
    elif flow_group:
        _fallback_active_flow_runs[flow_group].discard(run_id)


async def _refresh_index_active_runs_redis(previous_data: Optional[Dict[str, Any]], current_data: Dict[str, Any], run_id: str) -> None:
    if isinstance(previous_data, dict):
        prev_job_id = str(previous_data.get("job_id") or "").strip()
        prev_status = previous_data.get("status")
        if prev_job_id and _status_run_aktif(prev_status):
            await redis_client.srem(_kunci_active_runs(prev_job_id), run_id)
        prev_flow_group = _ambil_flow_group_dari_run_data(previous_data)
        if prev_flow_group and _status_run_aktif(prev_status):
            await redis_client.srem(_kunci_active_flow_runs(prev_flow_group), run_id)

    job_id = str(current_data.get("job_id") or "").strip()
    flow_group = _ambil_flow_group_dari_run_data(current_data)
    status_aktif = _status_run_aktif(current_data.get("status"))

    if job_id:
        if status_aktif:
            await redis_client.sadd(_kunci_active_runs(job_id), run_id)
        else:
            await redis_client.srem(_kunci_active_runs(job_id), run_id)

    if flow_group and status_aktif:
        await redis_client.sadd(_kunci_active_flow_runs(flow_group), run_id)
    elif flow_group:
        await redis_client.srem(_kunci_active_flow_runs(flow_group), run_id)


def _id_pesan_fallback_berikutnya() -> str:
    global _fallback_stream_seq
    _fallback_stream_seq += 1
    return f"{int(time.time() * 1000)}-{_fallback_stream_seq}"


async def init_queue():
    """Initialize Redis streams and consumer group."""
    if _sedang_mode_fallback_redis():
        return
    if is_mode_legacy_redis_queue():
        return

    try:
        await redis_client.xgroup_create(name=STREAM_JOBS, groupname=CG_WORKERS, id="$", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" in str(exc):
            return
        if _error_stream_tidak_didukung(exc):
            _aktifkan_mode_legacy_redis_queue()
            return
        raise
    except RedisError:
        _aktifkan_mode_fallback()
        # Fallback mode: no setup required.
        return


async def enqueue_job(event: Union[QueueEvent, Dict[str, Any]]) -> str:
    """Enqueue a job to the stream."""
    event_data = _ke_dict_event(event)
    event_data["enqueued_at"] = _sekarang_iso()

    if _sedang_mode_fallback_redis():
        message_id = _id_pesan_fallback_berikutnya()
        _fallback_stream.append({"id": message_id, "data": _salin_nilai(event_data)})
        return message_id

    if is_mode_legacy_redis_queue():
        try:
            message_id = _id_pesan_fallback_berikutnya()
            await redis_client.rpush(LIST_JOBS, json.dumps(event_data))
            return message_id
        except RedisError:
            _aktifkan_mode_fallback()
            message_id = _id_pesan_fallback_berikutnya()
            _fallback_stream.append({"id": message_id, "data": _salin_nilai(event_data)})
            return message_id

    try:
        return await redis_client.xadd(STREAM_JOBS, {"data": json.dumps(event_data)})
    except ResponseError as exc:
        if _error_stream_tidak_didukung(exc):
            _aktifkan_mode_legacy_redis_queue()
            try:
                message_id = _id_pesan_fallback_berikutnya()
                await redis_client.rpush(LIST_JOBS, json.dumps(event_data))
                return message_id
            except RedisError:
                _aktifkan_mode_fallback()
                message_id = _id_pesan_fallback_berikutnya()
                _fallback_stream.append({"id": message_id, "data": _salin_nilai(event_data)})
                return message_id
        raise
    except RedisError:
        _aktifkan_mode_fallback()
        message_id = _id_pesan_fallback_berikutnya()
        _fallback_stream.append({"id": message_id, "data": _salin_nilai(event_data)})
        return message_id


async def dequeue_job(worker_id: str) -> Optional[Dict[str, Any]]:
    """Dequeue a job from the stream for a worker."""
    if _sedang_mode_fallback_redis():
        if not _fallback_stream:
            return None
        item = _fallback_stream.pop(0)
        return {"message_id": item["id"], "data": _salin_nilai(item["data"])}

    if is_mode_legacy_redis_queue():
        try:
            row = await redis_client.blpop(LIST_JOBS, timeout=1)
            if not row:
                return None
            payload = row[1] if isinstance(row, (list, tuple)) and len(row) > 1 else None
            if not payload:
                return None
            data = json.loads(payload)
            return {"message_id": _id_pesan_fallback_berikutnya(), "data": data}
        except RedisTimeoutError:
            # Blocking pop may timeout when queue is empty; keep polling.
            return None
        except RedisError:
            _aktifkan_mode_fallback()
            if not _fallback_stream:
                return None
            item = _fallback_stream.pop(0)
            return {"message_id": item["id"], "data": _salin_nilai(item["data"])}

    try:
        result = await redis_client.xreadgroup(
            groupname=CG_WORKERS,
            consumername=worker_id,
            streams={STREAM_JOBS: ">"},
            count=1,
            block=1000,
        )
        if not result:
            return None

        _, messages = result[0]
        if not messages:
            return None

        message_id, message_data = messages[0]
        data = json.loads(message_data["data"])
        await redis_client.xack(STREAM_JOBS, CG_WORKERS, message_id)
        return {"message_id": message_id, "data": data}
    except RedisTimeoutError:
        # Read timeout on blocking stream read should behave like no data.
        return None
    except ResponseError as exc:
        if _error_stream_tidak_didukung(exc):
            _aktifkan_mode_legacy_redis_queue()
            return await dequeue_job(worker_id)
        raise
    except RedisError:
        _aktifkan_mode_fallback()
        if not _fallback_stream:
            return None
        item = _fallback_stream.pop(0)
        return {"message_id": item["id"], "data": _salin_nilai(item["data"])}


async def schedule_delayed_job(event: Union[QueueEvent, Dict[str, Any]], delay_seconds: int):
    """Schedule a job to be processed after a delay."""
    score = int(time.time()) + max(0, delay_seconds)
    payload = json.dumps(_ke_dict_event(event))

    if _sedang_mode_fallback_redis():
        _fallback_delayed.append({"score": score, "payload": payload})
        return

    try:
        await redis_client.zadd(ZSET_DELAYED, {payload: score})
    except RedisError:
        _aktifkan_mode_fallback()
        _fallback_delayed.append({"score": score, "payload": payload})


async def get_due_jobs() -> List[Dict[str, Any]]:
    """Get all jobs that are due (timestamp <= now)."""
    now = int(time.time())

    if _sedang_mode_fallback_redis():
        due_payloads: List[str] = []
        remaining: List[Dict[str, Any]] = []
        for item in _fallback_delayed:
            if int(item["score"]) <= now:
                due_payloads.append(item["payload"])
            else:
                remaining.append(item)
        _fallback_delayed[:] = remaining
        return [json.loads(payload) for payload in due_payloads]

    try:
        rows = await redis_client.zrangebyscore(ZSET_DELAYED, min=0, max=now, withscores=True)
        if not rows:
            return []

        payloads = [row[0] for row in rows]
        await redis_client.zrem(ZSET_DELAYED, *payloads)
        return [json.loads(payload) for payload in payloads]
    except RedisError:
        _aktifkan_mode_fallback()
        due_payloads: List[str] = []
        remaining: List[Dict[str, Any]] = []
        for item in _fallback_delayed:
            if int(item["score"]) <= now:
                due_payloads.append(item["payload"])
            else:
                remaining.append(item)
        _fallback_delayed[:] = remaining
        return [json.loads(payload) for payload in due_payloads]


def _buat_job_spec_version(
    job_id: str,
    spec: Dict[str, Any],
    *,
    source: str = "",
    actor: str = "",
    note: str = "",
) -> Dict[str, Any]:
    return {
        "version_id": f"v_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}",
        "job_id": str(job_id or "").strip(),
        "created_at": _sekarang_iso(),
        "source": str(source or "").strip(),
        "actor": str(actor or "").strip(),
        "note": str(note or "").strip(),
        "spec": _salin_nilai(spec),
    }


async def append_job_spec_version(
    job_id: str,
    spec: Dict[str, Any],
    *,
    source: str = "",
    actor: str = "",
    note: str = "",
    max_versions: int = JOB_SPEC_VERSIONS_MAX,
) -> Dict[str, Any]:
    row = _buat_job_spec_version(job_id, spec, source=source, actor=actor, note=note)
    key = _kunci_job_spec_versions(job_id)
    batas = max(1, int(max_versions))

    if _sedang_mode_fallback_redis():
        rows = _fallback_job_spec_versions[job_id]
        rows.insert(0, _salin_nilai(row))
        del rows[batas:]
        return row

    try:
        await redis_client.lpush(key, json.dumps(row))
        await redis_client.ltrim(key, 0, batas - 1)
    except RedisError:
        _aktifkan_mode_fallback()
        rows = _fallback_job_spec_versions[job_id]
        rows.insert(0, _salin_nilai(row))
        del rows[batas:]
    return row


async def list_job_spec_versions(job_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    safe_limit = max(1, int(limit))

    if _sedang_mode_fallback_redis():
        rows = _fallback_job_spec_versions.get(job_id, [])
        return [_salin_nilai(row) for row in rows[:safe_limit]]

    try:
        raw_rows = await redis_client.lrange(_kunci_job_spec_versions(job_id), 0, safe_limit - 1)
        rows: List[Dict[str, Any]] = []
        for item in raw_rows:
            row = json.loads(item)
            if isinstance(row, dict):
                rows.append(row)
        return rows
    except RedisError:
        _aktifkan_mode_fallback()
        rows = _fallback_job_spec_versions.get(job_id, [])
        return [_salin_nilai(row) for row in rows[:safe_limit]]


async def get_job_spec_version(job_id: str, version_id: str, limit_scan: int = 500) -> Optional[Dict[str, Any]]:
    target_id = str(version_id or "").strip()
    if not target_id:
        return None

    rows = await list_job_spec_versions(job_id, limit=max(1, int(limit_scan)))
    for row in rows:
        if str(row.get("version_id") or "").strip() == target_id:
            return row
    return None


async def rollback_job_spec_to_version(
    job_id: str,
    version_id: str,
    *,
    source: str = "rollback",
    actor: str = "",
    note: str = "",
) -> Optional[Dict[str, Any]]:
    row = await get_job_spec_version(job_id, version_id)
    if not row:
        return None

    spec = row.get("spec")
    if not isinstance(spec, dict):
        return None

    rollback_note = str(note or "").strip() or f"rollback_to:{version_id}"
    await save_job_spec(
        job_id,
        spec,
        source=source,
        actor=actor,
        note=rollback_note,
        save_version=True,
    )
    return await get_job_spec(job_id)


async def save_job_spec(
    job_id: str,
    spec: Dict[str, Any],
    *,
    source: str = "",
    actor: str = "",
    note: str = "",
    save_version: bool = True,
):
    """Save job specification to Redis."""
    if _sedang_mode_fallback_redis():
        _fallback_job_specs[job_id] = _salin_nilai(spec)
        _fallback_job_all.add(job_id)
        if save_version:
            await append_job_spec_version(job_id, spec, source=source, actor=actor, note=note)
        return

    try:
        await redis_client.set(f"{JOB_SPEC_PREFIX}{job_id}", json.dumps(spec))
        await redis_client.sadd(JOB_ALL_SET, job_id)
        if save_version:
            await append_job_spec_version(job_id, spec, source=source, actor=actor, note=note)
    except RedisError:
        _aktifkan_mode_fallback()
        _fallback_job_specs[job_id] = _salin_nilai(spec)
        _fallback_job_all.add(job_id)
        if save_version:
            await append_job_spec_version(job_id, spec, source=source, actor=actor, note=note)


async def get_job_spec(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job specification from Redis."""
    if _sedang_mode_fallback_redis():
        spec = _fallback_job_specs.get(job_id)
        return _salin_nilai(spec) if spec else None

    try:
        payload = await redis_client.get(f"{JOB_SPEC_PREFIX}{job_id}")
        if not payload:
            return None
        return json.loads(payload)
    except RedisError:
        _aktifkan_mode_fallback()
        spec = _fallback_job_specs.get(job_id)
        return _salin_nilai(spec) if spec else None


async def list_job_specs() -> List[Dict[str, Any]]:
    """Get all stored job specs."""
    if _sedang_mode_fallback_redis():
        job_ids = sorted(_fallback_job_all)
    else:
        try:
            job_ids = sorted(await redis_client.smembers(JOB_ALL_SET))
        except RedisError:
            _aktifkan_mode_fallback()
            job_ids = sorted(_fallback_job_all)

    specs: List[Dict[str, Any]] = []
    for job_id in job_ids:
        spec = await get_job_spec(job_id)
        if spec:
            specs.append(spec)
    return specs


async def enable_job(job_id: str):
    """Mark job as enabled."""
    if _sedang_mode_fallback_redis():
        _fallback_job_enabled.add(job_id)
        return

    try:
        await redis_client.sadd(JOB_ENABLED_SET, job_id)
    except RedisError:
        _aktifkan_mode_fallback()
        _fallback_job_enabled.add(job_id)


async def disable_job(job_id: str):
    """Mark job as disabled."""
    if _sedang_mode_fallback_redis():
        _fallback_job_enabled.discard(job_id)
        return

    try:
        await redis_client.srem(JOB_ENABLED_SET, job_id)
    except RedisError:
        _aktifkan_mode_fallback()
        _fallback_job_enabled.discard(job_id)


async def is_job_enabled(job_id: str) -> bool:
    """Check if a job is enabled."""
    if _sedang_mode_fallback_redis():
        return job_id in _fallback_job_enabled

    try:
        return bool(await redis_client.sismember(JOB_ENABLED_SET, job_id))
    except RedisError:
        _aktifkan_mode_fallback()
        return job_id in _fallback_job_enabled


async def list_enabled_job_ids() -> List[str]:
    """Get all enabled job IDs."""
    if _sedang_mode_fallback_redis():
        return sorted(_fallback_job_enabled)

    try:
        return sorted(await redis_client.smembers(JOB_ENABLED_SET))
    except RedisError:
        _aktifkan_mode_fallback()
        return sorted(_fallback_job_enabled)


async def save_run(run: Run):
    """Save run status to Redis."""
    run_data = _serialisasi_model(run)
    score = _ke_timestamp(run_data.get("scheduled_at"))

    if _sedang_mode_fallback_redis():
        previous = _fallback_runs.get(run.run_id)
        _fallback_runs[run.run_id] = _salin_nilai(run_data)
        _fallback_run_scores[run.run_id] = score
        _refresh_index_active_runs_fallback(previous, run_data, run.run_id)
        return

    try:
        previous_payload = await redis_client.get(f"{RUN_PREFIX}{run.run_id}")
        previous = json.loads(previous_payload) if previous_payload else None
        await redis_client.set(f"{RUN_PREFIX}{run.run_id}", json.dumps(run_data))
        await redis_client.zadd(ZSET_RUNS, {run.run_id: score})
        await _refresh_index_active_runs_redis(previous, run_data, run.run_id)
    except RedisError:
        _aktifkan_mode_fallback()
        previous = _fallback_runs.get(run.run_id)
        _fallback_runs[run.run_id] = _salin_nilai(run_data)
        _fallback_run_scores[run.run_id] = score
        _refresh_index_active_runs_fallback(previous, run_data, run.run_id)


async def get_run(run_id: str) -> Optional[Run]:
    """Get run status from Redis."""
    if _sedang_mode_fallback_redis():
        payload = _fallback_runs.get(run_id)
        if not payload:
            return None
        return Run(**_salin_nilai(payload))

    try:
        payload = await redis_client.get(f"{RUN_PREFIX}{run_id}")
        if not payload:
            return None
        return Run(**json.loads(payload))
    except RedisError:
        _aktifkan_mode_fallback()
        payload = _fallback_runs.get(run_id)
        if not payload:
            return None
        return Run(**_salin_nilai(payload))


async def list_runs(
    limit: int = 50,
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = 0,
    search: Optional[str] = None,
) -> List[Run]:
    """List runs ordered by latest schedule time."""
    page_limit = max(int(limit), 0)
    page_offset = max(int(offset), 0)
    if page_limit == 0:
        return []

    page_end = page_offset + page_limit
    if page_end <= 0:
        return []

    normalized_job_id = str(job_id or "").strip()
    normalized_status = str(status or "").strip().lower()
    normalized_search = str(search or "").strip().lower()

    def _run_match(run: Run) -> bool:
        if normalized_job_id and run.job_id != normalized_job_id:
            return False
        if normalized_status:
            run_status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if str(run_status or "").strip().lower() != normalized_status:
                return False
        if normalized_search:
            run_id_text = str(run.run_id or "").lower()
            job_id_text = str(run.job_id or "").lower()
            if normalized_search not in run_id_text and normalized_search not in job_id_text:
                return False
        return True

    scan_limit = max(page_limit * 4, 200)
    runs: List[Run] = []

    if _sedang_mode_fallback_redis():
        ordered = sorted(_fallback_run_scores.items(), key=lambda item: item[1], reverse=True)
        run_ids = [run_id for run_id, _ in ordered]
        for run_id in run_ids:
            run = await get_run(run_id)
            if not run:
                continue
            if not _run_match(run):
                continue
            runs.append(run)
            if len(runs) >= page_end:
                break
    else:
        try:
            cursor = 0
            while len(runs) < page_end:
                batch = await redis_client.zrevrange(ZSET_RUNS, cursor, cursor + scan_limit - 1)
                if not batch:
                    break

                for run_id in batch:
                    run = await get_run(run_id)
                    if not run:
                        continue
                    if not _run_match(run):
                        continue
                    runs.append(run)
                    if len(runs) >= page_end:
                        break

                if len(batch) < scan_limit:
                    break
                cursor += len(batch)
        except RedisError:
            _aktifkan_mode_fallback()
            return await list_runs(
                limit=page_limit,
                job_id=normalized_job_id or None,
                status=normalized_status or None,
                offset=page_offset,
                search=normalized_search or None,
            )

    return runs[page_offset:page_end]


async def add_run_to_job_history(job_id: str, run_id: str, max_history: int = 50):
    """Add run_id to job's run history list."""
    if _sedang_mode_fallback_redis():
        rows = _fallback_job_runs[job_id]
        if not rows or rows[0] != run_id:
            rows.insert(0, run_id)
        del rows[max_history:]
        return

    try:
        key = f"{JOB_RUNS_PREFIX}{job_id}"
        head = await redis_client.lindex(key, 0)
        if head != run_id:
            await redis_client.lpush(key, run_id)
            await redis_client.ltrim(key, 0, max_history - 1)
    except RedisError:
        _aktifkan_mode_fallback()
        rows = _fallback_job_runs[job_id]
        if not rows or rows[0] != run_id:
            rows.insert(0, run_id)
        del rows[max_history:]


async def get_job_run_ids(job_id: str, limit: int = 20) -> List[str]:
    """Get recent run IDs for a job."""
    if _sedang_mode_fallback_redis():
        return list(_fallback_job_runs.get(job_id, []))[:limit]

    try:
        return await redis_client.lrange(f"{JOB_RUNS_PREFIX}{job_id}", 0, limit - 1)
    except RedisError:
        _aktifkan_mode_fallback()
        return list(_fallback_job_runs.get(job_id, []))[:limit]


async def get_queue_metrics() -> Dict[str, int]:
    """Get queue metrics for dashboard."""
    if _sedang_mode_fallback_redis():
        return {"depth": len(_fallback_stream), "delayed": len(_fallback_delayed)}

    if is_mode_legacy_redis_queue():
        try:
            depth = await redis_client.llen(LIST_JOBS)
            delayed = await redis_client.zcard(ZSET_DELAYED)
            return {"depth": int(depth), "delayed": int(delayed)}
        except RedisError:
            _aktifkan_mode_fallback()
            return {"depth": len(_fallback_stream), "delayed": len(_fallback_delayed)}

    try:
        delayed = await redis_client.zcard(ZSET_DELAYED)

        # Prefer consumer-group backlog (pending + lag) instead of XLEN, because XLEN
        # is cumulative and does not represent current queue depth on stream mode.
        depth: Optional[int] = None
        groups = await redis_client.xinfo_groups(STREAM_JOBS)
        for group in groups or []:
            if isinstance(group, dict):
                name_raw = group.get("name")
                pending_raw = group.get("pending", 0)
                lag_raw = group.get("lag", 0)
            else:
                # Some Redis clients may return tuple-like rows.
                continue

            name = name_raw.decode() if isinstance(name_raw, (bytes, bytearray)) else str(name_raw)
            if name != CG_WORKERS:
                continue

            try:
                pending = int(pending_raw or 0)
            except Exception:
                pending = 0
            try:
                lag = int(lag_raw or 0)
            except Exception:
                lag = 0

            depth = max(0, pending + lag)
            break

        if depth is None:
            # Fallback when group info is unavailable.
            depth = int(await redis_client.xlen(STREAM_JOBS))

        return {"depth": int(depth), "delayed": int(delayed)}
    except ResponseError as exc:
        if _error_stream_tidak_didukung(exc):
            _aktifkan_mode_legacy_redis_queue()
            return await get_queue_metrics()
        raise
    except RedisError:
        _aktifkan_mode_fallback()
        return {"depth": len(_fallback_stream), "delayed": len(_fallback_delayed)}


async def has_active_runs(job_id: str) -> bool:
    """Check whether a job currently has queued/running runs."""
    normalized_job_id = job_id.strip()
    if not normalized_job_id:
        return False

    if _sedang_mode_fallback_redis():
        return len(_fallback_active_runs.get(normalized_job_id, set())) > 0

    try:
        return int(await redis_client.scard(_kunci_active_runs(normalized_job_id))) > 0
    except RedisError:
        _aktifkan_mode_fallback()
        return len(_fallback_active_runs.get(normalized_job_id, set())) > 0


async def count_active_runs_for_flow_group(flow_group: str) -> int:
    normalized_group = _normalisasi_flow_group(flow_group)
    if not normalized_group:
        return 0

    if _sedang_mode_fallback_redis():
        return int(len(_fallback_active_flow_runs.get(normalized_group, set())))

    try:
        return int(await redis_client.scard(_kunci_active_flow_runs(normalized_group)))
    except RedisError:
        _aktifkan_mode_fallback()
        return int(len(_fallback_active_flow_runs.get(normalized_group, set())))


async def get_job_failure_state(job_id: str) -> Dict[str, Any]:
    normalized_job_id = job_id.strip()
    if not normalized_job_id:
        return {
            "job_id": "",
            "consecutive_failures": 0,
            "cooldown_until": None,
            "last_error": None,
            "last_failure_at": None,
            "last_success_at": None,
            "updated_at": _sekarang_iso(),
        }

    if _sedang_mode_fallback_redis():
        row = _fallback_failure_state.get(normalized_job_id)
        if row:
            return _salin_nilai(row)
    else:
        try:
            payload = await redis_client.get(_kunci_failure_state(normalized_job_id))
            if payload:
                row = json.loads(payload)
                if isinstance(row, dict):
                    return row
        except RedisError:
            _aktifkan_mode_fallback()
            row = _fallback_failure_state.get(normalized_job_id)
            if row:
                return _salin_nilai(row)

    return {
        "job_id": normalized_job_id,
        "consecutive_failures": 0,
        "cooldown_until": None,
        "last_error": None,
        "last_failure_at": None,
        "last_success_at": None,
        "updated_at": _sekarang_iso(),
    }


async def record_job_outcome(
    job_id: str,
    *,
    success: bool,
    error: Optional[str] = None,
    failure_threshold: int = 3,
    failure_cooldown_sec: int = 120,
    failure_cooldown_max_sec: int = 3600,
) -> Dict[str, Any]:
    normalized_job_id = job_id.strip()
    if not normalized_job_id:
        raise ValueError("job_id wajib diisi.")

    threshold = max(1, int(failure_threshold))
    cooldown_base = max(10, int(failure_cooldown_sec))
    cooldown_max = max(cooldown_base, int(failure_cooldown_max_sec))

    row = await get_job_failure_state(normalized_job_id)
    sekarang = datetime.now(timezone.utc)

    if success:
        row["consecutive_failures"] = 0
        row["cooldown_until"] = None
        row["last_error"] = None
        row["last_success_at"] = sekarang.isoformat()
    else:
        gagal_beruntun = int(row.get("consecutive_failures") or 0) + 1
        row["consecutive_failures"] = gagal_beruntun
        row["last_failure_at"] = sekarang.isoformat()
        row["last_error"] = (error or "").strip()[:500] or None

        if gagal_beruntun >= threshold:
            level = gagal_beruntun - threshold
            cooldown = min(cooldown_max, cooldown_base * (2 ** level))
            row["cooldown_until"] = datetime.fromtimestamp(
                sekarang.timestamp() + cooldown, tz=timezone.utc
            ).isoformat()

    row["job_id"] = normalized_job_id
    row["updated_at"] = sekarang.isoformat()

    if _sedang_mode_fallback_redis():
        _fallback_failure_state[normalized_job_id] = _salin_nilai(row)
        return row

    try:
        await redis_client.set(_kunci_failure_state(normalized_job_id), json.dumps(row))
    except RedisError:
        _aktifkan_mode_fallback()
        _fallback_failure_state[normalized_job_id] = _salin_nilai(row)

    return row


async def get_job_cooldown_remaining(job_id: str) -> int:
    row = await get_job_failure_state(job_id)
    cooldown_until = row.get("cooldown_until")
    if not cooldown_until:
        return 0

    deadline = _ke_datetime_utc(cooldown_until)
    remaining = int((deadline - datetime.now(timezone.utc)).total_seconds())
    return max(0, remaining)


async def append_event(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Append event to timeline."""
    event = {
        "id": str(uuid.uuid4()),
        "type": event_type,
        "timestamp": _sekarang_iso(),
        "data": data,
    }

    if _sedang_mode_fallback_redis():
        _fallback_events.insert(0, _salin_nilai(event))
        del _fallback_events[EVENTS_MAX:]
        return event

    try:
        await redis_client.lpush(EVENTS_LOG, json.dumps(event))
        await redis_client.ltrim(EVENTS_LOG, 0, EVENTS_MAX - 1)
    except RedisError:
        _aktifkan_mode_fallback()
        _fallback_events.insert(0, _salin_nilai(event))
        del _fallback_events[EVENTS_MAX:]
    return event


async def get_events(limit: int = 200, since: Optional[str] = None, offset: int = 0) -> List[Dict[str, Any]]:
    """Get latest events in ascending time order."""
    page_limit = max(int(limit), 0)
    page_offset = max(int(offset), 0)
    if page_limit == 0:
        return []

    page_end = page_offset + page_limit
    if page_end <= 0:
        return []

    since_dt = _parse_iso_datetime(since)

    def _event_match_since(row: Dict[str, Any]) -> bool:
        if since_dt is None:
            return True
        return _ke_datetime_utc(row.get("timestamp")).astimezone(timezone.utc) > since_dt

    def _finalize(result_desc: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        selected = result_desc[page_offset:page_end]
        selected.reverse()
        return selected

    events_desc: List[Dict[str, Any]] = []

    if _sedang_mode_fallback_redis():
        for row in _fallback_events:
            event = _salin_nilai(row)
            if not _event_match_since(event):
                if since_dt is not None:
                    break
                continue
            events_desc.append(event)
            if len(events_desc) >= page_end:
                break
        return _finalize(events_desc)
    else:
        try:
            scan_limit = max(page_limit * 4, 200)
            cursor = 0
            while True:
                rows = await redis_client.lrange(EVENTS_LOG, cursor, cursor + scan_limit - 1)
                if not rows:
                    break

                stop_scan = False
                for raw in rows:
                    event = json.loads(raw)
                    if not _event_match_since(event):
                        if since_dt is not None:
                            stop_scan = True
                            break
                        continue
                    events_desc.append(event)
                    if len(events_desc) >= page_end:
                        stop_scan = True
                        break

                if stop_scan:
                    break
                if len(rows) < scan_limit:
                    break
                cursor += len(rows)
        except RedisError:
            _aktifkan_mode_fallback()
            return await get_events(limit=page_limit, since=since, offset=page_offset)

    return _finalize(events_desc)
