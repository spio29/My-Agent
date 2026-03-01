import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from redis.exceptions import RedisError

from app.core.redis_client import redis_client

TELEGRAM_ACCOUNTS_SET = "connector:telegram:accounts"
TELEGRAM_ACCOUNT_PREFIX = "connector:telegram:account:"
TELEGRAM_STATE_PREFIX = "connector:telegram:state:"

# Fallback store when Redis is unavailable.
_fallback_accounts: Dict[str, Dict[str, Any]] = {}
_fallback_last_update: Dict[str, int] = {}


def _sekarang_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kunci_akun(account_id: str) -> str:
    return f"{TELEGRAM_ACCOUNT_PREFIX}{account_id}"


def _kunci_last_update(account_id: str) -> str:
    return f"{TELEGRAM_STATE_PREFIX}{account_id}:last_update_id"


def _masking_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}...{token[-4:]}"


def _normalisasi_chat_ids(values: Optional[List[Any]]) -> List[str]:
    if not values:
        return []

    seen = set()
    output: List[str] = []
    for value in values:
        chat_id = str(value).strip()
        if not chat_id or chat_id in seen:
            continue
        seen.add(chat_id)
        output.append(chat_id)
    return output


def _payload_tampilan(data: Dict[str, Any], include_secret: bool = False) -> Dict[str, Any]:
    row = dict(data)
    token = row.get("bot_token")
    row["has_bot_token"] = bool(token)
    row["bot_token_masked"] = _masking_token(token)

    if not include_secret:
        row.pop("bot_token", None)

    return row


async def _ambil_akun_raw(account_id: str) -> Optional[Dict[str, Any]]:
    try:
        payload = await redis_client.get(_kunci_akun(account_id))
        if not payload:
            return None
        return json.loads(payload)
    except RedisError:
        value = _fallback_accounts.get(account_id)
        return dict(value) if value else None


async def list_telegram_accounts(include_secret: bool = False) -> List[Dict[str, Any]]:
    try:
        account_ids = sorted(await redis_client.smembers(TELEGRAM_ACCOUNTS_SET))
    except RedisError:
        account_ids = sorted(_fallback_accounts.keys())

    rows: List[Dict[str, Any]] = []
    for account_id in account_ids:
        row = await _ambil_akun_raw(account_id)
        if row:
            rows.append(_payload_tampilan(row, include_secret=include_secret))
    return rows


async def get_telegram_account(account_id: str, include_secret: bool = False) -> Optional[Dict[str, Any]]:
    row = await _ambil_akun_raw(account_id)
    if not row:
        return None
    return _payload_tampilan(row, include_secret=include_secret)


async def upsert_telegram_account(account_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    existing = await _ambil_akun_raw(account_id) or {}

    token_input = str(payload.get("bot_token") or "").strip()
    bot_token = token_input or existing.get("bot_token")
    if not bot_token:
        raise ValueError("bot_token wajib diisi saat pendaftaran akun pertama kali.")

    wait_seconds_raw = payload.get("wait_seconds", existing.get("wait_seconds", 2))
    try:
        wait_seconds = int(wait_seconds_raw)
    except Exception:
        wait_seconds = 2
    wait_seconds = max(0, min(30, wait_seconds))

    timezone_value = str(payload.get("timezone", existing.get("timezone", "Asia/Jakarta")) or "").strip()
    timezone_value = timezone_value or "Asia/Jakarta"

    default_channel = str(payload.get("default_channel", existing.get("default_channel", "telegram")) or "").strip()
    default_channel = default_channel or "telegram"

    default_account_id = str(payload.get("default_account_id", existing.get("default_account_id", "default")) or "").strip()
    default_account_id = default_account_id or "default"
    default_branch_id = str(payload.get("default_branch_id", existing.get("default_branch_id", "br_01")) or "").strip().lower()
    default_branch_id = default_branch_id or "br_01"
    inbound_followup_template = str(
        payload.get("inbound_followup_template", existing.get("inbound_followup_template", "")) or ""
    ).strip()

    now = _sekarang_iso()
    row = {
        "account_id": account_id,
        "enabled": bool(payload.get("enabled", existing.get("enabled", True))),
        "bot_token": bot_token,
        "allowed_chat_ids": _normalisasi_chat_ids(payload.get("allowed_chat_ids", existing.get("allowed_chat_ids", []))),
        "use_ai": bool(payload.get("use_ai", existing.get("use_ai", True))),
        "force_rule_based": bool(payload.get("force_rule_based", existing.get("force_rule_based", False))),
        "run_immediately": bool(payload.get("run_immediately", existing.get("run_immediately", True))),
        "wait_seconds": wait_seconds,
        "timezone": timezone_value,
        "default_channel": default_channel,
        "default_account_id": default_account_id,
        "default_branch_id": default_branch_id,
        "capture_inbound_text": bool(payload.get("capture_inbound_text", existing.get("capture_inbound_text", False))),
        "inbound_auto_followup": bool(payload.get("inbound_auto_followup", existing.get("inbound_auto_followup", True))),
        "inbound_followup_template": inbound_followup_template,
        "created_at": existing.get("created_at", now),
        "updated_at": now,
    }

    try:
        await redis_client.set(_kunci_akun(account_id), json.dumps(row))
        await redis_client.sadd(TELEGRAM_ACCOUNTS_SET, account_id)
    except RedisError:
        _fallback_accounts[account_id] = dict(row)

    return _payload_tampilan(row, include_secret=False)


async def delete_telegram_account(account_id: str) -> bool:
    key = _kunci_akun(account_id)
    removed = False

    try:
        deleted = await redis_client.delete(key)
        await redis_client.srem(TELEGRAM_ACCOUNTS_SET, account_id)
        await redis_client.delete(_kunci_last_update(account_id))
        removed = bool(deleted)
    except RedisError:
        removed = account_id in _fallback_accounts
        _fallback_accounts.pop(account_id, None)
        _fallback_last_update.pop(account_id, None)

    return removed


async def get_telegram_last_update_id(account_id: str) -> int:
    key = _kunci_last_update(account_id)
    try:
        value = await redis_client.get(key)
        if value is None:
            return 0
        return int(value)
    except (ValueError, TypeError):
        return 0
    except RedisError:
        return int(_fallback_last_update.get(account_id, 0))


async def set_telegram_last_update_id(account_id: str, update_id: int) -> None:
    key = _kunci_last_update(account_id)
    update_int = int(update_id)
    try:
        await redis_client.set(key, str(update_int))
    except RedisError:
        _fallback_last_update[account_id] = update_int
