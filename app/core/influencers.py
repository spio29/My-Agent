import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from redis.exceptions import RedisError

from app.core.redis_client import redis_client

INFLUENCER_PREFIX = "influencer:item:"
INFLUENCER_SET = "influencer:all"

_fallback_influencers: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(influencer_id: str) -> str:
    return f"{INFLUENCER_PREFIX}{influencer_id}"


def _normalize_channels(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    output: Dict[str, str] = {}
    for key, value in raw.items():
        name = str(key or "").strip().lower()
        val = str(value or "").strip()
        if not name or not val:
            continue
        output[name] = val
    return output


async def list_influencers(limit: int = 200) -> List[Dict[str, Any]]:
    max_limit = max(1, min(int(limit), 1000))
    try:
        ids = sorted(await redis_client.smembers(INFLUENCER_SET))
        rows: List[Dict[str, Any]] = []
        for influencer_id in ids:
            row = await get_influencer(influencer_id)
            if row:
                rows.append(row)
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return rows[:max_limit]
    except RedisError:
        rows = [dict(item) for item in _fallback_influencers.values()]
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return rows[:max_limit]


async def get_influencer(influencer_id: str) -> Optional[Dict[str, Any]]:
    clean = str(influencer_id or "").strip().lower()
    if not clean:
        return None
    try:
        payload = await redis_client.get(_key(clean))
        if not payload:
            return None
        data = json.loads(payload)
        if isinstance(data, dict):
            return data
    except RedisError:
        row = _fallback_influencers.get(clean)
        if row:
            return dict(row)
    except Exception:
        return None
    return None


async def upsert_influencer(influencer_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    clean = str(influencer_id or "").strip().lower()
    if not clean:
        raise ValueError("influencer_id is required")

    now = _now_iso()
    existing = await get_influencer(clean) or {}
    channels = _normalize_channels(payload.get("channels", existing.get("channels", {})))

    row = {
        "influencer_id": clean,
        "name": str(payload.get("name") or existing.get("name") or clean).strip(),
        "niche": str(payload.get("niche") or existing.get("niche") or "").strip(),
        "mode": str(payload.get("mode") or existing.get("mode") or "product").strip().lower(),
        "status": str(payload.get("status") or existing.get("status") or "active").strip().lower(),
        "template_id": str(payload.get("template_id") or existing.get("template_id") or "").strip(),
        "branch_id": str(payload.get("branch_id") or existing.get("branch_id") or "").strip().lower(),
        "channels": channels,
        "offer_name": str(payload.get("offer_name") or existing.get("offer_name") or "").strip(),
        "offer_price": float(payload.get("offer_price") or existing.get("offer_price") or 0),
        "metadata": payload.get("metadata", existing.get("metadata", {}))
        if isinstance(payload.get("metadata", existing.get("metadata", {})), dict)
        else {},
        "created_at": str(existing.get("created_at") or now),
        "updated_at": now,
    }

    try:
        await redis_client.set(_key(clean), json.dumps(row))
        await redis_client.sadd(INFLUENCER_SET, clean)
    except RedisError:
        _fallback_influencers[clean] = dict(row)

    return row

