from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.prospects import get_prospect, list_prospects, mark_followup_sent
from app.core.queue import append_event

DEFAULT_TEMPLATE = (
    "Halo {name}, saya follow up untuk {offer}. "
    "Kalau berkenan, saya bantu lanjutkan sampai deal hari ini."
)


def _render_template(template: str, prospect: Dict[str, Any]) -> str:
    text = str(template or "").strip() or DEFAULT_TEMPLATE
    mapping = {
        "name": str(prospect.get("name") or "Kak"),
        "offer": str(prospect.get("offer") or "penawaran kami"),
        "source": str(prospect.get("source") or "-"),
        "branch_id": str(prospect.get("branch_id") or "-"),
    }
    try:
        return text.format(**mapping).strip()
    except Exception:
        return text


async def _process_one(
    *,
    ctx,
    prospect: Dict[str, Any],
    template: str,
    account_id: str,
    next_followup_minutes: int,
) -> Dict[str, Any]:
    messaging_tool = ctx.tools.get("messaging")
    if not messaging_tool:
        return {
            "success": False,
            "prospect_id": prospect.get("prospect_id"),
            "error": "messaging tool is not available",
        }

    channel = str(prospect.get("channel") or "").strip().lower()
    to_id = str(prospect.get("contact_id") or "").strip()
    if not channel or not to_id:
        return {
            "success": False,
            "prospect_id": prospect.get("prospect_id"),
            "error": "prospect missing channel/contact_id",
        }

    message_text = _render_template(template, prospect)
    result = await messaging_tool.run(
        {
            "channel": channel,
            "to_id": to_id,
            "text": message_text,
            "account_id": account_id or None,
        },
        ctx,
    )
    if not isinstance(result, dict) or not result.get("success"):
        return {
            "success": False,
            "prospect_id": prospect.get("prospect_id"),
            "channel": channel,
            "to_id": to_id,
            "error": str((result or {}).get("error") or "follow-up send failed"),
        }

    prospect_id = str(prospect.get("prospect_id") or "").strip()
    note = f"[followup] sent via {channel} at {datetime.now(timezone.utc).isoformat()}"
    updated = await mark_followup_sent(
        prospect_id=prospect_id,
        next_followup_minutes=next_followup_minutes,
        note=note,
    )
    await append_event(
        "sales.followup_sent",
        {
            "prospect_id": prospect_id,
            "branch_id": prospect.get("branch_id"),
            "channel": channel,
            "to_id": to_id,
            "next_followup_minutes": next_followup_minutes,
        },
    )
    return {
        "success": True,
        "prospect_id": prospect_id,
        "channel": channel,
        "to_id": to_id,
        "message": "follow-up sent",
        "updated_stage": (updated or {}).get("stage"),
    }


async def run(ctx, inputs: Dict[str, Any]) -> Dict[str, Any]:
    branch_id = str(inputs.get("branch_id") or "").strip().lower()
    prospect_id = str(inputs.get("prospect_id") or "").strip()
    account_id = str(inputs.get("account_id") or "").strip()
    template = str(inputs.get("template") or "").strip() or DEFAULT_TEMPLATE

    try:
        max_items = int(inputs.get("max_items", 10))
    except Exception:
        max_items = 10
    max_items = max(1, min(max_items, 100))

    try:
        next_followup_minutes = int(inputs.get("next_followup_minutes", 1440))
    except Exception:
        next_followup_minutes = 1440
    next_followup_minutes = max(10, min(next_followup_minutes, 60 * 24 * 14))

    targets: List[Dict[str, Any]] = []
    if prospect_id:
        row = await get_prospect(prospect_id)
        if not row:
            return {"success": False, "error": f"prospect {prospect_id} not found"}
        targets = [row]
    else:
        targets = await list_prospects(branch_id=branch_id, due_only=True, limit=max_items)
        if not targets:
            return {
                "success": True,
                "processed": 0,
                "sent": 0,
                "failed": 0,
                "items": [],
                "message": "no due follow-up prospects",
            }

    results: List[Dict[str, Any]] = []
    sent = 0
    failed = 0
    for row in targets[:max_items]:
        outcome = await _process_one(
            ctx=ctx,
            prospect=row,
            template=template,
            account_id=account_id,
            next_followup_minutes=next_followup_minutes,
        )
        results.append(outcome)
        if outcome.get("success"):
            sent += 1
        else:
            failed += 1

    return {
        "success": failed == 0,
        "processed": len(results),
        "sent": sent,
        "failed": failed,
        "items": results,
    }

