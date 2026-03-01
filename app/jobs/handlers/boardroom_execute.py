from typing import Any, Dict

from app.core.branches import get_branch, update_branch_metrics
from app.core.boardroom import notify_chairman
from app.core.queue import append_event


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


async def run(ctx, inputs: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(inputs.get("mode") or "closing").strip().lower()
    branch_id = str(inputs.get("branch_id") or "").strip()
    run_id = str(getattr(ctx, "run_id", "") or "").strip()

    if not branch_id:
        return {"success": False, "error": "branch_id is required"}

    branch = await get_branch(branch_id)
    if not branch:
        return {"success": False, "error": f"Branch '{branch_id}' not found"}

    if mode == "closing":
        amount = _to_float(inputs.get("amount"), 0.0)
        if amount <= 0:
            return {"success": False, "error": "amount must be > 0 for closing mode"}

        closings = max(1, _to_int(inputs.get("closings"), 1))
        leads = max(0, _to_int(inputs.get("leads"), 0))
        customer = str(inputs.get("customer") or "anonymous").strip() or "anonymous"

        delta: Dict[str, Any] = {"revenue": amount, "closings": closings}
        if leads > 0:
            delta["leads"] = leads

        await update_branch_metrics(branch_id, delta)
        await append_event(
            "boardroom.command_executed",
            {
                "mode": mode,
                "branch_id": branch_id,
                "amount": amount,
                "closings": closings,
                "leads": leads,
                "customer": customer,
                "run_id": run_id,
            },
        )
        await notify_chairman(
            f"Mandat closing dieksekusi: {branch_id} +Rp {amount:,.0f}, closings +{closings}.",
            role="CEO",
        )
        return {
            "success": True,
            "mode": mode,
            "branch_id": branch_id,
            "amount": amount,
            "closings": closings,
            "leads": leads,
            "customer": customer,
        }

    if mode == "leads":
        leads = max(1, _to_int(inputs.get("leads"), 0))
        await update_branch_metrics(branch_id, {"leads": leads})
        await append_event(
            "boardroom.command_executed",
            {
                "mode": mode,
                "branch_id": branch_id,
                "leads": leads,
                "run_id": run_id,
            },
        )
        await notify_chairman(f"Mandat leads dieksekusi: {branch_id} leads +{leads}.", role="CEO")
        return {"success": True, "mode": mode, "branch_id": branch_id, "leads": leads}

    if mode == "metrics":
        metrics = inputs.get("metrics", {})
        if not isinstance(metrics, dict):
            return {"success": False, "error": "metrics must be an object"}

        delta: Dict[str, Any] = {}
        if "revenue" in metrics:
            delta["revenue"] = _to_float(metrics.get("revenue"), 0.0)
        if "leads" in metrics:
            delta["leads"] = _to_int(metrics.get("leads"), 0)
        if "closings" in metrics:
            delta["closings"] = _to_int(metrics.get("closings"), 0)
        delta = {key: value for key, value in delta.items() if value != 0}
        if not delta:
            return {"success": False, "error": "metrics delta is empty"}

        await update_branch_metrics(branch_id, delta)
        await append_event(
            "boardroom.command_executed",
            {
                "mode": mode,
                "branch_id": branch_id,
                "metrics": delta,
                "run_id": run_id,
            },
        )
        await notify_chairman(f"Mandat metric dieksekusi untuk {branch_id}: {delta}.", role="CEO")
        return {"success": True, "mode": mode, "branch_id": branch_id, "metrics": delta}

    return {"success": False, "error": f"unknown mode '{mode}'"}
