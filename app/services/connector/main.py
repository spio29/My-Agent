import asyncio
import json
import os
import shlex
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from redis.exceptions import RedisError, TimeoutError as RedisTimeoutError

from app.core.connector_accounts import (
    get_telegram_last_update_id,
    list_telegram_accounts,
    set_telegram_last_update_id,
)
from app.core.observability import logger
from app.core.queue import append_event, is_mode_fallback_redis, set_mode_fallback_redis, try_recover_redis
from app.core.redis_client import redis_client
from app.services.api.planner import PlannerRequest, build_plan_from_prompt
from app.services.api.planner_ai import PlannerAiRequest, build_plan_with_ai_dari_dashboard
from app.services.api.planner_execute import PlannerExecuteRequest, execute_prompt_plan

# Heartbeat constants
HEARTBEAT_TTL = 30  # seconds
CONNECTOR_PREFIX = "hb:connector"
AGENT_HEARTBEAT_KEY = "hb:agent:connector:telegram-bridge"

TELEGRAM_API_BASE = "https://api.telegram.org"
POLL_TIMEOUT_SEC = 3
POLL_LOOP_SLEEP_SEC = 1
IDLE_SLEEP_SEC = 2
INTERNAL_API_ORIGIN = str(os.getenv("API_INTERNAL_ORIGIN") or "http://api:8000").rstrip("/")
CONNECTOR_API_TOKEN = str(os.getenv("CONNECTOR_API_TOKEN") or "").strip()
CONNECTOR_API_AUTH_HEADER = str(os.getenv("CONNECTOR_API_AUTH_HEADER") or "Authorization").strip() or "Authorization"
CONNECTOR_API_AUTH_SCHEME = str(os.getenv("CONNECTOR_API_AUTH_SCHEME") or "Bearer").strip()
NO_CODE_EASY_SCRIPT = str(os.getenv("NO_CODE_EASY_SCRIPT") or "/app/ops/no-code/easy.sh").strip() or "/app/ops/no-code/easy.sh"
NO_CODE_MAX_ARGS = 20
NO_CODE_ALLOWED_CMDS = {
    "status",
    "nyala",
    "mati",
    "strategi",
    "nada",
    "followup",
    "ritme",
    "jadwal",
    "kanal",
    "rantai",
    "paket",
}


async def _is_redis_ready() -> bool:
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=0.5)
        return True
    except (RedisError, RedisTimeoutError, asyncio.TimeoutError, OSError):
        return False
    except Exception:
        return False


def _switch_fallback_redis(error: Exception) -> None:
    if is_mode_fallback_redis():
        return
    set_mode_fallback_redis(True)
    logger.warning(
        "Redis connector tidak tersedia, beralih ke fallback mode",
        extra={"error": str(error)},
    )


async def kirim_heartbeat_konektor(channel: str, account_id: str, status: str = "online"):
    """Update connector heartbeat in Redis."""
    if is_mode_fallback_redis():
        recovered = await try_recover_redis()
        if not recovered:
            return

    key = f"{CONNECTOR_PREFIX}:{channel}:{account_id}"
    try:
        await redis_client.setex(key, HEARTBEAT_TTL, status)
    except Exception as exc:
        _switch_fallback_redis(exc)


async def pantau_konektor():
    """Monitor connector heartbeats and log when one goes stale."""
    while True:
        try:
            if is_mode_fallback_redis():
                recovered = await try_recover_redis()
                if not recovered:
                    await asyncio.sleep(10)
                    continue

            daftar_kunci = await redis_client.keys(f"{CONNECTOR_PREFIX}:*")

            for key in daftar_kunci:
                bagian = key.split(":")
                if len(bagian) < 4:
                    continue
                channel = bagian[2]
                account_id = bagian[3]
                status = await redis_client.get(key)
                if not status:
                    logger.warning(
                        "Connector heartbeat expired",
                        extra={"channel": channel, "account_id": account_id},
                    )

            await asyncio.sleep(10)
        except Exception as exc:
            _switch_fallback_redis(exc)
            logger.error(f"Error monitoring connectors: {exc}")
            await asyncio.sleep(5)


