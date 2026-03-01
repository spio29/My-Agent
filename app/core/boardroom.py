import asyncio
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from .config import settings
from .models import QueueEvent, Run, RunStatus
from .queue import add_run_to_job_history, append_event, enqueue_job, save_run
from .redis_client import redis_client

CHAT_HISTORY_KEY = "boardroom:chat:history"
MAX_HISTORY = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(text: str) -> str:
    cleaned = str(text or "")
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?\s*think\s*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _resolve_boardroom_timeout() -> int:
    raw = str(os.getenv("BOARDROOM_AI_TIMEOUT_SEC") or "18").strip()
    try:
        return max(5, min(60, int(raw)))
    except Exception:
        return 18


def _resolve_chat_completions_url() -> str:
    base = str(settings.LOCAL_AI_URL or "").strip() or "http://localhost:11434/v1"
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _looks_like_operational_command(text: str) -> bool:
    lowered = str(text or "").lower()
    keywords = [
        "closing",
        "close deal",
        "deal",
        "catat closing",
        "record closing",
        "revenue",
        "omzet",
        "tambah lead",
        "leads",
        "update kpi",
    ]
    return any(keyword in lowered for keyword in keywords)


def _extract_branch_id(text: str) -> str:
    match = re.search(r"\b(br_[a-z0-9_-]+)\b", str(text or "").lower())
    return match.group(1) if match else ""


def _parse_amount_idr(text: str) -> float:
    normalized = str(text or "").lower()

    direct = re.search(r"(?:rp|idr)\s*([0-9][0-9\.,]*)", normalized)
    if direct:
        digits = re.sub(r"[^0-9]", "", direct.group(1))
        if digits:
            return float(digits)

    compact = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*(juta|jt|m|ribu|rb|k)\b", normalized)
    if compact:
        raw_value = compact.group(1).replace(",", ".")
        unit = compact.group(2)
        try:
            value = float(raw_value)
        except Exception:
            value = 0.0
        multiplier = 1.0
        if unit in {"juta", "jt", "m"}:
            multiplier = 1_000_000.0
        elif unit in {"ribu", "rb", "k"}:
            multiplier = 1_000.0
        return value * multiplier

    return 0.0


