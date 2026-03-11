import asyncio
import inspect
import json
import os
import re
import threading
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from app.core.integration_configs import get_integration_account, list_integration_accounts
from app.core.models import JobSpec, RetryPolicy, Schedule
from app.services.api.planner import PlannerJob, PlannerRequest, PlannerResponse, build_plan_from_prompt


class PlannerAiRequest(PlannerRequest):
    force_rule_based: bool = False
    model_id: Optional[str] = None
    ai_provider: str = "auto"
    ai_account_id: str = "default"
    # Legacy field kept for backward compatibility with existing clients.
    openai_account_id: str = "default"
    max_steps: int = Field(default=4, ge=1, le=12)


class PlannerAiCredentials(BaseModel):
    provider: str
    account_id: str
    model_id: str
    api_key: str = ""
    api_base: Optional[str] = None


ALLOWED_JOB_TYPES: Set[str] = {
    "monitor.channel",
    "report.daily",
    "backup.export",
    "agent.workflow",
}

DEFAULT_TIMEOUT_MS: Dict[str, int] = {
    "monitor.channel": 15000,
    "report.daily": 45000,
    "backup.export": 120000,
    "agent.workflow": 90000,
}

DEFAULT_RETRY: Dict[str, RetryPolicy] = {
    "monitor.channel": RetryPolicy(max_retry=5, backoff_sec=[1, 2, 5, 10, 30]),
    "report.daily": RetryPolicy(max_retry=3, backoff_sec=[5, 10, 30]),
    "backup.export": RetryPolicy(max_retry=2, backoff_sec=[10, 30]),
    "agent.workflow": RetryPolicy(max_retry=1, backoff_sec=[2, 5]),
}

JOB_TYPE_ALIAS_TO_CANONICAL: Dict[str, str] = {
    "monitor": "monitor.channel",
    "channel": "monitor.channel",
    "telegram": "monitor.channel",
    "whatsapp": "monitor.channel",
    "pantau": "monitor.channel",
    "report": "report.daily",
    "laporan": "report.daily",
    "harian": "report.daily",
    "daily": "report.daily",
    "backup": "backup.export",
    "export": "backup.export",
    "cadangan": "backup.export",
    "workflow": "agent.workflow",
    "agent": "agent.workflow",
    "alur": "agent.workflow",
}

PROVIDER_CHAIN_DEFAULT: List[str] = ["openai", "ollama"]
DEFAULT_MODEL_PER_PROVIDER: Dict[str, str] = {
    "openai": "openai/gpt-4o-mini",
    "ollama": "ollama/qwen3:8b",
}

_PLANNER_AI_SEMAPHORE: Optional[asyncio.Semaphore] = None
_PLANNER_AI_SEMAPHORE_SIZE: int = 0


def _planner_ai_timeout_sec() -> int:
    raw = str(os.getenv("PLANNER_AI_TIMEOUT_SEC") or "45").strip()
    try:
        return max(5, min(300, int(raw)))
    except Exception:
        return 45


def _planner_ai_max_concurrent() -> int:
    raw = str(os.getenv("PLANNER_AI_MAX_CONCURRENT") or "1").strip()
    try:
        return max(1, min(16, int(raw)))
    except Exception:
        return 1


def _planner_ai_queue_wait_sec() -> float:
    raw = str(os.getenv("PLANNER_AI_QUEUE_WAIT_SEC") or "1.5").strip()
    try:
        return max(0.1, min(30.0, float(raw)))
    except Exception:
        return 1.5


def _planner_ai_release_grace_sec() -> float:
    raw = str(os.getenv("PLANNER_AI_RELEASE_GRACE_SEC") or "30").strip()
    try:
        return max(5.0, min(600.0, float(raw)))
    except Exception:
        return 30.0


def _get_planner_ai_semaphore() -> Tuple[asyncio.Semaphore, int]:
    global _PLANNER_AI_SEMAPHORE, _PLANNER_AI_SEMAPHORE_SIZE
    size = _planner_ai_max_concurrent()
    if _PLANNER_AI_SEMAPHORE is None or _PLANNER_AI_SEMAPHORE_SIZE != size:
        _PLANNER_AI_SEMAPHORE = asyncio.Semaphore(size)
        _PLANNER_AI_SEMAPHORE_SIZE = size
    return _PLANNER_AI_SEMAPHORE, size


def _defer_semaphore_release(
    worker_task: "asyncio.Future[Any]",
    semaphore: asyncio.Semaphore,
    grace_sec: float,
) -> None:
    loop = asyncio.get_running_loop()
    released = False

    def _release_once() -> None:
        nonlocal released
        if released:
            return
        released = True
        semaphore.release()

    def _handle_worker_done(_task: "asyncio.Task[Any]") -> None:
        timeout_handle.cancel()
        _release_once()

    # Lepas slot segera saat worker background selesai.
    worker_task.add_done_callback(_handle_worker_done)
    # Tetap lepaskan slot setelah grace jika worker menggantung terlalu lama.
    timeout_handle = loop.call_later(grace_sec, _release_once)