def _chat_diizinkan(chat_id: Any, allowed_chat_ids: List[str]) -> bool:
    if not allowed_chat_ids:
        return True
    chat_id_str = str(chat_id).strip()
    return chat_id_str in {str(value).strip() for value in allowed_chat_ids if str(value).strip()}


def _ekstrak_perintah_dan_prompt_dari_teks(text: str) -> Dict[str, str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"command": "", "prompt": ""}

    daftar_prefix = {
        "/run": "run",
        "/exec": "exec",
        "/lead": "lead",
        "/inbound": "lead",
        "/won": "won",
        "/lost": "lost",
        "/ops": "ops",
        "/cc": "ops",
    }
    lowered = cleaned.lower()
    for prefix, command in daftar_prefix.items():
        if lowered.startswith(prefix):
            return {"command": command, "prompt": cleaned[len(prefix) :].strip()}
    return {"command": "", "prompt": ""}


def _build_api_auth_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if not CONNECTOR_API_TOKEN:
        return headers
    token_value = CONNECTOR_API_TOKEN
    if CONNECTOR_API_AUTH_SCHEME:
        token_value = f"{CONNECTOR_API_AUTH_SCHEME} {CONNECTOR_API_TOKEN}"
    headers[CONNECTOR_API_AUTH_HEADER] = token_value
    return headers


def _extract_sender_name(message: Dict[str, Any], chat_id: Any) -> str:
    sender = message.get("from") or {}
    first_name = str(sender.get("first_name") or "").strip()
    last_name = str(sender.get("last_name") or "").strip()
    username = str(sender.get("username") or "").strip()
    full_name = " ".join([part for part in [first_name, last_name] if part]).strip()
    if full_name:
        return full_name
    if username:
        return username
    return f"Lead {str(chat_id).strip()}"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _parse_command_lead_prompt(
    prompt: str,
    *,
    chat_id: Any,
    fallback_name: str,
    default_branch_id: str,
) -> Dict[str, Any]:
    clean_prompt = str(prompt or "").strip()
    if clean_prompt.startswith("{") and clean_prompt.endswith("}"):
        try:
            payload = json.loads(clean_prompt)
            if isinstance(payload, dict):
                body = dict(payload)
                body.setdefault("channel", "telegram")
                body.setdefault("contact_id", str(chat_id))
                body.setdefault("name", fallback_name)
                body.setdefault("branch_id", default_branch_id)
                return body
        except Exception:
            pass

    parts = [part.strip() for part in clean_prompt.split("|")]
    head = parts[0] if parts else ""
    head_tokens = [token.strip() for token in head.split() if token.strip()]

    channel = head_tokens[0].lower() if len(head_tokens) >= 1 else "telegram"
    contact_id = head_tokens[1] if len(head_tokens) >= 2 else str(chat_id)
    branch_id = head_tokens[2].lower() if len(head_tokens) >= 3 else default_branch_id

    name = parts[1] if len(parts) >= 2 and parts[1] else fallback_name
    offer = parts[2] if len(parts) >= 3 else ""
    message = parts[3] if len(parts) >= 4 else ""
    value_estimate = _safe_float(parts[4], 0.0) if len(parts) >= 5 else 0.0

    return {
        "branch_id": branch_id,
        "channel": channel,
        "contact_id": contact_id,
        "name": name,
        "source": "telegram.command.lead",
        "offer": offer,
        "message": message,
        "value_estimate": value_estimate,
    }


def _format_help_text() -> str:
    return (
        "Spio siap.\n"
        "- /run <perintah> = diskusi manager (rencana dulu, belum jalan)\n"
        "- /exec <perintah> = eksekusi penuh\n"
        "- /ops <aksi> = kontrol no-code (status/nyala/mati/strategi/dll)\n"
        "- /lead <channel> <contact> [branch] | <nama> | <offer> | <pesan> | <value>\n"
        "- /won <prospect_id> <amount> [catatan]\n"
        "- /lost <prospect_id> [alasan]"
    )


