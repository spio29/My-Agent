import json
import os
import inspect
from contextlib import suppress
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp

from app.core.agent_memory import (
    build_agent_memory_context,
    get_agent_memory,
    record_agent_workflow_outcome,
)
from app.core.approval_queue import list_approval_requests, create_approval_request
from app.core.experiments import record_experiment_variant_run, resolve_experiment_prompt_for_job
from app.core.integration_configs import list_integration_accounts, list_mcp_servers
from app.core.queue import append_event, schedule_delayed_job
from app.core.tools.command import (
    PREFIX_PERINTAH_BAWAAN,
    normalisasi_daftar_prefix_perintah,
    perintah_diizinkan_oleh_prefix,
    perintah_termasuk_sensitif,
)

from app.core.config import settings
OPENAI_CHAT_COMPLETIONS_URL = f"{settings.LOCAL_AI_URL.rstrip('/')}/chat/completions"
DEFAULT_OPENAI_MODEL = settings.PLANNER_AI_MODEL
MAX_STEPS = 5
PREVIEW_LIMIT = 500

DEFAULT_PROVIDER_BASE_URLS: Dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "github": "https://api.github.com",
    "notion": "https://api.notion.com/v1",
    "linear": "https://api.linear.app/graphql",
}


def _ambil_prefix_perintah_baseline() -> List[str]:
    raw = os.getenv("AGENT_COMMAND_ALLOW_PREFIXES", "")
    prefix = normalisasi_daftar_prefix_perintah(raw)
    if prefix:
        return prefix
    return list(PREFIX_PERINTAH_BAWAAN)


def _ambil_kebijakan_prefix_perintah(inputs: Dict[str, Any]) -> Dict[str, Any]:
    baseline = _ambil_prefix_perintah_baseline()
    requested = normalisasi_daftar_prefix_perintah(inputs.get("command_allow_prefixes"))

    if not requested:
        return {
            "baseline": baseline,
            "requested": [],
            "effective": baseline,
            "rejected": [],
        }

    allowed_subset: List[str] = []
    rejected: List[str] = []
    for prefix in requested:
        if perintah_diizinkan_oleh_prefix(prefix, baseline):
            allowed_subset.append(prefix)
        else:
            rejected.append(prefix)

    effective = allowed_subset if allowed_subset else baseline
    return {
        "baseline": baseline,
        "requested": requested,
        "effective": effective,
        "rejected": rejected,
    }


def _buat_request_izin_prefix_perintah(prefixes: List[str]) -> List[Dict[str, Any]]:
    requests: List[Dict[str, Any]] = []
    for prefix in prefixes:
        teks = str(prefix or "").strip()
        if not teks:
            continue
        requests.append(
            _buat_request_izin(
                kind="command_prefix",
                command=teks,
                reason=f"Prefix command '{teks}' berada di luar baseline allowlist backend.",
                action_hint="Minta admin menambah prefix via env AGENT_COMMAND_ALLOW_PREFIXES atau policy backend.",
            )
        )
    return _hapus_duplikat_request_izin(requests)


def _normalisasi_id_model(model_id: str) -> str:
    cleaned = model_id.strip()
    if cleaned.startswith("openai/"):
        cleaned = cleaned.split("/", 1)[1].strip()
    return cleaned or DEFAULT_OPENAI_MODEL


def _ekstrak_objek_json(raw_text: str) -> Optional[Dict[str, Any]]:
    text = raw_text.strip()
    if not text:
        return None

    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None

    try:
        payload = json.loads(text[start : end + 1])
    except Exception:
        return None

    return payload if isinstance(payload, dict) else None


def _rencana_fallback_lokal(raw_content: str) -> Dict[str, Any]:
    preview = _ringkas_teks(raw_content, 220) if raw_content else ""
    final_message = "Planner lokal tidak mengembalikan JSON valid. Workflow masuk mode aman."
    if preview:
        final_message = f"{final_message} Preview: {preview}"
    return {
        "summary": "Planner lokal fallback aktif.",
        "final_message": final_message,
        "steps": [],
    }


def _resolve_agent_workflow_max_iterations(inputs: Dict[str, Any], *, local_only_mode: bool) -> int:
    default_value = 2 if local_only_mode else 5

    raw = inputs.get("max_iterations")
    if raw in {None, ""}:
        if local_only_mode:
            raw = os.getenv("AGENT_WORKFLOW_MAX_ITERATIONS_LOCAL")
        if raw in {None, ""}:
            raw = os.getenv("AGENT_WORKFLOW_MAX_ITERATIONS")

    try:
        value = int(raw)
    except Exception:
        value = default_value

    return max(1, min(8, value))


def _ke_peta_string(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}

    output: Dict[str, str] = {}
    for key, value in raw.items():
        name = str(key).strip()
        if not name:
            continue
        output[name] = str(value)
    return output


def _sanitasi_rencana(raw: Dict[str, Any]) -> Dict[str, Any]:
    summary = str(raw.get("summary") or "Agent workflow plan generated.").strip()
    final_message = str(raw.get("final_message") or "").strip()
    raw_steps = raw.get("steps", [])
    if not isinstance(raw_steps, list):
        raw_steps = []

    steps: List[Dict[str, Any]] = []
    for row in raw_steps:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "").strip().lower()
        if kind == "note":
            text = str(row.get("text") or "").strip()
            if text:
                steps.append({"kind": "note", "text": text})
        elif kind == "provider_http":
            provider = str(row.get("provider") or "").strip().lower()
            if not provider:
                continue
            step = {
                "kind": "provider_http",
                "provider": provider,
                "account_id": str(row.get("account_id") or "default").strip() or "default",
                "method": str(row.get("method") or "GET").strip().upper(),
                "path": str(row.get("path") or "").strip(),
                "headers": _ke_peta_string(row.get("headers", {})),
                "body": row.get("body"),
            }
            steps.append(step)
        elif kind == "mcp_http":
            server_id = str(row.get("server_id") or "").strip()
            if not server_id:
                continue
            step = {
                "kind": "mcp_http",
                "server_id": server_id,
                "method": str(row.get("method") or "GET").strip().upper(),
                "path": str(row.get("path") or "").strip(),
                "headers": _ke_peta_string(row.get("headers", {})),
                "body": row.get("body"),
            }
            steps.append(step)
        elif kind == "local_command":
            perintah = str(row.get("command") or "").strip()
            if not perintah:
                continue
            raw_timeout = row.get("timeout_sec", 180)
            try:
                timeout_sec = int(raw_timeout)
            except Exception:
                timeout_sec = 180
            step = {
                "kind": "local_command",
                "command": perintah,
                "workdir": str(row.get("workdir") or "").strip(),
                "timeout_sec": max(1, min(1800, timeout_sec)),
            }
            steps.append(step)

        if len(steps) >= MAX_STEPS:
            break

    if not steps:
        steps = [{"kind": "note", "text": "Planner AI tidak memberi langkah aksi yang valid."}]

    return {
        "summary": summary,
        "final_message": final_message,
        "steps": steps,
    }


