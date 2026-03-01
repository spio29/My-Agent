import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.redis_client import redis_client

PROSPECT_PREFIX = "sales:prospect:item:"
PROSPECT_ALL_SET = "sales:prospect:all"
PROSPECT_BRANCH_PREFIX = "sales:prospect:branch:"

OPEN_STAGES = {"new", "contacted", "qualified", "proposal_sent", "negotiation"}
CLOSED_STAGES = {"won", "lost"}
ALL_STAGES = OPEN_STAGES | CLOSED_STAGES

CHANNEL_ALIASES = {
    "wa": "whatsapp",
    "whatsapp": "whatsapp",
    "ig": "instagram",
    "fb": "facebook",
    "tele": "telegram",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prospect_key(prospect_id: str) -> str:
    return f"{PROSPECT_PREFIX}{prospect_id}"


def _branch_set_key(branch_id: str) -> str:
    return f"{PROSPECT_BRANCH_PREFIX}{branch_id}"


def _normalize_stage(stage: Any) -> str:
    value = str(stage or "").strip().lower()
    if value in ALL_STAGES:
        return value
    return "new"


def normalize_prospect_channel(channel: Any) -> str:
    raw = str(channel or "").strip().lower()
    if not raw:
        return ""
    return CHANNEL_ALIASES.get(raw, raw)


def _normalize_tags(tags: Any) -> List[str]:
    if not isinstance(tags, list):
        return []
    out: List[str] = []
    seen = set()
    for row in tags:
        value = str(row or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _parse_iso(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _sort_key(row: Dict[str, Any]) -> str:
    return str(row.get("updated_at") or row.get("created_at") or "")


async def create_prospect(payload: Dict[str, Any]) -> Dict[str, Any]:
    branch_id = str(payload.get("branch_id") or "").strip().lower()
    name = str(payload.get("name") or "").strip()
    channel = normalize_prospect_channel(payload.get("channel"))
    contact_id = str(payload.get("contact_id") or "").strip()
    owner = str(payload.get("owner") or "").strip()

    if not branch_id:
        raise ValueError("branch_id is required")
    if not name:
        raise ValueError("name is required")
    if not channel:
        raise ValueError("channel is required")
    if not contact_id:
        raise ValueError("contact_id is required")

    now = _now_iso()
    prospect_id = f"pr_{uuid.uuid4().hex[:10]}"

    value_estimate_raw = payload.get("value_estimate", 0)
    try:
        value_estimate = float(value_estimate_raw)
    except Exception:
        value_estimate = 0.0

    next_followup_at = str(payload.get("next_followup_at") or "").strip()
    if not next_followup_at:
        next_followup_at = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()

    row = {
        "prospect_id": prospect_id,
        "branch_id": branch_id,
        "name": name,
        "channel": channel,
        "contact_id": contact_id,
        "source": str(payload.get("source") or "").strip(),
        "offer": str(payload.get("offer") or "").strip(),
        "owner": owner,
        "value_estimate": max(0.0, value_estimate),
        "stage": _normalize_stage(payload.get("stage")),
        "notes": str(payload.get("notes") or "").strip(),
        "tags": _normalize_tags(payload.get("tags", [])),
        "followup_count": 0,
        "last_contact_at": None,
        "next_followup_at": next_followup_at,
        "closed_at": None,
        "close_reason": "",
        "created_at": now,
        "updated_at": now,
    }

    await redis_client.set(_prospect_key(prospect_id), json.dumps(row))
    await redis_client.sadd(PROSPECT_ALL_SET, prospect_id)
    await redis_client.sadd(_branch_set_key(branch_id), prospect_id)
    return row


async def get_prospect(prospect_id: str) -> Optional[Dict[str, Any]]:
    raw = await redis_client.get(_prospect_key(prospect_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


async def list_prospects(
    *,
    branch_id: str = "",
    stage: str = "",
    limit: int = 200,
    due_only: bool = False,
) -> List[Dict[str, Any]]:
    ids: List[str]
    branch_clean = str(branch_id or "").strip().lower()
    if branch_clean:
        ids = list(await redis_client.smembers(_branch_set_key(branch_clean)))
    else:
        ids = list(await redis_client.smembers(PROSPECT_ALL_SET))

    stage_clean = _normalize_stage(stage) if stage else ""
    now_dt = datetime.now(timezone.utc)
    rows: List[Dict[str, Any]] = []
    for prospect_id in ids:
        row = await get_prospect(str(prospect_id))
        if not row:
            continue
        if stage_clean and str(row.get("stage") or "").strip().lower() != stage_clean:
            continue
        if due_only:
            row_stage = str(row.get("stage") or "").strip().lower()
            if row_stage in CLOSED_STAGES:
                continue
            due_at = _parse_iso(row.get("next_followup_at"))
            if not due_at or due_at > now_dt:
                continue
        rows.append(row)

    rows.sort(key=_sort_key, reverse=True)
    return rows[: max(1, min(int(limit), 1000))]


async def update_prospect(prospect_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    row = await get_prospect(prospect_id)
    if not row:
        return None

    if "name" in payload:
        row["name"] = str(payload.get("name") or row.get("name") or "").strip() or row.get("name") or ""
    if "source" in payload:
        row["source"] = str(payload.get("source") or "").strip()
    if "offer" in payload:
        row["offer"] = str(payload.get("offer") or "").strip()
    if "owner" in payload:
        row["owner"] = str(payload.get("owner") or "").strip()
    if "notes" in payload:
        row["notes"] = str(payload.get("notes") or "").strip()
    if "tags" in payload:
        row["tags"] = _normalize_tags(payload.get("tags", []))
    if "stage" in payload:
        row["stage"] = _normalize_stage(payload.get("stage"))
    if "next_followup_at" in payload:
        row["next_followup_at"] = str(payload.get("next_followup_at") or "").strip()
    if "contact_id" in payload:
        row["contact_id"] = str(payload.get("contact_id") or row.get("contact_id") or "").strip()
    if "channel" in payload:
        row["channel"] = normalize_prospect_channel(payload.get("channel") or row.get("channel") or "")
    if "value_estimate" in payload:
        raw = payload.get("value_estimate")
        try:
            row["value_estimate"] = max(0.0, float(raw))
        except Exception:
            pass

    row["updated_at"] = _now_iso()
    await redis_client.set(_prospect_key(prospect_id), json.dumps(row))
    return row


async def find_open_prospect_by_contact(
    *,
    branch_id: str,
    channel: str,
    contact_id: str,
) -> Optional[Dict[str, Any]]:
    clean_branch = str(branch_id or "").strip().lower()
    clean_channel = normalize_prospect_channel(channel)
    clean_contact = str(contact_id or "").strip()
    if not clean_branch or not clean_channel or not clean_contact:
        return None

    ids = list(await redis_client.smembers(_branch_set_key(clean_branch)))
    newest_row: Optional[Dict[str, Any]] = None
    newest_ts: Optional[datetime] = None

    for prospect_id in ids:
        row = await get_prospect(str(prospect_id))
        if not row:
            continue

        if str(row.get("channel") or "").strip().lower() != clean_channel:
            continue
        if str(row.get("contact_id") or "").strip() != clean_contact:
            continue

        stage = str(row.get("stage") or "").strip().lower()
        if stage in CLOSED_STAGES:
            continue

        row_dt = _parse_iso(row.get("updated_at")) or _parse_iso(row.get("created_at"))
        if newest_row is None:
            newest_row = row
            newest_ts = row_dt
            continue
        if row_dt and (newest_ts is None or row_dt > newest_ts):
            newest_row = row
            newest_ts = row_dt

    return newest_row


async def mark_followup_sent(
    *,
    prospect_id: str,
    next_followup_minutes: int = 1440,
    note: str = "",
) -> Optional[Dict[str, Any]]:
    row = await get_prospect(prospect_id)
    if not row:
        return None

    now_dt = datetime.now(timezone.utc)
    row["last_contact_at"] = now_dt.isoformat()
    row["followup_count"] = int(row.get("followup_count") or 0) + 1
    row["next_followup_at"] = (now_dt + timedelta(minutes=max(10, int(next_followup_minutes)))).isoformat()

    stage = str(row.get("stage") or "").strip().lower()
    if stage == "new":
        row["stage"] = "contacted"
    if note:
        old_notes = str(row.get("notes") or "").strip()
        row["notes"] = (old_notes + "\n" + note).strip() if old_notes else note

    row["updated_at"] = _now_iso()
    await redis_client.set(_prospect_key(prospect_id), json.dumps(row))
    return row


async def mark_prospect_won(
    *,
    prospect_id: str,
    amount: float,
    note: str = "",
) -> Optional[Dict[str, Any]]:
    row = await get_prospect(prospect_id)
    if not row:
        return None

    now = _now_iso()
    row["stage"] = "won"
    row["closed_at"] = now
    row["close_reason"] = "won"
    if note:
        old_notes = str(row.get("notes") or "").strip()
        row["notes"] = (old_notes + "\n" + note).strip() if old_notes else note
    row["value_estimate"] = max(0.0, float(amount))
    row["updated_at"] = now
    await redis_client.set(_prospect_key(prospect_id), json.dumps(row))
    return row


async def mark_prospect_lost(
    *,
    prospect_id: str,
    reason: str = "",
) -> Optional[Dict[str, Any]]:
    row = await get_prospect(prospect_id)
    if not row:
        return None

    now = _now_iso()
    row["stage"] = "lost"
    row["closed_at"] = now
    row["close_reason"] = str(reason or "lost").strip()
    row["updated_at"] = now
    await redis_client.set(_prospect_key(prospect_id), json.dumps(row))
    return row