def _format_ops_help_text() -> str:
    return (
        "Format /ops:\n"
        "- /ops status all\n"
        "- /ops nyala inf_001\n"
        "- /ops mati all\n"
        "- /ops strategi inf_001 natural|lembut|closing|endorse\n"
        "- /ops nada inf_001 warm|formal|tegas\n"
        "- /ops followup inf_001 lembut|keras|formal\n"
        "- /ops ritme inf_001 lambat|normal|cepat\n"
        "- /ops jadwal inf_001 09:00 09:30 21:00\n"
        "- /ops kanal inf_001 ig,fb,wa\n"
        "- /ops rantai all 09:00 70 130 80\n"
        "- /ops paket inf_001 santai|normal|agresif 09:00\n"
    )


async def _jalankan_no_code_ops(prompt: str) -> Dict[str, Any]:
    text = str(prompt or "").strip()
    if not text:
        return {"ok": False, "error": "Perintah /ops kosong.", "output": _format_ops_help_text()}

    try:
        args = shlex.split(text)
    except Exception:
        return {"ok": False, "error": "Format argumen /ops tidak valid.", "output": _format_ops_help_text()}

    if not args:
        return {"ok": False, "error": "Perintah /ops kosong.", "output": _format_ops_help_text()}
    if len(args) > NO_CODE_MAX_ARGS:
        return {"ok": False, "error": "Argumen terlalu panjang.", "output": _format_ops_help_text()}

    command = str(args[0]).strip().lower()
    if command not in NO_CODE_ALLOWED_CMDS:
        return {
            "ok": False,
            "error": f"Aksi /ops '{command}' tidak diizinkan.",
            "output": _format_ops_help_text(),
        }

    if not os.path.exists(NO_CODE_EASY_SCRIPT):
        return {
            "ok": False,
            "error": f"Script no-code tidak ditemukan: {NO_CODE_EASY_SCRIPT}",
            "output": "",
        }

    env = dict(os.environ)
    env.setdefault("SPIO_API_URL", INTERNAL_API_ORIGIN)
    if CONNECTOR_API_TOKEN:
        env.setdefault("SPIO_ADMIN_TOKEN", CONNECTOR_API_TOKEN)

    process = await asyncio.create_subprocess_exec(
        NO_CODE_EASY_SCRIPT,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=35)
    except asyncio.TimeoutError:
        with suppress(Exception):
            process.kill()
        return {"ok": False, "error": "Timeout menjalankan /ops.", "output": ""}

    out = (stdout or b"").decode("utf-8", errors="ignore").strip()
    err = (stderr or b"").decode("utf-8", errors="ignore").strip()
    merged = "\n".join([part for part in [out, err] if part]).strip()

    if process.returncode != 0:
        return {
            "ok": False,
            "error": f"/ops exit code {process.returncode}",
            "output": merged or "Tidak ada output.",
        }
    return {"ok": True, "output": merged or "OK"}


def _format_balasan_rencana(rencana: Any) -> str:
    def _format_jadwal(job: Any) -> str:
        schedule = getattr(getattr(job, "job_spec", None), "schedule", None)
        if not schedule:
            return "tanpa jadwal (event-driven)"
        interval = getattr(schedule, "interval_sec", None)
        cron = getattr(schedule, "cron", None)
        if interval:
            return f"interval {interval} detik"
        if cron:
            return f"cron {cron}"
        return "tanpa jadwal"

    lines = [
        "Spio Manager: rencana awal sudah siap (belum dieksekusi).",
        "",
        "Ringkasan Diskusi",
        f"- Sumber perencana: {getattr(rencana, 'planner_source', '-')}",
        f"- Ringkasan: {getattr(rencana, 'summary', '-')}",
        f"- Jumlah rencana job: {len(getattr(rencana, 'jobs', []))}",
    ]

    jobs = getattr(rencana, "jobs", []) or []
    if jobs:
        lines.append("- Draft job:")
    for row in jobs[:6]:
        job_spec = getattr(row, "job_spec", None)
        job_id = getattr(job_spec, "job_id", "-")
        job_type = getattr(job_spec, "type", "-")
        reason = getattr(row, "reason", "-")
        lines.append(f"  - {job_id} [{job_type}] ({_format_jadwal(row)})")
        lines.append(f"    alasan: {reason}")

    assumptions = list(getattr(rencana, "assumptions", []) or [])
    if assumptions:
        lines.append("- Asumsi:")
        for item in assumptions[:4]:
            lines.append(f"  - {item}")

    warnings = list(getattr(rencana, "warnings", []) or [])
    if warnings:
        lines.append("- Catatan:")
        for item in warnings[:4]:
            lines.append(f"  - {item}")

    lines.extend(
        [
            "",
            "Lanjutkan dengan /exec <instruksi final> kalau sudah oke.",
        ]
    )

    text = "\n".join(lines)
    if len(text) > 3800:
        return text[:3797] + "..."
    return text