def _ringkas_teks(raw: Any, limit: int = PREVIEW_LIMIT) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _tentukan_agent_key(ctx: Any, inputs: Dict[str, Any]) -> str:
    kandidat = [
        str(inputs.get("agent_key") or "").strip(),
        str(inputs.get("flow_group") or "").strip(),
    ]

    kanal = str(inputs.get("default_channel") or "").strip().lower()
    akun = str(inputs.get("default_account_id") or "").strip().lower()
    if kanal and akun:
        kandidat.append(f"{kanal}:{akun}")

    job_id = str(getattr(ctx, "job_id", "") or "").strip()
    if job_id:
        kandidat.append(f"job:{job_id}")

    for row in kandidat:
        if row:
            return row.lower()[:128]
    return "agent:umum"


def _signature_dari_step_rencana(step: Dict[str, Any]) -> str:
    kind = str(step.get("kind") or "").strip().lower()
    if kind == "provider_http":
        provider = str(step.get("provider") or "").strip().lower()
        method = str(step.get("method") or "GET").strip().upper()
        path = str(step.get("path") or "").strip().lower()
        return f"provider_http:{provider}:{method}:{path}"
    if kind == "mcp_http":
        server_id = str(step.get("server_id") or "").strip().lower()
        method = str(step.get("method") or "GET").strip().upper()
        path = str(step.get("path") or "").strip().lower()
        return f"mcp_http:{server_id}:{method}:{path}"
    if kind == "local_command":
        command = " ".join(str(step.get("command") or "").strip().lower().split())
        return f"local_command:{command[:120]}"
    return ""


def _terapkan_guardrail_memori(
    rencana: Dict[str, Any],
    memory_context: Dict[str, Any],
) -> Dict[str, Any]:
    avoid_signatures = {
        str(item).strip().lower()
        for item in memory_context.get("avoid_signatures", [])
        if str(item).strip()
    }
    if not avoid_signatures:
        rencana["memory_guardrail"] = []
        return rencana

    steps = rencana.get("steps", [])
    if not isinstance(steps, list):
        rencana["memory_guardrail"] = []
        return rencana

    filtered: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        signature = _signature_dari_step_rencana(step)
        if signature and signature.lower() in avoid_signatures:
            blocked.append(
                {
                    "signature": signature,
                    "kind": str(step.get("kind") or ""),
                    "reason": "Diblokir memori karena pola gagal berulang.",
                }
            )
            continue
        filtered.append(step)

    if not filtered:
        filtered = [
            {
                "kind": "note",
                "text": "Semua langkah aksi diblokir memori agen karena pola gagal berulang. "
                "Butuh puzzle alternatif atau approval manual.",
            }
        ]

    rencana["steps"] = filtered[:MAX_STEPS]
    rencana["memory_guardrail"] = blocked[:10]
    if blocked:
        summary = str(rencana.get("summary") or "").strip()
        rencana["summary"] = (
            f"{summary} Guardrail memori memblokir {len(blocked)} langkah berisiko."
            if summary
            else f"Guardrail memori memblokir {len(blocked)} langkah berisiko."
        )
    return rencana


def _tentukan_url_dasar_provider(provider: str, account: Dict[str, Any]) -> str:
    config = account.get("config", {})
    if not isinstance(config, dict):
        config = {}
    base_url = str(config.get("base_url") or "").strip()
    if base_url:
        return base_url
    return DEFAULT_PROVIDER_BASE_URLS.get(provider, "")


def _tentukan_url(base_url: str, path: str) -> str:
    cleaned_path = path.strip()
    if cleaned_path.startswith("http://") or cleaned_path.startswith("https://"):
        return cleaned_path
    if not base_url:
        return ""
    if not cleaned_path:
        return base_url
    return urljoin(base_url.rstrip("/") + "/", cleaned_path.lstrip("/"))


def _sisipkan_auth_provider(
    headers: Dict[str, str],
    provider: str,
    secret: str,
    config: Dict[str, Any],
) -> Dict[str, str]:
    output = dict(headers)

    if secret and "Authorization" not in output:
        output["Authorization"] = f"Bearer {secret}"

    if provider == "github":
        output.setdefault("Accept", "application/vnd.github+json")
    elif provider == "notion":
        version = str(config.get("notion_version") or "2022-06-28").strip()
        output.setdefault("Notion-Version", version)

    return output


