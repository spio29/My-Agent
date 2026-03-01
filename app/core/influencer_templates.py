import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from redis.exceptions import RedisError

from app.core.redis_client import redis_client

TEMPLATE_PREFIX = "influencer:template:item:"
TEMPLATE_SET = "influencer:template:all"

_fallback_templates: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(template_id: str) -> str:
    return f"{TEMPLATE_PREFIX}{template_id}"


def default_templates() -> List[Dict[str, Any]]:
    return [
        {
            "template_id": "endorse_brand_v1",
            "name": "Template Endorse Brand",
            "mode": "endorse",
            "description": "Fokus cari deal endorse brand, negosiasi, dan follow-up B2B.",
            "enabled": True,
            "default_branch_id": "br_01",
            "branch_blueprint_id": "bp_agency_digital",
            "channels_required": ["instagram", "facebook", "threads", "x", "telegram", "wa"],
            "job_templates": [
                {
                    "job_id_pattern": "inf-{influencer_id}-endorse-strategy",
                    "type": "agent.workflow",
                    "enabled": True,
                    "schedule": {"interval_sec": 3600},
                    "timeout_ms": 90000,
                    "retry_policy": {"max_retry": 2, "backoff_sec": [3, 8, 20]},
                    "inputs": {
                        "prompt": (
                            "Anda adalah manager partnership untuk influencer {influencer_name} niche {niche}. "
                            "Cari peluang endorse brand, susun pitch, dan siapkan langkah negosiasi."
                        ),
                        "branch_id": "{branch_id}",
                        "flow_group": "inf:{influencer_id}:endorse",
                        "agent_key": "endorse:{influencer_id}",
                        "default_channel": "telegram",
                        "default_account_id": "bot_a01",
                    },
                },
                {
                    "job_id_pattern": "inf-{influencer_id}-endorse-followup",
                    "type": "sales.followup",
                    "enabled": True,
                    "schedule": {"interval_sec": 7200},
                    "timeout_ms": 45000,
                    "retry_policy": {"max_retry": 2, "backoff_sec": [5, 15, 30]},
                    "inputs": {
                        "branch_id": "{branch_id}",
                        "account_id": "bot_a01",
                        "max_items": 8,
                        "next_followup_minutes": 720,
                        "template": (
                            "Halo {name}, terima kasih sudah mempertimbangkan kolaborasi dengan {influencer_name}. "
                            "Kami siap kirim rate card dan opsi deliverables yang paling cocok."
                        ),
                    },
                },
            ],
            "metadata": {"version": 1, "category": "brand"},
        },
        {
            "template_id": "product_sales_v1",
            "name": "Template Product Sales",
            "mode": "product",
            "description": "Fokus jual produk digital/web service dari traffic sosial ke closing.",
            "enabled": True,
            "default_branch_id": "br_01",
            "branch_blueprint_id": "bp_agency_digital",
            "channels_required": ["instagram", "facebook", "threads", "x", "wa", "shopee", "tokopedia"],
            "job_templates": [
                {
                    "job_id_pattern": "inf-{influencer_id}-content-strategy",
                    "type": "agent.workflow",
                    "enabled": True,
                    "schedule": {"interval_sec": 1800},
                    "timeout_ms": 90000,
                    "retry_policy": {"max_retry": 2, "backoff_sec": [3, 8, 20]},
                    "inputs": {
                        "prompt": (
                            "Anda adalah growth operator untuk influencer {influencer_name} niche {niche}. "
                            "Bangun strategi konten soft-selling untuk offer {offer_name} harga Rp {offer_price}."
                        ),
                        "branch_id": "{branch_id}",
                        "flow_group": "inf:{influencer_id}:product",
                        "agent_key": "product:{influencer_id}",
                        "default_channel": "telegram",
                        "default_account_id": "bot_a01",
                    },
                },
                {
                    "job_id_pattern": "inf-{influencer_id}-sales-followup",
                    "type": "sales.followup",
                    "enabled": True,
                    "schedule": {"interval_sec": 1800},
                    "timeout_ms": 45000,
                    "retry_policy": {"max_retry": 2, "backoff_sec": [5, 15, 30]},
                    "inputs": {
                        "branch_id": "{branch_id}",
                        "account_id": "bot_a01",
                        "max_items": 10,
                        "next_followup_minutes": 180,
                        "template": (
                            "Halo {name}, saya follow up terkait {offer_name}. "
                            "Harga saat ini Rp {offer_price}. Jika cocok, kita bisa lanjut closing hari ini."
                        ),
                    },
                },
            ],
            "metadata": {"version": 1, "category": "product"},
        },
    ]


async def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    clean = str(template_id or "").strip().lower()
    if not clean:
        return None
    try:
        payload = await redis_client.get(_key(clean))
        if not payload:
            return None
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed
    except RedisError:
        row = _fallback_templates.get(clean)
        if row:
            return dict(row)
    except Exception:
        return None
    return None


async def list_templates(limit: int = 200) -> List[Dict[str, Any]]:
    max_limit = max(1, min(int(limit), 1000))
    await ensure_default_templates()
    try:
        ids = sorted(await redis_client.smembers(TEMPLATE_SET))
        rows: List[Dict[str, Any]] = []
        for template_id in ids:
            row = await get_template(template_id)
            if row:
                rows.append(row)
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return rows[:max_limit]
    except RedisError:
        rows = [dict(item) for item in _fallback_templates.values()]
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return rows[:max_limit]


async def upsert_template(template_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    clean = str(template_id or "").strip().lower()
    if not clean:
        raise ValueError("template_id is required")

    existing = await get_template(clean) or {}
    now = _now_iso()
    row = {
        "template_id": clean,
        "name": str(payload.get("name") or existing.get("name") or clean).strip(),
        "mode": str(payload.get("mode") or existing.get("mode") or "product").strip().lower(),
        "description": str(payload.get("description") or existing.get("description") or "").strip(),
        "enabled": bool(payload.get("enabled", existing.get("enabled", True))),
        "default_branch_id": str(payload.get("default_branch_id") or existing.get("default_branch_id") or "").strip().lower(),
        "branch_blueprint_id": str(payload.get("branch_blueprint_id") or existing.get("branch_blueprint_id") or "bp_agency_digital").strip(),
        "channels_required": list(payload.get("channels_required", existing.get("channels_required", [])))
        if isinstance(payload.get("channels_required", existing.get("channels_required", [])), list)
        else [],
        "job_templates": list(payload.get("job_templates", existing.get("job_templates", [])))
        if isinstance(payload.get("job_templates", existing.get("job_templates", [])), list)
        else [],
        "metadata": payload.get("metadata", existing.get("metadata", {}))
        if isinstance(payload.get("metadata", existing.get("metadata", {})), dict)
        else {},
        "created_at": str(existing.get("created_at") or now),
        "updated_at": now,
    }

    try:
        await redis_client.set(_key(clean), json.dumps(row))
        await redis_client.sadd(TEMPLATE_SET, clean)
    except RedisError:
        _fallback_templates[clean] = dict(row)
    return row


async def ensure_default_templates() -> None:
    defaults = default_templates()
    for row in defaults:
        template_id = str(row.get("template_id") or "").strip().lower()
        if not template_id:
            continue
        existing = await get_template(template_id)
        if existing:
            continue
        await upsert_template(template_id, row)