def _jalankan_di_daemon_thread(
    func: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> "asyncio.Future[Any]":
    loop = asyncio.get_running_loop()
    future: "asyncio.Future[Any]" = loop.create_future()

    def _set_result(result: Any) -> None:
        if not future.done():
            future.set_result(result)

    def _set_exception(exc: BaseException) -> None:
        if not future.done():
            future.set_exception(exc)

    def _runner() -> None:
        try:
            result = func(*args, **kwargs)
        except BaseException as exc:  # pragma: no cover - background handoff
            if loop.is_closed():
                return
            loop.call_soon_threadsafe(_set_exception, exc)
            return

        if loop.is_closed():
            return
        loop.call_soon_threadsafe(_set_result, result)

    worker = threading.Thread(
        target=_runner,
        name="planner-ai-worker",
        daemon=True,
    )
    worker.start()
    return future


def _normalisasi_teks(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _buat_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return slug or "job"


def _pastikan_id_job_unik(base_id: str, used_ids: Set[str]) -> str:
    candidate = base_id
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base_id}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def _hapus_duplikat(items: List[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        output.append(cleaned)
    return output


LOW_SIGNAL_AI_MESSAGE_PATTERNS: Tuple[str, ...] = (
    "ai planner is running locally",
    "ai planner is set up for local use",
    "ai planner is ready for execution",
    "the local environment is set up",
    "the ai planner has access to the necessary libraries",
)


def _hapus_pesan_low_signal(items: List[str]) -> List[str]:
    output: List[str] = []
    for item in items:
        cleaned = str(item or "").strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if any(pattern in lowered for pattern in LOW_SIGNAL_AI_MESSAGE_PATTERNS):
            continue
        output.append(cleaned)
    return output


def _lokalisasi_pesan(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    lowered = cleaned.lower().strip()

    direct_map: Dict[str, str] = {
        "telegram is running and accessible.": "Telegram aktif dan dapat diakses.",
        "ensure telegram is running and accessible.": "Pastikan Telegram aktif dan dapat diakses.",
        "ensure the channel is active and accessible.": "Pastikan channel aktif dan dapat diakses.",
        "verify the api key is valid and accessible.": "Pastikan kunci API valid dan dapat diakses.",
        "ensure the telegram account is active and has access to the channel.": (
            "Pastikan akun Telegram aktif dan memiliki akses ke channel."
        ),
        "ensure the user has the necessary permissions to send reports.": (
            "Pastikan pengguna memiliki izin untuk mengirim laporan."
        ),
        "ensure the user has the necessary permissions to view messages.": (
            "Pastikan pengguna memiliki izin untuk melihat pesan."
        ),
        "ensure the user has the necessary permissions to generate reports.": (
            "Pastikan pengguna memiliki izin untuk membuat laporan."
        ),
    }

    if lowered in direct_map:
        return direct_map[lowered]

    result = cleaned

    replacements: List[Tuple[str, str]] = [
        (r"(?i)\bthe user has the necessary permissions to\b", "pengguna memiliki izin untuk"),
        (r"(?i)\bthe user has necessary permissions to\b", "pengguna memiliki izin untuk"),
        (r"(?i)\bsend reports\b", "mengirim laporan"),
        (r"(?i)\bview messages\b", "melihat pesan"),
        (r"(?i)\bgenerate reports\b", "membuat laporan"),
        (r"(?i)\bapi key\b", "kunci API"),
        (r"(?i)\btelegram\b", "Telegram"),
        (r"(?i)\bchannel\b", "channel"),
        (r"(?i)\bis running and accessible\b", "aktif dan dapat diakses"),
        (r"(?i)\bis active and accessible\b", "aktif dan dapat diakses"),
        (r"(?i)\bhas access to the channel\b", "memiliki akses ke channel"),
    ]
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result)

    ensure_match = re.match(r"(?i)^\s*ensure\s+(.+?)\.?\s*$", result)
    if ensure_match:
        clause = ensure_match.group(1).strip()
        if clause:
            return f"Pastikan {clause}."

    verify_match = re.match(r"(?i)^\s*verify\s+(.+?)\.?\s*$", result)
    if verify_match:
        clause = verify_match.group(1).strip()
        if clause:
            return f"Pastikan {clause}."

    fallback = re.sub(r"\s+", " ", result).strip()
    if not fallback:
        return ""
    if fallback == cleaned:
        return cleaned
    if not fallback.endswith("."):
        fallback += "."
    return fallback[0].upper() + fallback[1:]


def _lokalisasi_kumpulan_pesan(items: List[str]) -> List[str]:
    output: List[str] = []
    for item in items:
        localized = _lokalisasi_pesan(item)
        if localized:
            output.append(localized)
    return output


def _normalisasi_provider(provider: str) -> str:
    cleaned = str(provider or "").strip().lower()
    return cleaned or "auto"


def _normalisasi_model_id(provider: str, model_id: str) -> str:
    cleaned = str(model_id or "").strip()
    if not cleaned:
        return ""
    if "/" in cleaned:
        return cleaned
    if provider == "openai":
        return f"openai/{cleaned}"
    if provider == "ollama":
        return f"ollama/{cleaned}"
    return cleaned


def _ambil_base_url_dari_config(config: Any) -> str:
    if not isinstance(config, dict):
        return ""

    kandidat = [
        config.get("base_url"),
        config.get("api_base"),
        config.get("openai_base_url"),
    ]
    for value in kandidat:
        cleaned = str(value or "").strip()
        if cleaned:
            return cleaned
    return ""


def _ambil_env_int_terbatas(nama: str, default: int, minimum: int, maksimum: int) -> int:
    raw = str(os.getenv(nama) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, min(maksimum, int(raw)))
    except Exception:
        return default


def _normalisasi_ollama_base_url(raw: Optional[str]) -> str:
    base = str(raw or "").strip()
    if not base:
        base = str(os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").strip()
    if not base:
        base = "http://localhost:11434"
    base = base.rstrip("/")
    if base.lower().endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base


def _akun_provider_siapsaji(provider: str, row: Optional[Dict[str, Any]]) -> bool:
    if not row or not isinstance(row, dict):
        return False
    if not bool(row.get("enabled", True)):
        return False
    if provider == "openai":
        return bool(str(row.get("secret") or "").strip())
    return True


def _ekstrak_teks_json(raw: Any) -> Optional[str]:
    if raw is None:
        return None

    if isinstance(raw, dict):
        return json.dumps(raw)

    text = str(raw).strip()
    if not text:
        return None

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    return text[start : end + 1]


def _bangun_prompt_smolagents(
    request: PlannerAiRequest,
    *,
    compact: bool = False,
    prompt_user_override: Optional[str] = None,
) -> str:
    prompt_user = str(prompt_user_override if prompt_user_override is not None else request.prompt).strip()

    if compact:
        return (
            "Kamu adalah planner sistem job backend Python. "
            "Kembalikan HANYA JSON valid dengan schema: "
            "{summary:string, assumptions:string[], warnings:string[], jobs:[{job_id?:string,type:string,reason:string,assumptions:string[],warnings:string[],schedule:object|null,timeout_ms:number,retry_policy:{max_retry:number,backoff_sec:number[]},inputs:object}]}. "
            "Type job yang diizinkan: monitor.channel, report.daily, backup.export, agent.workflow. "
            "Jika data kurang, isi assumptions dan pakai default aman. "
            "Untuk report/backup harian prefer cron.\n"
            f"Prompt user: {prompt_user}\n"
            f"Timezone default: {request.timezone}\n"
            f"Default channel: {request.default_channel}\n"
            f"Default account_id: {request.default_account_id}\n"
        )

    return (
        "Kamu adalah planner sistem job backend Python.\n"
        "Ubah prompt user menjadi rencana job terstruktur dalam JSON valid.\n"
        "Kembalikan HANYA JSON (tanpa markdown, tanpa penjelasan).\n"
        "Schema JSON:\n"
        "{\n"
        '  "summary": "string",\n'
        '  "assumptions": ["string"],\n'
        '  "warnings": ["string"],\n'
        '  "jobs": [\n'
        "    {\n"
        '      "job_id": "optional-string",\n'
        '      "type": "monitor.channel|report.daily|backup.export|agent.workflow",\n'
        '      "reason": "string",\n'
        '      "assumptions": ["string"],\n'
        '      "warnings": ["string"],\n'
        '      "schedule": {"interval_sec": 30} atau {"cron": "0 7 * * *"} atau null (agent.workflow),\n'
        '      "timeout_ms": 15000,\n'
        '      "retry_policy": {"max_retry": 3, "backoff_sec": [1,2,5]},\n'
        '      "inputs": {"channel":"telegram","account_id":"bot_a01"} atau {"prompt":"instruksi user"}\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"Prompt user: {prompt_user}\n"
        f"Timezone default: {request.timezone}\n"
        f"Default channel: {request.default_channel}\n"
        f"Default account_id: {request.default_account_id}\n\n"
        "Aturan:\n"
        "1) Gunakan hanya type job yang diizinkan.\n"
        "2) Jika data kurang, isi assumptions dan pakai default aman.\n"
        "3) ID job harus singkat, slug, dan unik.\n"
        "4) Untuk laporan/backup harian, prefer cron.\n"
    )


def _inisialisasi_model_litellm(
    model_class: Any,
    model_id: str,
    api_key: Optional[str],
    api_base: Optional[str] = None,
) -> Any:
    daftar_percobaan: List[Dict[str, Any]] = []

    daftar_nama_model = ["model_id", "model"]
    daftar_nama_base = ["api_base", "base_url"]

    for nama_model in daftar_nama_model:
        kwargs_dasar: Dict[str, Any] = {nama_model: model_id}

        # Prioritaskan kombinasi dengan api_base agar provider lokal
        # (contoh: Ollama dari container) tidak jatuh ke default localhost.
        if api_base:
            for nama_base in daftar_nama_base:
                if api_key:
                    daftar_percobaan.append({**kwargs_dasar, nama_base: api_base, "api_key": api_key})
                daftar_percobaan.append({**kwargs_dasar, nama_base: api_base})

        if api_key:
            daftar_percobaan.append({**kwargs_dasar, "api_key": api_key})

        daftar_percobaan.append(dict(kwargs_dasar))

    errors: List[str] = []
    sudah_dicoba: Set[str] = set()
    for kwargs in daftar_percobaan:
        clean_kwargs = {key: value for key, value in kwargs.items() if value is not None}
        jejak = json.dumps(clean_kwargs, sort_keys=True)
        if jejak in sudah_dicoba:
            continue
        sudah_dicoba.add(jejak)
        try:
            return model_class(**clean_kwargs)
        except Exception as exc:
            errors.append(str(exc))

    raise RuntimeError("Gagal inisialisasi LiteLLMModel: " + " | ".join(errors))


def _buat_code_agent(code_agent_class: Any, model: Any, max_steps: int) -> Any:
    kwargs: Dict[str, Any] = {"tools": [], "model": model}

    try:
        signature = inspect.signature(code_agent_class)
        if "add_base_tools" in signature.parameters:
            kwargs["add_base_tools"] = False
        if "max_steps" in signature.parameters:
            kwargs["max_steps"] = max_steps
    except Exception:
        pass

    return code_agent_class(**kwargs)


async def _pilih_akun_openai_dashboard(account_id: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    return await _pilih_akun_provider_dashboard("openai", account_id)


async def _pilih_akun_provider_dashboard(provider: str, account_id: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    normalized_provider = _normalisasi_provider(provider)
    target_id = str(account_id or "default").strip() or "default"

    try:
        pilihan = await get_integration_account(normalized_provider, target_id, include_secret=True)
    except Exception:
        pilihan = None

    if _akun_provider_siapsaji(normalized_provider, pilihan):
        return pilihan, warnings

    try:
        daftar = await list_integration_accounts(provider=normalized_provider, include_secret=True)
    except Exception:
        daftar = []

    kandidat_akun: List[Dict[str, Any]] = []
    for row in daftar:
        if _akun_provider_siapsaji(normalized_provider, row):
            kandidat_akun.append(row)

    kandidat_akun.sort(key=lambda row: str(row.get("account_id") or ""))
    if kandidat_akun:
        kandidat = kandidat_akun[0]
        kandidat_id = str(kandidat.get("account_id") or "default").strip() or "default"
        if kandidat_id != target_id:
            warnings.append(
                f"Akun {normalized_provider}/{target_id} belum siap. Planner AI memakai akun {normalized_provider}/{kandidat_id}."
            )
        return kandidat, warnings

    return None, warnings


async def resolve_planner_ai_credential_candidates(
    request: PlannerAiRequest,
) -> Tuple[List[PlannerAiCredentials], List[str]]:
    warnings: List[str] = []
    daftar_kandidat: List[PlannerAiCredentials] = []

    provider_request = _normalisasi_provider(request.ai_provider)
    account_target = str(request.ai_account_id or "").strip() or str(request.openai_account_id or "default").strip() or "default"
    model_request = str(request.model_id or "").strip()

    provider_chain = [provider_request] if provider_request != "auto" else ([p for p in (_normalisasi_provider(item) for item in str(os.getenv("PLANNER_AI_PROVIDER_CHAIN") or ",".join(PROVIDER_CHAIN_DEFAULT)).split(",")) if p in ("openai", "ollama")] or list(PROVIDER_CHAIN_DEFAULT))

    for provider in provider_chain:
        butuh_warning = provider_request != "auto" or len(daftar_kandidat) == 0
        akun, warning_akun = await _pilih_akun_provider_dashboard(provider, account_target)
        if butuh_warning:
            warnings.extend(warning_akun)

        if akun:
            config = akun.get("config", {})
            model_dari_config = str(config.get("model_id") or "").strip() if isinstance(config, dict) else ""
            model_id = _normalisasi_model_id(provider, model_request or model_dari_config or DEFAULT_MODEL_PER_PROVIDER.get(provider, ""))
            api_key = str(akun.get("secret") or "").strip()
            api_base = _ambil_base_url_dari_config(config)

            if provider == "ollama":
                if not api_base:
                    api_base = str(os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").strip()
                if not api_key:
                    api_key = str(os.getenv("OLLAMA_API_KEY") or "ollama").strip()

            if model_id:
                daftar_kandidat.append(
                    PlannerAiCredentials(
                        provider=provider,
                        account_id=str(akun.get("account_id") or account_target or "default"),
                        model_id=model_id,
                        api_key=api_key,
                        api_base=api_base or None,
                    )
                )
            continue

        if provider == "openai":
            env_api_key = str(os.getenv("OPENAI_API_KEY") or "").strip()
            if env_api_key:
                model_id = _normalisasi_model_id(
                    "openai",
                    model_request or str(os.getenv("PLANNER_AI_MODEL") or DEFAULT_MODEL_PER_PROVIDER["openai"]).strip(),
                )
                daftar_kandidat.append(
                    PlannerAiCredentials(
                        provider="openai",
                        account_id="env",
                        model_id=model_id,
                        api_key=env_api_key,
                        api_base=str(os.getenv("OPENAI_BASE_URL") or "").strip() or None,
                    )
                )
                if butuh_warning:
                    warnings.append("Token OpenAI diambil dari environment (OPENAI_API_KEY).")
            else:
                if butuh_warning:
                    warnings.append("Akun OpenAI belum siap dan OPENAI_API_KEY belum diisi.")

        if provider == "ollama":
            model_id = _normalisasi_model_id(
                "ollama",
                model_request or str(os.getenv("OLLAMA_MODEL") or DEFAULT_MODEL_PER_PROVIDER["ollama"]).strip(),
            )
            api_base = str(os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").strip()
            api_key = str(os.getenv("OLLAMA_API_KEY") or "ollama").strip()
            daftar_kandidat.append(
                PlannerAiCredentials(
                    provider="ollama",
                    account_id="local",
                    model_id=model_id,
                    api_key=api_key,
                    api_base=api_base,
                )
            )
            if butuh_warning:
                warnings.append("Akun Ollama di dashboard belum siap, memakai konfigurasi lokal default.")

    kandidat_final: List[PlannerAiCredentials] = []
    jejak: Set[str] = set()
    for row in daftar_kandidat:
        signature = f"{row.provider}|{row.account_id}|{row.model_id}|{row.api_base or ''}"
        if signature in jejak:
            continue
        jejak.add(signature)
        kandidat_final.append(row)

    return kandidat_final, _hapus_duplikat(warnings)


async def resolve_planner_ai_credentials(
    request: PlannerAiRequest,
) -> Tuple[str, str, List[str]]:
    kandidat, warnings = await resolve_planner_ai_credential_candidates(request)
    if kandidat:
        return kandidat[0].model_id, kandidat[0].api_key, warnings

    model_id = str(request.model_id or "").strip() or str(os.getenv("PLANNER_AI_MODEL") or DEFAULT_MODEL_PER_PROVIDER["openai"]).strip()
    if not model_id:
        model_id = DEFAULT_MODEL_PER_PROVIDER["openai"]
    model_id = _normalisasi_model_id("openai", model_id)
    api_key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    return model_id, api_key, _hapus_duplikat(warnings)


def _jalankan_ollama_direct(
    request: PlannerAiRequest,
    *,
    model_id: str,
    api_base_override: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    base_url = _normalisasi_ollama_base_url(api_base_override)
    model_name = model_id.split("/", 1)[1] if model_id.startswith("ollama/") else model_id
    timeout_sec = _ambil_env_int_terbatas("PLANNER_AI_OLLAMA_TIMEOUT_SEC", _planner_ai_timeout_sec(), 5, 300)

    payload = {
        "model": model_name,
        "prompt": _bangun_prompt_smolagents(request, compact=True),
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
        },
    }

    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        return None, [f"Eksekusi Ollama direct gagal (HTTP {getattr(exc, 'code', 'error')}): {detail[:500]}"]
    except Exception as exc:
        return None, [f"Eksekusi Ollama direct gagal: {exc}"]

    try:
        raw = json.loads(body)
    except Exception as exc:
        return None, [f"Respons Ollama bukan JSON valid: {exc}"]

    output_text = str(raw.get("response") or "").strip() if isinstance(raw, dict) else ""
    if not output_text and isinstance(raw, dict):
        output_text = json.dumps(raw)

    json_text = _ekstrak_teks_json(output_text)
    if not json_text:
        return None, ["Output Ollama direct tidak berbentuk JSON yang valid."]

    try:
        data = json.loads(json_text)
    except Exception as exc:
        return None, [f"Gagal parse JSON dari output Ollama direct: {exc}"]

    if not isinstance(data, dict):
        return None, ["Payload Ollama direct bukan object JSON."]

    return data, warnings



def _jalankan_smolagents(
    request: PlannerAiRequest,
    *,
    model_id_override: Optional[str] = None,
    api_key_override: Optional[str] = None,
    api_base_override: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    warnings: List[str] = []

    try:
        import smolagents  # type: ignore
    except Exception:
        return None, ["smolagents belum terpasang. Gunakan: pip install smolagents litellm."]

    code_agent_class = getattr(smolagents, "CodeAgent", None)
    model_class = getattr(smolagents, "LiteLLMModel", None)

    if code_agent_class is None or model_class is None:
        return None, ["Versi smolagents tidak menyediakan CodeAgent/LiteLLMModel."]

    model_id = str(
        model_id_override
        or request.model_id
        or os.getenv("PLANNER_AI_MODEL", DEFAULT_MODEL_PER_PROVIDER["openai"])
    ).strip()
    api_key = str(api_key_override or os.getenv("OPENAI_API_KEY") or "").strip()
    api_base = str(api_base_override or os.getenv("PLANNER_AI_BASE_URL") or "").strip()

    if model_id.startswith("openai/") and not api_key:
        return None, [
            "Token OpenAI belum tersedia. Isi Setelan > Akun Integrasi (openai/default) "
            "atau set OPENAI_API_KEY. Planner AI fallback ke rule-based."
        ]

    if model_id.startswith("ollama/"):
        return _jalankan_ollama_direct(
            request,
            model_id=model_id,
            api_base_override=api_base or None,
        )

    try:
        model = _inisialisasi_model_litellm(
            model_class,
            model_id=model_id,
            api_key=api_key,
            api_base=api_base or None,
        )
    except Exception as exc:
        return None, [f"Gagal inisialisasi model AI: {exc}"]

    try:
        agent = _buat_code_agent(code_agent_class, model=model, max_steps=request.max_steps)
        raw_output = agent.run(_bangun_prompt_smolagents(request))
    except Exception as exc:
        return None, [f"Eksekusi smolagents gagal: {exc}"]

    json_text = _ekstrak_teks_json(raw_output)
    if not json_text:
        return None, ["Output AI tidak berbentuk JSON yang valid."]

    try:
        payload = json.loads(json_text)
    except Exception as exc:
        return None, [f"Gagal parse JSON dari output AI: {exc}"]

    if not isinstance(payload, dict):
        return None, ["Payload AI bukan object JSON."]

    return payload, warnings


def _jadwal_dari_teks(raw_text: str) -> Optional[Schedule]:
    text = re.sub(r"\s+", " ", str(raw_text or "").strip().lower())
    if not text:
        return None

    if text in {"none", "null", "manual", "on demand", "ondemand", "sekali"}:
        return None

    if re.match(r"^(\S+\s+){4}\S+$", text):
        try:
            return Schedule(cron=text)
        except Exception:
            return None

    jam = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", text)
    if jam:
        hour = int(jam.group(1))
        minute = int(jam.group(2))
        return Schedule(cron=f"{minute} {hour} * * *")

    pola_interval = [
        (r"(\d+)\s*(detik|sec|second|seconds|s)\b", 1),
        (r"(\d+)\s*(menit|minute|minutes|min|m)\b", 60),
        (r"(\d+)\s*(jam|hour|hours|h)\b", 3600),
    ]
    for pola, pengali in pola_interval:
        match = re.search(pola, text)
        if match:
            nilai = max(1, int(match.group(1))) * pengali
            return Schedule(interval_sec=nilai)

    if any(token in text for token in ["harian", "daily", "tiap hari", "setiap hari"]):
        return Schedule(cron="0 7 * * *")
    if any(token in text for token in ["mingguan", "weekly", "per minggu", "setiap minggu"]):
        return Schedule(cron="0 2 * * 1")

    return None


def _paksa_jadwal(raw: Any, warnings: List[str], index: int) -> Optional[Schedule]:
    if raw is None:
        return None

    if isinstance(raw, (int, float)):
        try:
            return Schedule(interval_sec=max(1, int(raw)))
        except Exception:
            warnings.append(f"Job #{index + 1}: interval schedule tidak valid, pakai default.")
            return None

    if isinstance(raw, str):
        parsed = _jadwal_dari_teks(raw)
        if parsed is not None:
            return parsed
        if raw.strip():
            warnings.append(f"Job #{index + 1}: format schedule string tidak dikenali, pakai default.")
        return None

    if not isinstance(raw, dict):
        warnings.append(f"Job #{index + 1}: schedule tidak valid, pakai default.")
        return None

    cron = raw.get("cron")
    if cron is None:
        cron = raw.get("cron_expr") or raw.get("expression")

    interval_sec = raw.get("interval_sec")
    if interval_sec is None:
        for key in ["interval", "interval_seconds", "every_sec", "every_seconds"]:
            if raw.get(key) is not None:
                interval_sec = raw.get(key)
                break

    if cron is None and interval_sec is None:
        text_candidate = raw.get("text") or raw.get("value") or raw.get("when") or raw.get("time")
        if text_candidate is not None:
            parsed = _jadwal_dari_teks(str(text_candidate))
            if parsed is not None:
                return parsed
        return None

    if isinstance(cron, str):
        cron = cron.strip() or None

    if interval_sec is not None:
        try:
            interval_sec = int(interval_sec)
            if interval_sec <= 0:
                raise ValueError("interval must be positive")
        except Exception:
            warnings.append(f"Job #{index + 1}: interval_sec tidak valid, diabaikan.")
            interval_sec = None

    if cron is None and interval_sec is None:
        return None

    try:
        return Schedule(cron=cron, interval_sec=interval_sec)
    except Exception:
        warnings.append(f"Job #{index + 1}: format schedule tidak valid, pakai default.")
        return None


def _jadwal_default_per_job(job_type: str) -> Optional[Schedule]:
    if job_type == "monitor.channel":
        return Schedule(interval_sec=30)
    if job_type == "report.daily":
        return Schedule(cron="0 7 * * *")
    if job_type == "agent.workflow":
        return None
    return Schedule(cron="0 2 * * *")


def _retry_default(job_type: str) -> RetryPolicy:
    source = DEFAULT_RETRY[job_type]
    return RetryPolicy(max_retry=source.max_retry, backoff_sec=list(source.backoff_sec))


def _normalisasi_job_type_ai(
    raw_job_type: Any,
    item: Dict[str, Any],
    request: PlannerAiRequest,
) -> Tuple[str, Optional[str]]:
    raw = str(raw_job_type or "").strip()
    normalized = raw.lower()

    if normalized in ALLOWED_JOB_TYPES:
        return normalized, None

    mapped = JOB_TYPE_ALIAS_TO_CANONICAL.get(normalized)
    if mapped:
        return mapped, raw

    context_text = " ".join(
        [
            normalized,
            str(item.get("reason") or ""),
            str(item.get("inputs") or ""),
            str(request.prompt or ""),
        ]
    ).lower()

    if any(token in context_text for token in ["telegram", "whatsapp", "channel", "monitor", "pantau"]):
        return "monitor.channel", raw
    if any(token in context_text for token in ["report", "laporan", "harian", "daily"]):
        return "report.daily", raw
    if any(token in context_text for token in ["backup", "export", "cadangan"]):
        return "backup.export", raw
    if any(token in context_text for token in ["workflow", "agent", "alur"]):
        return "agent.workflow", raw

    return raw, None


def _lengkapi_job_dari_intent_prompt(
    request: PlannerAiRequest,
    jobs: List[PlannerJob],
    used_ids: Set[str],
) -> None:
    # Hanya melengkapi intent operasional inti agar output AI model kecil tetap konsisten.
    tipe_yang_boleh_ditambah = {"monitor.channel", "report.daily", "backup.export"}
    if not jobs:
        return

    try:
        rule_plan = build_plan_from_prompt(request)
    except Exception:
        return

    target_types: List[str] = []
    for rule_job in rule_plan.jobs:
        tipe = str(rule_job.job_spec.type or "").strip()
        if tipe in tipe_yang_boleh_ditambah and tipe not in target_types:
            target_types.append(tipe)

    if not target_types:
        return

    existing_types: Set[str] = {str(job.job_spec.type or "").strip() for job in jobs}
    for rule_job in rule_plan.jobs:
        tipe = str(rule_job.job_spec.type or "").strip()
        if tipe not in target_types or tipe in existing_types:
            continue

        copied = rule_job.model_copy(deep=True)
        copied.job_spec.job_id = _pastikan_id_job_unik(_buat_slug(copied.job_spec.job_id), used_ids)
        copied.reason = f"{copied.reason} (dilengkapi dari intent prompt)"
        if isinstance(copied.job_spec.inputs, dict):
            copied.job_spec.inputs["source"] = "planner_prompt_enrichment"

        jobs.append(copied)
        existing_types.add(tipe)


def build_plan_from_ai_payload(request: PlannerAiRequest, payload: Dict[str, Any]) -> PlannerResponse:
    normalized_prompt = _normalisasi_teks(request.prompt)
    assumptions: List[str] = []
    warnings: List[str] = []
    jobs: List[PlannerJob] = []
    used_ids: Set[str] = set()

    assumptions.extend(
        _lokalisasi_kumpulan_pesan(
            _hapus_pesan_low_signal(payload.get("assumptions", []) if isinstance(payload.get("assumptions"), list) else [])
        )
    )
    warnings.extend(
        _lokalisasi_kumpulan_pesan(
            _hapus_pesan_low_signal(payload.get("warnings", []) if isinstance(payload.get("warnings"), list) else [])
        )
    )

    raw_jobs = payload.get("jobs")
    if not isinstance(raw_jobs, list):
        warnings.append("Payload AI tidak memiliki daftar jobs yang valid.")
        raw_jobs = []

    for index, item in enumerate(raw_jobs):
        if not isinstance(item, dict):
            warnings.append(f"Item jobs #{index + 1} bukan object, dilewati.")
            continue

        raw_job_type = str(item.get("type") or "").strip()
        job_type, mapped_from = _normalisasi_job_type_ai(raw_job_type, item, request)
        if raw_job_type and mapped_from is not None and raw_job_type != job_type:
            if raw_job_type.lower() not in JOB_TYPE_ALIAS_TO_CANONICAL:
                warnings.append(
                    f"Job #{index + 1}: type '{raw_job_type}' dinormalisasi menjadi '{job_type}'."
                )
        if job_type not in ALLOWED_JOB_TYPES:
            warnings.append(f"Job #{index + 1}: type '{raw_job_type}' tidak didukung, dilewati.")
            continue

        reason = str(item.get("reason") or f"Dibuat oleh planner AI untuk type {job_type}.")
        item_assumptions = _lokalisasi_kumpulan_pesan(
            _hapus_pesan_low_signal(item.get("assumptions", []) if isinstance(item.get("assumptions"), list) else [])
        )
        item_warnings = _lokalisasi_kumpulan_pesan(
            _hapus_pesan_low_signal(item.get("warnings", []) if isinstance(item.get("warnings"), list) else [])
        )

        if job_type == "agent.workflow":
            schedule = None
        else:
            schedule = _paksa_jadwal(item.get("schedule"), warnings, index) or _jadwal_default_per_job(job_type)

        retry_raw = item.get("retry_policy")
        retry_policy: RetryPolicy
        if isinstance(retry_raw, dict):
            try:
                retry_policy = RetryPolicy(
                    max_retry=int(retry_raw.get("max_retry", DEFAULT_RETRY[job_type].max_retry)),
                    backoff_sec=list(retry_raw.get("backoff_sec", DEFAULT_RETRY[job_type].backoff_sec)),
                )
            except Exception:
                retry_policy = _retry_default(job_type)
                warnings.append(f"Job #{index + 1}: retry_policy tidak valid, pakai default.")
        else:
            retry_policy = _retry_default(job_type)

        timeout_ms = item.get("timeout_ms", DEFAULT_TIMEOUT_MS[job_type])
        try:
            timeout_ms = int(timeout_ms)
        except Exception:
            timeout_ms = DEFAULT_TIMEOUT_MS[job_type]
            warnings.append(f"Job #{index + 1}: timeout_ms tidak valid, pakai default.")

        inputs = item.get("inputs", {})
        if not isinstance(inputs, dict):
            inputs = {}
            warnings.append(f"Job #{index + 1}: inputs tidak valid, pakai object kosong.")

        if job_type == "monitor.channel":
            inputs.setdefault("channel", request.default_channel)
            inputs.setdefault("account_id", request.default_account_id)
        if job_type == "agent.workflow":
            inputs.setdefault("prompt", request.prompt)
            inputs.setdefault("timezone", request.timezone)
            inputs.setdefault("default_channel", request.default_channel)
            inputs.setdefault("default_account_id", request.default_account_id)
        if job_type in {"report.daily", "backup.export"}:
            inputs.setdefault("timezone", request.timezone)
        inputs.setdefault("source", "planner_ai")

        base_id = str(item.get("job_id") or _buat_slug(f"{job_type}-{index + 1}"))
        job_id = _pastikan_id_job_unik(_buat_slug(base_id), used_ids)

        try:
            job_spec = JobSpec(
                job_id=job_id,
                type=job_type,
                schedule=schedule,
                timeout_ms=timeout_ms,
                retry_policy=retry_policy,
                inputs=inputs,
            )
        except Exception as exc:
            warnings.append(f"Job #{index + 1}: gagal validasi JobSpec ({exc}), dilewati.")
            continue

        jobs.append(
            PlannerJob(
                reason=reason,
                assumptions=item_assumptions,
                warnings=item_warnings,
                job_spec=job_spec,
            )
        )

    _lengkapi_job_dari_intent_prompt(request, jobs, used_ids)

    for job in jobs:
        assumptions.extend(job.assumptions)
        warnings.extend(job.warnings)

    assumptions = _hapus_duplikat(_lokalisasi_kumpulan_pesan(_hapus_pesan_low_signal(assumptions)))
    warnings = _hapus_duplikat(_lokalisasi_kumpulan_pesan(_hapus_pesan_low_signal(warnings)))

    summary = str(payload.get("summary") or f"Planner AI menghasilkan {len(jobs)} rencana tugas.")
    if not jobs:
        summary = "Planner AI belum menghasilkan job valid."

    return PlannerResponse(
        prompt=request.prompt,
        normalized_prompt=normalized_prompt,
        summary=summary,
        planner_source="smolagents",
        assumptions=assumptions,
        warnings=warnings,
        jobs=jobs,
    )


def build_plan_with_ai(
    request: PlannerAiRequest,
    *,
    model_id_override: Optional[str] = None,
    api_key_override: Optional[str] = None,
    api_base_override: Optional[str] = None,
    pre_warnings: Optional[List[str]] = None,
) -> PlannerResponse:
    fallback_plan = build_plan_from_prompt(request)
    warning_awal = _hapus_duplikat(_lokalisasi_kumpulan_pesan(_hapus_pesan_low_signal(list(pre_warnings or []))))

    if request.force_rule_based:
        fallback_plan.warnings = _hapus_duplikat(
            [*fallback_plan.warnings, *warning_awal, "force_rule_based aktif: planner AI dilewati."]
        )
        return fallback_plan

    payload, ai_warnings = _jalankan_smolagents(
        request,
        model_id_override=model_id_override,
        api_key_override=api_key_override,
        api_base_override=api_base_override,
    )
    gabung_warning_ai = _hapus_duplikat(
        _lokalisasi_kumpulan_pesan(_hapus_pesan_low_signal([*warning_awal, *ai_warnings]))
    )
    if payload is None:
        fallback_plan.warnings = _hapus_duplikat(
            [
                *fallback_plan.warnings,
                *gabung_warning_ai,
                "Planner AI gagal dipakai. Sistem otomatis memakai planner rule-based.",
            ]
        )
        return fallback_plan

    ai_plan = build_plan_from_ai_payload(request, payload)
    if not ai_plan.jobs:
        fallback_plan.warnings = _hapus_duplikat(
            [
                *fallback_plan.warnings,
                *gabung_warning_ai,
                *ai_plan.warnings,
                "Planner AI tidak menghasilkan job valid. Sistem memakai planner rule-based.",
            ]
        )
        return fallback_plan

    ai_plan.warnings = _hapus_duplikat([*ai_plan.warnings, *gabung_warning_ai])
    return ai_plan


async def build_plan_with_ai_dari_dashboard(request: PlannerAiRequest) -> PlannerResponse:
    kandidat, warnings_awal = await resolve_planner_ai_credential_candidates(request)
    fallback_plan = build_plan_from_prompt(request)

    if request.force_rule_based:
        fallback_plan.warnings = _hapus_duplikat(
            [*fallback_plan.warnings, *warnings_awal, "force_rule_based aktif: planner AI dilewati."]
        )
        return fallback_plan

    warning_terkumpul = _hapus_duplikat(_lokalisasi_kumpulan_pesan(_hapus_pesan_low_signal(list(warnings_awal))))
    if not kandidat:
        fallback_plan.warnings = _hapus_duplikat(
            [
                *fallback_plan.warnings,
                *warning_terkumpul,
                "Planner AI belum menemukan provider yang siap. Sistem memakai planner rule-based.",
            ]
        )
        return fallback_plan

    timeout_sec = _planner_ai_timeout_sec()
    queue_wait_sec = _planner_ai_queue_wait_sec()
    release_grace_sec = _planner_ai_release_grace_sec()
    semaphore, max_concurrent = _get_planner_ai_semaphore()

    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=queue_wait_sec)
    except asyncio.TimeoutError:
        fallback_plan.warnings = _hapus_duplikat(
            [
                *fallback_plan.warnings,
                *warning_terkumpul,
                (
                    f"Planner AI sedang sibuk (maks {max_concurrent} concurrent). "
                    f"Fallback ke rule-based setelah menunggu {queue_wait_sec:.1f} detik."
                ),
            ]
        )
        return fallback_plan

    release_on_exit = True
    try:
        for index, kredensial in enumerate(kandidat, start=1):
            warning_konteks = _hapus_duplikat(
                [
                    *warning_terkumpul,
                    f"Mencoba planner AI lewat {kredensial.provider}/{kredensial.account_id} (percobaan {index}/{len(kandidat)}).",
                ]
            )

            worker_task = _jalankan_di_daemon_thread(
                _jalankan_smolagents,
                request,
                model_id_override=kredensial.model_id,
                api_key_override=kredensial.api_key,
                api_base_override=kredensial.api_base,
            )
            try:
                payload, warnings_ai = await asyncio.wait_for(
                    asyncio.shield(worker_task),
                    timeout=float(timeout_sec),
                )
            except asyncio.TimeoutError:
                # Worker thread tidak bisa dipaksa stop segera. Tahan slot concurrency
                # sampai task background benar-benar selesai agar tidak terjadi snowball.
                _defer_semaphore_release(worker_task, semaphore, release_grace_sec)
                release_on_exit = False
                warning_terkumpul = _hapus_duplikat(
                    [
                        *warning_konteks,
                        (
                            f"Planner AI timeout di {kredensial.provider}/{kredensial.account_id} "
                            f"setelah {timeout_sec} detik."
                        ),
                        f"Planner AI gagal di {kredensial.provider}/{kredensial.account_id}.",
                        "Sisa provider dilewati untuk mencegah bottleneck berantai.",
                    ]
                )
                break
            except Exception as exc:
                if not worker_task.done():
                    worker_task.cancel()
                payload, warnings_ai = None, [
                    f"Planner AI error di {kredensial.provider}/{kredensial.account_id}: {exc}"
                ]

            if payload is None:
                warning_terkumpul = _hapus_duplikat(
                    [
                        *warning_konteks,
                        *warnings_ai,
                        f"Planner AI gagal di {kredensial.provider}/{kredensial.account_id}.",
                    ]
                )
                continue

            ai_plan = build_plan_from_ai_payload(request, payload)
            if ai_plan.jobs:
                ai_plan.warnings = _hapus_duplikat(
                    _lokalisasi_kumpulan_pesan(
                        _hapus_pesan_low_signal([*ai_plan.warnings, *warning_terkumpul, *warnings_ai])
                    )
                )
                return ai_plan

            warning_terkumpul = _hapus_duplikat(
                [
                    *warning_konteks,
                    *warnings_ai,
                    *ai_plan.warnings,
                    f"Planner AI di {kredensial.provider}/{kredensial.account_id} tidak menghasilkan job valid.",
                ]
            )

        fallback_plan.warnings = _hapus_duplikat(
            [
                *fallback_plan.warnings,
                *warning_terkumpul,
                "Planner AI gagal di semua provider yang tersedia. Sistem memakai planner rule-based.",
            ]
        )
        return fallback_plan
    finally:
        if release_on_exit:
            semaphore.release()