def _katalog_akun(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if not row.get("enabled", True):
            continue
        provider = str(row.get("provider") or "").strip().lower()
        if not provider:
            continue
        grouped.setdefault(provider, []).append(row)
    return grouped


def _pilih_akun(
    grouped: Dict[str, List[Dict[str, Any]]],
    provider: str,
    account_id: str,
) -> Optional[Dict[str, Any]]:
    rows = grouped.get(provider, [])
    if not rows:
        return None

    for row in rows:
        if str(row.get("account_id") or "") == account_id:
            return row

    for row in rows:
        if str(row.get("account_id") or "") == "default":
            return row

    return rows[0]


def _katalog_mcp(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not row.get("enabled", True):
            continue
        server_id = str(row.get("server_id") or "").strip()
        if server_id:
            output[server_id] = row
    return output


def _buat_request_izin(
    *,
    kind: str,
    reason: str,
    provider: Optional[str] = None,
    account_id: Optional[str] = None,
    server_id: Optional[str] = None,
    command: Optional[str] = None,
    action_hint: str = "",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "kind": kind,
        "reason": reason.strip(),
        "action_hint": action_hint.strip(),
    }
    if provider:
        payload["provider"] = provider.strip().lower()
    if account_id:
        payload["account_id"] = account_id.strip()
    if server_id:
        payload["server_id"] = server_id.strip()
    if command:
        payload["command"] = command.strip()
    return payload


def _hapus_duplikat_request_izin(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    output: List[Dict[str, Any]] = []
    for item in requests:
        signature = json.dumps(
            {
                "kind": item.get("kind"),
                "provider": item.get("provider"),
                "account_id": item.get("account_id"),
                "server_id": item.get("server_id"),
                "command": item.get("command"),
                "reason": item.get("reason"),
            },
            sort_keys=True,
        )
        if signature in seen:
            continue
        seen.add(signature)
        output.append(item)
    return output


def _kumpulkan_request_izin_dari_rencana(
    steps: List[Dict[str, Any]],
    provider_catalog: Dict[str, List[Dict[str, Any]]],
    mcp_catalog: Dict[str, Dict[str, Any]],
    command_allow_prefixes: List[str],
    allow_sensitive_commands: bool,
    approved_sensitive_commands: List[str],
) -> List[Dict[str, Any]]:
    requests: List[Dict[str, Any]] = []

    perintah_sensitif_disetujui = {str(item or "").strip().lower() for item in approved_sensitive_commands}

    for step in steps:
        kind = str(step.get("kind") or "").strip().lower()

        if kind == "provider_http":
            provider = str(step.get("provider") or "").strip().lower()
            account_id = str(step.get("account_id") or "default").strip() or "default"
            if not provider:
                continue
            selected = _pilih_akun(provider_catalog, provider, account_id)
            if not selected:
                requests.append(
                    _buat_request_izin(
                        kind="provider_account",
                        provider=provider,
                        account_id=account_id,
                        reason=f"Provider '{provider}' akun '{account_id}' belum tersedia atau belum aktif.",
                        action_hint="Tambahkan akun integrasi di Setelan > Akun Integrasi.",
                    )
                )

        if kind == "mcp_http":
            server_id = str(step.get("server_id") or "").strip()
            if not server_id:
                continue
            server = mcp_catalog.get(server_id)
            if not server:
                requests.append(
                    _buat_request_izin(
                        kind="mcp_server",
                        server_id=server_id,
                        reason=f"MCP server '{server_id}' belum tersedia atau belum aktif.",
                        action_hint="Tambahkan MCP server di Setelan > MCP Servers.",
                    )
                )
                continue

            transport = str(server.get("transport") or "").strip().lower()
            if transport not in {"http", "sse"}:
                requests.append(
                    _buat_request_izin(
                        kind="mcp_transport",
                        server_id=server_id,
                        reason=f"MCP server '{server_id}' belum bisa HTTP call karena transport '{transport}'.",
                        action_hint="Ubah transport MCP ke http/sse untuk dipakai workflow agent.",
                    )
                )

        if kind == "local_command":
            perintah = str(step.get("command") or "").strip()
            if not perintah:
                continue

            if (
                perintah_termasuk_sensitif(perintah)
                and not allow_sensitive_commands
                and perintah.lower() not in perintah_sensitif_disetujui
            ):
                requests.append(
                    _buat_request_izin(
                        kind="command_sensitive",
                        command=perintah,
                        reason=f"Perintah sensitif butuh review manual: {perintah}",
                        action_hint="Set allow_sensitive_commands=true setelah approval manual.",
                    )
                )
                continue

            if not perintah_diizinkan_oleh_prefix(perintah, command_allow_prefixes):
                requests.append(
                    _buat_request_izin(
                        kind="command_policy",
                        command=perintah,
                        reason=f"Perintah tidak ada di allowlist prefix: {perintah}",
                        action_hint="Minta admin menambah prefix via env AGENT_COMMAND_ALLOW_PREFIXES atau policy backend.",
                    )
                )

    return _hapus_duplikat_request_izin(requests)


def _buat_respons_butuh_izin(
    *,
    prompt: str,
    summary: str,
    model_id: str,
    approval_requests: List[Dict[str, Any]],
    provider_catalog: Dict[str, List[Dict[str, Any]]],
    mcp_catalog: Dict[str, Dict[str, Any]],
    command_allow_prefixes: List[str],
    allow_sensitive_commands: bool,
) -> Dict[str, Any]:
    provider_tersedia = {
        provider: sorted({str(row.get("account_id") or "default") for row in rows})
        for provider, rows in provider_catalog.items()
    }
    server_mcp_tersedia = sorted(mcp_catalog.keys())
    pesan = "Butuh izin untuk menambah puzzle/skill yang belum tersedia."

    return {
        "success": False,
        "requires_approval": True,
        "error": pesan,
        "summary": summary,
        "final_message": "",
        "model_id": model_id,
        "prompt": prompt,
        "steps_planned": 0,
        "steps_executed": 0,
        "step_results": [],
        "approval_requests": approval_requests,
        "available_providers": provider_tersedia,
        "available_mcp_servers": server_mcp_tersedia,
        "command_allow_prefixes": command_allow_prefixes,
        "allow_sensitive_commands": allow_sensitive_commands,
    }


async def _muat_perintah_sensitif_disetujui(limit: int = 200) -> List[str]:
    try:
        rows = await list_approval_requests(status="approved", limit=limit)
    except Exception:
        return []

    hasil = set()
    for row in rows:
        daftar_request = row.get("approval_requests", [])
        if not isinstance(daftar_request, list):
            continue
        for item in daftar_request:
            if not isinstance(item, dict):
                continue
            if str(item.get("kind") or "").strip().lower() != "command_sensitive":
                continue
            perintah = str(item.get("command") or "").strip().lower()
            if perintah:
                hasil.add(perintah)
    return sorted(hasil)


def _bangun_prompt_sistem_planner(
    provider_catalog: Dict[str, List[Dict[str, Any]]],
    mcp_catalog: Dict[str, Dict[str, Any]],
    command_allow_prefixes: List[str],
    allow_sensitive_commands: bool,
    agent_memory_context: Optional[Dict[str, Any]] = None,
    current_iteration: int = 0,
    previous_results: Optional[List[Dict[str, Any]]] = None,
) -> str:
    provider_lines: List[str] = []
    for provider, rows in sorted(provider_catalog.items()):
        account_ids = ", ".join(sorted({str(row.get("account_id") or "default") for row in rows}))
        provider_lines.append(f"- {provider}: accounts [{account_ids}]")
    if not provider_lines:
        provider_lines = ["- (none)"]

    mcp_lines: List[str] = []
    for server_id, row in sorted(mcp_catalog.items()):
        transport = str(row.get("transport") or "stdio")
        endpoint = str(row.get("url") or row.get("command") or "-")
        mcp_lines.append(f"- {server_id}: {transport} ({endpoint})")
    if not mcp_lines:
        mcp_lines = ["- (none)"]

    command_lines = [f"- {row}" for row in command_allow_prefixes] or ["- (none)"]

    memory_ctx = agent_memory_context if isinstance(agent_memory_context, dict) else {}
    memory_lines: List[str] = []
    if memory_ctx:
        memory_lines.append(f"- agent_key: {str(memory_ctx.get('agent_key') or '-')}")
        memory_lines.append(f"- total_runs: {int(memory_ctx.get('total_runs') or 0)}")
        memory_lines.append(f"- success_rate: {float(memory_ctx.get('success_rate') or 0.0)}%")
        avoid_rows = memory_ctx.get("avoid_signatures", [])
        if isinstance(avoid_rows, list) and avoid_rows:
            memory_lines.append("- CRITICAL: DO NOT repeat these failed patterns (avoid_signatures):")
            for row in avoid_rows[:10]:
                memory_lines.append(f"  - {str(row)}")
        
        recent_failures = memory_ctx.get("recent_failures", [])
        if isinstance(recent_failures, list) and recent_failures:
            memory_lines.append("- Lessons learned from recent failures:")
            for row in recent_failures[:5]:
                if not isinstance(row, dict):
                    continue
                signature = str(row.get("signature") or "-")
                error = _ringkas_teks(row.get("error"), 150)
                memory_lines.append(f"  - Pattern '{signature}' failed with: {error}")

    observation_lines: List[str] = []
    if previous_results:
        observation_lines.append("- Current Progress & Observations:")
        for i, res in enumerate(previous_results):
            status = "SUCCESS" if res.get("success") else "FAILED"
            kind = res.get("kind", "unknown")
            detail = _ringkas_teks(res.get("response_preview") or res.get("stdout_preview") or res.get("error") or "no detail", 200)
            observation_lines.append(f"  Step {i+1} ({kind}): {status} -> {detail}")

    return (
        "You are the CEO of a Digital Holding Company.\n"
        "Your owner (Chairman) expects you to manage multiple business units (jobs) and proactively find new profit streams.\n\n"
        "CORE RESPONSIBILITIES:\n"
        "1) STRATEGY: Analyze trends and delegate research to specialized managers (via schedule_job).\n"
        "2) PROFITABILITY: Every proposal must have a clear path to revenue.\n"
        "3) DELEGATION: You can create new subsidiary jobs (auto-provisioning) to handle specific operations.\n"
        "4) REPORTING: Provide high-level executive summaries to the Chairman.\n\n"
        "Return ONLY a valid JSON object with this schema:\n"
        "{\n"
        '  "thought": "your reasoning about the current state and next move",\n'
        '  "summary": "short summary of the planned actions",\n'
        '  "final_message": "fill this ONLY if you have completed the task or cannot proceed further",\n'
        '  "steps": [\n'
        "    note step (for observations/internal notes):\n"
        '      {"kind":"note","text":"string"}\n'
        "    provider HTTP step (external APIs):\n"
        '      {"kind":"provider_http","provider":"github","account_id":"default","method":"GET","path":"/user","headers":{},"body":null}\n'
        "    mcp HTTP step (model context protocol tools):\n"
        '      {"kind":"mcp_http","server_id":"mcp_main","method":"GET","path":"/health","headers":{},"body":null}\n'
        "    local command step (terminal execution):\n"
        '      {"kind":"local_command","command":"ls -la","workdir":"./","timeout_sec":300}\n'
        "    schedule job step (proactive self-scheduling):\n"
        '      {"kind":"schedule_job","target_job_id":"string","inputs":{},"delay_sec":3600}\n'
        "    create proposal step (report opportunities for approval):\n"
        '      {"kind":"create_proposal","title":"string","analysis":"string","proposed_plan":"string","impact":"string"}\n'
        "    multimedia step (generate images/videos):\n"
        '      {"kind":"multimedia","action":"generate_image","prompt":"string","branch_id":"string"}\n'
        "  ]\n"
        "}\n\n"
        "AUTONOMY RULES:\n"
        "1) PROACTIVITY: Use 'schedule_job' to follow up on tasks. 24/7 work is possible by chaining.\n"
        "2) CONTENT: Use 'multimedia' step to create visual assets for social media before posting.\n"
        "2) DISCOVERY: If you find a new opportunity or profit method, use 'create_proposal' to report it. DO NOT execute risky new methods without approval.\n"
        f"1) You are at iteration {current_iteration + 1}/5. If you cannot solve it now, provide a final_message explaining why.\n"
        "2) SELF-CORRECTION: If a previous step failed, analyze why and try a DIFFERENT approach. DO NOT just repeat the same failed command.\n"
        "3) MEMORY: Respect 'avoid_signatures'. They are patterns that consistently fail in this environment.\n"
        "4) SAFETY: Never generate destructive commands (rm -rf, format, etc.).\n"
        "5) Plan up to 3 steps at a time. If task is done, set steps to [] and fill final_message.\n\n"
        "AVAILABLE TOOLS:\n"
        "Providers:\n"
        + "\n".join(provider_lines)
        + "\n\nMCP servers:\n"
        + "\n".join(mcp_lines)
        + "\n\nAllowed local command prefixes:\n"
        + "\n".join(command_lines)
        + "\n\nMEMORY & CONTEXT:\n"
        + "\n".join(memory_lines)
        + "\n\n"
        + "\n".join(observation_lines)
        + f"\n\nallow_sensitive_commands={str(bool(allow_sensitive_commands)).lower()}"
    )


async def _rencanakan_aksi_dengan_openai(
    prompt: str,
    model_id: str,
    api_key: str,
    provider_catalog: Dict[str, List[Dict[str, Any]]],
    mcp_catalog: Dict[str, Dict[str, Any]],
    command_allow_prefixes: List[str],
    allow_sensitive_commands: bool,
    agent_memory_context: Optional[Dict[str, Any]] = None,
    current_iteration: int = 0,
    previous_results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    payload = {
        "model": model_id,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": _bangun_prompt_sistem_planner(
                    provider_catalog,
                    mcp_catalog,
                    command_allow_prefixes,
                    allow_sensitive_commands,
                    agent_memory_context,
                    current_iteration=current_iteration,
                    previous_results=previous_results,
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(OPENAI_CHAT_COMPLETIONS_URL, json=payload, headers=headers) as response:
            response_text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"OpenAI planner failed ({response.status}): {_ringkas_teks(response_text, 220)}")

    try:
        data = json.loads(response_text)
    except Exception:
        return _rencana_fallback_lokal(response_text)

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return _rencana_fallback_lokal(str(data.get("response") or response_text))

    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content", "")
    if isinstance(content, list):
        content = "\n".join(
            str(item.get("text", "") if isinstance(item, dict) else item)
            for item in content
        )

    parsed = _ekstrak_objek_json(str(content))
    if not parsed:
        return _rencana_fallback_lokal(str(content or response_text))
    return parsed


async def _panggil_planner_openai(
    *,
    prompt: str,
    model_id: str,
    api_key: str,
    provider_catalog: Dict[str, List[Dict[str, Any]]],
    mcp_catalog: Dict[str, Dict[str, Any]],
    command_allow_prefixes: List[str],
    allow_sensitive_commands: bool,
    agent_memory_context: Dict[str, Any],
    current_iteration: int = 0,
    previous_results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    kwargs = {
        "prompt": prompt,
        "model_id": model_id,
        "api_key": api_key,
        "provider_catalog": provider_catalog,
        "mcp_catalog": mcp_catalog,
        "command_allow_prefixes": command_allow_prefixes,
        "allow_sensitive_commands": allow_sensitive_commands,
        "current_iteration": current_iteration,
        "previous_results": previous_results,
    }

    try:
        signature = inspect.signature(_rencanakan_aksi_dengan_openai)
        if "agent_memory_context" in signature.parameters:
            kwargs["agent_memory_context"] = agent_memory_context
    except Exception:
        pass

    return await _rencanakan_aksi_dengan_openai(**kwargs)


def _langkah_sukses_dari_hasil_http(result: Dict[str, Any]) -> bool:
    if not bool(result.get("success", False)):
        return False
    status_raw = result.get("status")
    try:
        status_code = int(status_raw)
    except Exception:
        return True
    return 200 <= status_code < 400


async def _eksekusi_langkah_provider_http(
    ctx,
    step: Dict[str, Any],
    provider_catalog: Dict[str, List[Dict[str, Any]]],
    http_tool,
) -> Dict[str, Any]:
    provider = str(step.get("provider") or "").strip().lower()
    account_id = str(step.get("account_id") or "default").strip() or "default"
    account = _pilih_akun(provider_catalog, provider, account_id)
    if not account:
        return {
            "kind": "provider_http",
            "provider": provider,
            "account_id": account_id,
            "success": False,
            "error": "Provider/account not found or disabled.",
        }

    config = account.get("config", {}) if isinstance(account.get("config", {}), dict) else {}
    base_url = _tentukan_url_dasar_provider(provider, account)
    url = _tentukan_url(base_url, str(step.get("path") or ""))
    if not url:
        return {
            "kind": "provider_http",
            "provider": provider,
            "account_id": account_id,
            "success": False,
            "error": "Cannot resolve URL. Add base_url in integration config or use absolute URL path.",
        }

    headers = _ke_peta_string(config.get("headers", {}))
    headers.update(_ke_peta_string(step.get("headers", {})))
    secret = str(account.get("secret") or "").strip()
    headers = _sisipkan_auth_provider(headers, provider, secret, config)

    timeout_raw = config.get("timeout_sec", 30)
    try:
        timeout = max(5, min(120, int(timeout_raw)))
    except Exception:
        timeout = 30

    request_payload = {
        "method": str(step.get("method") or "GET").upper(),
        "url": url,
        "headers": headers,
        "body": step.get("body"),
        "timeout": timeout,
    }
    result = await http_tool.run(request_payload, ctx)

    return {
        "kind": "provider_http",
        "provider": provider,
        "account_id": str(account.get("account_id") or account_id),
        "method": request_payload["method"],
        "url": url,
        "status": result.get("status"),
        "success": _langkah_sukses_dari_hasil_http(result),
        "response_preview": _ringkas_teks(result.get("body")),
        "error": result.get("error"),
    }


async def _eksekusi_langkah_mcp_http(
    ctx,
    step: Dict[str, Any],
    mcp_catalog: Dict[str, Dict[str, Any]],
    http_tool,
) -> Dict[str, Any]:
    server_id = str(step.get("server_id") or "").strip()
    server = mcp_catalog.get(server_id)
    if not server:
        return {
            "kind": "mcp_http",
            "server_id": server_id,
            "success": False,
            "error": "MCP server not found or disabled.",
        }

    transport = str(server.get("transport") or "").strip().lower()
    if transport not in {"http", "sse"}:
        return {
            "kind": "mcp_http",
            "server_id": server_id,
            "success": False,
            "error": f"MCP server transport '{transport}' is not HTTP-callable.",
        }

    base_url = str(server.get("url") or "").strip()
    url = _tentukan_url(base_url, str(step.get("path") or ""))
    if not url:
        return {
            "kind": "mcp_http",
            "server_id": server_id,
            "success": False,
            "error": "Cannot resolve MCP URL.",
        }

    headers = _ke_peta_string(server.get("headers", {}))
    headers.update(_ke_peta_string(step.get("headers", {})))
    auth_token = str(server.get("auth_token") or "").strip()
    if auth_token and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {auth_token}"

    timeout_raw = server.get("timeout_sec", 20)
    try:
        timeout = max(1, min(120, int(timeout_raw)))
    except Exception:
        timeout = 20

    request_payload = {
        "method": str(step.get("method") or "GET").upper(),
        "url": url,
        "headers": headers,
        "body": step.get("body"),
        "timeout": timeout,
    }
    result = await http_tool.run(request_payload, ctx)

    return {
        "kind": "mcp_http",
        "server_id": server_id,
        "transport": transport,
        "method": request_payload["method"],
        "url": url,
        "status": result.get("status"),
        "success": _langkah_sukses_dari_hasil_http(result),
        "response_preview": _ringkas_teks(result.get("body")),
        "error": result.get("error"),
    }


async def _eksekusi_langkah_perintah_lokal(
    ctx,
    step: Dict[str, Any],
    command_tool,
    command_allow_prefixes: List[str],
    allow_sensitive_commands: bool,
    approved_sensitive_commands: List[str],
) -> Dict[str, Any]:
    perintah = str(step.get("command") or "").strip()
    workdir = str(step.get("workdir") or "").strip()
    timeout_sec = int(step.get("timeout_sec") or 180)

    if not command_tool:
        return {
            "kind": "local_command",
            "command": perintah,
            "workdir": workdir or ".",
            "timeout_sec": timeout_sec,
            "success": False,
            "error": "command tool is not available",
        }

    perintah_disetujui = {str(item or "").strip().lower() for item in approved_sensitive_commands}
    izinkan_sensitif_langkah = allow_sensitive_commands or perintah.lower() in perintah_disetujui

    payload = {
        "command": perintah,
        "workdir": workdir,
        "timeout_sec": timeout_sec,
        "allow_prefixes": command_allow_prefixes,
        "allow_sensitive": izinkan_sensitif_langkah,
    }
    hasil = await command_tool.run(payload, ctx)
    return {
        "kind": "local_command",
        "command": perintah,
        "workdir": str(hasil.get("workdir") or workdir or "."),
        "timeout_sec": timeout_sec,
        "success": bool(hasil.get("success", False)),
        "exit_code": hasil.get("exit_code"),
        "duration_ms": hasil.get("duration_ms"),
        "stdout_preview": _ringkas_teks(hasil.get("stdout")),
        "stderr_preview": _ringkas_teks(hasil.get("stderr")),
        "error": hasil.get("error"),
    }


async def _kirim_notifikasi_eksternal(title: str, impact: str, approval_id: str, role: str = "CEO"):
    token = os.getenv("TELEGRAM_NOTIF_TOKEN")
    chat_id = os.getenv("TELEGRAM_NOTIF_CHAT_ID")
    
    if not token or not chat_id:
        return

    text = (
        f"ðŸ¢ *Laporan Eksekutif HoldCo*\n\n"
        f"*Dari:* {role}\n"
        f"*Subjek:* {title}\n"
        f"*Estimasi Dampak:* {impact}\n"
        f"*ID Ref:* `{approval_id}`\n\n"
        f"Chairman, silakan tinjau proposal di dashboard untuk keputusan strategis (OKE)."
    )
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                await resp.text()
    except Exception:
        pass

async def run(ctx, inputs: Dict[str, Any]) -> Dict[str, Any]:
    prompt_awal = str(inputs.get("prompt") or "").strip()
    job_id_ctx = str(getattr(ctx, "job_id", "") or "").strip()
    run_id_ctx = str(getattr(ctx, "run_id", "") or "").strip()
    branch_id_ctx = str(inputs.get("branch_id") or inputs.get("target_branch_id") or "").strip()
    if not branch_id_ctx:
        flow_group_ctx = str(inputs.get("flow_group") or "").strip()
        if flow_group_ctx.lower().startswith("br_"):
            branch_id_ctx = flow_group_ctx

    try:
        konteks_experiment = await resolve_experiment_prompt_for_job(
            job_id_ctx,
            run_id=run_id_ctx,
            base_prompt=prompt_awal,
            experiment_id=str(inputs.get("experiment_id") or ""),
            preferred_variant=str(inputs.get("experiment_variant") or ""),
        )
    except Exception as exc:
        konteks_experiment = {
            "applied": False,
            "reason": "resolution_error",
            "job_id": str(job_id_ctx or "").strip().lower(),
            "experiment_id": str(inputs.get("experiment_id") or "").strip().lower(),
            "variant": "",
            "variant_name": "",
            "traffic_split_b": 0,
            "bucket": None,
            "prompt": prompt_awal,
            "error": str(exc),
        }

    prompt_pengguna = str(konteks_experiment.get("prompt") or prompt_awal).strip()
    raw_traffic_split = konteks_experiment.get("traffic_split_b", 0)
    try:
        traffic_split_b = int(raw_traffic_split)
    except Exception:
        traffic_split_b = 0
    experiment_payload = {
        "applied": bool(konteks_experiment.get("applied", False)),
        "reason": str(konteks_experiment.get("reason") or ""),
        "experiment_id": str(konteks_experiment.get("experiment_id") or ""),
        "variant": str(konteks_experiment.get("variant") or ""),
        "variant_name": str(konteks_experiment.get("variant_name") or ""),
        "traffic_split_b": max(0, min(100, traffic_split_b)),
        "bucket": konteks_experiment.get("bucket"),
    }

    if experiment_payload["applied"] and experiment_payload["experiment_id"]:
        with suppress(Exception):
            await record_experiment_variant_run(
                experiment_payload["experiment_id"],
                variant=experiment_payload["variant"],
                variant_name=experiment_payload["variant_name"],
                job_id=job_id_ctx,
                run_id=run_id_ctx,
                bucket=experiment_payload["bucket"],
            )

    if not prompt_pengguna:
        return {"success": False, "error": "prompt is required", "experiment": experiment_payload}

    agent_key = _tentukan_agent_key(ctx, inputs)
    memori_agent = await get_agent_memory(agent_key)
    konteks_memori = build_agent_memory_context(memori_agent)

    async def _muat_konteks_memori_terbaru() -> Dict[str, Any]:
        nonlocal konteks_memori
        with suppress(Exception):
            memori_terbaru = await get_agent_memory(agent_key)
            konteks_memori = build_agent_memory_context(memori_terbaru)
        return konteks_memori

    async def _catat_memori(
        *,
        success: bool,
        summary: str,
        final_message: str,
        step_results: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        with suppress(Exception):
            await record_agent_workflow_outcome(
                agent_key=agent_key,
                prompt=prompt_pengguna,
                success=success,
                summary=summary,
                final_message=final_message,
                step_results=step_results or [],
                error=error,
            )
        return await _muat_konteks_memori_terbaru()

    alat_http = ctx.tools.get("http")
    if not alat_http:
        return {"success": False, "error": "http tool is not available", "experiment": experiment_payload}
    alat_command = ctx.tools.get("command")

    daftar_integrasi = await list_integration_accounts(include_secret=True)
    daftar_mcp = await list_mcp_servers(include_secret=True)

    katalog_provider = _katalog_akun(daftar_integrasi)
    katalog_mcp = _katalog_mcp(daftar_mcp)
    perlu_izin_saat_kurang = bool(inputs.get("require_approval_for_missing", True))
    kebijakan_prefix = _ambil_kebijakan_prefix_perintah(inputs)
    daftar_prefix_perintah = kebijakan_prefix["effective"]
    prefix_perintah_diminta = kebijakan_prefix["requested"]
    prefix_perintah_ditolak = kebijakan_prefix["rejected"]
    izinkan_perintah_sensitif = bool(inputs.get("allow_sensitive_commands", False))
    perintah_sensitif_disetujui = await _muat_perintah_sensitif_disetujui() if not izinkan_perintah_sensitif else []

    if prefix_perintah_ditolak:
        requests = _buat_request_izin_prefix_perintah(prefix_perintah_ditolak)
        if requests and perlu_izin_saat_kurang:
            with suppress(Exception):
                await append_event(
                    "agent.approval_requested",
                    {
                        "prompt": prompt_pengguna[:200],
                        "reason": "command_prefix_extension_requested",
                        "request_count": len(requests),
                        "requests": requests,
                    },
                )

            konteks_memori_terbaru = await _catat_memori(
                success=False,
                summary="Workflow butuh approval untuk memperluas command allowlist.",
                final_message="",
                step_results=[],
                error="requires_approval_for_command_prefix_extension",
            )

            response_izin = _buat_respons_butuh_izin(
                prompt=prompt_pengguna,
                summary="Workflow butuh approval untuk prefix command di luar allowlist backend.",
                model_id="",
                approval_requests=requests,
                provider_catalog=katalog_provider,
                mcp_catalog=katalog_mcp,
                command_allow_prefixes=daftar_prefix_perintah,
                allow_sensitive_commands=izinkan_perintah_sensitif,
            )
            response_izin["agent_key"] = agent_key
            response_izin["memory_context"] = konteks_memori_terbaru
            response_izin["command_allow_prefixes_requested"] = prefix_perintah_diminta
            response_izin["command_allow_prefixes_rejected"] = prefix_perintah_ditolak
            response_izin["experiment"] = experiment_payload
            return response_izin

    akun_openai_pilihan = str(inputs.get("openai_account_id") or "default").strip() or "default"
    akun_openai = _pilih_akun(katalog_provider, "openai", akun_openai_pilihan)

    kunci_api_openai = ""
    id_model_openai = str(inputs.get("model_id") or "").strip()
    if akun_openai:
        kunci_api_openai = str(akun_openai.get("secret") or "").strip()
        if not id_model_openai:
            config = akun_openai.get("config", {})
            if isinstance(config, dict):
                id_model_openai = str(config.get("model_id") or "").strip()

    if not kunci_api_openai:
        kunci_api_openai = str(os.getenv("OPENAI_API_KEY") or os.getenv("LOCAL_AI_API_KEY") or "").strip()

    mode_ai = str(inputs.get("ai_mode") or os.getenv("AGENT_AI_MODE") or "").strip().lower()
    local_only_mode = mode_ai in {"local", "local_only", "local-only"}
    local_only_mode = local_only_mode or str(os.getenv("AGENT_LOCAL_ONLY") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    local_only_mode = local_only_mode or "11434" in OPENAI_CHAT_COMPLETIONS_URL

    if local_only_mode:
        model_lokal = str(
            inputs.get("local_model_id")
            or inputs.get("model_id")
            or os.getenv("PLANNER_AI_MODEL")
            or DEFAULT_OPENAI_MODEL
        ).strip()
        if model_lokal:
            id_model_openai = model_lokal

    if not kunci_api_openai and not local_only_mode:
        requests = [
            _buat_request_izin(
                kind="provider_account",
                provider="openai",
                account_id=akun_openai_pilihan,
                reason="Token OpenAI belum tersedia untuk planner agent.",
                action_hint="Isi token provider OpenAI di Setelan > Akun Integrasi.",
            )
        ]

        with_izin = _buat_respons_butuh_izin(
            prompt=prompt_pengguna,
            summary="Planner berhenti karena butuh akses provider OpenAI.",
            model_id="",
            approval_requests=requests,
            provider_catalog=katalog_provider,
            mcp_catalog=katalog_mcp,
            command_allow_prefixes=daftar_prefix_perintah,
            allow_sensitive_commands=izinkan_perintah_sensitif,
        )
        with_izin["agent_key"] = agent_key
        with_izin["command_allow_prefixes_requested"] = prefix_perintah_diminta
        with_izin["command_allow_prefixes_rejected"] = prefix_perintah_ditolak
        with_izin["experiment"] = experiment_payload
        with suppress(Exception):
            await append_event(
                "agent.approval_requested",
                {"prompt": prompt_pengguna[:200], "reason": "missing_openai_key", "requests": requests},
            )
        konteks_memori_terbaru = await _catat_memori(
            success=False,
            summary=(
                "Planner berhenti karena token OpenAI belum tersedia."
                if perlu_izin_saat_kurang
                else "Planner gagal karena OpenAI API key belum tersedia."
            ),
            final_message="",
            step_results=[],
            error="missing_openai_key" if perlu_izin_saat_kurang else "openai_api_key_missing",
        )
        if perlu_izin_saat_kurang:
            with_izin["memory_context"] = konteks_memori_terbaru
            return with_izin

        return {
            "success": False,
            "agent_key": agent_key,
            "memory_context": konteks_memori_terbaru,
            "command_allow_prefixes_requested": prefix_perintah_diminta,
            "command_allow_prefixes_rejected": prefix_perintah_ditolak,
            "experiment": experiment_payload,
            "error": "OpenAI API key belum tersedia. Isi provider 'openai' di dashboard atau set OPENAI_API_KEY.",
        }

    model_id = _normalisasi_id_model(
        id_model_openai or str(os.getenv("PLANNER_AI_MODEL") or DEFAULT_OPENAI_MODEL)
    )

    hasil_langkah_akumulasi: List[Dict[str, Any]] = []
    rencana_terakhir: Dict[str, Any] = {}
    iterasi_maks = _resolve_agent_workflow_max_iterations(inputs, local_only_mode=local_only_mode)
    iterasi_sekarang = 0
    final_message_ditemukan = ""
    summary_akumulasi = []
    rencana_signatures_terakhir: List[str] = []

    while iterasi_sekarang < iterasi_maks:
        iterasi_sekarang += 1
        
        try:
            rencana_raw = await _panggil_planner_openai(
                prompt=prompt_pengguna,
                model_id=model_id,
                api_key=kunci_api_openai,
                provider_catalog=katalog_provider,
                mcp_catalog=katalog_mcp,
                command_allow_prefixes=daftar_prefix_perintah,
                allow_sensitive_commands=izinkan_perintah_sensitif,
                agent_memory_context=konteks_memori,
                current_iteration=iterasi_sekarang - 1,
                previous_results=hasil_langkah_akumulasi,
            )
            rencana_terakhir = _sanitasi_rencana(rencana_raw)
            rencana_terakhir = _terapkan_guardrail_memori(rencana_terakhir, konteks_memori)
            
            if rencana_terakhir.get("summary"):
                summary_akumulasi.append(f"It{iterasi_sekarang}: {rencana_terakhir['summary']}")
            
            if rencana_terakhir.get("final_message"):
                final_message_ditemukan = rencana_terakhir["final_message"]
                break
                
            if not rencana_terakhir.get("steps"):
                break

            signatures_saat_ini: List[str] = []
            for step in rencana_terakhir.get("steps", []):
                if not isinstance(step, dict):
                    continue
                signature = _signature_dari_step_rencana(step)
                if not signature:
                    kind = str(step.get("kind") or "").strip().lower() or "unknown"
                    if kind == "note":
                        signature = f"note:{_ringkas_teks(str(step.get('text') or '').strip().lower(), 120)}"
                    else:
                        try:
                            signature = f"{kind}:{_ringkas_teks(json.dumps(step, sort_keys=True), 160)}"
                        except Exception:
                            signature = kind
                signatures_saat_ini.append(signature)

            if local_only_mode and signatures_saat_ini and signatures_saat_ini == rencana_signatures_terakhir:
                final_message_ditemukan = "Planner lokal menghentikan loop karena rencana berulang."
                break
            if signatures_saat_ini:
                rencana_signatures_terakhir = signatures_saat_ini
                
        except Exception as exc:
            if not hasil_langkah_akumulasi:
                konteks_memori_terbaru = await _catat_memori(
                    success=False,
                    summary="Agent planner gagal menyusun langkah.",
                    final_message="",
                    step_results=[],
                    error=str(exc),
                )
                return {
                    "success": False,
                    "agent_key": agent_key,
                    "memory_context": konteks_memori_terbaru,
                    "experiment": experiment_payload,
                    "error": f"Agent planner gagal: {exc}",
                }
            final_message_ditemukan = f"Planner error pada iterasi {iterasi_sekarang}: {exc}"
            break

        request_izin = _kumpulkan_request_izin_dari_rencana(
            rencana_terakhir["steps"],
            provider_catalog=katalog_provider,
            mcp_catalog=katalog_mcp,
            command_allow_prefixes=daftar_prefix_perintah,
            allow_sensitive_commands=izinkan_perintah_sensitif,
            approved_sensitive_commands=perintah_sensitif_disetujui,
        )
        if request_izin and perlu_izin_saat_kurang:
            with suppress(Exception):
                await append_event(
                    "agent.approval_requested",
                    {
                        "prompt": prompt_pengguna[:200],
                        "reason": "missing_resources_for_plan",
                        "request_count": len(request_izin),
                        "requests": request_izin,
                    },
                )
            konteks_memori_terbaru = await _catat_memori(
                success=False,
                summary="Rencana butuh approval untuk resource/puzzle baru.",
                final_message="",
                step_results=hasil_langkah_akumulasi,
                error="requires_approval_for_missing_resources",
            )
            response_izin = _buat_respons_butuh_izin(
                prompt=prompt_pengguna,
                summary="Rencana butuh izin untuk menambah puzzle/skill.",
                model_id=model_id,
                approval_requests=request_izin,
                provider_catalog=katalog_provider,
                mcp_catalog=katalog_mcp,
                command_allow_prefixes=daftar_prefix_perintah,
                allow_sensitive_commands=izinkan_perintah_sensitif,
            )
            response_izin["agent_key"] = agent_key
            response_izin["memory_context"] = konteks_memori_terbaru
            response_izin["memory_guardrail"] = rencana_terakhir.get("memory_guardrail", [])
            response_izin["step_results"] = hasil_langkah_akumulasi
            response_izin["experiment"] = experiment_payload
            return response_izin

        # Execute steps for this iteration
        iter_results = []
        for step in rencana_terakhir["steps"]:
            kind = step.get("kind")
            if kind == "note":
                iter_results.append({"kind": "note", "success": True, "text": str(step.get("text") or "")})
                continue

            if kind == "provider_http":
                hasil = await _eksekusi_langkah_provider_http(ctx, step, katalog_provider, alat_http)
                iter_results.append(hasil)
            elif kind == "mcp_http":
                hasil = await _eksekusi_langkah_mcp_http(ctx, step, katalog_mcp, alat_http)
                iter_results.append(hasil)
            elif kind == "local_command":
                hasil = await _eksekusi_langkah_perintah_lokal(
                    ctx,
                    step,
                    alat_command,
                    daftar_prefix_perintah,
                    izinkan_perintah_sensitif,
                    perintah_sensitif_disetujui,
                )
                iter_results.append(hasil)
            elif kind == "multimedia":
                alat_multimedia = ctx.tools.get("multimedia")
                if not alat_multimedia:
                    iter_results.append({"kind": "multimedia", "success": False, "error": "multimedia tool not available"})
                else:
                    # Automatically inject branch_id if not provided
                    if "branch_id" not in step and branch_id_ctx:
                        step["branch_id"] = branch_id_ctx
                    hasil = await alat_multimedia(step, ctx)
                    iter_results.append(hasil)
            elif kind == "revenue":
                alat_revenue = ctx.tools.get("revenue")
                if not alat_revenue:
                    iter_results.append({"kind": "revenue", "success": False, "error": "revenue tool not available"})
                else:
                    if "branch_id" not in step and branch_id_ctx:
                        step["branch_id"] = branch_id_ctx
                    hasil = await alat_revenue(step, ctx)
                    iter_results.append(hasil)
            elif kind == "schedule_job":
                target_id = str(step.get("target_job_id") or "").strip()
                delay = int(step.get("delay_sec") or 3600)
                sub_inputs = step.get("inputs", {})
                
                if not target_id:
                    iter_results.append({"kind": "schedule_job", "success": False, "error": "target_job_id is required"})
                else:
                    try:
                        from app.core.models import QueueEvent
                        import uuid
                        from datetime import datetime, timezone, timedelta
                        
                        # In a real scenario, we would fetch the JobSpec first. 
                        # For this proactive loop, we assume the agent knows the job_id or schedules its own.
                        run_id = f"proactive_{uuid.uuid4().hex[:8]}"
                        event = QueueEvent(
                            run_id=run_id,
                            job_id=target_id,
                            type="agent.workflow", # Default to workflow for proactivity
                            inputs=sub_inputs,
                            attempt=0,
                            scheduled_at=(datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(),
                        )
                        await schedule_delayed_job(event, delay)
                        iter_results.append({
                            "kind": "schedule_job", 
                            "success": True, 
                            "target_job_id": target_id, 
                            "run_id": run_id, 
                            "delay_sec": delay
                        })
                    except Exception as e:
                        iter_results.append({"kind": "schedule_job", "success": False, "error": str(e)})
            elif kind == "create_proposal":
                title = str(step.get("title") or "New Opportunity Found").strip()
                analysis = str(step.get("analysis") or "").strip()
                proposed_plan = str(step.get("proposed_plan") or "").strip()
                impact = str(step.get("impact") or "Unknown").strip()
                
                try:
                    # Formulate internal approval request
                    approval_id = f"prop_{uuid.uuid4().hex[:8]}"
                    req_payload = {
                        "approval_id": approval_id,
                        "job_id": job_id_ctx,
                        "run_id": run_id_ctx,
                        "status": "pending",
                        "summary": f"Opportunity Discovery: {title}",
                        "details": {
                            "title": title,
                            "analysis": analysis,
                            "proposed_plan": proposed_plan,
                            "impact": impact,
                            "agent_key": agent_key
                        },
                        "approval_requests": [
                            {
                                "kind": "discovery_approval",
                                "reason": f"New profit method/opportunity identified: {title}",
                                "action_hint": "Review the analysis and click OKE to allow the agent to proceed with this method."
                            }
                        ]
                    }
                    await create_approval_request(req_payload)
                    
                    # Determine role for notification
                    role_label = "CEO"
                    if "research" in agent_key: role_label = "Manager Riset"
                    elif "growth" in agent_key: role_label = "Manager Growth"
                    elif "op" in agent_key: role_label = "Manager Operasional"
                    
                    # Send external notification with role
                    await _kirim_notifikasi_eksternal(title, impact, approval_id, role=role_label)
                    
                    iter_results.append({
                        "kind": "create_proposal", 
                        "success": True, 
                        "approval_id": approval_id, 
                        "message": "Proposal submitted for human review."
                    })
                except Exception as e:
                    iter_results.append({"kind": "create_proposal", "success": False, "error": str(e)})
            
            # Record each step to global results
            hasil_langkah_akumulasi.append(iter_results[-1])
            
            # If a critical step fails, we might want to let the agent re-plan immediately
            if not iter_results[-1].get("success") and kind != "note":
                break

        # Refresh memory context for next iteration
        await _muat_konteks_memori_terbaru()

        if local_only_mode:
            langkah_non_catatan = [
                row for row in iter_results if str(row.get("kind") or "").strip().lower() not in {"", "note"}
            ]
            if not langkah_non_catatan:
                if not final_message_ditemukan:
                    final_message_ditemukan = "Planner lokal selesai: tidak ada langkah aksi lanjutan."
                break

    langkah_aksi = [row for row in hasil_langkah_akumulasi if row.get("kind") in {"provider_http", "mcp_http", "local_command"}]
    sukses_total = all(bool(row.get("success")) for row in langkah_aksi) if langkah_aksi else True
    
    if not final_message_ditemukan and iterasi_sekarang >= iterasi_maks:
        final_message_ditemukan = f"Mencapai batas iterasi maksimum ({iterasi_maks})."

    provider_tersedia = {
        provider: sorted({str(row.get("account_id") or "default") for row in rows})
        for provider, rows in katalog_provider.items()
    }
    server_mcp_tersedia = sorted(katalog_mcp.keys())

    hasil = {
        "success": sukses_total,
        "agent_key": agent_key,
        "summary": " | ".join(summary_akumulasi),
        "final_message": final_message_ditemukan,
        "model_id": model_id,
        "prompt_original": prompt_awal,
        "prompt": prompt_pengguna,
        "iterations": iterasi_sekarang,
        "steps_planned": len(rencana_terakhir.get("steps", [])),
        "steps_executed": len(hasil_langkah_akumulasi),
        "step_results": hasil_langkah_akumulasi,
        "experiment": experiment_payload,
        "memory_context": konteks_memori,
        "memory_guardrail": rencana_terakhir.get("memory_guardrail", []),
        "available_providers": provider_tersedia,
        "available_mcp_servers": server_mcp_tersedia,
        "command_allow_prefixes": daftar_prefix_perintah,
        "allow_sensitive_commands": izinkan_perintah_sensitif,
    }
    with suppress(Exception):
        await append_event(
            "agent.workflow_executed",
            {
                "success": sukses_total,
                "iterations": iterasi_sekarang,
                "steps_executed": len(hasil_langkah_akumulasi),
                "experiment_applied": experiment_payload["applied"],
            },
        )
    konteks_memori_terbaru = await _catat_memori(
        success=sukses_total,
        summary=hasil["summary"],
        final_message=final_message_ditemukan,
        step_results=hasil_langkah_akumulasi,
        error=None if sukses_total else "workflow_autonomous_loop_failed",
    )
    hasil["memory_context"] = konteks_memori_terbaru
    return hasil