def _format_balasan_eksekusi(execution: Any) -> str:
    def terjemah_status(status: Optional[str]) -> str:
        peta = {
            "created": "dibuat",
            "updated": "diperbarui",
            "error": "gagal simpan",
            "queued": "antre",
            "running": "berjalan",
            "success": "berhasil",
            "failed": "gagal",
        }
        if not status:
            return "-"
        return peta.get(status, status)

    def label_perencana(source: Optional[str]) -> str:
        if source == "smolagents":
            return "Smolagents"
        if source == "rule_based":
            return "Berbasis Aturan"
        return str(source or "-")

    def format_detail_teknis_per_hasil(row: Any) -> str:
        run_status = row.run_status or row.queue_status or "-"
        return (
            f"- job_id={row.job_id}; type={row.type}; "
            f"create_status={row.create_status}; run_status={run_status}"
        )

    jumlah_dibuat = sum(1 for row in execution.results if row.create_status == "created")
    jumlah_diperbarui = sum(1 for row in execution.results if row.create_status == "updated")
    jumlah_error = sum(1 for row in execution.results if row.create_status == "error")
    run_berhasil = sum(1 for row in execution.results if row.run_status == "success")
    run_gagal = sum(1 for row in execution.results if row.run_status == "failed")

    lines = [
        "Spio: perintah sudah diproses.",
        "",
        "Ringkasan (Bahasa Indonesia)",
        f"- Sumber perencana: {label_perencana(getattr(execution, 'planner_source', None))}",
        f"- Ringkasan sistem: {execution.summary}",
        f"- Jumlah tugas: {len(execution.results)} (dibuat {jumlah_dibuat}, diperbarui {jumlah_diperbarui}, gagal {jumlah_error})",
        f"- Hasil eksekusi: berhasil {run_berhasil}, gagal {run_gagal}",
    ]

    if execution.results:
        lines.append("- Sampel hasil:")
    for row in execution.results[:5]:
        run_label = row.run_status or row.queue_status or "-"
        lines.append(f"  - {row.job_id}: {terjemah_status(row.create_status)}, eksekusi {terjemah_status(run_label)}")

    if execution.warnings:
        lines.append("- Catatan: " + "; ".join(execution.warnings[:2]))

    lines.extend(
        [
            "",
            "Detail Teknis Sistem",
            f"- planner_source={execution.planner_source}",
            f"- total_results={len(execution.results)}",
            f"- create_status: created={jumlah_dibuat}, updated={jumlah_diperbarui}, error={jumlah_error}",
            f"- run_status: success={run_berhasil}, failed={run_gagal}",
        ]
    )

    for row in execution.results[:5]:
        lines.append(format_detail_teknis_per_hasil(row))

    lines.extend(
        [
            "",
            "Terjemahan Istilah Teknis",
            "- created=dibuat; updated=diperbarui; error=gagal simpan",
            "- queued=antre; running=berjalan; success=berhasil; failed=gagal",
        ]
    )

    text = "\n".join(lines)
    if len(text) > 3800:
        return text[:3797] + "..."
    return text


async def _panggil_api_telegram(
    session: aiohttp.ClientSession,
    bot_token: str,
    method: str,
    payload: Dict[str, Any],
) -> Optional[Any]:
    url_api = f"{TELEGRAM_API_BASE}/bot{bot_token}/{method}"
    try:
        async with session.post(url_api, json=payload) as response:
            data_respons = await response.json(content_type=None)
            if response.status >= 400:
                logger.warning(
                    "Telegram API status error",
                    extra={"method": method, "status": response.status, "response": data_respons},
                )
                return None
            if not isinstance(data_respons, dict) or not data_respons.get("ok"):
                logger.warning(
                    "Telegram API returned non-ok payload",
                    extra={"method": method, "response": data_respons},
                )
                return None
            return data_respons.get("result")
    except Exception as exc:
        logger.warning("Telegram API call failed", extra={"method": method, "error": str(exc)})
        return None


