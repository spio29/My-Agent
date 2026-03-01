from typing import Dict, Any
from .base import Tool
from app.core.branches import get_branch, update_branch_metrics
from app.core.queue import append_event

class RevenueTool(Tool):
    @property
    def name(self) -> str:
        return "revenue"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    async def run(self, input_data: Dict[str, Any], ctx) -> Dict[str, Any]:
        try:
            amount = float(input_data.get("amount") or 0)
        except Exception:
            amount = 0
        customer = str(input_data.get("customer") or "anonymous").strip() or "anonymous"
        branch_id = str(
            input_data.get("branch_id")
            or input_data.get("target_branch_id")
            or getattr(ctx, "branch_id", "")
            or ""
        ).strip()
        try:
            closings = int(input_data.get("closings") or 1)
        except Exception:
            closings = 1
        closings = max(1, closings)

        try:
            leads = int(input_data.get("leads") or 0)
        except Exception:
            leads = 0
        leads = max(0, leads)
        
        if amount <= 0:
            return {"success": False, "error": "Invalid amount"}
        if not branch_id:
            return {"success": False, "error": "branch_id is required"}

        branch = await get_branch(branch_id)
        if not branch:
            return {"success": False, "error": f"Branch '{branch_id}' not found"}

        try:
            # 1. Update Branch Metrics (Real-time dashboard update)
            delta = {
                "revenue": amount,
                "closings": closings
            }
            if leads > 0:
                delta["leads"] = leads
            await update_branch_metrics(branch_id, delta)
            
            # 2. Record Audit Event
            await append_event("revenue.closing_recorded", {
                "amount": amount,
                "closings": closings,
                "leads": leads,
                "customer": customer,
                "branch_id": branch_id,
                "run_id": getattr(ctx, "run_id", "manual")
            })
            
            # 3. Notify Chairman (Proactive CEO)
            from app.core.boardroom import notify_chairman
            await notify_chairman(
                f"CLOSING SUKSES! Cabang {branch_id} mencatat Rp {amount:,.0f} dari customer {customer}.",
                role="CEO",
            )

            return {
                "success": True,
                "amount": amount,
                "closings": closings,
                "leads": leads,
                "branch_id": branch_id,
                "message": f"Revenue of {amount} successfully recorded for branch {branch_id}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