def _parse_leads(text: str) -> int:
    normalized = str(text or "").lower()
    patterns = [
        r"leads?\s*(?:\+|=|naik|tambah)?\s*([0-9]+)",
        r"([0-9]+)\s*leads?\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            try:
                return max(0, int(match.group(1)))
            except Exception:
                continue
    return 0


def _extract_customer(text: str) -> str:
    match = re.search(
        r"(?:customer|pelanggan)\s*[:=]?\s*([a-zA-Z0-9_.\-\s]{2,40})",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return " ".join(match.group(1).strip().split())


def _extract_operational_command(text: str) -> Dict[str, Any]:
    lowered = str(text or "").lower()
    branch_id = _extract_branch_id(lowered)
    if not branch_id:
        return {}

    closing_keywords = [
        "catat closing",
        "record closing",
        "closing",
        "close deal",
        "deal",
        "penjualan",
        "revenue",
        "omzet",
    ]
    if any(keyword in lowered for keyword in closing_keywords):
        amount = _parse_amount_idr(lowered)
        if amount > 0:
            command: Dict[str, Any] = {
                "mode": "closing",
                "branch_id": branch_id,
                "amount": amount,
                "closings": 1,
            }
            leads = _parse_leads(lowered)
            if leads > 0:
                command["leads"] = leads
            customer = _extract_customer(text)
            if customer:
                command["customer"] = customer
            return command

    if "lead" in lowered:
        leads = _parse_leads(lowered)
        if leads > 0:
            return {"mode": "leads", "branch_id": branch_id, "leads": leads}

    return {}


async def _enqueue_boardroom_command(command: Dict[str, Any]) -> Dict[str, str]:
    now = datetime.now(timezone.utc)
    run_id = f"run_{int(now.timestamp())}_{uuid.uuid4().hex[:8]}"
    trace_id = f"trace_{uuid.uuid4().hex}"
    branch_id = str(command.get("branch_id") or "unknown").strip()
    job_id = f"boardroom-exec-{branch_id}"

    payload_inputs = dict(command)
    payload_inputs["source"] = "boardroom.chat"

    run = Run(
        run_id=run_id,
        job_id=job_id,
        status=RunStatus.QUEUED,
        attempt=0,
        scheduled_at=now,
        inputs=payload_inputs,
        trace_id=trace_id,
    )
    await save_run(run)
    await add_run_to_job_history(job_id, run_id)

    event = QueueEvent(
        run_id=run_id,
        job_id=job_id,
        type="boardroom.execute",
        inputs=payload_inputs,
        attempt=0,
        scheduled_at=now.isoformat(),
        timeout_ms=30000,
        trace_id=trace_id,
    )
    await enqueue_job(event)
    await append_event(
        "run.queued",
        {"run_id": run_id, "job_id": job_id, "job_type": "boardroom.execute", "source": "boardroom.chat"},
    )
    return {"job_id": job_id, "run_id": run_id}


def _request_ceo_reply_sync(text: str) -> str:
    prompt = _clean_text(text)
    if not prompt:
        return ""

    model_id = str(os.getenv("BOARDROOM_AI_MODEL") or settings.PLANNER_AI_MODEL or "").strip() or "gpt-4o-mini"
    timeout_sec = _resolve_boardroom_timeout()

    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Anda adalah CEO SPIO. Jawab dalam Bahasa Indonesia yang profesional, "
                    "langsung ke inti, dan actionable. Maksimal 5 kalimat. "
                    "Jangan gunakan tag <think> atau chain-of-thought."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.35,
        "max_tokens": 320,
    }

    headers = {"Content-Type": "application/json"}
    api_key = str(os.getenv("OPENAI_API_KEY") or os.getenv("LOCAL_AI_API_KEY") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        _resolve_chat_completions_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
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
        raise RuntimeError(f"Local AI HTTP {getattr(exc, 'code', 'error')}: {detail[:220]}") from exc
    except Exception as exc:
        raise RuntimeError(f"Local AI request failed: {exc}") from exc

    try:
        parsed = json.loads(body)
    except Exception as exc:
        raise RuntimeError(f"Local AI response is not valid JSON: {exc}") from exc

    if isinstance(parsed, dict):
        choices = parsed.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = _clean_text(str(message.get("content") or ""))
                    if content:
                        return content
        content = _clean_text(str(parsed.get("response") or ""))
        if content:
            return content

    return ""


async def _generate_ceo_reply(text: str) -> str:
    return await asyncio.to_thread(_request_ceo_reply_sync, text)


async def send_message_to_ceo(text: str, sender: str = "Chairman") -> Dict[str, Any]:
    msg_id = f"msg_{uuid.uuid4().hex[:6]}"
    payload = {
        "id": msg_id,
        "sender": sender,
        "text": text,
        "timestamp": _now_iso(),
    }

    await redis_client.lpush(CHAT_HISTORY_KEY, json.dumps(payload))
    await redis_client.ltrim(CHAT_HISTORY_KEY, 0, MAX_HISTORY - 1)
    return payload


async def get_chat_history(limit: int = 20) -> List[Dict[str, Any]]:
    raw_msgs = await redis_client.lrange(CHAT_HISTORY_KEY, 0, limit - 1)
    msgs = [json.loads(m) for m in raw_msgs]
    msgs.reverse()
    return msgs


async def process_chairman_mandate(text: str):
    cleaned = _clean_text(text)
    if not cleaned:
        return {"status": "ignored", "message": "Mandat kosong."}

    await send_message_to_ceo(cleaned, sender="Chairman")

    await append_event("ceo.mandate_received", {"text": cleaned})

    if _looks_like_operational_command(cleaned):
        command = _extract_operational_command(cleaned)
        if not command:
            helper = (
                "Mandat operasional terdeteksi, tapi format belum lengkap. "
                "Contoh: `catat closing br_01 Rp 1500000 customer Andi` "
                "atau `tambah lead br_01 12`."
            )
            await send_message_to_ceo(helper, sender="CEO")
            await append_event(
                "ceo.mandate_action_rejected",
                {"reason": "invalid_format", "text_preview": cleaned[:180]},
            )
            return {"status": "needs_format", "message": helper, "ceo_replied": True}

        try:
            queued = await _enqueue_boardroom_command(command)
            mode = str(command.get("mode") or "").strip().lower()
            if mode == "closing":
                amount = float(command.get("amount") or 0)
                branch_id = str(command.get("branch_id") or "-")
                reply = (
                    f"Mandat eksekusi diterima. Closing untuk {branch_id} sebesar Rp {amount:,.0f} "
                    f"sudah masuk antrean worker (run {queued['run_id']})."
                )
            elif mode == "leads":
                leads = int(command.get("leads") or 0)
                branch_id = str(command.get("branch_id") or "-")
                reply = (
                    f"Mandat eksekusi diterima. Penambahan lead +{leads} untuk {branch_id} "
                    f"sudah masuk antrean worker (run {queued['run_id']})."
                )
            else:
                reply = f"Mandat eksekusi sudah diantrikan (run {queued['run_id']})."

            await send_message_to_ceo(reply, sender="CEO")
            await append_event(
                "ceo.mandate_action_queued",
                {"mode": mode or "unknown", "run_id": queued["run_id"], "job_id": queued["job_id"]},
            )
            return {
                "status": "queued",
                "message": "Mandat berhasil diantrikan ke worker.",
                "ceo_replied": True,
                "run_id": queued["run_id"],
                "job_id": queued["job_id"],
            }
        except Exception as exc:
            await append_event("ceo.mandate_action_failed", {"error": str(exc)[:220]})

    try:
        ceo_reply = await _generate_ceo_reply(cleaned)
    except Exception as exc:
        await append_event("ceo.mandate_reply_failed", {"error": str(exc)[:220]})
        ceo_reply = ""

    if ceo_reply:
        await send_message_to_ceo(ceo_reply, sender="CEO")
        await append_event("ceo.mandate_replied", {"length": len(ceo_reply)})
        return {"status": "received", "message": "CEO merespons mandat.", "ceo_replied": True}

    return {"status": "received", "message": "Mandat diterima. CEO sedang menganalisis.", "ceo_replied": False}


async def notify_chairman(text: str, role: str = "CEO"):
    suggestion = ""
    if "NO AMMO" in text.upper() or "account" in text.lower():
        suggestion = "\n\nSaran CEO: Segera input akun baru di menu 'The Armory' atau pindahkan akun dari unit bisnis yang sedang idle."

    final_text = f"{text}{suggestion}"
    await send_message_to_ceo(final_text, sender=role)

    from app.jobs.handlers.agent_workflow import _kirim_notifikasi_eksternal

    await _kirim_notifikasi_eksternal(
        title="Proactive CEO Update",
        impact="Actionable Insight",
        approval_id=f"auto_{uuid.uuid4().hex[:4]}",
        role=role,
    )