async def _kirim_pesan_telegram(
    session: aiohttp.ClientSession,
    bot_token: str,
    chat_id: Any,
    text: str,
) -> None:
    await _panggil_api_telegram(
        session,
        bot_token,
        "sendMessage",
        {"chat_id": chat_id, "text": text[:3800]},
    )


async def _panggil_api_internal(
    session: aiohttp.ClientSession,
    *,
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = f"{INTERNAL_API_ORIGIN}{path}"
    headers = _build_api_auth_headers()
    try:
        async with session.request(method.upper(), url, json=payload, headers=headers) as response:
            body = await response.json(content_type=None)
            if 200 <= response.status < 300:
                if isinstance(body, dict):
                    return {"ok": True, "status": response.status, "data": body}
                return {"ok": True, "status": response.status, "data": {"raw": body}}
            return {"ok": False, "status": response.status, "error": body}
    except Exception as exc:
        return {"ok": False, "status": 0, "error": {"detail": str(exc)}}


async def _handle_sales_inbound(
    session: aiohttp.ClientSession,
    *,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    clean_payload = dict(payload)
    if "branch_id" in clean_payload:
        clean_payload["branch_id"] = str(clean_payload.get("branch_id") or "").strip().lower()
    if "channel" in clean_payload:
        clean_payload["channel"] = str(clean_payload.get("channel") or "").strip().lower()
    if "contact_id" in clean_payload:
        clean_payload["contact_id"] = str(clean_payload.get("contact_id") or "").strip()

    return await _panggil_api_internal(
        session,
        method="POST",
        path="/sales/inbound",
        payload=clean_payload,
    )


async def _handle_close_won(
    session: aiohttp.ClientSession,
    *,
    prospect_id: str,
    amount: float,
    note: str = "",
) -> Dict[str, Any]:
    return await _panggil_api_internal(
        session,
        method="POST",
        path=f"/sales/prospects/{prospect_id}/close-won",
        payload={
            "amount": float(amount),
            "note": str(note or "").strip(),
        },
    )


async def _handle_close_lost(
    session: aiohttp.ClientSession,
    *,
    prospect_id: str,
    reason: str = "",
) -> Dict[str, Any]:
    return await _panggil_api_internal(
        session,
        method="POST",
        path=f"/sales/prospects/{prospect_id}/close-lost",
        payload={"reason": str(reason or "").strip()},
    )


async def _proses_update_telegram(
    session: aiohttp.ClientSession,
    account: Dict[str, Any],
    update: Dict[str, Any],
) -> None:
    id_akun = account["account_id"]
    bot_token = str(account.get("bot_token") or "")

    id_update = int(update.get("update_id") or 0)
    if id_update > 0:
        await set_telegram_last_update_id(id_akun, id_update)

    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = str(message.get("text") or "").strip()

    if chat_id is None or not text:
        return

    if text.lower() in {"/start", "/help"}:
        await _kirim_pesan_telegram(
            session,
            bot_token,
            chat_id,
            _format_help_text(),
        )
        return

    if not _chat_diizinkan(chat_id, account.get("allowed_chat_ids", [])):
        await _kirim_pesan_telegram(
            session,
            bot_token,
            chat_id,
            "Chat ini belum diizinkan untuk menjalankan perintah.",
        )
        await append_event(
            "telegram.command.rejected",
            {"account_id": id_akun, "chat_id": str(chat_id), "reason": "chat_not_allowed"},
        )
        return

    default_branch_id = str(account.get("default_branch_id") or "br_01").strip().lower() or "br_01"
    default_account_id = str(account.get("default_account_id", id_akun))
    sender_name = _extract_sender_name(message, chat_id)
    capture_inbound_text = bool(account.get("capture_inbound_text", False))
    inbound_auto_followup = bool(account.get("inbound_auto_followup", True))
    inbound_followup_template = str(account.get("inbound_followup_template") or "").strip()

    perintah = _ekstrak_perintah_dan_prompt_dari_teks(text)
    command = perintah.get("command", "")
    prompt = perintah.get("prompt", "")
    if not command:
        if capture_inbound_text:
            inbound_payload = {
                "branch_id": default_branch_id,
                "channel": "telegram",
                "contact_id": str(chat_id),
                "name": sender_name,
                "source": "telegram.inbound.text",
                "message": text,
                "tags": ["telegram", "inbound"],
                "auto_followup": inbound_auto_followup,
                "account_id": default_account_id,
            }
            if inbound_followup_template:
                inbound_payload["followup_template"] = inbound_followup_template

            inbound_result = await _handle_sales_inbound(session, payload=inbound_payload)
            if inbound_result.get("ok"):
                body = inbound_result.get("data", {})
                prospect_id = str(body.get("prospect_id") or "-")
                action = str(body.get("action") or "created")
                await _kirim_pesan_telegram(
                    session,
                    bot_token,
                    chat_id,
                    f"Inbound tercatat ({action}). prospect_id={prospect_id}",
                )
                await append_event(
                    "telegram.inbound.captured",
                    {
                        "account_id": id_akun,
                        "chat_id": str(chat_id),
                        "prospect_id": prospect_id,
                        "action": action,
                    },
                )
            else:
                await _kirim_pesan_telegram(
                    session,
                    bot_token,
                    chat_id,
                    "Gagal mencatat inbound. Coba lagi atau pakai format /lead.",
                )
                await append_event(
                    "telegram.inbound.failed",
                    {
                        "account_id": id_akun,
                        "chat_id": str(chat_id),
                        "error": inbound_result.get("error"),
                    },
                )
            return

        await _kirim_pesan_telegram(session, bot_token, chat_id, "Perintah belum dikenali.\n" + _format_help_text())
        return

    if command in {"run", "exec", "lead", "won", "lost"} and not prompt:
        await _kirim_pesan_telegram(
            session,
            bot_token,
            chat_id,
            "Perintah kosong. Cek format dengan /help.",
        )
        return

    await append_event(
        "telegram.command.received",
        {"account_id": id_akun, "chat_id": str(chat_id), "prompt": prompt[:200], "command": command},
    )

    try:
        use_ai = bool(account.get("use_ai", True))
        force_rule_based = bool(account.get("force_rule_based", False))
        timezone = str(account.get("timezone", "Asia/Jakarta"))
        default_channel = str(account.get("default_channel", "telegram"))

        if command == "run":
            if use_ai:
                plan_request = PlannerAiRequest(
                    prompt=prompt,
                    force_rule_based=force_rule_based,
                    timezone=timezone,
                    default_channel=default_channel,
                    default_account_id=default_account_id,
                )
                rencana = await build_plan_with_ai_dari_dashboard(plan_request)
            else:
                plan_request = PlannerRequest(
                    prompt=prompt,
                    timezone=timezone,
                    default_channel=default_channel,
                    default_account_id=default_account_id,
                )
                rencana = build_plan_from_prompt(plan_request)

            teks_balasan = _format_balasan_rencana(rencana)
            await _kirim_pesan_telegram(session, bot_token, chat_id, teks_balasan)
            await append_event(
                "telegram.command.planned",
                {
                    "account_id": id_akun,
                    "chat_id": str(chat_id),
                    "planner_source": rencana.planner_source,
                    "job_count": len(rencana.jobs),
                },
            )
            return

        if command == "ops":
            hasil_ops = await _jalankan_no_code_ops(prompt)
            if hasil_ops.get("ok"):
                output = str(hasil_ops.get("output") or "OK")
                await _kirim_pesan_telegram(
                    session,
                    bot_token,
                    chat_id,
                    "No-Code OPS sukses.\n\n" + output,
                )
                await append_event(
                    "telegram.command.ops",
                    {
                        "account_id": id_akun,
                        "chat_id": str(chat_id),
                        "status": "ok",
                        "prompt": prompt[:300],
                    },
                )
            else:
                output = str(hasil_ops.get("output") or "")
                error = str(hasil_ops.get("error") or "Unknown error")
                response = "No-Code OPS gagal.\n" + error
                if output:
                    response += "\n\n" + output
                await _kirim_pesan_telegram(
                    session,
                    bot_token,
                    chat_id,
                    response,
                )
                await append_event(
                    "telegram.command.ops",
                    {
                        "account_id": id_akun,
                        "chat_id": str(chat_id),
                        "status": "failed",
                        "error": error,
                        "prompt": prompt[:300],
                    },
                )
            return

        if command == "exec":
            request = PlannerExecuteRequest(
                prompt=prompt,
                use_ai=use_ai,
                force_rule_based=force_rule_based,
                run_immediately=bool(account.get("run_immediately", True)),
                wait_seconds=int(account.get("wait_seconds", 2)),
                timezone=timezone,
                default_channel=default_channel,
                default_account_id=default_account_id,
            )

            hasil_eksekusi = await execute_prompt_plan(request)
            teks_balasan = _format_balasan_eksekusi(hasil_eksekusi)
            await _kirim_pesan_telegram(session, bot_token, chat_id, teks_balasan)

            await append_event(
                "telegram.command.executed",
                {
                    "account_id": id_akun,
                    "chat_id": str(chat_id),
                    "planner_source": hasil_eksekusi.planner_source,
                    "job_count": len(hasil_eksekusi.results),
                },
            )
            return

        if command == "lead":
            payload = _parse_command_lead_prompt(
                prompt,
                chat_id=chat_id,
                fallback_name=sender_name,
                default_branch_id=default_branch_id,
            )
            payload.setdefault("branch_id", default_branch_id)
            payload.setdefault("channel", "telegram")
            payload.setdefault("contact_id", str(chat_id))
            payload.setdefault("name", sender_name)
            payload.setdefault("source", "telegram.command.lead")
            payload["auto_followup"] = inbound_auto_followup
            payload["account_id"] = default_account_id
            if inbound_followup_template:
                payload.setdefault("followup_template", inbound_followup_template)

            inbound_result = await _handle_sales_inbound(session, payload=payload)
            if inbound_result.get("ok"):
                body = inbound_result.get("data", {})
                prospect_id = str(body.get("prospect_id") or "-")
                action = str(body.get("action") or "created")
                run_id = str(body.get("run_id") or "").strip()
                followup_note = f"; followup_run={run_id}" if run_id else ""
                await _kirim_pesan_telegram(
                    session,
                    bot_token,
                    chat_id,
                    f"Lead {action}. prospect_id={prospect_id}{followup_note}",
                )
                await append_event(
                    "telegram.command.lead",
                    {
                        "account_id": id_akun,
                        "chat_id": str(chat_id),
                        "prospect_id": prospect_id,
                        "action": action,
                        "run_id": run_id,
                    },
                )
            else:
                await _kirim_pesan_telegram(
                    session,
                    bot_token,
                    chat_id,
                    f"Gagal proses /lead. detail={inbound_result.get('error')}",
                )
                await append_event(
                    "telegram.command.lead_failed",
                    {
                        "account_id": id_akun,
                        "chat_id": str(chat_id),
                        "error": inbound_result.get("error"),
                    },
                )
            return

        if command == "won":
            tokens = [token.strip() for token in prompt.split(" ", 2) if token.strip()]
            if len(tokens) < 2:
                await _kirim_pesan_telegram(
                    session,
                    bot_token,
                    chat_id,
                    "Format /won: /won <prospect_id> <amount> [catatan]",
                )
                return
            prospect_id = tokens[0]
            amount = _safe_float(tokens[1], -1)
            note = tokens[2] if len(tokens) >= 3 else "closed via telegram command"
            if amount <= 0:
                await _kirim_pesan_telegram(session, bot_token, chat_id, "Amount harus lebih dari 0.")
                return

            close_result = await _handle_close_won(session, prospect_id=prospect_id, amount=amount, note=note)
            if close_result.get("ok"):
                row = close_result.get("data", {})
                await _kirim_pesan_telegram(
                    session,
                    bot_token,
                    chat_id,
                    f"Prospect WON. id={row.get('prospect_id')} amount={int(amount)}",
                )
                await append_event(
                    "telegram.command.won",
                    {"account_id": id_akun, "chat_id": str(chat_id), "prospect_id": prospect_id, "amount": amount},
                )
            else:
                await _kirim_pesan_telegram(
                    session,
                    bot_token,
                    chat_id,
                    f"Gagal /won. detail={close_result.get('error')}",
                )
            return

        if command == "lost":
            tokens = [token.strip() for token in prompt.split(" ", 1) if token.strip()]
            if len(tokens) < 1:
                await _kirim_pesan_telegram(
                    session,
                    bot_token,
                    chat_id,
                    "Format /lost: /lost <prospect_id> [alasan]",
                )
                return
            prospect_id = tokens[0]
            reason = tokens[1] if len(tokens) >= 2 else "lost via telegram command"

            close_result = await _handle_close_lost(session, prospect_id=prospect_id, reason=reason)
            if close_result.get("ok"):
                row = close_result.get("data", {})
                await _kirim_pesan_telegram(
                    session,
                    bot_token,
                    chat_id,
                    f"Prospect LOST. id={row.get('prospect_id')}",
                )
                await append_event(
                    "telegram.command.lost",
                    {"account_id": id_akun, "chat_id": str(chat_id), "prospect_id": prospect_id},
                )
            else:
                await _kirim_pesan_telegram(
                    session,
                    bot_token,
                    chat_id,
                    f"Gagal /lost. detail={close_result.get('error')}",
                )
            return
    except Exception as exc:
        pesan_error = "\n".join(
            [
                "Spio gagal menjalankan perintah.",
                f"Ringkasan: {exc}",
                f"Detail teknis: error_type={exc.__class__.__name__}; error_message={exc}",
            ]
        )
        await _kirim_pesan_telegram(session, bot_token, chat_id, pesan_error)
        await append_event(
            "telegram.command.failed",
            {"account_id": id_akun, "chat_id": str(chat_id), "error": str(exc)},
        )


async def _polling_akun(session: aiohttp.ClientSession, account: Dict[str, Any]) -> None:
    id_akun = account["account_id"]
    bot_token = str(account.get("bot_token") or "").strip()
    aktif = bool(account.get("enabled", True))

    if not aktif:
        await kirim_heartbeat_konektor("telegram", id_akun, "offline")
        return

    if not bot_token:
        await kirim_heartbeat_konektor("telegram", id_akun, "degraded")
        return

    await kirim_heartbeat_konektor("telegram", id_akun, "connected")

    id_update_terakhir = await get_telegram_last_update_id(id_akun)
    payload: Dict[str, Any] = {"timeout": POLL_TIMEOUT_SEC}
    if id_update_terakhir > 0:
        payload["offset"] = id_update_terakhir + 1

    daftar_update = await _panggil_api_telegram(session, bot_token, "getUpdates", payload)
    if not daftar_update:
        return

    for update in daftar_update:
        if isinstance(update, dict):
            await _proses_update_telegram(session, account, update)


async def telegram_connector():
    """Telegram bridge: read messages and execute planner commands."""
    logger.info("Starting Telegram connector bridge")

    timeout = aiohttp.ClientTimeout(total=POLL_TIMEOUT_SEC + 8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                daftar_akun = await list_telegram_accounts(include_secret=True)
                if not is_mode_fallback_redis():
                    try:
                        await redis_client.setex(AGENT_HEARTBEAT_KEY, HEARTBEAT_TTL, "connected")
                    except Exception as exc:
                        _switch_fallback_redis(exc)

                if not daftar_akun:
                    await asyncio.sleep(IDLE_SLEEP_SEC)
                    continue

                for account in daftar_akun:
                    await _polling_akun(session, account)

                await asyncio.sleep(POLL_LOOP_SLEEP_SEC)
            except Exception as exc:
                logger.error(f"Telegram connector loop error: {exc}")
                await asyncio.sleep(3)


async def connector_main():
    """Main connector loop."""
    redis_ready = await _is_redis_ready()
    set_mode_fallback_redis(not redis_ready)
    if not redis_ready:
        logger.warning("Connector berjalan tanpa Redis (fallback mode aktif).")

    await append_event(
        "system.connector_started",
        {"message": "Connector service started", "redis_ready": redis_ready},
    )
    daftar_tugas = [
        asyncio.create_task(telegram_connector()),
        asyncio.create_task(pantau_konektor()),
    ]
    await asyncio.gather(*daftar_tugas)


if __name__ == "__main__":
    asyncio.run(connector_main())
